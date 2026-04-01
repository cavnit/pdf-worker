"""PDF rasterisation and text extraction microservice."""

import base64
import logging
import tempfile
from asyncio import get_event_loop
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import FastAPI, HTTPException, Query, UploadFile

logger = logging.getLogger(__name__)

app = FastAPI(title="pdf-worker", version="0.1.0")
_thread_pool = ThreadPoolExecutor()

# Claude Vision API limits
MAX_DIMENSION = 7500
MAX_RAW_BYTES = 3_700_000


def _with_temp_pdf(pdf_bytes: bytes, fn: Callable[[pymupdf.Document], Any]) -> Any:
    """Write pdf_bytes to a temp file, open it, call fn(doc), then clean up."""
    tmp_path: Path | None = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(pdf_bytes)
        tmp.close()
        tmp_path = Path(tmp.name)

        doc = pymupdf.open(str(tmp_path))
        try:
            return fn(doc)
        finally:
            doc.close()
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


async def _run_in_pool(fn: Callable[..., Any], *args: Any) -> Any:
    """Run a sync function in the shared thread pool."""
    loop = get_event_loop()
    return await loop.run_in_executor(_thread_pool, partial(fn, *args))


@app.get("/health")
async def health() -> dict[str, str]:
    """Docker health check endpoint."""
    return {"status": "ok"}


def _extract_page_metadata(page: pymupdf.Page, page_number: int) -> dict:
    """Extract metadata for a single page (no rasterisation)."""
    raw_text = page.get_text()
    rect = page.rect
    images = page.get_images(full=True)

    return {
        "page_number": page_number,
        "width": int(rect.width),
        "height": int(rect.height),
        "text_length": len(raw_text),
        "image_count": len(images),
        "raw_text": raw_text,
    }


def _metadata_sync(pdf_bytes: bytes) -> dict:
    """CPU-bound metadata extraction — runs in a thread pool."""

    def _extract(doc: pymupdf.Document) -> dict:
        pages: list[dict] = []
        for i in range(len(doc)):
            try:
                pages.append(_extract_page_metadata(doc[i], i + 1))
            except Exception:
                logger.exception("Failed to extract metadata for page %d", i + 1)
                pages.append({
                    "page_number": i + 1,
                    "error": f"Failed to process page {i + 1}",
                })
        return {"page_count": len(doc), "pages": pages}

    return _with_temp_pdf(pdf_bytes, _extract)


def _rasterise_page_sync(pdf_bytes: bytes, page_number: int, dpi: int) -> dict:
    """CPU-bound single-page rasterisation — runs in a thread pool."""

    def _rasterise(doc: pymupdf.Document) -> dict:
        if page_number < 1 or page_number > len(doc):
            raise ValueError(
                f"page {page_number} out of range (document has {len(doc)} pages)"
            )

        page = doc[page_number - 1]
        scale = dpi / 72

        render_scale = scale
        while True:
            render_matrix = pymupdf.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=render_matrix)

            if pix.width > MAX_DIMENSION or pix.height > MAX_DIMENSION:
                long_side = max(pix.width, pix.height)
                render_scale *= MAX_DIMENSION / long_side
                logger.info(
                    "Page %d exceeds %dpx (%dx%d), reducing scale to %.2f",
                    page_number, MAX_DIMENSION, pix.width, pix.height, render_scale,
                )
                continue

            png_bytes = pix.tobytes("png")

            if len(png_bytes) > MAX_RAW_BYTES and render_scale > 1.0:
                render_scale *= 0.75
                logger.info(
                    "Page %d image too large (%d bytes), reducing scale to %.2f",
                    page_number, len(png_bytes), render_scale,
                )
                continue

            break

        image_b64 = base64.b64encode(png_bytes).decode("ascii")

        return {
            "page_number": page_number,
            "image_base64": image_b64,
            "image_size_bytes": len(png_bytes),
        }

    return _with_temp_pdf(pdf_bytes, _rasterise)


@app.post("/process")
async def process_pdf(file: UploadFile) -> dict:
    """Process a PDF file: extract text and metadata for all pages."""
    content = await file.read()
    return await _run_in_pool(_metadata_sync, content)


@app.post("/process/page")
async def process_page(
    file: UploadFile,
    page: int = Query(ge=1),
    dpi: int = Query(default=200, ge=36, le=600),
) -> dict:
    """Rasterise a single page of a PDF file."""
    content = await file.read()
    try:
        return await _run_in_pool(_rasterise_page_sync, content, page, dpi)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
