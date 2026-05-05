# NotebookLM 整合完整參考

> 目的:任何新 session / 新 agent 看完這份文件,可以**立即**完成本專案的 NotebookLM 整合,不用重踩我們踩過的坑。

---

## 1. 為什麼用 notebooklm-py

NotebookLM **沒有官方 API**。`notebooklm-py` 是社群非官方 wrapper,做法:
- 模擬瀏覽器拿 Google 登入 cookie
- 用 cookie 直接打 NotebookLM 內部的 RPC 端點

優點:能完整使用 NotebookLM(包含 web UI 沒給的功能)
缺點:
- Cookie 會過期(通常數週)
- Google 改 endpoint 隨時可能壞
- 高用量可能被風控
- 不適合面對外部使用者(只該給內部小團隊用)

repo: <https://github.com/teng-lin/notebooklm-py>

---

## 2. 環境準備

### 2-1. 套件分兩組

```python
# requirements.txt (production / 部署到 server 用)
notebooklm-py>=0.1.0
# ⚠️ 不裝 [browser] extra — server 不需要 playwright

# 本機**初次取 cookie** 才需要這兩個 (一次性):
# pip install "notebooklm-py[browser]"
# playwright install chromium
```

### 2-2. 預設檔案位置

| 檔案 | 路徑 |
|---|---|
| 瀏覽器 profile | `~/.notebooklm/browser_profile/` (chromium 的設定) |
| Cookie storage | `~/.notebooklm/storage_state.json` (Playwright 格式) |
| Linux | `~` = `$HOME` |
| Windows | `~` = `%USERPROFILE%` (例:`C:\Users\KupeR\`) |

cookie 才是 API 真正讀的那個檔案。**browser_profile 只是登入用的容器**。

---

## 3. 認證:取得 storage_state.json

### 3-1. 官方 CLI (`notebooklm login`) 在 Windows 有個 bug

**現象**:
- 你用同一個 profile 登過 → cookie 留在 profile
- 下次跑 `notebooklm login`,playwright 開瀏覽器,Google 看到 session 自動跳轉到 NotebookLM
- CLI 在你按 Enter 之後,試圖 `page.goto("https://accounts.google.com/")` 想把 cookie 從地區網域(.google.com.tw)改回 .google.com
- 但因為已登入,goto 中途被 Google redirect 中斷
- 拋 `Page.goto: Navigation interrupted`,storage_state.json 沒寫成

**官方 source 出問題的位置**:`notebooklm/cli/session.py` 約 line 230:
```python
page.goto(GOOGLE_ACCOUNTS_URL, wait_until="load")  # ← 會炸
```

### 3-2. 解法:用我們寫的 `manual_login.py`

它跳過那個壞掉的 force-redirect,直接存 cookie。

```python
# manual_login.py 的核心邏輯
from playwright.sync_api import sync_playwright
from pathlib import Path

HOME = Path.home() / ".notebooklm"
BROWSER_PROFILE = HOME / "browser_profile"
STORAGE_PATH = HOME / "storage_state.json"

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_PROFILE),
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--password-store=basic",
        ],
        ignore_default_args=["--enable-automation"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://notebooklm.google.com/")

    input("[等使用者完成登入後按 ENTER] ")

    # 直接存,不做 force-redirect
    context.storage_state(path=str(STORAGE_PATH))
    context.close()
```

### 3-3. 操作步驟(整理成一行行可貼)

```powershell
# 1. (Windows) 砍掉舊 profile 確保乾淨
Remove-Item -Recurse -Force "$env:USERPROFILE\.notebooklm\browser_profile" -ErrorAction SilentlyContinue

# 2. 跑 manual_login.py
cd 專案根目錄
.\.venv\Scripts\Activate.ps1
python manual_login.py

# 3. 在跳出的 chromium 完成 Google 登入,看到 NotebookLM 首頁
# 4. 回 PowerShell 按 Enter
# 5. 它會把 cookie 存到 ~/.notebooklm/storage_state.json + 複製到 credentials/
```

### 3-4. 驗證 cookie 有效

```bash
notebooklm auth check          # 本地檔案 + JSON 結構驗證
notebooklm auth check --test   # ⭐ 加 --test 才真的打 API 驗證 cookie 還有效
```

成功的輸出長這樣:
```
Authentication Check
┌─────────────────┬───────────┐
│ Storage exists  │ ✓ pass    │
│ JSON valid      │ ✓ pass    │
│ Cookies present │ ✓ pass    │ 19 cookies
│ SID cookie      │ ✓ pass    │
│ Token fetch     │ ✓ pass    │ ← 這個 pass 才代表 cookie 真的能呼 API
└─────────────────┴───────────┘
Authentication is valid.
```

---

## 4. Python API 使用模式

### 4-1. 基本架構

```python
from notebooklm import NotebookLMClient

# 從 cookie 檔案載入(預設 ~/.notebooklm/storage_state.json)
async with await NotebookLMClient.from_storage("path/to/storage_state.json") as client:
    # ... 對 client 做事
    pass
```

⚠️ **關鍵語法**:`async with await NotebookLMClient.from_storage(...)`
- `from_storage()` 本身是 awaitable(回傳 client)
- `async with` 管理生命週期
- 兩個都要

### 4-2. 完整工作流

```python
# 1. 建 notebook
nb = await client.notebooks.create("我的會議_20260430")
print(nb.id)  # 例:5cb6738d-a8f3-45cf-8f1d-0866b6131082

# 2. 上傳音檔(wait=True 會塊住等處理完成)
source = await client.sources.add_file(nb.id, "/path/to/audio.m4a", wait=True)
# 這步通常 2-10 分鐘,視音檔長度

# 3. 取逐字稿
fulltext = await client.sources.get_fulltext(nb.id, source.id)
# ⚠️ 回傳的是 SourceFulltext dataclass,不是字串!
# 真正的文字在 .content
transcript_str = fulltext.content
# 其他欄位:fulltext.title, fulltext.char_count, fulltext.url

# 4. 用 chat 取結構化摘要
answer = await client.chat.ask(nb.id, "你的 prompt 字串")
print(answer.answer)  # ← 字串,模型回答內容

# 5. 刪除 notebook
await client.notebooks.delete(nb.id)

# 6. 列出所有 notebooks(常用於清理)
nbs = await client.notebooks.list()
for nb in nbs:
    print(nb.id, nb.title, getattr(nb, "created_at", None))
```

### 4-3. 還能做什麼

從 README:
```python
# 加網址當 source
await client.sources.add_url(nb.id, "https://example.com", wait=True)

# 產生其他類型內容
await client.artifacts.generate_audio(nb.id, instructions="...")
await client.artifacts.generate_video(nb.id, ...)
await client.artifacts.generate_quiz(nb.id, ...)
await client.artifacts.generate_mind_map(nb.id)

# 等 artifact 完成
await client.artifacts.wait_for_completion(nb.id, status.task_id)

# 下載
await client.artifacts.download_audio(nb.id, "out.mp3")
```

---

## 5. Prompt 設計:要結構化 JSON

LLM 回覆是自由文字,要塞回 Google Sheet 的固定欄位需要 parse。**最穩的做法是要求模型直接吐 JSON**:

```python
PROMPT = """\
你是業務部會議紀錄專員。請根據會議錄音逐字稿,產生標準化會議紀錄。

## 輸出格式
嚴格只輸出一個 JSON 物件,**前後不要有任何說明文字、不要加程式碼圍欄 ```**。格式:

{
  "main_content": ["議題摘要 1", "議題摘要 2"],
  "followup_items": ["追蹤事項 1", "追蹤事項 2"]
}

## 規則
1. main_content 最多 10 條,每條 1-2 句,聚焦關鍵議題與結論
2. followup_items 只列明確的待辦,含負責人/期限若有
3. 全部繁體中文
4. 嚴格 JSON,不能有多餘逗號、註解
"""
```

### 5-1. 即使這樣 prompt,實務上模型還是常常加圍欄

所以 parse 要容錯:

```python
import json
import re

def parse_json_from_llm(raw: str) -> dict:
    """從可能含雜訊的 LLM 回覆中抓出 JSON。"""
    # 移除 ```json ... ``` 圍欄
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    # 抓第一個 { 到最後一個 } 之間
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"找不到 JSON: {raw[:500]}")
    return json.loads(match.group(0))
