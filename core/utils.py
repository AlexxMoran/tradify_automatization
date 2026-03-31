from __future__ import annotations

import logging

from fastapi import Request


def collapse_whitespace(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def clean_optional_text(value: object, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    cleaned = collapse_whitespace(str(value))
    return cleaned or fallback


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
