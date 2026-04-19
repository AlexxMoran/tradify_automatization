from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PhysicalRow:
    top: float
    words: list[dict[str, Any]]


@dataclass(slots=True)
class HeaderContext:
    rows: list[PhysicalRow]
    has_origin: bool


@dataclass(slots=True)
class PageTableContext:
    columns: dict[str, tuple[float, float]]
    has_origin: bool
    currency: str
