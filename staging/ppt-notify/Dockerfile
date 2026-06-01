FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data directory for SQLite DB
RUN mkdir -p /app/data

ENV TELEGRAM_BOT_TOKEN=""
ENV TELEGRAM_CHAT_ID=""
ENV PPT_TTS_NOTIFY="0"

CMD ["python", "notify_daemon.py"]
