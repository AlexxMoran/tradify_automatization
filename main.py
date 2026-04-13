from contextlib import asynccontextmanager
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from clients import BaseLinkerClient
from core.config import get_settings
from core.helpers import log_unhandled_request_exception
from domains.invoice_enrichment.api import router as invoice_router
from domains.invoice_enrichment.application.invoice_processing_pipeline import (
    InvoiceProcessingPipeline,
)
from domains.invoice_enrichment.goods_description import (
    GoodsDescriptionGateway,
    GoodsDescriptionGenerator,
    GoodsDescriptionNormalizer,
    GoodsDescriptionValidator,
    GoodsRuleResolver,
)
from domains.invoice_enrichment.invoice_parser import InvoicePdfParser
from domains.invoice_enrichment.pdf_documents import (
    GoodsDescriptionPdfBuilder,
    PdfMergeService,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.baselinker_client = BaseLinkerClient()
    normalizer = GoodsDescriptionNormalizer()
    app.state.invoice_processing_pipeline = InvoiceProcessingPipeline(
        parser=InvoicePdfParser(),
        description_generator=GoodsDescriptionGenerator(
            resolver=GoodsRuleResolver(),
            gateway=GoodsDescriptionGateway(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                generation_mode=settings.description_generation_mode,
            ),
            normalizer=normalizer,
            validator=GoodsDescriptionValidator(normalizer),
        ),
        pdf_builder=GoodsDescriptionPdfBuilder(),
        pdf_merger=PdfMergeService(),
    )
    yield
    await app.state.baselinker_client.aclose()


settings = get_settings()
app = FastAPI(lifespan=lifespan)
app.include_router(invoice_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log_unhandled_request_exception(logger, request, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def main() -> None:
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
