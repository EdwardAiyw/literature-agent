FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LITERATURE_AGENT_SERVER=true LITERATURE_AGENT_DATA_DIR=/data \
    LITERATURE_AGENT_BOOTSTRAP=/data/bootstrap.json
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
RUN pip install --no-cache-dir -e ./backend \
    && groupadd -g 10001 literature \
    && useradd -u 10001 -g literature -M -s /usr/sbin/nologin literature
COPY frontend/dist frontend/dist
COPY LICENSE LICENSE
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "literature_agent.api:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--no-access-log"]
