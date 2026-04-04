FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    DATABASE_PATH=/app/data/knowledge.db

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY pyproject.toml uv.lock README.md run.py /app/
COPY app /app/app
COPY docs /app/docs
COPY admin_bot_rules.md AGENTS.md .env.example /app/

RUN uv sync --frozen && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uv", "run", "python", "run.py", "--host", "0.0.0.0", "--no-reload"]
