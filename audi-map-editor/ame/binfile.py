from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

DTYPE_FORMATS = {
    "uint8":  ("B", 1, False),
    "int8":   ("b", 1, True),
    "uint16": ("H", 2, False),
    "int16":  ("h", 2, True),
    "uint32": ("I", 4, False),
    "int32":  ("i", 4, True),
    "float32":("f", 4, True),
}

NUMPY_DTYPES = {
    "uint8": np.uint8, "int8": np.int8,
    "uint16": np.uint16, "int16": np.int16,
    "uint32": np.uint32, "int32": np.int32,
    "float32": np.float32,
}


def dtype_size(dtype: str) -> int:
    return DTYPE_FORMATS[dtype][1]


def dtype_signed(dtype: str) -> bool:
    return DTYPE_FORMATS[dtype][2]


@dataclass
class BinFile:
    path: Path | None
    data: bytearray
    modified: bool = False

    @classmethod
    def load(cls, path: str | Path) -> "BinFile":
        path = Path(path)
        with open(path, "rb") as fh:
            data = bytearray(fh.read())
        return cls(path=path, data=data, modified=False)

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("no path to save to")
        with open(target, "wb") as fh:
            fh.write(self.data)
        self.path = target
        self.modified = False
        return target

    @property
    def size(self) -> int:
        return len(self.data)

    def read_value(self, address: int, dtype: str, big_endian: bool = False) -> float | int:
        fmt, size, _signed = DTYPE_FORMATS[dtype]
        prefix = ">" if big_endian else "<"
        chunk = bytes(self.data[address:address + size])
        if len(chunk) != size:
            raise IndexError(f"address 0x{address:X} out of range")
        return struct.unpack(prefix + fmt, chunk)[0]

    def write_value(self, address: int, value: float | int, dtype: str, big_endian: bool = False) -> None:
        fmt, size, _signed = DTYPE_FORMATS[dtype]
        prefix = ">" if big_endian else "<"
        if dtype != "float32":
            value = int(round(value))
        packed = struct.pack(prefix + fmt, value)
        self.data[address:address + size] = packed
        self.modified = True

    def read_array(self, address: int, count: int, dtype: str, big_endian: bool = False) -> np.ndarray:
        size = dtype_size(dtype)
        total = size * count
        chunk = bytes(self.data[address:address + total])
        if len(chunk) != total:
            raise IndexError(f"address 0x{address:X} +{total} out of range")
        np_dtype = NUMPY_DTYPES[dtype]
        endian = ">" if big_endian else "<"
        arr = np.frombuffer(chunk, dtype=np.dtype(endian + np_dtype().dtype.str[1:]))
        return arr.astype(np_dtype, copy=True)

    def write_array(self, address: int, values: Iterable[float | int], dtype: str, big_endian: bool = False) -> None:
        arr = np.asarray(list(values))
        np_dtype = NUMPY_DTYPES[dtype]
        if dtype == "float32":
            arr = arr.astype(np.float32, copy=False)
        else:
            info = np.iinfo(np_dtype)
            arr = np.clip(np.rint(arr), info.min, info.max).astype(np_dtype, copy=False)
        endian = ">" if big_endian else "<"
        packed = arr.astype(np.dtype(endian + np_dtype().dtype.str[1:])).tobytes()
        self.data[address:address + len(packed)] = packed
        self.modified = True