```

---

## 6. 錯誤處理

### 6-1. 自動重試(網路錯誤)

```python
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)
import asyncio
import logging

log = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError, OSError)),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
async def call_notebooklm():
    async with await NotebookLMClient.from_storage() as client:
        ...
```

### 6-2. Cookie 過期偵測

過期會看到 `401 Unauthorized` 或 `fetch_tokens` 失敗。處理:
```python
try:
    async with await NotebookLMClient.from_storage(path) as client:
        ...
except Exception as e:
    if "401" in str(e) or "auth" in str(e).lower():
        raise RuntimeError(
            "NotebookLM cookie 過期,請重跑 manual_login.py"
        ) from e
    raise
```

### 6-3. SourceFulltext 不是字串

❌ **常見錯誤**:
```python
transcript = await client.sources.get_fulltext(nb.id, source.id)
len(transcript)        # TypeError: object of type 'SourceFulltext' has no len()
transcript[:500]       # TypeError: 'SourceFulltext' object is not subscriptable
```

✅ **正確**:
```python
fulltext = await client.sources.get_fulltext(nb.id, source.id)
transcript = fulltext.content     # str
char_count = fulltext.char_count  # int
title = fulltext.title            # str
```

---

## 7. 雲端部署(Fly.io)時的 cookie 管理

雲端容器**沒有 chromium**,只能讀預先產好的 storage_state.json。

### 7-1. 把 cookie 塞進 Fly Secrets

```powershell
# 把整份 JSON 當環境變數
fly secrets set NOTEBOOKLM_STORAGE_JSON="$(cat credentials/notebooklm_storage.json)"
```

### 7-2. 容器啟動時還原成檔案 (`start.sh`)

```bash
#!/bin/sh
mkdir -p /app/credentials
if [ -n "$NOTEBOOKLM_STORAGE_JSON" ]; then
    printf '%s' "$NOTEBOOKLM_STORAGE_JSON" > /app/credentials/notebooklm_storage.json
