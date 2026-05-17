"""EDC17 firmware identification.

Bosch EDC17 variants used by VAG (incl. Audi A6) follow a predictable layout:
the SW marker, the EPK/CTPROT string and a part-number string live in fixed
zones near the start of certain 64 KB sub-blocks. We grep for those and
report what we recognise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .binfile import BinFile

# Common map-data window for EDC17_CP44 / CP54 / C46. Last 768 KB of the
# 4 MB image is the calibration block ("DS1") - unencrypted, holds maps.
DATA_BLOCKS = {
    "EDC17CP44": (0x340000, 0x400000),
    "EDC17CP54": (0x340000, 0x400000),
    "EDC17C46":  (0x340000, 0x400000),
    "EDC17C64":  (0x340000, 0x400000),
}


@dataclass
class EcuInfo:
    variant: str = ""           # EDC17CP44 etc.
    tricore: str = ""           # TC1797
    ctprot: str = ""            # CTPROT_V02.05.010c
    sw_number: str = ""         # 10375181881071C5WA
    epk: str = ""               # 37/1/EDC17_CP44/5/P1071//C1071C5WA///
    part_number: str = ""       # 4G0907401B
    engine_desc: str = ""       # 3.0TDI EDC17  CDUC
    data_block: tuple[int, int] | None = None

    def summary(self) -> str:
        lines = []
        if self.variant:
            lines.append(f"ECU:        {self.variant}  ({self.tricore or '?'})")
        if self.part_number:
            lines.append(f"Part #:     {self.part_number}")
        if self.engine_desc:
            lines.append(f"Engine:     {self.engine_desc}")
        if self.sw_number:
            lines.append(f"SW number:  {self.sw_number}")
        if self.epk:
            lines.append(f"EPK:        {self.epk}")
        if self.ctprot:
            lines.append(f"CTPROT:     {self.ctprot}")
        if self.data_block:
            a, b = self.data_block
            lines.append(f"Data block: 0x{a:06X} - 0x{b:06X}")
        return "\n".join(lines)


def identify(binf: BinFile) -> EcuInfo:
    data = bytes(binf.data)
    info = EcuInfo()

    m = re.search(rb"EDC17[_A-Z0-9]{0,8}", data)
    if m:
        token = m.group(0).replace(b"_", b"").decode("ascii", "ignore")
        info.variant = token[:9].rstrip("_")
    m = re.search(rb"TC1\d{3}", data)
    if m:
        info.tricore = m.group(0).decode("ascii", "ignore")
    m = re.search(rb"CTPROT_V[0-9A-Za-z\.]+", data)
    if m:
        info.ctprot = m.group(0).decode("ascii", "ignore")

    m = re.search(rb"1037\d{6}[0-9A-Z]{6}", data)
    if m:
        info.sw_number = m.group(0).decode("ascii", "ignore")

    m = re.search(rb"\d{1,3}/\d+/EDC17[_A-Z0-9]+/\d+/[A-Z0-9]+/{1,2}[A-Z0-9]+/{1,3}", data)
    if m:
        info.epk = m.group(0).decode("ascii", "ignore")

    # Real VAG ECU part number has a revision letter (4G0907401B). The base
    # form without the letter also occurs; prefer the revisioned one if both
    # appear. Both sit near the EV_ECM marker.
    candidates = re.findall(rb"\b[0-9][A-Z][0-9A-Z]\d{6}[A-Z]?\b", data)
    revisioned = [c for c in candidates if c[-1:].isalpha()]
    pick = revisioned[0] if revisioned else (candidates[0] if candidates else None)
    if pick:
        info.part_number = pick.decode("ascii", "ignore").strip()

    m = re.search(rb"[0-9]\.[0-9]TDI\s+EDC17[^\x00]{0,40}", data)
    if m:
        info.engine_desc = m.group(0).decode("ascii", "ignore").strip()

    if info.variant in DATA_BLOCKS:
        info.data_block = DATA_BLOCKS[info.variant]
    elif info.variant.startswith("EDC17"):
        info.data_block = (0x340000, 0x400000)

    return info
