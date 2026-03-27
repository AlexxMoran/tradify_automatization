from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from api import router as api_router
from clients import BaseLinkerClient
from core.config import get_settings
from services.goods_description import GoodsDescriptionGenerator


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.baselinker_client = BaseLinkerClient()
    app.state.description_generator = GoodsDescriptionGenerator()
    yield
    await app.state.baselinker_client.aclose()


settings = get_settings()
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)


def main() -> None:
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
