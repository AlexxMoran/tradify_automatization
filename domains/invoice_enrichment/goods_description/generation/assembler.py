from __future__ import annotations

from domains.invoice_enrichment.goods_description.draft import Draft
from domains.invoice_enrichment.goods_description.models import LineEnrichmentContext
from domains.invoice_enrichment.goods_description.normalization.normalizer import (
    Normalizer,
)
from domains.invoice_enrichment.models import GoodsDescriptionEntry


class Assembler:
    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer

    def merge_drafts(
        self,
        contexts: list[LineEnrichmentContext],
        raw_items: list[Draft],
    ) -> list[GoodsDescriptionEntry]:
        return self._normalizer.merge_descriptions(
            [context.source_item for context in contexts],
            {context.line_no: context.hints for context in contexts},
            raw_items,
        )

    def entry_to_draft(self, entry: GoodsDescriptionEntry) -> Draft:
        return Draft(
            line_no=entry.line_no,
            description_en=entry.description_en,
            description_pl=entry.description_pl,
            made_of=entry.made_of,
            made_in=entry.made_in,
            country_of_origin=entry.country_of_origin,
            melt_and_pour=entry.melt_and_pour,
            manufacturer_data=entry.manufacturer_data,
        )
