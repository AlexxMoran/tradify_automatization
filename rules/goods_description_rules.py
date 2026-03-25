from __future__ import annotations


BANNED_WORDS = {"aluminium", "aluminum", "copper"}

COUNTRY_MAP = {
    "DE": "Germany",
    "AT": "Austria",
    "PL": "Poland",
    "CN": "China",
    "US": "United States",
    "GB": "United Kingdom",
    "IT": "Italy",
    "ES": "Spain",
    "FR": "France",
    "CZ": "Czech Republic",
    "NL": "Netherlands",
}

DESCRIPTION_RULES = (
    (
        ("metronome",),
        (
            "Mechanical metronome for musical instruments, intended for household use.",
            "Mechaniczny metronom do instrumentow muzycznych, przeznaczony do uzytku domowego.",
        ),
    ),
    (
        ("violin", "stretto"),
        (
            "Care accessory for a musical instrument, intended for household use.",
            "Akcesorium do pielegnacji instrumentu muzycznego, przeznaczone do uzytku domowego.",
        ),
    ),
    (
        ("guitar", "piano", "instrument"),
        (
            "Accessory for a musical instrument, intended for household use.",
            "Akcesorium do instrumentu muzycznego, przeznaczone do uzytku domowego.",
        ),
    ),
)

MATERIAL_RULES = (
    (("metronome",), "Plastic/steel"),
    (("violin", "stretto"), "Plastic/steel"),
    (("wood", "mahogany", "ivory"), "Mixed materials"),
)

MANUFACTURER_RULES = (
    (
        ("wittner",),
        "Wittner GmbH, Bahnhofstrasse 8-10, 78056 Villingen-Schwenningen, Germany",
    ),
    (
        ("stretto",),
        "Thomastik-Infeld GmbH, Diehlgasse 27, 1050 Vienna, Austria",
    ),
)
