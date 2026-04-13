from __future__ import annotations

from domains.invoice_enrichment.application.errors import (
    ParsingError,
    PdfCompositionError,
)
from domains.invoice_enrichment.application.sources import InvoiceSource
from domains.invoice_enrichment.goods_description import GoodsDescriptionGenerator
from domains.invoice_enrichment.invoice_parser import (
    InvoiceParsingError,
    InvoicePdfParser,
)
from domains.invoice_enrichment.models import ProcessedInvoiceResult
from domains.invoice_enrichment.pdf_documents import (
    GoodsDescriptionPdfBuilder,
    PdfDocumentError,
    PdfMergeService,
)


class InvoiceProcessingPipeline:
    def __init__(
        self,
        *,
        parser: InvoicePdfParser,
        description_generator: GoodsDescriptionGenerator,
        pdf_builder: GoodsDescriptionPdfBuilder,
        pdf_merger: PdfMergeService,
    ) -> None:
        self._parser = parser
        self._description_generator = description_generator
        self._pdf_builder = pdf_builder
        self._pdf_merger = pdf_merger

    async def process(self, source: InvoiceSource) -> ProcessedInvoiceResult:
        source_document = await source.load()
        parsed_document = self._parse_document(source_document.pdf_bytes)
        descriptions = await self._description_generator.generate(parsed_document)
        return self._build_pdf(source_document, parsed_document, descriptions)

    def _parse_document(self, pdf_bytes: bytes):
        try:
            return self._parser.parse(pdf_bytes)
        except InvoiceParsingError as exc:
            raise ParsingError(str(exc)) from exc

    def _build_pdf(
        self, source_document, parsed_document, descriptions
    ) -> ProcessedInvoiceResult:
        try:
            result, description_pdf_bytes = self._pdf_builder.build(
                source_document,
                parsed_document,
                descriptions,
            )
            return self._pdf_merger.merge(
                result, source_document.pdf_bytes, description_pdf_bytes
            )
        except PdfDocumentError as exc:
            raise PdfCompositionError(str(exc)) from exc
