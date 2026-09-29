# ==========================================================
# Job Market Intelligence Platform - Streamlit dashboard image
#
# The dashboard runs from the repository root (WORKDIR /app) so its imports
# resolve exactly as they do locally: dashboard/, src/, ml/ and backend/.
# It installs the project-wide requirements.txt - the same file local
# dashboard development uses - so dependency management is not duplicated.
#
# The dashboard reads PostgreSQL directly through src.data.queries, so it
# needs the DB_* environment variables (DB_HOST=postgres) from
# docker-compose.yml at runtime, just like the API.
# ``.env`` is excluded by .dockerignore and must NEVER be copied in.
# ==========================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the dashboard's dependencies first (the shared requirements.txt),
# so the layer is cached and a code-only change never re-downloads wheels.
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# Bring in the whole repository (dashboard/, src/, ml/, backend/).
COPY . .

# Run as a non-root user; Streamlit keeps its runtime state in /tmp and the
# user home, which are writable, and never needs to write into /app.
RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

# The dashboard's default port.
EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", "dashboard/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]