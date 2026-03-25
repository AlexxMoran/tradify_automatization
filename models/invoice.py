from dataclasses import asdict, dataclass, field

from pydantic import BaseModel, Field


class GenerateInvoiceRequest(BaseModel):
    order_id: str = Field(..., pattern=r"^\d{1,12}$")


@dataclass(slots=True)
class InvoiceLineItem:
    line_no: int
    item_name: str
    hs_code: str
    origin: str
    currency: str
    quantity: str
    unit_price: str
    line_value: str
    unit_net_weight_kg: str
    total_net_weight_kg: str
    source_text: str


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
    currency: str | None = None
    source_filename: str | None = None
    original_pdf_size_bytes: int | None = None
    description_pdf_size_bytes: int | None = None
    merged_pdf_size_bytes: int | None = None
    line_items: list[InvoiceLineItem] = field(default_factory=list)
    descriptions: list[GoodsDescriptionEntry] = field(default_factory=list)
    merged_pdf_bytes: bytes = field(default=b"", repr=False)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("merged_pdf_bytes", None)
        return data
