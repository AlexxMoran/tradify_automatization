from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from core.utils import clean_optional_text
from domains.invoice_enrichment.goods_description.diagnostics import (
    Diagnostics,
)
from domains.invoice_enrichment.models import (
    GoodsDescriptionEntry,
    InvoiceLineItem,
    ResolvedRuleHints,
)

ValidationSeverity = Literal["warning", "critical"]


@dataclass(slots=True)
class LineEnrichmentContext:
    source_item: InvoiceLineItem
    hints: ResolvedRuleHints

    @property
    def line_no(self) -> int:
        return self.source_item.line_no


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    line_no: int
    field: str
    severity: ValidationSeverity
    message: str

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "line_no": self.line_no,
            "field": self.field,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(slots=True)
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    def issues_for_line(self, line_no: int) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.line_no == line_no]


@dataclass(slots=True)
class ReviewPatchItem:
    line_no: int
    changes: dict[str, str] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        allowed_fields: set[str],
    ) -> "ReviewPatchItem":
        raw_changes = payload.get("changes")
        raw_reasons = payload.get("reasons")
        changes: dict[str, str] = {}
        reasons: dict[str, str] = {}

        if isinstance(raw_changes, list):
            for change in raw_changes:
                if not isinstance(change, dict):
                    continue
                field_key = str(change.get("field", ""))
                if field_key in allowed_fields:
                    changes[field_key] = clean_optional_text(change.get("value"))
                    reasons[field_key] = clean_optional_text(change.get("reason"))
        elif isinstance(raw_changes, dict):
            for field_name, value in raw_changes.items():
                field_key = str(field_name)
                if field_key in allowed_fields:
                    changes[field_key] = clean_optional_text(value)

        if isinstance(raw_reasons, dict):
            for field_name, value in raw_reasons.items():
                reasons[str(field_name)] = clean_optional_text(value)

        return cls(
            line_no=int(payload["line_no"]),
            changes={key: value for key, value in changes.items() if value},
            reasons={key: value for key, value in reasons.items() if value},
        )


@dataclass(slots=True)
class ReviewPatch:
    items: list[ReviewPatchItem] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(item.changes for item in self.items)


@dataclass(slots=True)
class GenerationResult:
    descriptions: list[GoodsDescriptionEntry]
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
