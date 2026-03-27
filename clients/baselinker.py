import base64
import json
import logging
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)


class BaseLinkerError(Exception):
    pass


@dataclass(slots=True)
class ExternalInvoiceFile:
    order_id: str
    invoice_id: int
    invoice_number: str
    pdf_bytes: bytes


class BaseLinkerClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.api_token = settings.baselinker_api_token
        self.api_url = settings.baselinker_api_url
        self.timeout_seconds = settings.baselinker_timeout_seconds
        self._http_client = httpx.AsyncClient(timeout=self.timeout_seconds)

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def fetch_external_invoice_pdf(self, order_id: str) -> ExternalInvoiceFile:
        invoices = await self.get_invoices(order_id)

        if not invoices:
            raise BaseLinkerError(f"No invoices found for order_id={order_id}")

        invoice = self._select_invoice(invoices)
        invoice_id = invoice.get("invoice_id")

        if invoice_id is None:
            raise BaseLinkerError("Invoice payload does not contain invoice_id")

        payload = await self._request(
            method="getInvoiceFile",
            parameters={
                "invoice_id": int(invoice_id),
                "get_external": True,
            },
        )

        encoded_invoice = payload.get("invoice")
        if not encoded_invoice:
            raise BaseLinkerError("BaseLinker returned an empty invoice file payload")

        return ExternalInvoiceFile(
            order_id=str(order_id),
            invoice_id=int(invoice_id),
            invoice_number=str(payload.get("invoice_number") or invoice.get("number") or ""),
            pdf_bytes=self._decode_invoice_data(str(encoded_invoice)),
        )

    async def get_invoices(self, order_id: str) -> list[dict[str, Any]]:
        try:
            order_id_int = int(order_id)
        except ValueError:
            raise BaseLinkerError(f"Invalid order_id: {order_id!r} is not a valid integer")
        payload = await self._request(
            method="getInvoices",
            parameters={
                "order_id": order_id_int,
            },
        )
        invoices = payload.get("invoices", [])

        if not isinstance(invoices, list):
            raise BaseLinkerError("BaseLinker returned invoices in an unexpected format")

        return invoices

    async def _request(self, method: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if not self.api_token:
            raise BaseLinkerError("BASELINKER_API_TOKEN is not configured")

        try:
            response = await self._http_client.post(
                self.api_url,
                headers={"X-BLToken": self.api_token},
                data={
                    "method": method,
                    "parameters": json.dumps(parameters),
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise BaseLinkerError(f"BaseLinker request timed out for method={method}") from exc
        except httpx.HTTPStatusError as exc:
            raise BaseLinkerError(
                f"BaseLinker request failed with HTTP {exc.response.status_code} for method={method}"
            ) from exc
        except httpx.HTTPError as exc:
            raise BaseLinkerError(f"BaseLinker request failed for method={method}: {exc}") from exc

        try:
            payload = response.json()
        except (JSONDecodeError, ValueError) as exc:
            raise BaseLinkerError(
                f"BaseLinker returned an invalid JSON payload for method={method}"
            ) from exc
        if not isinstance(payload, dict):
            raise BaseLinkerError(
                f"BaseLinker returned an unexpected JSON payload type for method={method}"
            )

        status = payload.get("status")
        if status != "SUCCESS":
            error_code = payload.get("error_code", "UNKNOWN")
            error_message = payload.get("error_message", "BaseLinker request failed")
            logger.warning("BaseLinker %s failed: %s - %s", method, error_code, error_message)
            raise BaseLinkerError(f"{method} failed (code: {error_code})")

        return payload

    def _select_invoice(self, invoices: list[dict[str, Any]]) -> dict[str, Any]:
        return max(invoices, key=lambda invoice: int(invoice.get("invoice_id", 0)))

    def _decode_invoice_data(self, encoded_invoice: str) -> bytes:
        if "," in encoded_invoice:
            encoded_invoice = encoded_invoice.split(",", maxsplit=1)[1]
        elif encoded_invoice.startswith("data:"):
            encoded_invoice = encoded_invoice[5:]

        try:
            return base64.b64decode(encoded_invoice, validate=True)
        except (ValueError, TypeError) as exc:
            raise BaseLinkerError("Failed to decode BaseLinker invoice payload") from exc
