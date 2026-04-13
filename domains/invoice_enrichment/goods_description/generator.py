from __future__ import annotations

from domains.invoice_enrichment.goods_description.dto import GoodsDescriptionDraft
from domains.invoice_enrichment.goods_description.gateway import GoodsDescriptionGateway
from domains.invoice_enrichment.goods_description.normalizer import (
    GoodsDescriptionNormalizer,
)
from domains.invoice_enrichment.goods_description.prompts import (
    build_goods_description_prompt,
    build_goods_description_repair_prompt,
)
from domains.invoice_enrichment.goods_description.resolver import GoodsRuleResolver
from domains.invoice_enrichment.goods_description.validator import (
    GoodsDescriptionValidator,
)
from domains.invoice_enrichment.models import GoodsDescriptionEntry, ParsedDocument


class GoodsDescriptionGenerator:
    def __init__(
        self,
        *,
        resolver: GoodsRuleResolver,
        gateway: GoodsDescriptionGateway,
        normalizer: GoodsDescriptionNormalizer,
        validator: GoodsDescriptionValidator,
    ) -> None:
        self._resolver = resolver
        self._gateway = gateway
        self._normalizer = normalizer
        self._validator = validator

    async def generate(
        self,
        parsed_document: ParsedDocument,
    ) -> list[GoodsDescriptionEntry]:
        if not parsed_document.line_items:
            return []

        hints_by_line = {
            item.line_no: self._resolver.resolve(item)
            for item in parsed_document.line_items
        }
        payload = [
            self._normalizer.build_openai_payload_item(
                item, hints_by_line[item.line_no]
            )
            for item in parsed_document.line_items
        ]

        raw_items = await self._gateway.request_items(
            build_goods_description_prompt(
                payload,
                document_type=parsed_document.document_type,
                document_ref=parsed_document.document_ref,
            ),
            use_web_search=True,
        )
        descriptions = self._normalizer.merge_descriptions(
            parsed_document.line_items, hints_by_line, raw_items
        )

        invalid_items = self._collect_invalid_items(
            parsed_document, descriptions, hints_by_line
        )
        if invalid_items:
            repaired_raw_items = await self._gateway.request_items(
                build_goods_description_repair_prompt(
                    invalid_items,
                    document_type=parsed_document.document_type,
                    document_ref=parsed_document.document_ref,
                ),
                use_web_search=True,
            )
            repaired_by_line = {item.line_no: item for item in repaired_raw_items}
            descriptions = self._normalizer.merge_descriptions(
                parsed_document.line_items,
                hints_by_line,
                raw_items,
                repaired_by_line=repaired_by_line,
            )

        self._validator.validate_descriptions(parsed_document.line_items, descriptions)
        return descriptions

    def _collect_invalid_items(
        self,
        parsed_document: ParsedDocument,
        descriptions: list[GoodsDescriptionEntry],
        hints_by_line,
    ) -> list[dict[str, object]]:
        invalid_items: list[dict[str, object]] = []
        description_by_line = {entry.line_no: entry for entry in descriptions}

        for item in parsed_document.line_items:
            description = description_by_line[item.line_no]
            invalid_fields = self._validator.collect_invalid_fields(item, description)
            if not invalid_fields:
                continue

            invalid_items.append(
                {
                    **self._normalizer.build_openai_payload_item(
                        item, hints_by_line[item.line_no]
                    ),
                    "invalid_fields": invalid_fields,
                    "current_draft": GoodsDescriptionDraft(
                        line_no=description.line_no,
                        description_en=description.description_en,
                        description_pl=description.description_pl,
                        made_of=description.made_of,
                        made_in=description.made_in,
                        country_of_origin=description.country_of_origin,
                        melt_and_pour=description.melt_and_pour,
                        manufacturer_data=description.manufacturer_data,
                    ).to_current_draft(),
                }
            )
        return invalid_items
