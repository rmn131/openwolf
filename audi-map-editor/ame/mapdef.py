from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import numpy as np

from .binfile import BinFile, dtype_size


@dataclass
class AxisDef:
    address: int = 0
    count: int = 0
    dtype: str = "uint16"
    big_endian: bool = False
    factor: float = 1.0
    offset: float = 0.0
    units: str = ""
    name: str = ""

    def read(self, binf: BinFile) -> np.ndarray:
        if self.count <= 0:
            return np.arange(0, 1)
        raw = binf.read_array(self.address, self.count, self.dtype, self.big_endian)
        return raw.astype(np.float64) * self.factor + self.offset

    def write(self, binf: BinFile, values) -> None:
        if self.count <= 0:
            return
        physical = np.asarray(values, dtype=np.float64)
        raw = (physical - self.offset) / (self.factor if self.factor else 1.0)
        binf.write_array(self.address, raw, self.dtype, self.big_endian)


@dataclass
class MapDef:
    name: str = "unnamed"
    address: int = 0
    rows: int = 1
    cols: int = 1
    dtype: str = "uint16"
    big_endian: bool = False
    factor: float = 1.0
    offset: float = 0.0
    units: str = ""
    notes: str = ""
    x_axis: AxisDef = field(default_factory=AxisDef)
    y_axis: AxisDef = field(default_factory=AxisDef)

    @property
    def data_size(self) -> int:
        return self.rows * self.cols * dtype_size(self.dtype)

    def is_2d(self) -> bool:
        return self.rows <= 1 or self.cols <= 1

    def read(self, binf: BinFile) -> np.ndarray:
        count = max(self.rows, 1) * max(self.cols, 1)
        raw = binf.read_array(self.address, count, self.dtype, self.big_endian)
        phys = raw.astype(np.float64) * self.factor + self.offset
        return phys.reshape(max(self.rows, 1), max(self.cols, 1))

    def write(self, binf: BinFile, values) -> None:
        physical = np.asarray(values, dtype=np.float64).reshape(-1)
        raw = (physical - self.offset) / (self.factor if self.factor else 1.0)
        binf.write_array(self.address, raw, self.dtype, self.big_endian)


def map_to_dict(m: MapDef) -> dict:
    d = asdict(m)
    d["address"] = int(m.address)
    d["x_axis"]["address"] = int(m.x_axis.address)
    d["y_axis"]["address"] = int(m.y_axis.address)
    return d


def map_from_dict(d: dict) -> MapDef:
    d = dict(d)
    x = AxisDef(**d.pop("x_axis", {}))
    y = AxisDef(**d.pop("y_axis", {}))
    allowed = {f.name for f in fields(MapDef) if f.name not in ("x_axis", "y_axis")}
    return MapDef(x_axis=x, y_axis=y, **{k: v for k, v in d.items() if k in allowed})


@dataclass
class Project:
    bin_path: str = ""
    ecu: str = ""
    maps: list[MapDef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bin_path": self.bin_path,
            "ecu": self.ecu,
            "maps": [map_to_dict(m) for m in self.maps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(
            bin_path=d.get("bin_path", ""),
            ecu=d.get("ecu", ""),
            maps=[map_from_dict(m) for m in d.get("maps", [])],
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
