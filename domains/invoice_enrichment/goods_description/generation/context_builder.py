from __future__ import annotations

from domains.invoice_enrichment.goods_description.models import LineEnrichmentContext
from domains.invoice_enrichment.goods_description.normalization.normalizer import (
    Normalizer,
)
from domains.invoice_enrichment.goods_description.rule_resolver import RuleResolver
from domains.invoice_enrichment.models import ParsedDocument


class ContextBuilder:
    def __init__(
        self,
        *,
        resolver: RuleResolver,
        normalizer: Normalizer,
    ) -> None:
        self._resolver = resolver
        self._normalizer = normalizer

    def build(self, parsed_document: ParsedDocument) -> list[LineEnrichmentContext]:
        return [
            LineEnrichmentContext(
                source_item=item,
                hints=self._resolver.resolve(item),
            )
            for item in parsed_document.line_items
        ]

    def build_prompt_payload(
        self,
        contexts: list[LineEnrichmentContext],
    ) -> list[dict[str, object]]:
        return [self.build_prompt_payload_item(context) for context in contexts]

    def build_prompt_payload_item(
        self,
        context: LineEnrichmentContext,
    ) -> dict[str, object]:
        return self._normalizer.build_openai_payload_item(
            context.source_item,
            context.hints,
        )
