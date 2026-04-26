FROM python:3.11-slim

WORKDIR /app

# Install uv (Python package manager)
RUN pip install --no-cache-dir uv

# Copy dependency manifests first so layer caching works on app-only changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY backend ./backend
COPY frontend ./frontend

# Don't run as root in production
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8082

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8082"]