fi
export NOTEBOOKLM_STORAGE="/app/credentials/notebooklm_storage.json"
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
```

⚠️ **注意 `printf '%s'` 而非 `echo`**,避免 echo 加上多餘換行讓 JSON parse 失敗。

### 7-3. Cookie 過期維護流程

```powershell
# 1. 本機重新登入
notebooklm auth check --test                                    # 確認確實過期
Remove-Item -Recurse -Force "$env:USERPROFILE\.notebooklm\browser_profile" -ErrorAction SilentlyContinue
python manual_login.py                                          # 重產 cookie

# 2. 推到 Fly
$json = Get-Content credentials\notebooklm_storage.json -Raw
fly secrets set NOTEBOOKLM_STORAGE_JSON="$json"                 # 自動觸發 deploy
```

---

## 8. 常用維護指令

```bash
# 認證相關
notebooklm auth check              # 本地驗證
notebooklm auth check --test       # 含網路測試
notebooklm auth check --json       # 機器可讀

# Notebook 相關
notebooklm notebook list           # 列所有 notebook
notebooklm notebook delete <id>    # 刪除特定 notebook
notebooklm use <id>                # 設當前 context

# Source 相關
notebooklm source list             # 列當前 notebook 的 source
notebooklm source add <url>        # 加 source

# 其他
notebooklm language list           # 列支援語言
notebooklm metadata --json         # 匯出 notebook metadata
notebooklm status --paths          # 印實際使用的檔案路徑
```

---

## 9. 本專案實際串接範例

封裝在 `notebook_service.py`:

```python
from pathlib import Path
from notebooklm import NotebookLMClient
from tenacity import retry, stop_after_attempt, wait_exponential

