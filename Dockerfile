FROM python:3.11-slim

# Force full rebuild — v6.5 — 2026-06-04 (color-upload flow + dedup fixes)
LABEL version="6.5" maintainer="TopKap" build_date="2026-06-04"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the PORT that Railway will route traffic to
EXPOSE 8080

# FastAPI is the main process — binds to PORT immediately
# Telegram bot runs as async background task inside FastAPI lifespan
CMD ["python", "-m", "bot.main"]
