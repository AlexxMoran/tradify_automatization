from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.utils import clean_optional_text
from domains.invoice_enrichment.goods_description.constraints import REVIEW_PATCH_FIELDS
from domains.invoice_enrichment.goods_description.draft import Draft
from domains.invoice_enrichment.goods_description.models import (
    ReviewPatch,
    ReviewPatchItem,
)

logger = logging.getLogger(__name__)


class ResponseParser:
    def parse_drafts(self, output_text: str) -> list[Draft]:
        items = self.parse_items(output_text)
        drafts: list[Draft] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                drafts.append(Draft.from_payload(item))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping invalid description draft item: %s", exc)
        return drafts

    def parse_review_patch(self, output_text: str) -> ReviewPatch:
        items = self.parse_items(output_text)
        patch_items: list[ReviewPatchItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                patch_items.append(
                    ReviewPatchItem.from_payload(
                        item,
                        allowed_fields=REVIEW_PATCH_FIELDS,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping invalid review patch item: %s", exc)
        return ReviewPatch(patch_items)

    def parse_items(self, output_text: str) -> list[Any]:
        normalized = clean_optional_text(output_text)
        if not normalized:
            logger.warning("OpenAI response is empty")
            return []

        data = self._load_json_payload(normalized)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return items

        logger.warning("OpenAI response does not contain a valid items array")
        return []

    def _load_json_payload(self, output_text: str) -> Any:
        candidates = [output_text]

        fenced_match = re.search(
            r"```(?:json)?\s*(.+?)\s*```",
            output_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if fenced_match:
            candidates.insert(0, fenced_match.group(1).strip())

        for start_char, end_char in (("{", "}"), ("[", "]")):
            start = output_text.find(start_char)
            end = output_text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                candidates.append(output_text[start : end + 1])

        seen: set[str] = set()
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        logger.warning("OpenAI response is not valid JSON")
        return None
