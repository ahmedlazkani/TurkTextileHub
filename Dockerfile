FROM python:3.11-slim

# Force full rebuild — v5.1 — 2026-05-17
LABEL version="5.1" maintainer="TopKap" build_date="2026-05-17"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "bot.main"]
