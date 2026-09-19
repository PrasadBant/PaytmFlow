FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project specification files
COPY pyproject.toml .

# Install dependencies using uv into system environment
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application files, configs, and migrations
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY docker-entrypoint.sh .

# Ensure entrypoint script is executable
RUN chmod +x docker-entrypoint.sh

# Create storage directory for evidence uploads
RUN mkdir -p storage/evidence

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Uses shell form (not exec-form CMD) so ${PORT:-8000} actually expands -
# Render (and most PaaS hosts) inject their own PORT env var at runtime and
# require the container to bind to it; falling back to 8000 keeps `docker
# run` / docker-compose (which don't set PORT) working unchanged.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
