# 上線部署 Step-by-Step

兩個獨立部署:**後端 (Fly.io)** + **前端 (GitHub Pages)**。
照順序做:先後端拿到 URL,前端 config 才填得進去。

---

## A. 後端部署 — Fly.io

### A-1. 安裝 flyctl

PowerShell(管理員權限):

```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

裝完關 PowerShell 重開,確認:
```powershell
fly version
```

### A-2. 註冊 / 登入 Fly.io

```powershell
fly auth signup    # 第一次,需要綁信用卡(免費額度 ~$5/月,夠你用)
# 已有帳號就用:
fly auth login
```

⚠️ **必須綁信用卡才能用**,但只要你的使用量不超過免費額度($5/月),不會收錢。每天早會用一次的話,遠遠用不到。

### A-3. 改 app 名稱(全域唯一)

打開 `fly.toml`,把:
```toml
app = "meeting-minutes"
```
改成你的(只能有小寫字母、數字、連字號,例:`yourname-meeting`):
```toml
app = "kuper-meeting-minutes"
```

### A-4. 建立 app (不部署)

```powershell
cd "E:\KupeR-Drive\KupeR\VS CODE\會議紀錄"
fly launch --no-deploy --copy-config --reuse-app
```

它會問:
- **Choose a region** → 直接 Enter(已預設 nrt 東京)
- **Postgres / Redis / sentry** → 全部 N(都不需要)
- 其他 → 接受預設

### A-5. 上傳 Secrets

```powershell
.\deploy_secrets.ps1
```

如果 PowerShell 卡執行政策,先跑:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### A-6. 部署

```powershell
fly deploy
```

第一次 build 大約 3-5 分鐘(下載 Python image、裝套件)。
看到 `Successfully deployed` 就完成。

### A-7. 取得 URL + 測試

```powershell
fly status
```
看到類似:
```
Hostname = kuper-meeting-minutes.fly.dev
```

開瀏覽器測:
```
https://kuper-meeting-minutes.fly.dev/api/health
```
應該回:
```json
{"status":"ok","time":"...","jobs_in_memory":0}
```

✅ 後端上線成功!**記下這個 URL**(下面要用)

---

## B. 前端部署 — GitHub Pages

### B-1. 改 `frontend/config.js`

把 `API_BASE` 換成上一步的 Fly URL:

```js
window.APP_CONFIG = {
  API_BASE: "https://kuper-meeting-minutes.fly.dev",
};
```

### B-2. 建 GitHub Repo

1. 開 https://github.com/new
2. Repo 名稱建議:`meeting-minutes-bot` (或任何你想的名字)
3. **Public**(免費 GH Pages 需要 Public)
   - 若資料敏感想 Private → 需 GitHub Pro($4/月)
4. **不要勾**任何初始化選項(README/.gitignore/license)
5. 「Create repository」

### B-3. 推 code 上去

GitHub repo 頁面複製 `git@github.com:YOU/meeting-minutes-bot.git` 之類的 URL。

```powershell
cd "E:\KupeR-Drive\KupeR\VS CODE\會議紀錄"

# 第一次 init
git init
git branch -M main
git add .
git status                    # ⚠️ 確認 .env / credentials/ 沒被加到!
git commit -m "Initial commit"

# 連到 GitHub
git remote add origin https://github.com/你的GH帳號/meeting-minutes-bot.git
git push -u origin main
```

### B-4. 啟用 GitHub Pages

1. GitHub repo → **Settings**
2. 左側 **Pages**
3. **Source** 選 **GitHub Actions**(不是 Deploy from a branch)
4. 等 1 分鐘自動 deploy
5. **Actions** 分頁可看 build 進度
6. 完成後在 Pages 設定頁面看到:
   ```
   Your site is live at https://你的帳號.github.io/meeting-minutes-bot/
   ```

### B-5. 把前端網址加到後端 CORS

後端要允許前端的 origin,不然瀏覽器會擋 (CORS error)。

```powershell
fly secrets set ALLOWED_ORIGINS="https://你的帳號.github.io"
```

⚠️ 注意:**只到 .github.io 為止**,不含 `/repo-name/` 後綴(origin 只認 host)。

`fly secrets set` 會自動重啟機器,等 30 秒。

---

## C. 端到端測試

1. 打開 `https://你的帳號.github.io/meeting-minutes-bot/`
2. 第一次跳出 token 輸入 → 貼 `.env` 裡的 `API_TOKEN` 值
3. 選記錄人、拖音檔、按開始處理
4. 等 5-10 分鐘
5. 檢查 Google Sheet 多一個分頁 ✓

## D. 分享給部門

把這個 URL 給同事:
```
https://你的帳號.github.io/meeting-minutes-bot/
```

第一次他們要輸入 token,你私下給他們 `API_TOKEN` 字串。
存 localStorage 後不用再輸入。

---

## 🔧 常用維護指令

```powershell
# 即時看後端 log
fly logs

# SSH 進機器除錯
fly ssh console

# 看機器狀態
fly status

# 看所有 secrets (不顯示值,只列名)
fly secrets list

# 改 RECORDERS
fly secrets set RECORDERS="新的,名單,逗號分隔"

# 重新部署 (改了 code 後)
fly deploy

# Cookie 過期(看 log 看到 401):
notebooklm login          # 本機重登
.\deploy_secrets.ps1      # 重新上傳 (會 stage)
fly deploy                # 觸發 stage 生效
```

## 💰 免費額度監控

```powershell
# 每月看用量
fly auth whoami
fly billing
```

Fly.io 免費額度:`$5/月`。早會每天用 5-10 分鐘,大概 $0.5-1/月,完全在範圍內。
擔心的話 → Fly Dashboard → Billing → 設 spending limit 為 $5。

## 🚨 緊急狀況

| 症狀 | 處理 |
|---|---|
| 後端不通 (timeout) | `fly logs` 看錯誤,通常是 cookie 過期 |
| 上傳失敗 401 | token 錯了,前端「重設 token」 |
| CORS error | `ALLOWED_ORIGINS` 沒含 GH Pages URL |
| 寫 Sheet 403 | service account 被踢出 sheet 共用 |
| Bill 異常增加 | 檢查是否有人惡意連續上傳 → 鎖 token、加 firewall |
