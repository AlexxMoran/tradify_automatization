from __future__ import annotations

from core.utils import clean_optional_text
from domains.invoice_enrichment.goods_description.models import (
    ValidationIssue,
    ValidationReport,
)
from domains.invoice_enrichment.goods_description.normalization.normalizer import (
    Normalizer,
)
from domains.invoice_enrichment.goods_description.rules import ENGLISH_REQUIRED_SUFFIX
from domains.invoice_enrichment.models import GoodsDescriptionEntry, InvoiceLineItem


class Validator:
    REQUIRED_FIELDS = (
        "description_en",
        "description_pl",
        "made_of",
        "made_in",
        "country_of_origin",
        "manufacturer_data",
    )

    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer

    def build_report(
        self,
        line_items: list[InvoiceLineItem],
        descriptions: list[GoodsDescriptionEntry],
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        if len(line_items) != len(descriptions):
            return ValidationReport(
                [
                    ValidationIssue(
                        line_no=0,
                        field="items",
                        severity="critical",
                        message="Description count does not match invoice line count",
                    )
                ]
            )

        expected_lines = [item.line_no for item in line_items]
        actual_lines = [item.line_no for item in descriptions]
        if expected_lines != actual_lines:
            return ValidationReport(
                [
                    ValidationIssue(
                        line_no=0,
                        field="items",
                        severity="critical",
                        message="Description line order does not match invoice line order",
                    )
                ]
            )

        source_by_line = {item.line_no: item for item in line_items}
        for description in descriptions:
            invalid_fields = self.collect_invalid_fields(
                source_by_line[description.line_no], description
            )
            issues.extend(
                self._issue_for_field(description.line_no, field_name)
                for field_name in invalid_fields
            )
        return ValidationReport(issues)

    def _issue_for_field(self, line_no: int, field_name: str) -> ValidationIssue:
        messages = {
            "description_en": "English description is missing the required household-use ending",
            "description_pl": "Polish description is missing a valid household-use ending",
            "made_of": "Material is empty or outside the allowed material list",
            "made_in": "Made-in country is missing",
            "country_of_origin": "Country of origin is missing",
            "manufacturer_data": "Manufacturer data is missing, incomplete, or not a postal address",
            "melt_and_pour": "Melt and pour value does not match material and made-in country",
        }
        return ValidationIssue(
            line_no=line_no,
            field=field_name,
            severity="critical",
            message=(
                f"Line {line_no}: "
                f"{messages.get(field_name, f'{field_name} is invalid')}"
            ),
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
        if not description.description_en.endswith(ENGLISH_REQUIRED_SUFFIX):
            invalid_fields.append("description_en")
        if not self._normalizer.has_valid_polish_suffix(description.description_pl):
            invalid_fields.append("description_pl")
        if self._normalizer.address_mentions_china(description.manufacturer_data) and (
            clean_optional_text(source_item.origin).upper() == "CN"
            or description.country_of_origin != "China"
        ):
            invalid_fields.append("manufacturer_data")
        return sorted(set(invalid_fields))
