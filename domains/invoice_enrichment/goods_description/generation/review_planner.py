from __future__ import annotations

from domains.invoice_enrichment.goods_description.models import (
    LineEnrichmentContext,
    ValidationReport,
)


class ReviewPlanner:
    def select_contexts(
        self,
        contexts: list[LineEnrichmentContext],
        validation_report: ValidationReport,
    ) -> list[LineEnrichmentContext]:
        selected: list[LineEnrichmentContext] = []
        for context in contexts:
            if validation_report.issues_for_line(context.line_no):
                selected.append(context)
                continue
            if "manufacturer_data" not in context.hints.strict_fields:
                selected.append(context)
                continue
            if not context.hints.manufacturer_data_hint:
                selected.append(context)
        return selected
