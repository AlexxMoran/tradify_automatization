from __future__ import annotations

from domains.invoice_enrichment.goods_description.draft import Draft
from domains.invoice_enrichment.goods_description.generation.assembler import (
    Assembler,
)
from domains.invoice_enrichment.goods_description.models import (
    LineEnrichmentContext,
    ReviewPatch,
)
from domains.invoice_enrichment.models import GoodsDescriptionEntry


class PatchApplier:
    def __init__(self, assembler: Assembler) -> None:
        self._assembler = assembler

    def apply(
        self,
        contexts: list[LineEnrichmentContext],
        descriptions: list[GoodsDescriptionEntry],
        patch: ReviewPatch,
    ) -> list[GoodsDescriptionEntry]:
        drafts_by_line = {
            entry.line_no: self._assembler.entry_to_draft(entry)
            for entry in descriptions
        }
        for patch_item in patch.items:
            draft = drafts_by_line.get(patch_item.line_no)
            if draft is None:
                draft = Draft(line_no=patch_item.line_no)
                drafts_by_line[patch_item.line_no] = draft
            for field_name, value in patch_item.changes.items():
                if hasattr(draft, field_name):
                    setattr(draft, field_name, value)
        return self._assembler.merge_drafts(contexts, list(drafts_by_line.values()))
