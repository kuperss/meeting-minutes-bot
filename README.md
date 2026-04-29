# 業務部會議紀錄自動化

錄音上傳 → NotebookLM 產逐字稿與摘要 → 自動寫回 Google Sheet 指定分頁。

## 架構

```
手機/電腦 (拖拉/錄音上傳)
    ↓
前端 (GitHub Pages,靜態)
    ↓ multipart + Bearer token
後端 (Fly.io,FastAPI Docker)
 ├─ notebook_service  → notebooklm-py (建 nb / 上傳 / 取逐字稿 / 問摘要)
 └─ sheets_service    → gspread (複製範本分頁 / 填欄位)
    ↓
Google Sheet (已有 GAS 自動同步到追蹤表)
```

## 檔案結構

```
會議紀錄/
├── app.py                 # FastAPI:路由、認證、上傳驗證、rate limit
├── config.py              # 所有設定 + Sheet 儲存格對應表
├── pipeline.py            # audio → NotebookLM → Sheet 的主流程
├── notebook_service.py    # notebooklm-py 包裝 + 重試邏輯
├── sheets_service.py      # gspread 包裝
├── prompts.py             # 給 NotebookLM 的 JSON 輸出 prompt
├── cleanup.py             # 14 天 notebook 自動刪除(排程)
├── logging_setup.py       # 統一 logging
├── requirements.txt
│
├── Dockerfile             # Fly.io 部署用
├── start.sh               # 從 env 還原 secrets + 啟動
├── fly.toml               # Fly.io 設定
├── .dockerignore
│
├── frontend/
│   ├── index.html         # 前端(拖拉上傳 + 進度條 + token)
│   └── config.js          # API_BASE 設定 (部署後改)
│
├── .github/workflows/
│   └── pages.yml          # GH Pages 自動部署
│
├── .env.example
└── .gitignore
```

---

## 🚀 完整部署流程

### Step 1: Google Service Account

