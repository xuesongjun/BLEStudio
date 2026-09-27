"""从统一 CaptureResult 导出 VCD 调试波形。"""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence

import numpy as np

from .models import CaptureResult


@dataclass
class _EventSource:
    identifier: str
    width: int
    initial: int
    indices: np.ndarray
    values: np.ndarray


def _output_path(result: CaptureResult) -> Path:
    result.config.output_dir.mkdir(parents=True, exist_ok=True)
    return result.config.output_dir / f"{result.config.output_stem}.vcd"


def _identifier(index: int) -> str:
    alphabet = [chr(value) for value in range(33, 127)]
    base = len(alphabet)
    output = ""
    number = index
    while True:
        output = alphabet[number % base] + output
        number = number // base - 1
        if number < 0:
            return output


def _safe_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_$\[\]:.-]", "_", name)
    return sanitized or "signal"


def _format_value(value: int, width: int, identifier: str) -> str:
    if width == 1:
        return f"{int(value) & 1}{identifier}"
    mask = (1 << width) - 1
    return f"b{int(value) & mask:0{width}b} {identifier}"


def _array_source(identifier: str, values: np.ndarray, width: int = 1) -> _EventSource:
    array = np.asarray(values).reshape(-1)
    if array.size == 0:
        return _EventSource(
            identifier, width, 0,
            np.empty(0, dtype=np.int64),
            np.empty(0, dtype=np.int64),
        )
    changes = np.flatnonzero(array[1:] != array[:-1]) + 1
    return _EventSource(
        identifier=identifier,
        width=width,
        initial=int(array[0]),
        indices=changes.astype(np.int64, copy=False),
        values=array[changes].astype(np.int64, copy=False),
    )


def _position_maps_to_indices(values: Any, sample_count: int) -> np.ndarray:
    if isinstance(values, np.ndarray):
        values = values.tolist()
    if not isinstance(values, (list, tuple)):
        return np.empty(0, dtype=np.int64)
    indices: List[int] = []
    for positions in values[:sample_count]:
        if isinstance(positions, dict) and positions:
            indices.append(min(int(value) for value in positions.values()))
        else:
            indices.append(-1)
    return np.asarray(indices, dtype=np.int64)


def _sample_indices(result: CaptureResult, side: str) -> np.ndarray:
    info = result.sample_info
    if result.is_iq:
        positions = _position_maps_to_indices(
            info.get(f"{side}_sample_positions"), result.sample_count
        )
        edges = np.asarray(info.get(f"{side}_edges", []), dtype=np.int64).reshape(-1)
    else:
        positions = _position_maps_to_indices(
            info.get("sample_positions"), result.sample_count
        )
        edges = np.asarray(info.get("edges", []), dtype=np.int64).reshape(-1)

    if len(positions) == result.sample_count and np.any(positions >= 0):
        if len(edges):
            missing = np.flatnonzero(positions < 0)
            fillable = missing[missing < len(edges)]
            positions[fillable] = edges[fillable]
        return positions
    if len(edges) >= result.sample_count:
        return edges[:result.sample_count]

    raw_rate = result.raw_capture.sample_rate
    if raw_rate <= 0 or result.sample_rate <= 0:
        return np.arange(result.sample_count, dtype=np.int64)
    ratio = raw_rate / result.sample_rate
    return np.rint(np.arange(result.sample_count) * ratio).astype(np.int64)


def _bus_source(
    identifier: str,
    values: np.ndarray,
    indices: np.ndarray,
    width: int,
    raw_sample_count: int,
) -> _EventSource:
    data = np.asarray(values).reshape(-1).astype(np.int64, copy=False)
    positions = np.asarray(indices).reshape(-1).astype(np.int64, copy=False)
    length = min(len(data), len(positions))
    data = data[:length]
    positions = positions[:length]

    valid = (positions >= 0) & (positions < raw_sample_count)
    data = data[valid]
    positions = positions[valid]
    if not len(data):
        return _EventSource(
            identifier, width, 0,
            np.empty(0, dtype=np.int64),
            np.empty(0, dtype=np.int64),
        )

    order = np.argsort(positions, kind="stable")
    positions = positions[order]
    data = data[order]

    # 同一 raw tick 的 deskew word 只保留最终组装值。
    keep_last = np.r_[positions[1:] != positions[:-1], True]
    positions = positions[keep_last]
    data = data[keep_last]

    initial = 0
    if positions[0] == 0:
        zero_count = int(np.searchsorted(positions, 0, side="right"))
        initial = int(data[zero_count - 1])
        positions = positions[zero_count:]
        data = data[zero_count:]

    if len(data):
        previous = np.r_[initial, data[:-1]]
        changed = data != previous
        positions = positions[changed]
        data = data[changed]
    return _EventSource(identifier, width, initial, positions, data)


