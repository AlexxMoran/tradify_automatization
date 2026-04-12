from __future__ import annotations


def collapse_whitespace(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def clean_optional_text(value: object, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    cleaned = collapse_whitespace(str(value))
    return cleaned or fallback
