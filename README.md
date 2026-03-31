# pdf-worker

PDF rasterisation and text extraction microservice. Accepts a PDF upload, processes each page with PyMuPDF, and returns a JSON manifest containing per-page text, dimensions, image counts, and base64-encoded PNG renders.

Designed to run inside a Docker network with no authentication.

## Endpoints

### `POST /process`

Upload a PDF as multipart form data. Optional query parameter `dpi` (default 200).

```bash
curl -X POST "http://localhost:8000/process?dpi=200" \
  -F "file=@document.pdf"
```

### `GET /health`

Returns `{"status": "ok"}` for Docker health checks.

## Development

```bash
uv sync
uv run uvicorn pdf_worker.main:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker build -t pdf-worker .
docker run -p 8000:8000 pdf-worker
```
