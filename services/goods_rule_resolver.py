from __future__ import annotations

from dataclasses import replace

from core.utils import collapse_whitespace
from models import InvoiceLineItem, ResolvedRuleHints
from rules.goods_description_rules import (
    COUNTRY_MAP,
    BrandRule,
    CategoryRule,
    load_brand_rules,
    load_category_rules,
    normalize_lookup_text,
)


class GoodsRuleResolver:
    def __init__(self) -> None:
        self._brand_rules = load_brand_rules()
        self._category_rules = load_category_rules()

    def resolve(self, item: InvoiceLineItem) -> ResolvedRuleHints:
        text = normalize_lookup_text(f"{item.item_name} {item.source_text}")
        brand = self._match_brand(text)
        category = self._match_category(text)

        hints = ResolvedRuleHints()
        if brand is not None:
            hints = replace(
                hints,
                brand_name=brand.brand_name,
                manufacturer_name=brand.manufacturer_name,
                country_of_origin_hint=brand.country_of_origin,
                made_in_hint=brand.country_of_origin,
                manufacturer_data_hint=brand.manufacturer_data,
                strict_fields=brand.strict_fields,
            )

        if category is not None:
            hints = replace(
                hints,
                category_key=category.id,
                description_en_hint=category.description_en_hint,
                description_pl_hint=category.description_pl_hint,
                made_of_hint=category.material_override,
                strict_terms=category.strict_terms,
                prompt_notes=category.prompt_notes,
            )

        hints = self._apply_origin_overrides(item, hints, text)
        return self._compact(hints)

    def _match_brand(self, text: str) -> BrandRule | None:
        matches = [
            rule
            for rule in self._brand_rules
            if any(normalize_lookup_text(keyword) in text for keyword in rule.keywords)
        ]
        if not matches:
            return None
        return max(matches, key=lambda rule: max(len(keyword) for keyword in rule.keywords))

    def _match_category(self, text: str) -> CategoryRule | None:
        matches = [
            rule
            for rule in self._category_rules
            if any(normalize_lookup_text(keyword) in text for keyword in rule.keywords)
        ]
        if not matches:
            return None
        return max(matches, key=lambda rule: max(len(keyword) for keyword in rule.keywords))

    def _apply_origin_overrides(
        self,
        item: InvoiceLineItem,
        hints: ResolvedRuleHints,
        normalized_text: str,
    ) -> ResolvedRuleHints:
        padded_text = f" {normalized_text} "
        origin = (item.origin or "").strip().upper()
        country_hint = hints.country_of_origin_hint
        address_hint = hints.manufacturer_data_hint
        made_in_hint = hints.made_in_hint
        prompt_notes = list(hints.prompt_notes)

        if hints.brand_name == "Universal Music":
            if any(token in padded_text for token in (" uk ", " united kingdom ", " brit", " british ")):
                country_hint = "United Kingdom"
                address_hint = "Universal Music Operations Ltd., 4 Pancras Square, London N1C 4AG, United Kingdom"
                made_in_hint = country_hint
            elif any(token in padded_text for token in (" de ", " germany ", " german ")):
                country_hint = "Germany"
                address_hint = "Universal Music GmbH, Stralauer Allee 1, 10245 Berlin, Germany"
                made_in_hint = country_hint
            else:
                country_hint = "United States"
                address_hint = "Universal Music Group, 2220 Colorado Avenue, Santa Monica, CA 90404, USA"
                made_in_hint = country_hint

        if origin == "AT" and hints.category_key == "video_game":
            prompt_notes.append(
                "Invoice origin AT is usually a distributor like Koch Media or Plaion. Ignore Austria unless the brand itself resolves to Austria."
            )

        if origin == "PL" and "van haasteren" in normalized_text:
            country_hint = "Netherlands"
            made_in_hint = country_hint

        if origin == "CN":
            prompt_notes.append(
                "Invoice origin CN must not become China in the final answer. Use the brand headquarters country instead, or Taiwan if the brand still resolves to China."
            )
            if country_hint == "China":
                country_hint = "Taiwan"
                made_in_hint = country_hint

        if not country_hint and origin:
            country_hint = COUNTRY_MAP.get(origin, origin.title())
            made_in_hint = country_hint

        return replace(
            hints,
            country_of_origin_hint=collapse_whitespace(country_hint),
            made_in_hint=collapse_whitespace(made_in_hint),
            manufacturer_data_hint=collapse_whitespace(address_hint),
            prompt_notes=tuple(dict.fromkeys(note for note in prompt_notes if note)),
        )

    def _compact(self, hints: ResolvedRuleHints) -> ResolvedRuleHints:
        return replace(
            hints,
            category_key=collapse_whitespace(hints.category_key),
            brand_name=collapse_whitespace(hints.brand_name),
            manufacturer_name=collapse_whitespace(hints.manufacturer_name),
            description_en_hint=collapse_whitespace(hints.description_en_hint),
            description_pl_hint=collapse_whitespace(hints.description_pl_hint),
            made_of_hint=collapse_whitespace(hints.made_of_hint),
            made_in_hint=collapse_whitespace(hints.made_in_hint),
            country_of_origin_hint=collapse_whitespace(hints.country_of_origin_hint),
            manufacturer_data_hint=collapse_whitespace(hints.manufacturer_data_hint),
        )