def _write_scope(
    handle: Any,
    scope: str,
    definitions: Sequence[tuple[str, int, str]],
) -> None:
    handle.write(f"$scope module {_safe_name(scope)} $end\n")
    for identifier, width, name in definitions:
        handle.write(
            f"$var wire {width} {identifier} {_safe_name(name)} $end\n"
        )
    handle.write("$upscope $end\n")


def export_vcd(
    result: CaptureResult,
    path: Optional[str | Path] = None,
) -> Path:
    """导出 DDR/SDR VCD；不会重新运行 capture processing。"""
    output = Path(path) if path is not None else _output_path(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = result.raw_capture
    if raw.sample_rate <= 0:
        raise ValueError("VCD 导出要求 raw capture sample_rate 大于 0")

    definitions: dict[str, list[tuple[str, int, str]]] = {
        "capture": [],
        "extra": [],
        "debug": [],
    }
    sources: List[_EventSource] = []

    def add_array(scope: str, name: str, array: np.ndarray, width: int = 1) -> None:
        identifier = _identifier(len(sources))
        definitions[scope].append((identifier, width, name))
        sources.append(_array_source(identifier, array, width))

    def add_bus(scope: str, name: str, values: np.ndarray, indices: np.ndarray) -> None:
        identifier = _identifier(len(sources))
        width = result.config.bit_width
        definitions[scope].append((identifier, width, name))
        sources.append(
            _bus_source(
                identifier, values, indices, width, raw.sample_count
            )
        )

    if raw.clock is not None:
        add_array("capture", "clock", raw.clock)
    # VCD 使用 raw timeline，因此优先消费未降采样的 extra signals。
    extra_signals = raw.extra_signals or result.extra_signals
    for name, values in sorted(extra_signals.items()):
        add_array("extra", name, values)

    if result.is_iq:
        if result.data2 is None:
            raise ValueError("IQ CaptureResult 缺少 data2")
        add_bus("capture", "I_unsigned", result.data1, _sample_indices(result, "i"))
        add_bus("capture", "Q_unsigned", result.data2, _sample_indices(result, "q"))
    else:
        add_bus("capture", "data_unsigned", result.data1, _sample_indices(result, "data"))

    if result.config.include_debug_data:
        for channel, values in sorted(raw.channels.items()):
            add_array("debug", f"raw_ch{channel}", values)
        for channel, values in sorted(result.cleaned_channels.items()):
            add_array("debug", f"cleaned_ch{channel}", values)

    with output.open("w", encoding="ascii", newline="\n") as handle:
        handle.write("$date generated by BLE Studio $end\n")
        handle.write("$version ble_studio.logic_analyzer.vcd $end\n")
        handle.write("$timescale 1ps $end\n")
        handle.write(
            f"$comment raw_sample_rate_hz={raw.sample_rate:.12g}; "
            f"output_sample_rate_hz={result.sample_rate:.12g} $end\n"
        )
        for scope, scope_definitions in definitions.items():
            if scope_definitions:
                _write_scope(handle, scope, scope_definitions)
        handle.write("$enddefinitions $end\n")
        handle.write("$dumpvars\n")
        for source in sources:
            handle.write(
                _format_value(source.initial, source.width, source.identifier) + "\n"
            )
        handle.write("$end\n")

        heap: List[tuple[int, int, int]] = []
        for source_index, source in enumerate(sources):
            if len(source.indices):
                heapq.heappush(
                    heap, (int(source.indices[0]), source_index, 0)
                )

        last_time_ps = -1
        while heap:
            raw_index = heap[0][0]
            events: List[tuple[_EventSource, int]] = []
            while heap and heap[0][0] == raw_index:
                _, source_index, position = heapq.heappop(heap)
                source = sources[source_index]
                events.append((source, int(source.values[position])))
                next_position = position + 1
                if next_position < len(source.indices):
                    heapq.heappush(
                        heap,
                        (
                            int(source.indices[next_position]),
                            source_index,
                            next_position,
                        ),
                    )

            time_ps = int(round(raw_index * 1e12 / raw.sample_rate))
            if time_ps < last_time_ps:
                time_ps = last_time_ps
            if time_ps != last_time_ps:
                handle.write(f"#{time_ps}\n")
                last_time_ps = time_ps
            for source, value in events:
                handle.write(
                    _format_value(value, source.width, source.identifier) + "\n"
                )
    return output


__all__ = ["export_vcd"]
