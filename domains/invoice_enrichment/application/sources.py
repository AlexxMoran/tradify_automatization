from __future__ import annotations

from typing import Protocol

from clients import BaseLinkerClient, BaseLinkerError

from domains.invoice_enrichment.application.errors import (
    ConfigurationError,
    ExternalDependencyError,
)
from domains.invoice_enrichment.models import SourceInvoiceDocument


class InvoiceSource(Protocol):
    async def load(self) -> SourceInvoiceDocument:
        """Load a source invoice document."""


class BaseLinkerInvoiceSource:
    def __init__(self, client: BaseLinkerClient, order_id: str) -> None:
        self._client = client
        self._order_id = order_id

    async def load(self) -> SourceInvoiceDocument:
        try:
            invoice_file = await self._client.fetch_external_invoice_pdf(self._order_id)
        except BaseLinkerError as exc:
            message = str(exc)
            if "not configured" in message.lower():
                raise ConfigurationError(message) from exc
            raise ExternalDependencyError(message) from exc

        return SourceInvoiceDocument(
            order_id=invoice_file.order_id,
            invoice_id=invoice_file.invoice_id,
            invoice_number=invoice_file.invoice_number or None,
            source_filename=invoice_file.invoice_number
            or f"invoice_{invoice_file.order_id}.pdf",
            pdf_bytes=invoice_file.pdf_bytes,
        )


class UploadedPdfInvoiceSource:
    def __init__(
        self,
        pdf_bytes: bytes,
        *,
        order_id: str,
        source_filename: str | None,
    ) -> None:
        self._document = SourceInvoiceDocument(
            order_id=order_id,
            source_filename=source_filename,
            pdf_bytes=pdf_bytes,
        )

    async def load(self) -> SourceInvoiceDocument:
        return self._document
