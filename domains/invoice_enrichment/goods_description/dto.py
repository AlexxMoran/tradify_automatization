from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.utils import clean_optional_text


@dataclass(slots=True)
class GoodsDescriptionDraft:
    line_no: int
    description_en: str = ""
    description_pl: str = ""
    made_of: str = ""
    made_in: str = ""
    country_of_origin: str = ""
    melt_and_pour: str = ""
    manufacturer_data: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "GoodsDescriptionDraft":
        return cls(
            line_no=int(payload["line_no"]),
            description_en=clean_optional_text(payload.get("description_en")),
            description_pl=clean_optional_text(payload.get("description_pl")),
            made_of=clean_optional_text(payload.get("made_of")),
            made_in=clean_optional_text(payload.get("made_in")),
            country_of_origin=clean_optional_text(payload.get("country_of_origin")),
            melt_and_pour=clean_optional_text(payload.get("melt_and_pour")),
            manufacturer_data=clean_optional_text(payload.get("manufacturer_data")),
        )

    def to_current_draft(self) -> dict[str, str]:
        return {
            "description_en": self.description_en,
            "description_pl": self.description_pl,
            "made_of": self.made_of,
            "made_in": self.made_in,
            "country_of_origin": self.country_of_origin,
            "melt_and_pour": self.melt_and_pour,
            "manufacturer_data": self.manufacturer_data,
        }
