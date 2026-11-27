"""QIDI Box: the filament in each slot of QIDI's multi-filament feeder.

The Box adds ``box_stepper slotN`` and ``box_extras`` objects to Klipper
(seen on a Q2 with one Box). Newer firmware reports decoded
per-slot details in ``box_extras.boxes[N].filament_info``; older firmware only
stores numeric codes in ``save_variables``. The lookup tables below mirror the
printer's own ``officiall_filas_list.cfg`` (``[filaN]``, ``[colordict]`` and
``[vendor_list]``) and only turn those older codes into readable values.
Slots are numbered from 0 in Klipper (``slot0``-``slot3`` are Box 1) and
``slot16`` means nothing from the Box feeds the toolhead.
"""

from __future__ import annotations

import re
from typing import Any

FILAMENTS = {
    1: "PLA Rapido",
    2: "PLA Matte",
    3: "PLA Metal",
    4: "PLA Silk",
    5: "PLA-CF",
    6: "PLA-Wood",
    7: "PLA Basic",
    8: "PLA Matte Basic",
    10: "Support For PLA",
    11: "ABS Rapido",
    12: "ABS-GF",
    13: "ABS-Metal",
    14: "ABS-Odorless",
    15: "TPU-GF",
    18: "ASA",
    19: "ASA-Aero",
    20: "ASA-CF",
    23: "PC",
    24: "UltraPA",
    25: "PA6-CF",
    26: "UltraPA-CF25",
    27: "PA12-CF",
    30: "PAHT-CF",
    31: "PAHT-GF",
    32: "Support For PAHT",
    33: "Support For PET/PA",
    34: "PC/ABS-FR",
    35: "TPEE",
    36: "PEBA",
    37: "PET-CF",
    38: "PET-GF",
    39: "PETG Basic",
    40: "PETG-Tough",
    41: "PETG Rapido",
    42: "PETG-CF",
    43: "PETG-GF",
    44: "PPS-CF",
    45: "PETG Translucent",
    46: "PPS-GF",
    47: "PVA",
    48: "TPU-AERO 64D",
    49: "TPU-Aero",
    50: "TPU 95A-HF",
}
COLORS = {
    1: "#FAFAFA",
    2: "#060606",
    3: "#D9E3ED",
    4: "#5CF30F",
    5: "#63E492",
    6: "#2850FF",
    7: "#FE98FE",
    8: "#DFD628",
    9: "#228332",
    10: "#99DEFF",
    11: "#1714B0",
    12: "#CEC0FE",
    13: "#CADE4B",
    14: "#1353AB",
    15: "#5EA9FD",
    16: "#A878FF",
    17: "#FE717A",
    18: "#FF362D",
    19: "#E2DFCD",
    20: "#898F9B",
    21: "#6E3812",
    22: "#CAC59F",
    23: "#F28636",
    24: "#B87F2B",
}
VENDORS = {
    0: "Generic",
    1: "QIDI",
}

SLOTS_PER_BOX = 4
EXTERNAL_SLOT = 16
_SLOT_RE = re.compile(r"^box_stepper slot(\d+)$")
_SLOT_NAME_RE = re.compile(r"^slot(\d+)$")


def slot_indices(objects: list[str] | set[str]) -> list[int]:
    """Return the 0-based Box slots the printer reports, or [] without a Box."""
    if "box_extras" not in objects:
        return []
    found = (_SLOT_RE.match(obj) for obj in objects)
    return sorted(int(match.group(1)) for match in found if match)


def _section(status: dict[str, Any], key: str) -> dict[str, Any]:
    value = status.get(key)
    return value if isinstance(value, dict) else {}


def _variables(status: dict[str, Any]) -> dict[str, Any]:
    variables = _section(status, "save_variables").get("variables")
    return variables if isinstance(variables, dict) else {}


def _filament_info(status: dict[str, Any], index: int) -> dict[str, Any]:
    """Return the decoded ``filament_info`` entry for a slot, else ``{}``."""
    boxes = _section(status, "box_extras").get("boxes")
    number = index // SLOTS_PER_BOX
    box = boxes[number] if isinstance(boxes, list) and number < len(boxes) else None
    info = box.get("filament_info") if isinstance(box, dict) else None
    position = index % SLOTS_PER_BOX
    entry = info[position] if isinstance(info, list) and position < len(info) else None
    return entry if isinstance(entry, dict) else {}


def _lookup(table: dict[int, str], code: Any) -> str | None:
    return table.get(code) if isinstance(code, int) else None


def _hex_color(value: Any) -> str | None:
    """Return ``#RRGGBB`` from a colour id, hex string or list of hex strings."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, int):
        return _lookup(COLORS, value)
    if isinstance(value, str) and value:
        return value if value.startswith("#") else f"#{value}"
    return None


def slot_is_empty(status: dict[str, Any], index: int) -> bool:
    """Return True when the slot's runout switch reports no filament."""
    stepper = _section(status, f"box_stepper slot{index}")
    return stepper.get("runout_button") == 1


def slot_number(value: Any) -> int | None:
    """Return the 0-based slot for ``slotN``, or None for ``slot16`` and the rest."""
    match = _SLOT_NAME_RE.match(value) if isinstance(value, str) else None
    if not match or int(match.group(1)) >= EXTERNAL_SLOT:
        return None
    return int(match.group(1))


def slot_is_active(status: dict[str, Any], index: int) -> bool:
    """Return True when the slot feeds the toolhead.

    ``box_extras.loaded_slot`` is what feeds it now (``slot16``: nothing from
    the Box); ``save_variables.slotN == 2`` can still mark an earlier slot, so
    it counts only on firmware without ``loaded_slot``.
    """
    if slot_is_empty(status, index):
        return False
    extras = _section(status, "box_extras")
    if "loaded_slot" in extras:
        return slot_number(extras.get("loaded_slot")) == index
    return _variables(status).get(f"slot{index}") == 2


def slot_filament(status: dict[str, Any], index: int) -> str:
    """Return the filament loaded in a slot, ``Empty``, or ``Unknown``."""
    if slot_is_empty(status, index):
        return "Empty"
    name = _filament_info(status, index).get("filament_str")
    if isinstance(name, str) and name:
        return name
    code = _variables(status).get(f"filament_slot{index}")
    if isinstance(code, int):
        return FILAMENTS.get(code, f"Unknown ({code})")
    if code is not None and str(code):
        return str(code)
    return "Unknown"


def slot_attributes(status: dict[str, Any], index: int) -> dict[str, Any]:
    """Return a slot's colour, whether it feeds the toolhead, and its filament details.

    ``color`` is None for an empty slot: the printer keeps the last spool's
    colour, which would otherwise show a spool that is not there.
    """
    variables = _variables(status)
    info = _filament_info(status, index)
    empty = slot_is_empty(status, index)
    vendor = info.get("vendor_str")
    return {
        "color": None
        if empty
        else _hex_color(info.get("color_rgb_str"))
        or _hex_color(variables.get(f"color_slot{index}")),
        "active": slot_is_active(status, index),
        "vendor": vendor
        if isinstance(vendor, str) and vendor
        else _lookup(VENDORS, variables.get(f"vendor_slot{index}")),
        "filament_type": info.get("filament_type"),
        "min_temp": info.get("min_temp"),
        "max_temp": info.get("max_temp"),
        "runout": empty,
    }
