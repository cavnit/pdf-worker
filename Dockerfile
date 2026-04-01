FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY pdf_worker/ pdf_worker/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "pdf_worker.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
