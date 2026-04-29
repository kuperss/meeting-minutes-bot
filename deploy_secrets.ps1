# 一鍵把本機的 .env / credentials/ 推到 Fly.io Secrets
# 用法: .\deploy_secrets.ps1
#
# 前置:
#   1. flyctl 已安裝且 fly auth login 完成
#   2. fly.toml 的 app 名已改成你的(全域唯一)
#   3. 該 app 已 fly launch --no-deploy 建好
#   4. .env 與 credentials/*.json 都齊全

$ErrorActionPreference = "Stop"

function Read-EnvFile {
    param([string]$Path)
    $hash = @{}
    Get-Content $Path | ForEach-Object {
        if ($_ -match "^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$") {
            $key = $matches[1]
            $val = $matches[2].Trim('"').Trim("'")
            $hash[$key] = $val
        }
    }
    return $hash
}

Write-Host "=== 讀取本機設定 ===" -ForegroundColor Cyan
$env_vars = Read-EnvFile ".env"

$sa_path = "credentials/service_account.json"
$nb_path = "credentials/notebooklm_storage.json"

if (-not (Test-Path $sa_path)) { throw "找不到 $sa_path" }
if (-not (Test-Path $nb_path)) { throw "找不到 $nb_path" }

$sa_json = Get-Content $sa_path -Raw -Encoding UTF8
$nb_json = Get-Content $nb_path -Raw -Encoding UTF8

# 確認 fly.toml 與已登入
Write-Host "=== 檢查 flyctl ===" -ForegroundColor Cyan
fly auth whoami
fly status --json | Out-Null
if ($LASTEXITCODE -ne 0) { throw "fly status 失敗,請先 fly launch --no-deploy" }

Write-Host ""
Write-Host "=== 上傳 Secrets ===" -ForegroundColor Cyan
Write-Host "(這會觸發 app 重啟,但因 auto_stop 設定,沒在處理時不會立刻啟動機器)"
Write-Host ""

# 一次設多個,避免多次 restart
$args_list = @(
    "API_TOKEN=$($env_vars['API_TOKEN'])",
    "SPREADSHEET_ID=$($env_vars['SPREADSHEET_ID'])",
    "TEMPLATE_SHEET_NAME=$($env_vars['TEMPLATE_SHEET_NAME'])",
    "RECORDERS=$($env_vars['RECORDERS'])",
    "ALLOWED_ORIGINS=$($env_vars['ALLOWED_ORIGINS'])",
    "NOTEBOOK_RETENTION_DAYS=$($env_vars['NOTEBOOK_RETENTION_DAYS'])",
    "GOOGLE_SERVICE_ACCOUNT_JSON=$sa_json",
    "NOTEBOOKLM_STORAGE_JSON=$nb_json"
)

fly secrets set --stage @args_list
Write-Host ""
Write-Host "(已 staged,等下一次 fly deploy 才生效)" -ForegroundColor Yellow
Write-Host ""
Write-Host "=== 完成 ===" -ForegroundColor Green
Write-Host "下一步:fly deploy"
