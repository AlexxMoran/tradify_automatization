from __future__ import annotations

from domains.invoice_enrichment.application.errors import (
    ConfigurationError,
    ExternalDependencyError,
)
from domains.invoice_enrichment.goods_description.draft import Draft
from domains.invoice_enrichment.goods_description.models import ReviewPatch
from domains.invoice_enrichment.goods_description.ai.response_parser import (
    ResponseParser,
)
from domains.invoice_enrichment.goods_description.ai.response_schemas import (
    goods_description_items_schema,
    goods_description_review_patch_schema,
)


class Gateway:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str,
        generation_mode: str,
        response_parser: ResponseParser | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._reasoning_effort = reasoning_effort.lower().strip()
        self._generation_mode = generation_mode.lower().strip() or "hybrid"
        self._response_parser = response_parser or ResponseParser()
        self._client = None

        if self._api_key:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)

    async def request_items(
        self,
        prompt: str,
        *,
        use_web_search: bool,
    ) -> list[Draft]:
        output_text = await self._request_output_text(
            prompt,
            use_web_search=use_web_search,
            response_format=goods_description_items_schema(),
        )
        return self._response_parser.parse_drafts(output_text)

    async def request_review_patch(
        self,
        prompt: str,
        *,
        use_web_search: bool,
    ) -> ReviewPatch:
        output_text = await self._request_output_text(
            prompt,
            use_web_search=use_web_search,
            response_format=goods_description_review_patch_schema(),
        )
        return self._response_parser.parse_review_patch(output_text)

    async def _request_output_text(
        self,
        prompt: str,
        *,
        use_web_search: bool,
        response_format: dict[str, object],
    ) -> str:
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
                "text": {"format": response_format},
            }
            if self._supports_reasoning_effort():
                request_kwargs["reasoning"] = {"effort": self._reasoning_effort}
            if use_web_search:
                request_kwargs["tools"] = [{"type": "web_search"}]
                request_kwargs["tool_choice"] = "required"
            response = await self._client.responses.create(**request_kwargs)
        except Exception as exc:
            raise ExternalDependencyError(
                f"OpenAI description generation failed: {exc}"
            ) from exc

        return response.output_text

    def _supports_reasoning_effort(self) -> bool:
        if not self._reasoning_effort:
            return False
        normalized_model = self._model.lower().strip()
        return normalized_model.startswith(("gpt-5", "o1", "o3", "o4"))
