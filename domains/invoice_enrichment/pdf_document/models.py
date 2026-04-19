from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HeaderMetadata:
    document_type: str
    invoice_ref: str
    issue_date: str | None = None
