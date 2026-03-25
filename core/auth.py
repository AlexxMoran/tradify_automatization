import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from core.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    settings = get_settings()

    if not settings.api_key:
        raise HTTPException(status_code=503, detail="API key authentication is not configured on this server")

    if not api_key or not secrets.compare_digest(
        api_key.encode("utf-8"),
        settings.api_key.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
