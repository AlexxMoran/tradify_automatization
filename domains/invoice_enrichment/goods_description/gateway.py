from __future__ import annotations

import json
import re
from typing import Any

from core.utils import clean_optional_text
from domains.invoice_enrichment.application.errors import (
    ConfigurationError,
    DomainValidationError,
    ExternalDependencyError,
)
from domains.invoice_enrichment.goods_description.dto import GoodsDescriptionDraft


class GoodsDescriptionGateway:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        generation_mode: str,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._generation_mode = generation_mode.lower().strip() or "hybrid"
        self._client = None

        if self._api_key:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)

    async def request_items(
        self,
        prompt: str,
        *,
        use_web_search: bool,
    ) -> list[GoodsDescriptionDraft]:
        if self._generation_mode != "hybrid":
            raise ConfigurationError(
                "DESCRIPTION_GENERATION_MODE must be set to 'hybrid'"
            )
        if not self._api_key or not self._client:
            raise ConfigurationError(
                "OPENAI_API_KEY is required when DESCRIPTION_GENERATION_MODE=hybrid"
            )

        try:
            request_kwargs = {
                "model": self._model,
                "input": prompt,
            }
            if use_web_search:
                request_kwargs["tools"] = [{"type": "web_search"}]
                request_kwargs["tool_choice"] = "required"
            response = await self._client.responses.create(**request_kwargs)
        except Exception as exc:
            raise ExternalDependencyError(
                f"OpenAI description generation failed: {exc}"
            ) from exc

        items = self._parse_openai_items(response.output_text)
        return [
            GoodsDescriptionDraft.from_payload(item)
            for item in items
            if isinstance(item, dict)
        ]

    def _parse_openai_items(self, output_text: str) -> list[Any]:
        normalized = clean_optional_text(output_text)
        if not normalized:
            raise DomainValidationError("OpenAI response is empty")

        data = self._load_json_payload(normalized)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return items
        raise DomainValidationError(
            "OpenAI response does not contain a valid items array"
        )

    def _load_json_payload(self, output_text: str) -> Any:
        candidates = [output_text]

        fenced_match = re.search(
            r"```(?:json)?\s*(.+?)\s*```", output_text, flags=re.DOTALL | re.IGNORECASE
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

        raise DomainValidationError("OpenAI response is not valid JSON")
