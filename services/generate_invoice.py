from __future__ import annotations

from clients import BaseLinkerClient, BaseLinkerError, ExternalInvoiceFile
from models import ProcessedInvoiceResult
from services.goods_description import DescriptionGenerationError, GoodsDescriptionGenerator
from services.invoice_parser import InvoiceParsingError, InvoicePdfParser
from services.pdf_documents import GoodsDescriptionPdfBuilder, PdfDocumentError, PdfMergeService


class GenerateInvoiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class GenerateInvoiceService:
    def __init__(
        self,
        baselinker_client: BaseLinkerClient,
        description_generator: GoodsDescriptionGenerator,
    ) -> None:
        self._baselinker = baselinker_client
        self._generator = description_generator

    async def __call__(self, order_id: str) -> ProcessedInvoiceResult:
        invoice_file = await self._fetch_invoice_file(order_id)
        parsed_document = self._parse_document(invoice_file.pdf_bytes)
        descriptions = await self._generate_descriptions(parsed_document)
        return self._build_pdf(invoice_file, parsed_document, descriptions)

    async def _fetch_invoice_file(self, order_id: str) -> ExternalInvoiceFile:
        try:
            return await self._baselinker.fetch_external_invoice_pdf(order_id)
        except BaseLinkerError as exc:
            raise GenerateInvoiceError(str(exc), status_code=502) from exc

    def _parse_document(self, pdf_bytes: bytes):
        try:
            return InvoicePdfParser().parse(pdf_bytes)
        except InvoiceParsingError as exc:
            raise GenerateInvoiceError(str(exc), status_code=422) from exc

    async def _generate_descriptions(self, parsed_document):
        try:
            return await self._generator.generate(parsed_document)
        except DescriptionGenerationError as exc:
            raise GenerateInvoiceError(str(exc), status_code=422) from exc

    def _build_pdf(self, invoice_file, parsed_document, descriptions) -> ProcessedInvoiceResult:
        try:
            result, description_pdf_bytes = GoodsDescriptionPdfBuilder().build(
                invoice_file,
                parsed_document,
                descriptions,
            )
            return PdfMergeService().merge(result, invoice_file.pdf_bytes, description_pdf_bytes)
        except PdfDocumentError as exc:
            raise GenerateInvoiceError(str(exc), status_code=500) from exc


class GenerateInvoiceTestService:
    def __init__(self, description_generator: GoodsDescriptionGenerator) -> None:
        self._generator = description_generator

    async def __call__(
        self,
        pdf_bytes: bytes,
        *,
        order_id: str,
        source_filename: str | None,
    ) -> ProcessedInvoiceResult:
        parsed_document = self._parse_document(pdf_bytes)
        descriptions = await self._generate_descriptions(parsed_document)
        return self._build_pdf(
            pdf_bytes,
            order_id=order_id,
            source_filename=source_filename,
            parsed_document=parsed_document,
            descriptions=descriptions,
        )

    def _parse_document(self, pdf_bytes: bytes):
        try:
            return InvoicePdfParser().parse(pdf_bytes)
        except InvoiceParsingError as exc:
            raise GenerateInvoiceError(str(exc), status_code=422) from exc

    async def _generate_descriptions(self, parsed_document):
        try:
            return await self._generator.generate(parsed_document)
        except DescriptionGenerationError as exc:
            raise GenerateInvoiceError(str(exc), status_code=422) from exc

    def _build_pdf(
        self,
        pdf_bytes: bytes,
        *,
        order_id: str,
        source_filename: str | None,
        parsed_document,
        descriptions,
    ) -> ProcessedInvoiceResult:
        try:
            result = ProcessedInvoiceResult(
                message="Invoice processed successfully",
                order_id=order_id,
                document_type=parsed_document.document_type,
                document_ref=parsed_document.document_ref,
                issue_date=parsed_document.issue_date,
                currency=parsed_document.currency or (
                    parsed_document.line_items[0].currency if parsed_document.line_items else None
                ),
                source_filename=source_filename,
                original_pdf_size_bytes=len(pdf_bytes),
                line_items=parsed_document.line_items,
                descriptions=descriptions,
            )
            description_pdf_bytes = GoodsDescriptionPdfBuilder().render(result, source_pdf_bytes=pdf_bytes)
            return PdfMergeService().merge(result, pdf_bytes, description_pdf_bytes)
        except PdfDocumentError as exc:
            raise GenerateInvoiceError(str(exc), status_code=500) from exc
