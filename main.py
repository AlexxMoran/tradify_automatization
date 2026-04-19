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
from domains.invoice_enrichment.goods_description.ai.gateway import Gateway
from domains.invoice_enrichment.goods_description.generation.generator import (
    Generator,
)
from domains.invoice_enrichment.goods_description.normalization.normalizer import (
    Normalizer,
)
from domains.invoice_enrichment.goods_description.rule_resolver import RuleResolver
from domains.invoice_enrichment.goods_description.generation.validator import (
    Validator,
)
from domains.invoice_enrichment.invoice_pdf_parser.parser import Parser
from domains.invoice_enrichment.pdf_document.builder import (
    Builder,
)
from domains.invoice_enrichment.pdf_document.merge_service import (
    MergeService,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.baselinker_client = BaseLinkerClient()
    normalizer = Normalizer()
    app.state.invoice_processing_pipeline = InvoiceProcessingPipeline(
        parser=Parser(),
        description_generator=Generator(
            resolver=RuleResolver(),
            gateway=Gateway(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                reasoning_effort=settings.openai_reasoning_effort,
                generation_mode=settings.description_generation_mode,
            ),
            normalizer=normalizer,
            validator=Validator(normalizer),
        ),
        pdf_builder=Builder(),
        pdf_merger=MergeService(),
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
