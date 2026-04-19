from __future__ import annotations

from domains.invoice_enrichment.goods_description.generation.assembler import (
    Assembler,
)
from domains.invoice_enrichment.goods_description.generation.context_builder import (
    ContextBuilder,
)
from domains.invoice_enrichment.goods_description.generation.fallback import (
    Fallback,
)
from domains.invoice_enrichment.goods_description.models import (
    LineEnrichmentContext,
    ValidationReport,
)
from domains.invoice_enrichment.models import GoodsDescriptionEntry


class ReviewPayloadBuilder:
    def __init__(
        self,
        *,
        context_builder: ContextBuilder,
        assembler: Assembler,
        fallback: Fallback,
    ) -> None:
        self._context_builder = context_builder
        self._assembler = assembler
        self._fallback = fallback

    def build(
        self,
        contexts: list[LineEnrichmentContext],
        descriptions: list[GoodsDescriptionEntry],
        validation_report: ValidationReport,
    ) -> list[dict[str, object]]:
        descriptions_by_line = {entry.line_no: entry for entry in descriptions}
        payload: list[dict[str, object]] = []

        for context in contexts:
            description = descriptions_by_line.get(context.line_no)
            if description is None:
                description = self._fallback.build_entry(context)
            issues = validation_report.issues_for_line(context.line_no)
            payload.append(
                {
                    **self._context_builder.build_prompt_payload_item(context),
                    "current_draft": self._assembler.entry_to_draft(
                        description
                    ).to_current_draft(),
                    "validation_issues": [issue.to_prompt_dict() for issue in issues],
                }
            )
        return payload
