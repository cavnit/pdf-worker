"""PDF rasterisation and text extraction microservice."""

import base64
import logging
import tempfile
from pathlib import Path

import pymupdf
from fastapi import FastAPI, Query, UploadFile

logger = logging.getLogger(__name__)

app = FastAPI(title="pdf-worker", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    """Docker health check endpoint."""
    return {"status": "ok"}


@app.post("/process")
async def process_pdf(
    file: UploadFile,
    dpi: int = Query(default=200, ge=36, le=600),
) -> dict:
    """Process a PDF file: extract text, rasterise pages, gather metadata.

    Args:
        file: Uploaded PDF file.
        dpi: Resolution for page rasterisation (default 200).

    Returns:
        JSON manifest with per-page metadata and base64-encoded PNG images.
    """
    tmp_path: Path | None = None

    try:
        # Write uploaded bytes to a temp file for PyMuPDF
        content = await file.read()
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(content)
        tmp.close()
        tmp_path = Path(tmp.name)

        doc = pymupdf.open(str(tmp_path))
        scale = dpi / 72
        matrix = pymupdf.Matrix(scale, scale)

        pages: list[dict] = []

        for page_number in range(len(doc)):
            try:
                page = doc[page_number]

                # Extract raw text
                raw_text = page.get_text()

                # Rasterise to PNG
                pix = page.get_pixmap(matrix=matrix)
                png_bytes = pix.tobytes("png")
                image_b64 = base64.b64encode(png_bytes).decode("ascii")

                # Page dimensions (in points)
                rect = page.rect
                width = int(rect.width)
                height = int(rect.height)

                # Count embedded images
                images = page.get_images(full=True)
                image_count = len(images)

                pages.append(
                    {
                        "page_number": page_number + 1,
                        "width": width,
                        "height": height,
                        "text_length": len(raw_text),
                        "image_count": image_count,
                        "raw_text": raw_text,
                        "image_base64": image_b64,
                        "image_size_bytes": len(png_bytes),
                    }
                )
            except Exception:
                logger.exception("Failed to process page %d", page_number + 1)
                pages.append(
                    {
                        "page_number": page_number + 1,
                        "error": f"Failed to process page {page_number + 1}",
                    }
                )

        doc.close()

        return {
            "page_count": len(pages),
            "pages": pages,
        }

    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