class NotebookLMService:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=30), reraise=True)
    async def process_audio(self, audio_path: Path, notebook_name: str) -> dict:
        async with await NotebookLMClient.from_storage(self.storage_path) as client:
            # 1. 建 notebook
            nb = await client.notebooks.create(notebook_name)

            # 2. 上傳音檔(wait=True 等處理完)
            source = await client.sources.add_file(
                nb.id, str(audio_path), wait=True
            )

            # 3. 取逐字稿(.content 才是字串)
            transcript = ""
            try:
                fulltext = await client.sources.get_fulltext(nb.id, source.id)
                transcript = getattr(fulltext, "content", "") or ""
            except Exception:
                pass  # 不致命

            # 4. 問結構化 JSON 摘要
            answer = await client.chat.ask(nb.id, MEETING_MINUTES_PROMPT)
            minutes = self._parse_minutes(answer.answer)

            return {
                "notebook_id": nb.id,
                "transcript": transcript,
                "minutes": minutes,
            }

    @staticmethod
    def _parse_minutes(raw: str) -> dict:
        import json, re
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"無法 parse JSON: {raw[:500]}")
        parsed = json.loads(match.group(0))
        parsed.setdefault("main_content", [])
        parsed.setdefault("followup_items", [])
        return parsed
```

---

## 10. 從零開始的「最小重現」清單

新 agent / 新環境要快速複製這個流程,跑這 8 步:

```powershell
# === 1. 建專案 venv 並裝套件 ===
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install notebooklm-py "notebooklm-py[browser]" playwright tenacity

# === 2. 裝 chromium (給 manual_login.py 用) ===
playwright install chromium

# === 3. 取 cookie (用 manual_login.py,不要用官方 CLI) ===
python manual_login.py
# 在跳出的瀏覽器完成 Google 登入 → 看到 NotebookLM 首頁 → 回終端按 Enter

# === 4. 驗證 ===
notebooklm auth check --test
# 期待五項全 ✓ pass

# === 5. 開 Python REPL 試打一次 ===
python
```
```python
import asyncio
from notebooklm import NotebookLMClient

async def test():
    async with await NotebookLMClient.from_storage() as client:
        nbs = await client.notebooks.list()
        print(f"目前有 {len(nbs)} 個 notebook")
        for nb in nbs[:3]:
            print(f"  {nb.id}: {nb.title}")

asyncio.run(test())
```
看到 notebook 列表 → 整個鏈路通了。

---

## 11. 已知地雷 / FAQ

| 症狀 | 原因 | 解 |
|---|---|---|
| `Page.goto: Navigation interrupted` | 用 `notebooklm login` 但 profile 已有 session | 用 `manual_login.py` |
| `'SourceFulltext' object has no len()` | get_fulltext 回的不是字串 | 用 `.content` |
| `'SourceFulltext' object is not subscriptable` | 同上 | 同上 |
| Cookie 突然全 401 | 過期或 Google 風控 | 重跑 `manual_login.py` |
| Fly 上 cookie 失效 | 容器沒寫 storage_state.json | 確認 `start.sh` 有 `printf '%s'` 寫檔 |
| JSON parse 失敗 | 模型加了圍欄或前後綴 | 用容錯 regex extract |
| 處理時間 10 分鐘以上 | 音檔很長 + Google 那邊忙 | 加 timeout、用 progress callback 通知前端 |
| 「找不到 source」 | `add_file` 沒等處理完就用 | `add_file(..., wait=True)` |
| `from_storage()` 拋 FileNotFoundError | cookie 路徑錯 | `notebooklm status --paths` 看實際路徑 |

---

## 12. 為什麼要這麼麻煩(脈絡)

NotebookLM 沒官方 API。所有讓你能「程式化呼叫 NotebookLM」的方式,本質都是模擬瀏覽器或拿瀏覽器 cookie。所以:
- ✅ **個人/小團隊內部使用**:可以,認知到風險即可
- ❌ **對外公開 SaaS**:不要,Google 一更新就全壞 + 帳號可能被鎖
- ⚠️ **要長期穩定**:考慮改用 Whisper(逐字稿) + Gemini/Claude API(摘要),全部官方 API,沒這些煩惱

---

**最後**:這份文件配合 `manual_login.py`、`notebook_service.py`、`prompts.py` 一起看,基本上把 NotebookLM 整合的所有眉角都收進去了。
