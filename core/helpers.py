from io import BytesIO
import logging
from pathlib import Path
import re

from fastapi import HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from domains.invoice_enrichment.models import ProcessedInvoiceResult

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024


def get_trace_id(request: Request) -> str:
    trace_context = request.headers.get("X-Cloud-Trace-Context", "").strip()
    if not trace_context:
        return ""
    return trace_context.split("/", maxsplit=1)[0]


def build_request_log_context(request: Request, **fields: object) -> str:
    parts = [
        f"method={request.method}",
        f"path={request.url.path}",
    ]

    trace_id = get_trace_id(request)
    if trace_id:
        parts.append(f"trace={trace_id}")

    for key, value in fields.items():
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized:
            continue
        parts.append(f"{key}={normalized}")

    return " ".join(parts)


def log_request_warning(
    logger: logging.Logger,
    message: str,
    request: Request,
    *,
    error: object | None = None,
    **fields: object,
) -> None:
    context = build_request_log_context(request, **fields)
    if error is None:
        logger.warning("%s %s", message, context)
        return
    logger.warning("%s %s error=%s", message, context, str(error))


def log_unhandled_request_exception(
    logger: logging.Logger,
    request: Request,
    exc: Exception,
) -> None:
    logger.exception(
        "unhandled_exception %s error=%s",
        build_request_log_context(request),
        str(exc),
    )


def build_test_filename_stem(source_filename: str | None, order_id: str) -> str:
    if source_filename:
        stem = Path(source_filename).stem.strip()
        if stem:
            return stem
    return f"invoice_{order_id}"


def build_pdf_response(
    result: ProcessedInvoiceResult,
    filename_stem: str,
    *,
    suffix: str = "_merged",
) -> StreamingResponse:
    safe_filename = _sanitize_filename_stem(filename_stem)
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}{suffix}.pdf"',
        "X-Line-Items": str(len(result.line_items)),
    }
    return StreamingResponse(
        BytesIO(result.merged_pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )


async def read_pdf_with_limit(pdf: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total_size = 0

    while True:
        chunk = await pdf.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Uploaded PDF exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)} MB limit",
            )
        chunks.append(chunk)

    return b"".join(chunks)


def _sanitize_filename_stem(filename_stem: str) -> str:
    sanitized = re.sub(r"[\x00-\x1f\x7f]+", "", filename_stem)
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", sanitized)
    sanitized = sanitized.strip("._-")
    return sanitized or "invoice"
