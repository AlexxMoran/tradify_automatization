from __future__ import annotations

import json


def build_goods_description_prompt(payload: list[dict[str, object]]) -> str:
    return (
        "You enrich invoice rows for a customs goods description table. "
        "Use only the provided invoice items. Do not add or remove rows. "
        "Return strict JSON in the form "
        "{\"items\":[{\"line_no\":1,\"description_en\":\"...\",\"description_pl\":\"...\","
        "\"made_of\":\"...\",\"made_in\":\"...\",\"country_of_origin\":\"...\","
        "\"melt_and_pour\":\"...\",\"manufacturer_data\":\"...\"}]}. "
        "The descriptions must explain what the product is and its household-use purpose. "
        "Do not mention professional usage. "
        "Do not use the words aluminium, aluminum, or copper. "
        "The made_of field must be extremely short: maximum two words. "
        "Prefer a compact material format like 'plastic/steel' when two materials are known. "
        "If a field cannot be determined with confidence, use 'UNKNOWN' for factual fields or 'N/A' for non-applicable fields. "
        "Use the origin field from the source row for made_in and country_of_origin unless there is a clear reason not to. "
        "If origin is empty, do not treat that as an error: still generate the descriptive fields from the available row data. "
        "When origin is empty and you cannot determine made_in or country_of_origin with confidence, return 'N/A' for those fields. "
        "Do not change currency, quantities, prices, or weights. "
        f"Invoice items: {json.dumps(payload, ensure_ascii=False)}"
    )
