FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 只裝必要的系統套件(notebooklm-py 純 API 不需要 chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# 建 credentials 目錄讓 start.sh 從 env 寫入
RUN mkdir -p /app/credentials /app/uploads

EXPOSE 8000

# tini 負責信號轉發(優雅關機)
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "./start.sh"]
