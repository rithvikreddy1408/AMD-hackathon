FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for sentence-transformers / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache optimisation)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source into /app/backend so absolute imports like
# `from backend.api...` resolve correctly under PYTHONPATH=/app
COPY backend/ ./backend/

# Copy scenarios (YAML files) to the same relative path they're expected at
COPY scenarios/ ./scenarios/

ENV PYTHONPATH=/app

EXPOSE 8000

# Production: Gunicorn managing Uvicorn workers
CMD ["gunicorn", "backend.api.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
