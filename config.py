"""集中管理所有設定與 Sheet 對應儲存格位置。

⚠️ 若範本改過格式 (欄位移動、加行數),只需要改這支檔案,不用動 pipeline 邏輯。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


# ─── 驗證與 CORS ───────────────────────────────────────────
API_TOKEN = os.getenv("API_TOKEN", "")

ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]


# ─── 環境設定 ──────────────────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", "./credentials/service_account.json"
)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
TEMPLATE_SHEET_NAME = os.getenv("TEMPLATE_SHEET_NAME", "範本")

NOTEBOOKLM_STORAGE = os.getenv(
    "NOTEBOOKLM_STORAGE", "./credentials/notebooklm_storage.json"
)

UPLOADS_DIR = BASE_DIR / os.getenv("UPLOADS_DIR", "uploads").lstrip("./")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

RECORDERS: list[str] = [
    r.strip() for r in os.getenv("RECORDERS", "").split(",") if r.strip()
]

NOTEBOOK_RETENTION_DAYS = int(os.getenv("NOTEBOOK_RETENTION_DAYS", "14"))

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))


# ─── Sheet 欄位位置 ─────────────────────────────────────────
# 根據你提供的範本截圖整理。若實際儲存格位置不同,改這裡即可。
@dataclass(frozen=True)
class SheetLayout:
    date_cell: str = "G2"                    # 日期
    recorder_cell: str = "G3"                # 記錄人
    status_cell: str = "G4"                  # 追蹤事項狀態 (待追蹤/無)

    main_content_start_row: int = 6          # 主要內容起始列
    main_content_end_row: int = 15           # 主要內容結束列 (10 條)
    main_content_col: str = "B"              # 整列 B:G 合併,寫到 B
    main_content_numbered: bool = True       # 寫入時自動加 "1. ", "2. " 編號

    followup_start_row: int = 17             # 需後續追蹤事項起始列
    followup_col: str = "C"                  # B 是 checkbox,內容寫到 C (合併到 G)
    followup_max_rows: int = 5               # 範本實際只到 row 21 (5 條)


LAYOUT = SheetLayout()


# ─── NotebookLM notebook 命名 ───────────────────────────────
NOTEBOOK_NAME_FORMAT = "業務部會議_{date}"


# ─── Sheet 分頁命名 ─────────────────────────────────────────
SHEET_TAB_NAME_FORMAT = "{date}"
