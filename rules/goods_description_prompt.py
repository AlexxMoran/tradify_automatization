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
        "Use the item_name, HS code, product description, weights, prices, quantities, and any manufacturer clues in the row to infer the most likely material and country fields. "
        "When origin is empty, infer made_in and country_of_origin from the product description, item name, HS code, and the rest of the row context instead of relying on origin. "
        "When origin is empty, still generate made_of from the row data instead of leaving it blank. "
        "If origin is empty, do not default to UNKNOWN immediately; first infer the most likely made_of, made_in, and country_of_origin from the available row data. "
        "Use UNKNOWN for made_of, made_in, or country_of_origin only as a last resort when the row does not contain enough signals for a reasonable inference. "
        "The melt_and_pour field must reflect whether the item appears to be cast/poured metal. "
        "If made_of suggests metal content such as steel, iron, brass, zinc, alloy, stainless steel, or generic metal, use the same country data as made_in/country_of_origin in melt_and_pour. "
        "If the product does not appear to be metal-based, return 'N/A' for melt_and_pour. "
        "The manufacturer_data field must contain only a postal-style manufacturer address. "
        "Do not write explanations, assumptions, product notes, importer notes, or free-form sentences in manufacturer_data. "
        "If you cannot infer a plausible manufacturer address from the row, brand clues, or product context, return 'UNKNOWN'. "
        "Do not change currency, quantities, prices, or weights. "
        f"Invoice items: {json.dumps(payload, ensure_ascii=False)}"
    )
