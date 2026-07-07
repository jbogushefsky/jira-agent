FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
# Dev extras (pytest, debugpy, ...) are installed here too, not just ad hoc in a running
# container — this is a local dev tool with no separate prod image, so there's no downside, and
# it means `docker compose exec backend pytest` works right after any rebuild without a manual
# `pip install -e ".[dev]"` first.
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000
EXPOSE 5678

CMD ["sh", "-c", "alembic upgrade head && python -X frozen_modules=off -m debugpy --listen 0.0.0.0:5678 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
