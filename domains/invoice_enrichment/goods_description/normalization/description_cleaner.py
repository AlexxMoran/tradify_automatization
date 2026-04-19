from __future__ import annotations

import re

from core.utils import clean_optional_text, collapse_whitespace
from domains.invoice_enrichment.goods_description.normalization.template_builder import (
    TemplateBuilder,
)
from domains.invoice_enrichment.goods_description.rules import (
    ENGLISH_REQUIRED_SUFFIX,
    PLACEHOLDER_VALUES,
    POLISH_REQUIRED_SUFFIXES,
    THULE_FORBIDDEN_DESCRIPTION_TERMS,
)
from domains.invoice_enrichment.models import InvoiceLineItem


class DescriptionCleaner:
    def __init__(self, template_builder: TemplateBuilder | None = None) -> None:
        self._template_builder = template_builder or TemplateBuilder()

    def resolve(
        self,
        value: object,
        *,
        hint: str,
        language: str,
        category_key: str,
        item: InvoiceLineItem,
    ) -> str:
        raw = clean_optional_text(value)
        if self._is_placeholder(raw):
            raw = hint
        if self._looks_instructional_description(raw):
            raw = ""
        if not raw:
            return self.fallback(item, language=language, category_key=category_key)
        raw = self.sanitize(raw, language=language, category_key=category_key)
        if raw:
            if category_key == "thule_bicycle_mount":
                return self.fallback(
                    item,
                    language=language,
                    category_key=category_key,
                )
            return raw
        return self.fallback(item, language=language, category_key=category_key)

    def fallback(
        self,
        item: InvoiceLineItem,
        *,
        language: str,
        category_key: str,
    ) -> str:
        return self._template_builder.build(
            item,
            language=language,
            category_key=category_key,
        )

    def has_valid_polish_suffix(self, value: str) -> bool:
        lowered = value.lower()
        return any(lowered.endswith(suffix) for suffix in POLISH_REQUIRED_SUFFIXES)

    def sanitize(self, value: str, *, language: str, category_key: str) -> str:
        cleaned = collapse_whitespace(value.strip())
        cleaned = re.sub(r"\bprofessional\b", "household", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"\bhome use use\b", "household use", cleaned, flags=re.IGNORECASE
        )
        if category_key == "thule_bicycle_mount":
            for term in THULE_FORBIDDEN_DESCRIPTION_TERMS:
                cleaned = re.sub(
                    re.escape(term),
                    "bicycle wall mounting",
                    cleaned,
                    flags=re.IGNORECASE,
                )

        if language == "en":
            if cleaned.lower().endswith(ENGLISH_REQUIRED_SUFFIX):
                return collapse_whitespace(cleaned)
            cleaned = re.sub(
                rf"(,?\s*)?{re.escape(ENGLISH_REQUIRED_SUFFIX)}$",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip(" ,.;")
            cleaned = (
                f"{cleaned}, {ENGLISH_REQUIRED_SUFFIX}"
                if cleaned
                else f"Product {ENGLISH_REQUIRED_SUFFIX}"
            )
            return collapse_whitespace(cleaned)

        if self.has_valid_polish_suffix(cleaned):
            return collapse_whitespace(cleaned)
        cleaned = re.sub(
            r"(,?\s*)?przeznaczon(?:y|a|e)\s+do\s+uzytku\s+domowego\.?$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" ,.;")
        suffix = self._guess_polish_suffix(cleaned)
        cleaned = f"{cleaned}, {suffix}" if cleaned else f"Produkt, {suffix}"
        return collapse_whitespace(cleaned)

    def _guess_polish_suffix(self, text: str) -> str:
        lowered = text.lower()
        if any(
            token in lowered
            for token in (
                "puzzle",
                "sluchawki",
                "druty",
                "gry",
                "akcesoria",
                "akcesorium",
            )
        ):
            return self._polish_suffix("neutral")
        if any(
            token in lowered for token in ("opona", "detka", "gra", "plyta", "zabawka")
        ):
            return self._polish_suffix("feminine")
        return self._polish_suffix("masculine")

    def _polish_suffix(self, grammatical_kind: str) -> str:
        fallback_by_kind = {
            "masculine": "przeznaczony do uzytku domowego.",
            "feminine": "przeznaczona do uzytku domowego.",
            "neutral": "przeznaczone do uzytku domowego.",
        }
        index_by_kind = {"masculine": 0, "feminine": 1, "neutral": 2}
        index = index_by_kind.get(grammatical_kind, 0)
        if len(POLISH_REQUIRED_SUFFIXES) > index:
            return POLISH_REQUIRED_SUFFIXES[index]
        return fallback_by_kind.get(grammatical_kind, fallback_by_kind["masculine"])

    def _looks_instructional_description(self, value: str) -> bool:
        lowered = collapse_whitespace(value).lower()
        return lowered.startswith(
            (
                "describe as ",
                "describe the ",
                "opisz jako ",
                "opisz ",
            )
        )

    def _is_placeholder(self, value: str | None) -> bool:
        if value is None:
            return True
        return collapse_whitespace(str(value)).upper() in PLACEHOLDER_VALUES
