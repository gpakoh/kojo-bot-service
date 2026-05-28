# /quart-ollama_bot/databases/kojo/docker/Dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY requirements-prod.txt requirements.txt
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

COPY utils ./utils
COPY tg_bot ./tg_bot
COPY services ./services
COPY config ./config
COPY alembic ./alembic
COPY alembic.ini .
COPY pyproject.toml .

# Change ownership to appuser
RUN chown -R appuser:appuser /app

# tests не нужны в прод-образе
# COPY tests ./tests

ENV PYTHONPATH=/app
ENV TZ="Europe/Moscow"

USER appuser

CMD ["python", "-m", "tg_bot.main"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:${BOT_INTERNAL_PORT:-8080}/ready || exit 1