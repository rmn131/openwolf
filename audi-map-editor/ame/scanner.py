"""Heuristic scanner for EDC17 map structures.

EDC17 calibration blocks have no central table-of-contents that we can rely on
without DAMOS/A2L. What works is searching for the *axes*: short sequences of
strictly increasing little-endian int16 values that look like physical axes
(RPM, load, MAP, IQ, time, etc.). The data table for a map usually starts
immediately after its Y-axis (the longer of the two for a 3D map).

This module exposes :func:`scan` which walks a byte range and yields
:class:`AxisHit` and :class:`MapHit` candidates the user can confirm in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np

from .binfile import BinFile


@dataclass
class AxisHit:
    address: int
    count: int
    dtype: str           # "uint16" or "int16"
    big_endian: bool
    values: np.ndarray   # raw values
    score: float

    def describe(self) -> str:
        lo, hi = int(self.values.min()), int(self.values.max())
        return (
            f"0x{self.address:06X}  n={self.count:2d}  {self.dtype}  "
            f"range {lo}..{hi}  score {self.score:.2f}"
        )


@dataclass
class MapHit:
    address: int
    rows: int
    cols: int
    dtype: str
    big_endian: bool
    x_axis: AxisHit | None
    y_axis: AxisHit | None
    score: float

    def describe(self) -> str:
        return (
            f"0x{self.address:06X}  {self.rows}x{self.cols}  {self.dtype}  "
            f"score {self.score:.2f}"
        )


def _axis_score(values: np.ndarray) -> float:
    """Higher is better; 0 means rejected."""
    n = values.size
    if n < 4 or n > 32:
        return 0.0
    diffs = np.diff(values.astype(np.int64))
    if np.any(diffs <= 0):
        return 0.0
    span = int(values[-1]) - int(values[0])
    if span <= 0 or span > 60000:
        return 0.0
    # Even-ish spacing scores well, but we still allow non-linear axes.
    mean_step = diffs.mean()
    if mean_step <= 0:
        return 0.0
    cv = float(diffs.std() / mean_step)
    monotonic = 1.0
    smoothness = max(0.0, 1.0 - min(cv, 2.0) / 2.0)
    length_bonus = min(n, 16) / 16.0
    return monotonic * 0.5 + smoothness * 0.3 + length_bonus * 0.2


def find_axes(
    binf: BinFile,
    start: int,
    end: int,
    *,
    dtype: str = "uint16",
    big_endian: bool = False,
    min_count: int = 6,
    max_count: int = 24,
    step: int = 2,
    min_score: float = 0.55,
) -> list[AxisHit]:
    """Slide over [start, end) looking for plausible numeric axes."""
    item = 2
    np_dtype = np.uint16 if dtype == "uint16" else np.int16
    endian = ">" if big_endian else "<"

    raw_block = bytes(binf.data[start:end])
    total = len(raw_block) // item
    if total < min_count:
        return []
    arr = np.frombuffer(raw_block[: total * item], dtype=np.dtype(endian + np_dtype().dtype.str[1:]))
    arr = arr.astype(np_dtype)

    hits: list[AxisHit] = []
    i = 0
    while i + min_count <= total:
        # extend a run as long as values strictly increase
        j = i + 1
        while j < total and int(arr[j]) > int(arr[j - 1]) and (j - i) < max_count:
            j += 1
        run_len = j - i
        if run_len >= min_count:
            seg = arr[i:j]
            score = _axis_score(seg)
            if score >= min_score:
                hits.append(
                    AxisHit(
                        address=start + i * item,
                        count=run_len,
                        dtype=dtype,
                        big_endian=big_endian,
                        values=seg.copy(),
                        score=score,
                    )
                )
            i = j  # skip past this run
        else:
            i += step // item if step >= item else 1
    return hits


def pair_into_maps(
    binf: BinFile,
    axes: list[AxisHit],
    *,
    data_dtypes: tuple[str, ...] = ("uint16", "int16", "uint8"),
    max_gap: int = 64,
) -> list[MapHit]:
    """Look for 3D maps as ``[x_axis][y_axis][data]`` triples in flash.

    For each pair of adjacent axes (x then y, almost touching) try to read
    ``x.count * y.count`` cells of each supported dtype starting right after
    the y-axis; the candidate becomes a map if the data values stay within a
    reasonable physical range (cheap sanity check).
    """
    hits: list[MapHit] = []
    by_addr = sorted(axes, key=lambda h: h.address)
    for i, xa in enumerate(by_addr):
        x_end = xa.address + xa.count * 2
        for ya in by_addr[i + 1: i + 6]:
            if ya.address < x_end:
                continue
            if ya.address - x_end > max_gap:
                break
            data_addr = ya.address + ya.count * 2
            for dt in data_dtypes:
                try:
                    arr = binf.read_array(data_addr, xa.count * ya.count, dt)
                except IndexError:
                    continue
                if arr.size == 0:
                    continue
                spread = float(arr.max() - arr.min())
                if spread < 1.0:
                    continue
                # Reject obvious code/garbage: too many zeros or saturated FFs.
                zeros = float((arr == 0).sum()) / arr.size
                if dt.startswith("u") and zeros > 0.6:
                    continue
                score = 0.5 * xa.score + 0.5 * ya.score
                hits.append(
                    MapHit(
                        address=data_addr,
                        rows=ya.count,
                        cols=xa.count,
                        dtype=dt,
                        big_endian=False,
                        x_axis=xa,
                        y_axis=ya,
                        score=score,
                    )
                )
                break  # accept first dtype that fits
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def scan(
    binf: BinFile,
    start: int,
    end: int,
    *,
    progress=None,
) -> tuple[list[AxisHit], list[MapHit]]:
    """Convenience wrapper used by the UI."""
    axes: list[AxisHit] = []
    for dt in ("uint16", "int16"):
        if progress:
            progress(f"scanning axes as {dt}...")
        axes.extend(find_axes(binf, start, end, dtype=dt))
    if progress:
        progress(f"found {len(axes)} axis candidates, pairing into maps...")
    maps = pair_into_maps(binf, axes)
    if progress:
        progress(f"found {len(maps)} map candidates")
    return axes, maps
