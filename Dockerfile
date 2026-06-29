FROM python:3.12-slim

# Install build dependencies for matrix-nio[e2e] (libolm) and lxml.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libolm-dev \
    libolm3 \
    libxml2-dev \
    libxslt-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/

# Data directory for SQLite DB and matrix-nio key store.
RUN mkdir -p /data
VOLUME ["/data"]

ENV MENSA_BOT_CONFIG=/data/config.yaml

CMD ["python", "-m", "bot.main"]
