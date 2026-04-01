# pdf-worker

PDF rasterisation and text extraction microservice. Accepts a PDF upload, extracts per-page metadata and text with PyMuPDF, and rasterises individual pages on demand as base64-encoded PNGs.

Designed to run inside a Docker network with no authentication.

## Endpoints

### `POST /process`

Upload a PDF as multipart form data. Returns metadata only (no images).

```bash
curl -X POST "http://localhost:8000/process" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "page_count": 10,
  "pages": [
    {
      "page_number": 1,
      "width": 612,
      "height": 792,
      "text_length": 1234,
      "image_count": 3,
      "raw_text": "..."
    }
  ]
}
```

### `POST /process/page`

Upload a PDF and rasterise a single page. Returns a base64-encoded PNG image.

Query parameters:
- `page` (required) — 1-indexed page number
- `dpi` (optional, default 200) — render resolution

Images are automatically downscaled to stay within Claude Vision API limits (max 7500px, max 3.7MB raw).

```bash
curl -X POST "http://localhost:8000/process/page?page=1&dpi=100" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "page_number": 1,
  "image_base64": "iVBOR...",
  "image_size_bytes": 245000
}
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

Runs 4 uvicorn workers with CPU-bound rasterisation offloaded to a thread pool.
