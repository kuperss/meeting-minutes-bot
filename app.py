"""FastAPI 後端:接收上傳 → 背景處理 → 前端 polling 取進度。"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

import config
from logging_setup import log
from pipeline import process_meeting


# ─── 限制 ──────────────────────────────────────────────────
MAX_UPLOAD_MB = 500                          # 單檔上限 500 MB
ALLOWED_AUDIO_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".webm",
    ".mp4",  # 手機錄影檔
}


# ─── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("伺服器啟動:host=%s port=%s", config.HOST, config.PORT)
    log.info(
        "設定:SPREADSHEET_ID=%s TEMPLATE=%s RECORDERS=%d 人 TOKEN=%s ORIGINS=%s",
        config.SPREADSHEET_ID[:8] + "…" if config.SPREADSHEET_ID else "(未設)",
        config.TEMPLATE_SHEET_NAME,
        len(config.RECORDERS),
        "已設" if config.API_TOKEN else "⚠️ 未設(開放模式)",
        config.ALLOWED_ORIGINS or ["*"],
    )
    yield
    log.info("伺服器關閉")


# ─── App ───────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="業務部會議紀錄自動化", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# ─── 驗證 ──────────────────────────────────────────────────
bearer = HTTPBearer(auto_error=False)


def verify_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not config.API_TOKEN:
        return  # 未設 token (僅限本機測試)
    if not creds or creds.credentials != config.API_TOKEN:
        raise HTTPException(401, "Unauthorized")


# ─── Job 狀態 ─────────────────────────────────────────────
JOBS: dict[str, dict[str, Any]] = {}


def _new_job() -> str:
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {
        "id": jid,
        "status": "pending",
        "messages": [],
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    return jid


def _log(jid: str, msg: str) -> None:
    JOBS[jid]["messages"].append(
        {"ts": datetime.now().strftime("%H:%M:%S"), "msg": msg}
    )
    log.info("[job %s] %s", jid, msg)


# ─── 路由 ──────────────────────────────────────────────────
@app.get("/")
async def root():
    idx = FRONTEND_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return {"status": "ok", "message": "backend is running. frontend on GH Pages."}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.now().isoformat(timespec="seconds"),
        "jobs_in_memory": len(JOBS),
    }


@app.get("/api/recorders")
async def get_recorders(_=Depends(verify_token)):
    return {"recorders": config.RECORDERS}


@app.post("/api/upload")
@limiter.limit("10/minute")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    recorder: str = Form(...),
    meeting_date: str | None = Form(None),
    _=Depends(verify_token),
):
    if not recorder:
        raise HTTPException(400, "請選擇記錄人")

    # 副檔名檢查
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_AUDIO_EXTS:
        raise HTTPException(
            400,
            f"不支援的檔案類型 {ext}。請上傳:{', '.join(sorted(ALLOWED_AUDIO_EXTS))}",
        )

    # 解析日期
    m_date = (
        datetime.strptime(meeting_date, "%Y-%m-%d").date()
        if meeting_date
        else date.today()
    )

    # 存檔 (邊收邊寫,同步檢查大小)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{ts}_{Path(file.filename or 'audio').name}".replace("/", "_").replace("\\", "_")
    save_path = config.UPLOADS_DIR / safe_name

    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    try:
        async with aiofiles.open(save_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    await f.close()
                    save_path.unlink(missing_ok=True)
                    raise HTTPException(413, f"檔案超過 {MAX_UPLOAD_MB} MB 上限")
                await f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        save_path.unlink(missing_ok=True)
        raise HTTPException(500, f"存檔失敗: {e}") from e

    jid = _new_job()
    _log(jid, f"收到檔案 {file.filename} ({total // 1024} KB)")

    asyncio.create_task(_run_pipeline(jid, save_path, recorder, m_date))

    return {"job_id": jid}


async def _run_pipeline(jid: str, audio: Path, recorder: str, m_date: date):
    JOBS[jid]["status"] = "running"
    try:
        result = await process_meeting(
            audio, recorder, m_date, progress=lambda m: _log(jid, m)
        )
        JOBS[jid]["status"] = "done"
        JOBS[jid]["result"] = result
        log.info("[job %s] ✓ 完成,分頁: %s", jid, result["tab_name"])
    except Exception as e:  # noqa: BLE001
        JOBS[jid]["status"] = "error"
        JOBS[jid]["error"] = str(e)
        _log(jid, f"❌ 失敗: {e}")
        log.exception("[job %s] 失敗", jid)


@app.get("/api/jobs/{jid}")
async def get_job(jid: str, _=Depends(verify_token)):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "找不到 job")
    return job


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=config.HOST, port=config.PORT, reload=False)
