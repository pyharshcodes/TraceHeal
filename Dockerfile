# ==============================================================================
# TraceHeal Production Multi-Stage Dockerfile
# ==============================================================================
FROM python:3.12-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy codebase
COPY backend /app/backend
COPY target_services /app/target_services
COPY frontend /app/frontend
COPY cli /app/cli
COPY pyproject.toml README.md /app/

# Install TraceHeal as editable CLI package
RUN pip install --no-cache-dir -e .

# Create runtime directories
RUN mkdir -p /app/data /app/patches /app/sandboxes

# Create unprivileged service user
RUN useradd -m -u 1000 traceheal && \
    chown -R traceheal:traceheal /app

USER traceheal

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
