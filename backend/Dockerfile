# ==========================================================
# Job Market Intelligence Platform - FastAPI backend image
#
# Builds the API image. The container runs from the repository root so that
# ``backend.app.main`` can import its dependencies the same way local
# development does: src/, dashboard/, ml/ and backend/ all visible under
# WORKDIR /app.
#
# The database is NOT part of this image - it runs as the separate ``postgres``
# Compose service, and connection settings (DB_HOST=postgres, DB_* from
# docker-compose.yml environment) arrive as environment variables at runtime.
# ``.env`` is excluded by .dockerignore and must NEVER be copied in.
#
# Build with:   docker compose build api
# Run from the repo root so the build context contains src/, dashboard/ and ml/.
# ==========================================================
FROM python:3.11-slim

# Non-interactive pip, UTF-8 output, no bytecode cache layers in the image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install backend dependencies FIRST (only file needed at this point), so the
# layer is cached and a code-only change never re-downloads wheels.
COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r backend/requirements.txt

# Bring in the whole repository (src/, dashboard/, ml/, backend/).
# .dockerignore keeps .env, tests, notebooks and local state out of the image.
COPY . .

# Run as a non-root user: the API only reads the code and reads the database,
# so no writes into /app are needed.
RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

# The API is served here; interactive docs at /docs and /redoc.
# Runtime liveness is checked by Compose (GET /health), not here.
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]