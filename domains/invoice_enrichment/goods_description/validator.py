from __future__ import annotations

from core.utils import clean_optional_text
from domains.invoice_enrichment.application.errors import DomainValidationError
from domains.invoice_enrichment.goods_description.normalizer import (
    GoodsDescriptionNormalizer,
)
from domains.invoice_enrichment.models import GoodsDescriptionEntry, InvoiceLineItem


class GoodsDescriptionValidator:
    REQUIRED_FIELDS = (
        "description_en",
        "description_pl",
        "made_of",
        "made_in",
        "country_of_origin",
        "manufacturer_data",
    )

    def __init__(self, normalizer: GoodsDescriptionNormalizer) -> None:
        self._normalizer = normalizer

    def validate_descriptions(
        self,
        line_items: list[InvoiceLineItem],
        descriptions: list[GoodsDescriptionEntry],
    ) -> None:
        if len(line_items) != len(descriptions):
            raise DomainValidationError(
                "Description count does not match invoice line count; PDF generation aborted"
            )

        expected_lines = [item.line_no for item in line_items]
        actual_lines = [item.line_no for item in descriptions]
        if expected_lines != actual_lines:
            raise DomainValidationError(
                "Description line order does not match invoice line order"
            )

        source_by_line = {item.line_no: item for item in line_items}
        for description in descriptions:
            invalid_fields = self.collect_invalid_fields(
                source_by_line[description.line_no], description
            )
            if invalid_fields:
                raise DomainValidationError(
                    f"Invalid generated fields for line {description.line_no}: {', '.join(invalid_fields)}"
                )

    def collect_invalid_fields(
        self,
        source_item: InvoiceLineItem,
        description: GoodsDescriptionEntry,
    ) -> list[str]:
        invalid_fields: list[str] = []
        for field_name in self.REQUIRED_FIELDS:
            if self._normalizer.is_placeholder(getattr(description, field_name)):
                invalid_fields.append(field_name)
        expected_melt_and_pour = self._normalizer.expected_melt_and_pour(
            source_item,
            description.made_of,
            description.made_in,
        )
        if description.melt_and_pour != expected_melt_and_pour:
            invalid_fields.append("melt_and_pour")
        if self._normalizer.material_contains_banned_words(description.made_of):
            invalid_fields.append("made_of")
        if not self._normalizer.is_full_address(description.manufacturer_data):
            invalid_fields.append("manufacturer_data")
        if not description.description_en.endswith("intended for household use."):
            invalid_fields.append("description_en")
        if not self._normalizer.has_valid_polish_suffix(description.description_pl):
            invalid_fields.append("description_pl")
        if self._normalizer.address_mentions_china(description.manufacturer_data) and (
            clean_optional_text(source_item.origin).upper() == "CN"
            or description.country_of_origin != "China"
        ):
            invalid_fields.append("manufacturer_data")
        return sorted(set(invalid_fields))
