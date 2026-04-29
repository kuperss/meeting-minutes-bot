#!/bin/sh
set -e

mkdir -p /app/credentials

# 從 env 還原敏感檔案(Fly.io Secrets 走 env 傳)
if [ -n "$NOTEBOOKLM_STORAGE_JSON" ]; then
    printf '%s' "$NOTEBOOKLM_STORAGE_JSON" > /app/credentials/notebooklm_storage.json
    echo "✓ NotebookLM cookie 已還原"
fi

if [ -n "$GOOGLE_SERVICE_ACCOUNT_JSON" ]; then
    printf '%s' "$GOOGLE_SERVICE_ACCOUNT_JSON" > /app/credentials/service_account.json
    echo "✓ Service account 已還原"
fi

# 固定路徑(覆蓋 .env 可能的相對路徑)
export NOTEBOOKLM_STORAGE="/app/credentials/notebooklm_storage.json"
export GOOGLE_SERVICE_ACCOUNT_JSON="/app/credentials/service_account.json"

exec uvicorn app:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --log-level info \
    --access-log \
    --timeout-keep-alive 75
