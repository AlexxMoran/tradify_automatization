from __future__ import annotations

from domains.invoice_enrichment.goods_description.constraints import REVIEW_PATCH_FIELDS
from domains.invoice_enrichment.goods_description.rules import ALLOWED_MATERIALS


def goods_description_items_schema() -> dict[str, object]:
    item_properties = {
        "line_no": {"type": "integer"},
        "description_en": {"type": "string"},
        "description_pl": {"type": "string"},
        "made_of": {"type": "string", "enum": list(ALLOWED_MATERIALS)},
        "made_in": {"type": "string"},
        "country_of_origin": {"type": "string"},
        "melt_and_pour": {"type": "string"},
        "manufacturer_data": {"type": "string"},
    }
    return {
        "type": "json_schema",
        "name": "goods_description_items",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": item_properties,
                        "required": list(item_properties),
                    },
                }
            },
            "required": ["items"],
        },
    }


def goods_description_review_patch_schema() -> dict[str, object]:
    change_properties = {
        "field": {"type": "string", "enum": sorted(REVIEW_PATCH_FIELDS)},
        "value": {"type": "string"},
        "reason": {"type": "string"},
    }
    item_properties = {
        "line_no": {"type": "integer"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": change_properties,
                "required": list(change_properties),
            },
        },
    }
    return {
        "type": "json_schema",
        "name": "goods_description_review_patch",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": item_properties,
                        "required": list(item_properties),
                    },
                }
            },
            "required": ["items"],
        },
    }
