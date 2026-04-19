from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class GenerateInvoiceRequest(BaseModel):
    order_id: str = Field(..., pattern=r"^\d{1,12}$")


@dataclass(slots=True)
class SourceInvoiceDocument:
    order_id: str
    pdf_bytes: bytes
    invoice_id: int | None = None
    invoice_number: str | None = None
    source_filename: str | None = None


@dataclass(slots=True)
class InvoiceLineItem:
    line_no: int
    item_name: str
    hs_code: str
    origin: str | None
    currency: str
    quantity: str
    unit_price: str
    line_value: str
    unit_net_weight_kg: str
    total_net_weight_kg: str
    source_text: str


DocumentType = Literal["commercial_invoice", "inter_store_shift", "unknown"]


@dataclass(slots=True)
class ParsedDocument:
    document_type: DocumentType
    document_ref: str | None
    issue_date: str | None
    currency: str | None
    line_items: list[InvoiceLineItem] = field(default_factory=list)


@dataclass(slots=True)
class ResolvedRuleHints:
    category_key: str = ""
    brand_name: str = ""
    manufacturer_name: str = ""
    description_en_hint: str = ""
    description_pl_hint: str = ""
    made_of_hint: str = ""
    made_in_hint: str = ""
    country_of_origin_hint: str = ""
    manufacturer_data_hint: str = ""
    strict_terms: tuple[str, ...] = ()
    prompt_notes: tuple[str, ...] = ()
    strict_fields: tuple[str, ...] = ()

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "category_key": self.category_key,
            "brand_name": self.brand_name,
            "manufacturer_name": self.manufacturer_name,
            "description_en_hint": self.description_en_hint,
            "description_pl_hint": self.description_pl_hint,
            "made_of_hint": self.made_of_hint,
            "made_in_hint": self.made_in_hint,
            "country_of_origin_hint": self.country_of_origin_hint,
            "manufacturer_data_hint": self.manufacturer_data_hint,
            "strict_terms": list(self.strict_terms),
            "prompt_notes": list(self.prompt_notes),
            "strict_fields": list(self.strict_fields),
        }


@dataclass(slots=True)
class GoodsDescriptionEntry:
    line_no: int
    item_name: str
    hs_code: str
    description_en: str
    description_pl: str
    made_of: str
    made_in: str
    country_of_origin: str
    melt_and_pour: str
    manufacturer_data: str
    currency: str
    quantity: str
    unit_price: str
    line_value: str
    net_weight_kg: str


@dataclass(slots=True)
class ProcessedInvoiceResult:
    message: str
    order_id: str
    invoice_id: int | None = None
    invoice_number: str | None = None
    document_type: DocumentType = "unknown"
    document_ref: str | None = None
    issue_date: str | None = None
    currency: str | None = None
    source_filename: str | None = None
    original_pdf_size_bytes: int | None = None
    description_pdf_size_bytes: int | None = None
    merged_pdf_size_bytes: int | None = None
    line_items: list[InvoiceLineItem] = field(default_factory=list)
    descriptions: list[GoodsDescriptionEntry] = field(default_factory=list)
    enrichment_warnings: list[str] = field(default_factory=list)
    enrichment_diagnostics: list[dict[str, object]] = field(default_factory=list)
    merged_pdf_bytes: bytes = field(default=b"", repr=False)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("merged_pdf_bytes", None)
        return data
