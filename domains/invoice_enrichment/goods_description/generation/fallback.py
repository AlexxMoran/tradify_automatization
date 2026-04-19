from __future__ import annotations

from dataclasses import replace

from domains.invoice_enrichment.goods_description.diagnostics import (
    Diagnostics,
)
from domains.invoice_enrichment.goods_description.draft import Draft
from domains.invoice_enrichment.goods_description.models import LineEnrichmentContext
from domains.invoice_enrichment.goods_description.normalization.normalizer import (
    Normalizer,
)
from domains.invoice_enrichment.goods_description.rules import (
    DEFAULT_UNKNOWN_COUNTRY,
    ENGLISH_REQUIRED_SUFFIX,
)
from domains.invoice_enrichment.models import GoodsDescriptionEntry


class Fallback:
    DEFAULT_COUNTRY = DEFAULT_UNKNOWN_COUNTRY

    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer

    def build_entry(
        self,
        context: LineEnrichmentContext,
        draft: Draft | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> GoodsDescriptionEntry:
        if diagnostics is not None:
            diagnostics.add(
                stage="fallback",
                line_no=context.line_no,
                message="Built goods description from local fallback",
                severity="info",
            )
        entry = self._normalizer.merge_openai_entry(
            context.source_item,
            context.hints,
            draft,
            None,
        )
        return self.ensure_complete(context, entry, diagnostics=diagnostics)

    def ensure_complete(
        self,
        context: LineEnrichmentContext,
        entry: GoodsDescriptionEntry,
        *,
        diagnostics: Diagnostics | None = None,
    ) -> GoodsDescriptionEntry:
        item = context.source_item
        hints = context.hints
        country_of_origin = entry.country_of_origin
        if self._normalizer.is_placeholder(country_of_origin):
            self._add_field_diagnostic(
                diagnostics,
                context,
                "country_of_origin",
                "Filled country of origin from local fallback",
            )
            country_of_origin = (
                hints.country_of_origin_hint
                or self._normalizer.country_fallback(item.origin, hints)
                or self.DEFAULT_COUNTRY
            )

        made_in = entry.made_in
        if self._normalizer.is_placeholder(made_in):
            self._add_field_diagnostic(
                diagnostics,
                context,
                "made_in",
                "Filled made-in country from local fallback",
            )
            made_in = hints.made_in_hint or country_of_origin

        made_of = entry.made_of
        if self._normalizer.is_placeholder(
            made_of
        ) or self._normalizer.material_contains_banned_words(made_of):
            self._add_field_diagnostic(
                diagnostics,
                context,
                "made_of",
                "Filled material from local fallback",
            )
            made_of = hints.made_of_hint or self._normalizer.fallback_material(item)

        description_en = entry.description_en
        if not description_en.endswith(ENGLISH_REQUIRED_SUFFIX):
            self._add_field_diagnostic(
                diagnostics,
                context,
                "description_en",
                "Filled English description from local template",
            )
            description_en = self._normalizer.fallback_description(
                item,
                language="en",
                category_key=hints.category_key,
            )

        description_pl = entry.description_pl
        if not self._normalizer.has_valid_polish_suffix(description_pl):
            self._add_field_diagnostic(
                diagnostics,
                context,
                "description_pl",
                "Filled Polish description from local template",
            )
            description_pl = self._normalizer.fallback_description(
                item,
                language="pl",
                category_key=hints.category_key,
            )

        manufacturer_data = entry.manufacturer_data
        if not self._is_usable_manufacturer_data(
            manufacturer_data,
            invoice_origin=item.origin,
            country_of_origin=country_of_origin,
        ):
            self._add_field_diagnostic(
                diagnostics,
                context,
                "manufacturer_data",
                "Replaced manufacturer data with local hint",
            )
            manufacturer_data = hints.manufacturer_data_hint
        if not self._is_usable_manufacturer_data(
            manufacturer_data,
            invoice_origin=item.origin,
            country_of_origin=country_of_origin,
        ):
            self._add_field_diagnostic(
                diagnostics,
                context,
                "manufacturer_data",
                "Used synthetic manufacturer fallback address",
            )
            manufacturer_data = self._synthetic_manufacturer_address(country_of_origin)

        if "country_of_origin" in hints.strict_fields and hints.country_of_origin_hint:
            country_of_origin = hints.country_of_origin_hint
        if "made_in" in hints.strict_fields and hints.made_in_hint:
            made_in = hints.made_in_hint
        if "manufacturer_data" in hints.strict_fields and hints.manufacturer_data_hint:
            manufacturer_data = hints.manufacturer_data_hint

        melt_and_pour = self._normalizer.derive_melt_and_pour(item, made_of, made_in)

        return replace(
            entry,
            description_en=description_en,
            description_pl=description_pl,
            made_of=made_of,
            made_in=made_in,
            country_of_origin=country_of_origin,
            melt_and_pour=melt_and_pour,
            manufacturer_data=manufacturer_data,
        )

    def _is_usable_manufacturer_data(
        self,
        value: str,
        *,
        invoice_origin: str | None,
        country_of_origin: str,
    ) -> bool:
        if not self._normalizer.is_full_address(value):
            return False
        if self._normalizer.address_mentions_china(value) and (
            (invoice_origin or "").strip().upper() == "CN"
            or country_of_origin != "China"
        ):
            return False
        return True

    def _synthetic_manufacturer_address(self, country: str) -> str:
        country = country or self.DEFAULT_COUNTRY
        return (
            "Unidentified Manufacturer, "
            f"Address Unavailable 1, 00000 Unknown City, {country}"
        )

    def _add_field_diagnostic(
        self,
        diagnostics: Diagnostics | None,
        context: LineEnrichmentContext,
        field_name: str,
        message: str,
    ) -> None:
        if diagnostics is None:
            return
        diagnostics.add(
            stage="fallback",
            line_no=context.line_no,
            field=field_name,
            message=message,
        )
