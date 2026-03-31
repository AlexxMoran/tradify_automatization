from contextlib import asynccontextmanager
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api import router as api_router
from clients import BaseLinkerClient
from core.config import get_settings
from core.utils import log_unhandled_request_exception
from services.goods_description import GoodsDescriptionGenerator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.baselinker_client = BaseLinkerClient()
    app.state.description_generator = GoodsDescriptionGenerator()
    yield
    await app.state.baselinker_client.aclose()


settings = get_settings()
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)


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
