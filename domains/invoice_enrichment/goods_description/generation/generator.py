from __future__ import annotations

import logging

from domains.invoice_enrichment.goods_description.draft import Draft
from domains.invoice_enrichment.goods_description.generation.assembler import (
    Assembler,
)
from domains.invoice_enrichment.goods_description.generation.context_builder import (
    ContextBuilder,
)
from domains.invoice_enrichment.goods_description.generation.fallback import (
    Fallback,
)
from domains.invoice_enrichment.goods_description.generation.finalizer import (
    Finalizer,
)
from domains.invoice_enrichment.goods_description.ai.gateway import Gateway
from domains.invoice_enrichment.goods_description.diagnostics import (
    Diagnostics,
)
from domains.invoice_enrichment.goods_description.models import (
    GenerationResult,
    ReviewPatch,
)
from domains.invoice_enrichment.goods_description.normalization.normalizer import (
    Normalizer,
)
from domains.invoice_enrichment.goods_description.prompts.generation import (
    build_goods_description_prompt,
)
from domains.invoice_enrichment.goods_description.prompts.review import (
    build_goods_description_review_prompt,
)
from domains.invoice_enrichment.goods_description.generation.patch_applier import (
    PatchApplier,
)
from domains.invoice_enrichment.goods_description.generation.review_payload_builder import (
    ReviewPayloadBuilder,
)
from domains.invoice_enrichment.goods_description.generation.review_planner import (
    ReviewPlanner,
)
from domains.invoice_enrichment.goods_description.rule_resolver import RuleResolver
from domains.invoice_enrichment.goods_description.generation.validator import (
    Validator,
)
from domains.invoice_enrichment.models import GoodsDescriptionEntry, ParsedDocument

logger = logging.getLogger(__name__)


class Generator:
    def __init__(
        self,
        *,
        resolver: RuleResolver,
        gateway: Gateway,
        normalizer: Normalizer,
        validator: Validator,
    ) -> None:
        self._gateway = gateway
        self._validator = validator
        self._context_builder = ContextBuilder(
            resolver=resolver,
            normalizer=normalizer,
        )
        self._assembler = Assembler(normalizer)
        self._fallback = Fallback(normalizer)
        self._finalizer = Finalizer(self._fallback)
        self._review_payload_builder = ReviewPayloadBuilder(
            context_builder=self._context_builder,
            assembler=self._assembler,
            fallback=self._fallback,
        )
        self._patch_applier = PatchApplier(self._assembler)
        self._review_planner = ReviewPlanner()

    async def generate(
        self,
        parsed_document: ParsedDocument,
    ) -> list[GoodsDescriptionEntry]:
        result = await self.generate_with_diagnostics(parsed_document)
        return result.descriptions

    async def generate_with_diagnostics(
        self,
        parsed_document: ParsedDocument,
    ) -> GenerationResult:
        diagnostics = Diagnostics()
        if not parsed_document.line_items:
            return GenerationResult([], diagnostics)

        contexts = self._context_builder.build(parsed_document)
        payload = self._context_builder.build_prompt_payload(contexts)
        descriptions = await self._run_initial_phase(
            contexts, payload, parsed_document, diagnostics
        )
        descriptions = await self._run_review_phase(
            contexts, descriptions, parsed_document, diagnostics
        )
        self._log_final_report(parsed_document, descriptions, diagnostics)
        return GenerationResult(descriptions, diagnostics)

    async def _run_initial_phase(
        self,
        contexts,
        payload,
        parsed_document: ParsedDocument,
        diagnostics: Diagnostics,
    ):
        raw_items = await self._safe_request_items(
            build_goods_description_prompt(
                payload,
                document_type=parsed_document.document_type,
                document_ref=parsed_document.document_ref,
            ),
            diagnostics=diagnostics,
        )
        if not raw_items:
            diagnostics.add(
                stage="generation",
                message="Initial AI generation returned no usable draft items",
            )
        descriptions = self._assembler.merge_drafts(contexts, raw_items)
        return self._finalizer.finalize(contexts, descriptions, diagnostics=diagnostics)

    async def _run_review_phase(
        self,
        contexts,
        descriptions,
        parsed_document: ParsedDocument,
        diagnostics: Diagnostics,
    ):
        validation_report = self._validator.build_report(
            parsed_document.line_items,
            descriptions,
        )
        review_contexts = self._review_planner.select_contexts(
            contexts, validation_report
        )
        if not review_contexts:
            diagnostics.add(
                stage="review",
                message="Skipped AI review because all rows are covered by strict local rules",
                severity="info",
            )
            return descriptions

        review_patch = await self._safe_request_review_patch(
            build_goods_description_review_prompt(
                self._review_payload_builder.build(
                    review_contexts, descriptions, validation_report
                ),
                document_type=parsed_document.document_type,
                document_ref=parsed_document.document_ref,
            ),
            diagnostics=diagnostics,
        )
        if not review_patch.has_changes:
            return descriptions

        diagnostics.add(
            stage="review",
            message=f"Applied AI review patch to {len(review_patch.items)} row(s)",
            severity="info",
        )
        descriptions = self._patch_applier.apply(contexts, descriptions, review_patch)
        return self._finalizer.finalize(contexts, descriptions, diagnostics=diagnostics)

    async def _safe_request_items(
        self,
        prompt: str,
        *,
        diagnostics: Diagnostics,
    ) -> list[Draft]:
        try:
            return await self._gateway.request_items(prompt, use_web_search=True)
        except Exception as exc:
            logger.warning(
                "Initial goods description generation failed; using fallback: %s",
                exc,
            )
            diagnostics.add(
                stage="generation",
                message=f"Initial AI generation failed; using fallback: {exc}",
                severity="error",
            )
            return []

    async def _safe_request_review_patch(
        self,
        prompt: str,
        *,
        diagnostics: Diagnostics,
    ) -> ReviewPatch:
        try:
            return await self._gateway.request_review_patch(prompt, use_web_search=True)
        except Exception as exc:
            logger.warning(
                "Goods description review failed; using current draft: %s", exc
            )
            diagnostics.add(
                stage="review",
                message=f"AI review failed; using current draft: {exc}",
                severity="error",
            )
            return ReviewPatch()

    def _add_validation_diagnostics(
        self,
        validation_report,
        diagnostics: Diagnostics,
    ) -> None:
        for issue in validation_report.issues:
            diagnostics.add(
                stage="validation",
                line_no=issue.line_no,
                field=issue.field,
                severity=issue.severity,
                message=issue.message,
            )

    def _log_final_report(
        self,
        parsed_document: ParsedDocument,
        descriptions: list[GoodsDescriptionEntry],
        diagnostics: Diagnostics,
    ) -> None:
        report = self._validator.build_report(parsed_document.line_items, descriptions)
        if not report.has_issues:
            return
        self._add_validation_diagnostics(report, diagnostics)
        logger.warning(
            "Goods description finalized with validation warnings: %s",
            "; ".join(issue.message for issue in report.issues),
        )
