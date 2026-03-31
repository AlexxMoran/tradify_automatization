from io import BytesIO
import logging
from pathlib import Path
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from core.auth import verify_api_key
from core.utils import log_request_warning
from models import GenerateInvoiceRequest, ProcessedInvoiceResult
from services import GenerateInvoiceError, GenerateInvoiceService, GenerateInvoiceTestService

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024


@router.get("/")
def root():
    return {"message": "Invoice Builder API is running"}


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Invoice Builder API",
    }


@router.post("/generate", dependencies=[Depends(verify_api_key)])
async def generate_invoice(request: Request, payload: GenerateInvoiceRequest):
    service = GenerateInvoiceService(
        baselinker_client=request.app.state.baselinker_client,
        description_generator=request.app.state.description_generator,
    )

    try:
        result = await service(payload.order_id)
    except GenerateInvoiceError as exc:
        log_request_warning(
            logger,
            "generate_failed",
            request,
            order_id=payload.order_id,
            error=exc,
        )
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    filename = result.invoice_number or f"invoice_{result.order_id}"
    return _build_pdf_response(result, filename)


@router.post("/generate-test", dependencies=[Depends(verify_api_key)])
async def generate_test(
    request: Request,
    pdf: UploadFile = File(...),
    order_id: str = Form(default="manual-test"),
):
    if pdf.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    pdf_bytes = await _read_pdf_with_limit(pdf)
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

    service = GenerateInvoiceTestService(
        description_generator=request.app.state.description_generator,
    )
    try:
        result = await service(
            pdf_bytes,
            order_id=order_id,
            source_filename=pdf.filename,
        )
    except GenerateInvoiceError as exc:
        log_request_warning(
            logger,
            "generate_test_failed",
            request,
            order_id=order_id,
            source_filename=pdf.filename,
            error=exc,
        )
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    filename = _build_test_filename_stem(pdf.filename, order_id)
    return _build_pdf_response(result, filename, suffix="_mutated")


def _build_test_filename_stem(source_filename: str | None, order_id: str) -> str:
    if source_filename:
        stem = Path(source_filename).stem.strip()
        if stem:
            return stem
    return f"invoice_{order_id}"


def _build_pdf_response(
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


async def _read_pdf_with_limit(pdf: UploadFile) -> bytes:
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