1. [Google Cloud Console](https://console.cloud.google.com/) 建專案
2. 啟用 **Google Sheets API** 與 **Google Drive API**
3. IAM → 建 Service Account → 建 JSON key → 下載
4. **把試算表分享給 service account 的 email**(編輯者權限)
   - email 在 JSON 裡 `client_email` 欄位

### Step 2: NotebookLM cookie(一次性,本機做)

```bash
pip install "notebooklm-py[browser]"
playwright install chromium
notebooklm login
# 用部門共用 Google 帳號登入
# cookie 存在預設位置,cp 出來備用
```

cookie 過期後(通常幾週),重跑 `notebooklm login` 並重新上傳 secret。

### Step 3: 本機先測通

```bash
# 建 venv
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
pip install "notebooklm-py[browser]"   # 只本機登入需要
playwright install chromium

# 複製範例並填
cp .env.example .env
# 編輯 .env:API_TOKEN, SPREADSHEET_ID, RECORDERS, ALLOWED_ORIGINS

# 把 service account JSON 放到:
#   credentials/service_account.json
# NotebookLM cookie 放到:
#   credentials/notebooklm_storage.json

# CLI 跑一次測試(不用起 web)
python pipeline.py path/to/audio.mp3 小明

# 起 web (本機)
python app.py
# 開 http://localhost:8000
```

### Step 4: 部署後端到 Fly.io

```bash
# 裝 flyctl
# Windows PowerShell:
iwr https://fly.io/install.ps1 -useb | iex
# Mac:  brew install flyctl

# 登入
fly auth login

# 初始化 (會讀 fly.toml,但會問你改 app 名)
fly launch --no-deploy

# 改 fly.toml 的 app 為你的唯一名稱

# 設 Secrets(敏感資料)
fly secrets set API_TOKEN="$(openssl rand -hex 32)"
fly secrets set SPREADSHEET_ID="你的試算表 ID"
fly secrets set RECORDERS="小明,小華,小美,阿強"
fly secrets set ALLOWED_ORIGINS="https://<你的user>.github.io"

# Service account JSON (整份貼進)
fly secrets set GOOGLE_SERVICE_ACCOUNT_JSON="$(cat credentials/service_account.json)"

# NotebookLM cookie (整份貼進)
fly secrets set NOTEBOOKLM_STORAGE_JSON="$(cat credentials/notebooklm_storage.json)"

# 部署
fly deploy

# 取得 URL
fly status
# → https://<app-name>.fly.dev
```

### Step 5: 部署前端到 GitHub Pages

1. 把整個資料夾推到 GitHub repo
2. `frontend/config.js` 改 `API_BASE` 為你的 Fly URL:
   ```js
   window.APP_CONFIG = {
     API_BASE: "https://meeting-minutes.fly.dev",
   };
   ```
3. GitHub repo → **Settings → Pages**:
   - Source: **GitHub Actions**
4. Push 到 `main`(或手動 trigger):
   - `.github/workflows/pages.yml` 自動 build 與 deploy
5. 取得 URL:`https://<user>.github.io/<repo>/`

### Step 6: 驗證

1. 開手機/電腦訪問 GH Pages URL
2. 首次會要 token(就是 Step 4 產的那個)
3. 選記錄人、拖拉音檔、按開始處理
4. 等進度跑完,檢查 Google Sheet 是否多一個分頁

---

## 🔄 日常運作

| 動作 | 怎麼做 |
|---|---|
| 上傳會議錄音 | 打開 GH Pages URL,拖拉或上傳 |
| 檢查結果 | Google Sheet 找對應日期分頁 |
| 清理舊 notebook(14 天前) | 你電腦排程跑 `python cleanup.py` |
| Cookie 過期 | 本機 `notebooklm login` → `fly secrets set NOTEBOOKLM_STORAGE_JSON=...` |
| 新增記錄人 | `fly secrets set RECORDERS="...,新人"` |
| 調整 Sheet 欄位 | 改 `config.py` 的 `SheetLayout` → `fly deploy` |

---

## ⚙️ 優化已內建

- ✅ **Bearer Token 認證** — 所有 API 必須帶 token
- ✅ **CORS 白名單** — 只允許設定的 origin
- ✅ **File Size / Type 檢查** — 500MB 上限,僅允許音訊/視訊
- ✅ **Rate Limiting** — 每 IP 每分鐘 10 次上傳
- ✅ **NotebookLM 自動重試** — 網路錯誤指數退避重試 3 次
- ✅ **上傳進度條** — 即時顯示 MB 數
- ✅ **統一 logging** — stdout 格式化,Fly logs 易讀
- ✅ **Fly auto_stop** — 閒置自動停,省錢
- ✅ **Healthcheck** — Fly 知道 app 是否活著
- ✅ **優雅關機** — tini 處理信號
- ✅ **Token 前端 localStorage** — 不寫死在 code

## ⚠️ 已知限制

- **JOBS 存記憶體** — Fly auto_stop 重啟會丟失進行中的 job(已完成的 Sheet 還是有結果)
- **uploads/ 是 ephemeral** — Fly 重啟時清空(不影響處理結果)
- **cookie 要手動維護** — 過期 → 本機重登 → 重設 secret
- **NotebookLM 非官方 API** — Google 改動可能壞掉,建議一個部門共用 Google 帳號跑

## 🧪 疑難排解

| 症狀 | 檢查 |
|---|---|
| 前端 401 Unauthorized | token 輸入錯,點右下「重設 token」 |
| 前端 CORS 錯誤 | `ALLOWED_ORIGINS` 有沒有加 GH Pages URL |
| 寫 Sheet 403 | Service account email 沒加到 Sheet 分享清單 |
| 「找不到範本分頁」 | `TEMPLATE_SHEET_NAME` 與實際分頁名不符 |
| 「無法從 NotebookLM 抓出 JSON」 | 看 Fly log 看原文,調整 `prompts.py` |
| NotebookLM 突然全部 401/403 | cookie 過期,重跑 `notebooklm login` |
| Fly deploy 失敗 | `fly logs` 看錯誤,通常是 Dockerfile 或 secrets |

```bash
# 常用 Fly 指令
fly logs              # 即時 log
fly ssh console       # SSH 進 container
fly status            # app 狀態
fly secrets list      # 列所有 secrets (不顯示值)
fly machine list      # 看機器狀態
fly deploy            # 重新部署
```
