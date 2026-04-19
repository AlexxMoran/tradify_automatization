from __future__ import annotations

from domains.invoice_enrichment.application.errors import (
    ParsingError as PipelineParsingError,
    PdfCompositionError,
)
from domains.invoice_enrichment.application.sources import InvoiceSource
from domains.invoice_enrichment.goods_description.generation.generator import (
    Generator,
)
from domains.invoice_enrichment.invoice_pdf_parser.parsing_error import (
    ParsingError as ParserError,
)
from domains.invoice_enrichment.invoice_pdf_parser.parser import Parser
from domains.invoice_enrichment.models import ProcessedInvoiceResult
from domains.invoice_enrichment.pdf_document.builder import (
    Builder,
)
from domains.invoice_enrichment.pdf_document.document_error import DocumentError
from domains.invoice_enrichment.pdf_document.merge_service import (
    MergeService,
)


class InvoiceProcessingPipeline:
    def __init__(
        self,
        *,
        parser: Parser,
        description_generator: Generator,
        pdf_builder: Builder,
        pdf_merger: MergeService,
    ) -> None:
        self._parser = parser
        self._description_generator = description_generator
        self._pdf_builder = pdf_builder
        self._pdf_merger = pdf_merger

    async def process(self, source: InvoiceSource) -> ProcessedInvoiceResult:
        source_document = await source.load()
        parsed_document = self._parse_document(source_document.pdf_bytes)
        generation_result = await self._description_generator.generate_with_diagnostics(
            parsed_document
        )
        return self._build_pdf(
            source_document,
            parsed_document,
            generation_result.descriptions,
            generation_result.diagnostics,
        )

    def _parse_document(self, pdf_bytes: bytes):
        try:
            return self._parser.parse(pdf_bytes)
        except ParserError as exc:
            raise PipelineParsingError(str(exc)) from exc

    def _build_pdf(
        self, source_document, parsed_document, descriptions, diagnostics
    ) -> ProcessedInvoiceResult:
        try:
            result, description_pdf_bytes = self._pdf_builder.build(
                source_document,
                parsed_document,
                descriptions,
                diagnostics=diagnostics,
            )
            return self._pdf_merger.merge(
                result, source_document.pdf_bytes, description_pdf_bytes
            )
        except DocumentError as exc:
            raise PdfCompositionError(str(exc)) from exc
