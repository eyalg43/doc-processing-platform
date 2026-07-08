FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (cached layer — only re-runs if pyproject.toml changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Add venv to PATH so uvicorn/celery are found
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Default command: API server
# Override in Kubernetes with ["celery", "-A", "app.workers.celery_app", "worker"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
