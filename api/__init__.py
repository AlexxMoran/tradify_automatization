import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from core.auth import verify_api_key
from core.helpers import build_pdf_response, build_test_filename_stem, log_request_warning, read_pdf_with_limit
from models import GenerateInvoiceRequest
from services import GenerateInvoiceError, GenerateInvoiceService, GenerateInvoiceTestService

router = APIRouter()
logger = logging.getLogger(__name__)


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
    return build_pdf_response(result, filename)


@router.post("/generate-test", dependencies=[Depends(verify_api_key)])
async def generate_test(
    request: Request,
    pdf: UploadFile = File(...),
    order_id: str = Form(default="manual-test"),
):
    if pdf.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    pdf_bytes = await read_pdf_with_limit(pdf)
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

    filename = build_test_filename_stem(pdf.filename, order_id)
    return build_pdf_response(result, filename, suffix="_mutated")
