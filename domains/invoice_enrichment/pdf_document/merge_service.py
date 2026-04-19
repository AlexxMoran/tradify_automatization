from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter

from domains.invoice_enrichment.models import ProcessedInvoiceResult
from domains.invoice_enrichment.pdf_document.document_error import DocumentError


class MergeService:
    def merge(
        self,
        result: ProcessedInvoiceResult,
        original_pdf_bytes: bytes,
        description_pdf_bytes: bytes,
    ) -> ProcessedInvoiceResult:
        try:
            writer = PdfWriter()
            writer.append(PdfReader(BytesIO(original_pdf_bytes)))
            writer.append(PdfReader(BytesIO(description_pdf_bytes)))
            buffer = BytesIO()
            writer.write(buffer)
        except Exception as exc:
            raise DocumentError(
                f"Failed to merge invoice PDF documents: {exc}"
            ) from exc
        merged = buffer.getvalue()
        result.description_pdf_size_bytes = len(description_pdf_bytes)
        result.merged_pdf_size_bytes = len(merged)
        result.merged_pdf_bytes = merged
        return result
