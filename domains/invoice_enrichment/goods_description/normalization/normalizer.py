from __future__ import annotations

from typing import Any

from core.utils import collapse_whitespace
from domains.invoice_enrichment.goods_description.normalization.address_rules import (
    AddressRules,
)
from domains.invoice_enrichment.goods_description.normalization.country_rules import (
    CountryRules,
)
from domains.invoice_enrichment.goods_description.normalization.description_cleaner import (
    DescriptionCleaner,
)
from domains.invoice_enrichment.goods_description.normalization.template_builder import (
    TemplateBuilder,
)
from domains.invoice_enrichment.goods_description.draft import Draft
from domains.invoice_enrichment.goods_description.normalization.material_rules import (
    MaterialRules,
)
from domains.invoice_enrichment.goods_description.rules import PLACEHOLDER_VALUES
from domains.invoice_enrichment.models import (
    GoodsDescriptionEntry,
    InvoiceLineItem,
    ResolvedRuleHints,
)


class Normalizer:
    def __init__(self, template_builder: TemplateBuilder | None = None) -> None:
        self._material_rules = MaterialRules()
        self._country_rules = CountryRules()
        self._address_rules = AddressRules()
        self._description_cleaner = DescriptionCleaner(template_builder)

    def merge_descriptions(
        self,
        line_items: list[InvoiceLineItem],
        hints_by_line: dict[int, ResolvedRuleHints],
        raw_items: list[Draft],
        *,
        repaired_by_line: dict[int, Draft] | None = None,
    ) -> list[GoodsDescriptionEntry]:
        raw_by_line = {item.line_no: item for item in raw_items}
        repaired_by_line = repaired_by_line or {}

        descriptions: list[GoodsDescriptionEntry] = []
        for source_item in line_items:
            hints = hints_by_line[source_item.line_no]
            base_entry = raw_by_line.get(source_item.line_no)
            repaired_entry = repaired_by_line.get(source_item.line_no)
            entry = self.merge_openai_entry(
                source_item, hints, base_entry, repaired_entry
            )
            descriptions.append(entry)
        return descriptions

    def merge_openai_entry(
        self,
        item: InvoiceLineItem,
        hints: ResolvedRuleHints,
        base_entry: Draft | None,
        repaired_entry: Draft | None,
    ) -> GoodsDescriptionEntry:
        raw = self._merge_drafts(base_entry, repaired_entry)
        country_of_origin, made_in = self._resolve_country_fields(item, hints, raw)
        made_of = self._resolve_made_of(item, hints, raw)
        manufacturer_data = self._resolve_manufacturer(
            item, hints, raw, country_of_origin
        )
        description_en, description_pl = self._resolve_descriptions(item, hints, raw)
        melt_and_pour = self.derive_melt_and_pour(item, made_of, made_in)
        return GoodsDescriptionEntry(
            line_no=item.line_no,
            item_name=item.item_name,
            hs_code=item.hs_code,
            description_en=description_en,
            description_pl=description_pl,
            made_of=made_of,
            made_in=made_in,
            country_of_origin=country_of_origin,
            melt_and_pour=melt_and_pour,
            manufacturer_data=manufacturer_data,
            currency=item.currency,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_value=item.line_value,
            net_weight_kg=item.total_net_weight_kg,
        )

    def _resolve_country_fields(
        self, item: InvoiceLineItem, hints: ResolvedRuleHints, raw: Draft
    ) -> tuple[str, str]:
        country_fallback = self._country_fallback(item.origin, hints)
        country_of_origin = self._resolve_country_field(
            raw.country_of_origin,
            hint=hints.country_of_origin_hint,
            invoice_origin=item.origin,
        )
        made_in = self._resolve_country_field(
            raw.made_in,
            hint=hints.made_in_hint or country_of_origin,
            invoice_origin=item.origin,
        )
        if "made_in" in hints.strict_fields or not made_in:
            made_in = country_of_origin
        if "country_of_origin" in hints.strict_fields and hints.country_of_origin_hint:
            country_of_origin = hints.country_of_origin_hint
        if "made_in" in hints.strict_fields and hints.made_in_hint:
            made_in = hints.made_in_hint
        if not country_of_origin:
            country_of_origin = country_fallback
        if not made_in:
            made_in = country_of_origin
        return country_of_origin, made_in

    def _resolve_made_of(
        self, item: InvoiceLineItem, hints: ResolvedRuleHints, raw: Draft
    ) -> str:
        made_of = self._resolve_material_field(
            raw.made_of, hint=hints.made_of_hint, item=item
        )
        return made_of or hints.made_of_hint or self.fallback_material(item)

    def _resolve_manufacturer(
        self,
        item: InvoiceLineItem,
        hints: ResolvedRuleHints,
        raw: Draft,
        country_of_origin: str,
    ) -> str:
        manufacturer_data = self._resolve_manufacturer_data(
            raw.manufacturer_data,
            hint=hints.manufacturer_data_hint,
            invoice_origin=item.origin,
            country_of_origin=country_of_origin,
        )
        if "manufacturer_data" in hints.strict_fields and hints.manufacturer_data_hint:
            manufacturer_data = hints.manufacturer_data_hint
        return manufacturer_data or hints.manufacturer_data_hint

    def _resolve_descriptions(
        self, item: InvoiceLineItem, hints: ResolvedRuleHints, raw: Draft
    ) -> tuple[str, str]:
        description_en = self._resolve_description(
            raw.description_en,
            hint=hints.description_en_hint,
            language="en",
            category_key=hints.category_key,
            item=item,
        )
        description_pl = self._resolve_description(
            raw.description_pl,
            hint=hints.description_pl_hint,
            language="pl",
            category_key=hints.category_key,
            item=item,
        )
        return (
            description_en or hints.description_en_hint,
            description_pl or hints.description_pl_hint,
        )

    def build_openai_payload_item(
        self,
        item: InvoiceLineItem,
        hints: ResolvedRuleHints,
    ) -> dict[str, object]:
        return {
            "line_no": item.line_no,
            "item_name": item.item_name,
            "hs_code": item.hs_code,
            "invoice_origin_hint": item.origin or "",
            "currency": item.currency,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_value": item.line_value,
            "unit_net_weight_kg": item.unit_net_weight_kg,
            "total_net_weight_kg": item.total_net_weight_kg,
            "source_text": item.source_text,
            "resolved_hints": hints.to_prompt_dict(),
        }

    def expected_melt_and_pour(
        self, item: InvoiceLineItem, made_of: str, made_in: str
    ) -> str:
        if self.is_fully_metal_material(made_of) or self.looks_fully_metal(
            collapse_whitespace(f"{item.item_name} {item.source_text}").lower()
        ):
            return made_in
        return "N/A"

    def is_placeholder(self, value: str | None) -> bool:
        if value is None:
            return True
        return collapse_whitespace(str(value)).upper() in PLACEHOLDER_VALUES

    def material_contains_banned_words(self, value: str) -> bool:
        return self._material_rules.contains_banned_words(value)

    def is_full_address(self, value: str) -> bool:
        return self._address_rules.is_full_address(value)

    def has_valid_polish_suffix(self, value: str) -> bool:
        return self._description_cleaner.has_valid_polish_suffix(value)

    def address_mentions_china(self, value: str) -> bool:
        return self._address_rules.mentions_china(value)

    def derive_melt_and_pour(
        self, item: InvoiceLineItem, made_of: str, made_in: str
    ) -> str:
        if self.is_fully_metal_material(made_of) or self.looks_fully_metal(
            collapse_whitespace(f"{item.item_name} {item.source_text}").lower()
        ):
            return made_in
        return "N/A"

    def fallback_material(self, item: InvoiceLineItem) -> str:
        return self._material_rules.fallback(item)

    def country_fallback(
        self, invoice_origin: str | None, hints: ResolvedRuleHints | None
    ) -> str:
        return self._country_rules.fallback(invoice_origin, hints)

    def fallback_description(
        self,
        item: InvoiceLineItem,
        *,
        language: str,
        category_key: str,
    ) -> str:
        return self._description_cleaner.fallback(
            item,
            language=language,
            category_key=category_key,
        )

    def _merge_drafts(
        self,
        base_entry: Draft | None,
        repaired_entry: Draft | None,
    ) -> Draft:
        merged = Draft(
            line_no=(repaired_entry or base_entry or Draft(line_no=0)).line_no
        )
        for field_name in (
            "description_en",
            "description_pl",
            "made_of",
            "made_in",
            "country_of_origin",
            "melt_and_pour",
            "manufacturer_data",
        ):
            base_value = getattr(base_entry, field_name, "")
            repaired_value = getattr(repaired_entry, field_name, "")
            setattr(merged, field_name, repaired_value or base_value)
        return merged

    def _resolve_country_field(
        self, value: Any, *, hint: str, invoice_origin: str | None
    ) -> str:
        return self._country_rules.resolve(
            value,
            hint=hint,
            invoice_origin=invoice_origin,
        )

    def _country_fallback(
        self, invoice_origin: str | None, hints: ResolvedRuleHints | None
    ) -> str:
        return self._country_rules.fallback(invoice_origin, hints)

    def _resolve_material_field(
        self, value: Any, *, hint: str, item: InvoiceLineItem
    ) -> str:
        return self._material_rules.resolve(value, hint=hint, item=item)

    def _resolve_manufacturer_data(
        self,
        value: Any,
        *,
        hint: str,
        invoice_origin: str | None,
        country_of_origin: str,
    ) -> str:
        return self._address_rules.resolve(
            value,
            hint=hint,
            invoice_origin=invoice_origin,
            country_of_origin=country_of_origin,
        )

    def _resolve_description(
        self,
        value: Any,
        *,
        hint: str,
        language: str,
        category_key: str,
        item: InvoiceLineItem,
    ) -> str:
        return self._description_cleaner.resolve(
            value,
            hint=hint,
            language=language,
            category_key=category_key,
            item=item,
        )

    def is_fully_metal_material(self, value: str) -> bool:
        return self._material_rules.is_fully_metal_material(value)

    def looks_fully_metal(self, text: str) -> bool:
        return self._material_rules.looks_fully_metal(text)
