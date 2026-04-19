from __future__ import annotations

from domains.invoice_enrichment.goods_description.generation.fallback import (
    Fallback,
)
from domains.invoice_enrichment.goods_description.diagnostics import (
    Diagnostics,
)
from domains.invoice_enrichment.goods_description.models import LineEnrichmentContext
from domains.invoice_enrichment.models import GoodsDescriptionEntry


class Finalizer:
    def __init__(self, fallback: Fallback) -> None:
        self._fallback = fallback

    def finalize(
        self,
        contexts: list[LineEnrichmentContext],
        descriptions: list[GoodsDescriptionEntry],
        *,
        diagnostics: Diagnostics | None = None,
    ) -> list[GoodsDescriptionEntry]:
        descriptions_by_line = {entry.line_no: entry for entry in descriptions}
        finalized: list[GoodsDescriptionEntry] = []

        for context in contexts:
            entry = descriptions_by_line.get(context.line_no)
            if entry is None:
                entry = self._fallback.build_entry(context, diagnostics=diagnostics)
            else:
                entry = self._fallback.ensure_complete(
                    context,
                    entry,
                    diagnostics=diagnostics,
                )
            finalized.append(entry)

        return finalized
