# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Keep container logs unbuffered and avoid writing bytecode into the application tree.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install Python dependencies separately to retain Docker layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

# Run the service without root privileges.  The persistent /data path is owned
# by this account and must be backed by a named volume or host mount in production.
RUN addgroup --system --gid 10001 topkap \
    && adduser --system --uid 10001 --ingroup topkap --home /app --shell /usr/sbin/nologin topkap \
    && mkdir -p /data \
    && chown -R topkap:topkap /app /data

COPY --chown=topkap:topkap . ./

USER topkap

EXPOSE 8080
VOLUME ["/data"]

# The health endpoint reports both the HTTP service and the Telegram polling task.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import json, urllib.request; payload=json.load(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)); assert payload.get('status') == 'ok' and payload.get('bot_running') is True" || exit 1

# Exactly one worker is required: Telegram long polling must not run in parallel.
CMD ["sh", "-c", "exec uvicorn bot.main:create_app --factory --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 1"]
