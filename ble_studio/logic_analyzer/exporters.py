"""CaptureResult 的统一文件导出。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from .models import CaptureResult


def _output_path(result: CaptureResult, suffix: str) -> Path:
    result.config.output_dir.mkdir(parents=True, exist_ok=True)
    return result.config.output_dir / f"{result.config.output_stem}{suffix}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _array_summary(value: Any) -> Any:
    """为 summary 压缩大数组，只保留可诊断的结构信息。"""
    if isinstance(value, np.ndarray):
        summary: Dict[str, Any] = {
            "shape": list(value.shape),
            "dtype": str(value.dtype),
        }
        if value.size:
            if np.issubdtype(value.dtype, np.number):
                summary["min"] = _jsonable(np.min(value))
                summary["max"] = _jsonable(np.max(value))
            summary["first"] = _jsonable(value.reshape(-1)[:8])
        return summary
    if isinstance(value, dict):
        return {str(key): _array_summary(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 32:
            return {
                "length": len(value),
                "first": [_array_summary(item) for item in value[:4]],
            }
        return [_array_summary(item) for item in value]
    return _jsonable(value)


def build_summary(result: CaptureResult) -> Dict[str, Any]:
    """构建不包含全量采样数据的 JSON metadata。"""
    config = result.config
    measured = result.sample_rate_measured
    measured_error_ppm = None
    if measured is not None and result.sample_rate_nominal > 0:
        measured_error_ppm = (
            (measured - result.sample_rate_nominal)
            / result.sample_rate_nominal
            * 1e6
        )

    summary: Dict[str, Any] = {
        "schema": "ble_studio.logic_analyzer.capture.v1",
        "input_file": str(config.input_file),
        "output_base": str(config.output_base),
        "profile": config.profile,
        "mode": config.mode,
        "is_iq": result.is_iq,
        "sample_count": result.sample_count,
        "raw_sample_count": result.raw_capture.sample_count,
        "raw_sample_rate_hz": result.raw_capture.sample_rate,
        "sample_rate_hz": result.sample_rate,
        "sample_rate_nominal_hz": result.sample_rate_nominal,
        "sample_rate_measured_hz": measured,
        "sample_rate_error_ppm": measured_error_ppm,
        "bit_width": config.bit_width,
        "data_bits_lsb_first": list(config.data_bits),
        "clock_channel": config.clk_channel,
        "rising_edge_data": config.rising_edge_data,
        "falling_edge_data": config.falling_edge_data,
        "extra_signals": sorted(
            result.extra_signals or result.raw_capture.extra_signals
        ),
        "processing": {
            "eye_align": config.eye_align,
            "glitch_filter": config.glitch_filter,
            "adaptive_filter": config.adaptive_filter,
            "output_spike_filter": config.output_spike_filter,
        },
        "outputs_requested": list(config.save_formats),
        "max_plot_samples": config.max_plot_samples,
        "visualization": {
            "sampling_strategy": "uniform_index",
            "source_sample_count": result.sample_count,
            "plot_sample_count": min(result.sample_count, config.max_plot_samples),
        },
        "warnings": list(dict.fromkeys(config.warnings + result.warnings)),
        "sample_info": _array_summary(result.sample_info),
        "rx_result": _jsonable(result.rx_result),
    }
    if result.is_iq:
        summary["npy_semantics"] = "normalized_complex_iq"
        summary["mem_layout"] = "I in high bits, Q in low bits"
        summary["txt_layout"] = "two-column signed decimal I Q"
    else:
        summary["npy_semantics"] = "signed_parallel_samples"
        summary["mem_layout"] = "single signed word as two's-complement hex"
        summary["txt_layout"] = "single-column signed decimal"
    return summary


def export_summary_json(
    result: CaptureResult,
    path: Optional[str | Path] = None,
) -> Path:
    """写出结构化 summary，禁止嵌入全量采样。"""
    output = Path(path) if path is not None else _output_path(result, ".summary.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(build_summary(result), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return output


def export_rx_txt(
    result: CaptureResult,
    path: Optional[str | Path] = None,
) -> Path:
    """导出 IQImporter 可直接读取的两列 signed decimal TXT。"""
    output = Path(path) if path is not None else _output_path(result, ".txt")
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="ascii", newline="\n") as handle:
        handle.write("// BLE Studio RX-compatible samples\n")
        handle.write(f"// Mode: {result.config.mode}\n")
        handle.write(f"// Sample Rate: {result.sample_rate:.12g} Hz\n")
        handle.write(f"// Bit Width: {result.config.bit_width}\n")
        handle.write(f"// Samples: {result.sample_count}\n")
        if result.is_iq:
            handle.write("// Format: I_signed Q_signed\n")
            if result.signed_data2 is None:
                raise ValueError("IQ CaptureResult 缺少 signed_data2")
            for i_value, q_value in zip(result.signed_data1, result.signed_data2):
                handle.write(f"{int(i_value)} {int(q_value)}\n")
        else:
            handle.write("// Format: data_signed\n")
            for value in result.signed_data1:
                handle.write(f"{int(value)}\n")
    return output


def _position_text(positions: Any) -> str:
    if not isinstance(positions, dict):
        return ""
    return ";".join(
        f"{key}:{int(value)}"
        for key, value in sorted(positions.items(), key=lambda item: str(item[0]))
    )


def _sequence_item(sequence: Any, index: int, default: Any = "") -> Any:
    if isinstance(sequence, np.ndarray):
        return sequence[index] if index < len(sequence) else default
    if isinstance(sequence, (list, tuple)):
        return sequence[index] if index < len(sequence) else default
    return default


def export_debug_csv(
    result: CaptureResult,
    path: Optional[str | Path] = None,
) -> Path:
    """导出提取值、边沿和逐 bit 采样位置，供 deskew 诊断。"""
    output = Path(path) if path is not None else _output_path(result, ".debug.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    info = result.sample_info

    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if result.is_iq:
            header = [
                "index", "time_s", "I_unsigned", "Q_unsigned",
                "I_signed", "Q_signed", "I_edge", "Q_edge",
                "I_sample_positions", "Q_sample_positions",
            ]
            writer.writerow(header)
            if result.data2 is None or result.signed_data2 is None:
                raise ValueError("IQ CaptureResult 缺少 Q 数据")
            for index in range(result.sample_count):
                writer.writerow([
                    index,
                    f"{index / result.sample_rate:.15g}",
                    int(result.data1[index]),
                    int(result.data2[index]),
                    int(result.signed_data1[index]),
                    int(result.signed_data2[index]),
                    _sequence_item(info.get("i_edges"), index),
                    _sequence_item(info.get("q_edges"), index),
                    _position_text(_sequence_item(info.get("i_sample_positions"), index)),
                    _position_text(_sequence_item(info.get("q_sample_positions"), index)),
                ])
        else:
            writer.writerow([
                "index", "time_s", "data_unsigned", "data_signed",
                "edge", "sample_positions",
            ])
            for index in range(result.sample_count):
                writer.writerow([
                    index,
                    f"{index / result.sample_rate:.15g}",
                    int(result.data1[index]),
                    int(result.signed_data1[index]),
                    _sequence_item(info.get("edges"), index),
                    _position_text(_sequence_item(info.get("sample_positions"), index)),
                ])
    return output


def export_npy(
    result: CaptureResult,
    path: Optional[str | Path] = None,
) -> Path:
    """导出单一 canonical 数组：IQ 为 complex128，SDR 为 signed integer。"""
    output = Path(path) if path is not None else _output_path(result, ".npy")
    output.parent.mkdir(parents=True, exist_ok=True)
    data = result.iq if result.is_iq else result.signed_data1
    if data is None:
        raise ValueError("IQ CaptureResult 无法生成 normalized complex IQ")
    np.save(output, data)
    return output


def _sample_position_arrays(result: CaptureResult) -> Dict[str, np.ndarray]:
    """将逐 bit position dict 转成 MATLAB/NPZ 可稳定表示的矩阵。"""
    info = result.sample_info
    channels = list(result.config.data_bits)
    regular = info.get("regular_sampling")
    if regular:
        return {
            "sample_index_start": np.asarray([regular.get("start", 0)], dtype=np.int64),
            "sample_index_step": np.asarray([regular.get("step", 1)], dtype=np.int64),
            "sample_index_count": np.asarray(
                [regular.get("count", result.sample_count)], dtype=np.int64
            ),
        }

    def matrix(key: str) -> np.ndarray:
        values = info.get(key, [])
        output = np.full((result.sample_count, len(channels)), -1, dtype=np.int64)
        for row in range(min(result.sample_count, len(values))):
            positions = values[row]
            if not isinstance(positions, dict):
                continue
            for column, channel in enumerate(channels):
                value = positions.get(channel)
                if value is None:
                    value = positions.get(str(channel))
                if value is None:
                    value = positions.get(f"data{channel}")
                if value is not None:
                    output[row, column] = int(value)
        return output

    arrays: Dict[str, np.ndarray] = {}
    if result.is_iq:
        i_positions = matrix("i_sample_positions")
        q_positions = matrix("q_sample_positions")
        arrays["I_sample_positions"] = i_positions
        arrays["Q_sample_positions"] = q_positions
        arrays["sample_positions"] = np.stack([i_positions, q_positions], axis=0)
        arrays["I_edges"] = np.asarray(info.get("i_edges", []), dtype=np.int64)
        arrays["Q_edges"] = np.asarray(info.get("q_edges", []), dtype=np.int64)
    else:
        arrays["sample_positions"] = matrix("sample_positions")
        arrays["edges"] = np.asarray(info.get("edges", []), dtype=np.int64)
    return arrays


def _canonical_arrays(result: CaptureResult) -> Dict[str, Any]:
    measured = (
        float(result.sample_rate_measured)
        if result.sample_rate_measured is not None
        else np.nan
    )
    arrays: Dict[str, Any] = {
        "fs": float(result.sample_rate),
        "fs_nominal": float(result.sample_rate_nominal),
        "fs_measured": measured,
        "bit_width": int(result.config.bit_width),
        "data_bits_lsb_first": np.asarray(result.config.data_bits, dtype=np.int16),
    }
    arrays.update(_sample_position_arrays(result))

    if result.is_iq:
        if result.data2 is None or result.signed_data2 is None:
            raise ValueError("IQ CaptureResult 缺少 Q 数据")
        arrays.update({
            "iq": result.iq,
            "I_unsigned": result.data1,
            "Q_unsigned": result.data2,
            "I_raw": result.data1,
            "Q_raw": result.data2,
            "I_signed": result.signed_data1,
            "Q_signed": result.signed_data2,
        })
    else:
        arrays.update({
            "data_unsigned": result.data1,
            "data_raw": result.data1,
            "data_signed": result.signed_data1,
        })
    extra_signals = result.extra_signals or result.raw_capture.extra_signals
    for name, values in sorted(extra_signals.items()):
        safe_name = "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in name
        )
        arrays[f"extra_{safe_name or 'signal'}"] = np.asarray(values)
    return arrays


def export_npz(
    result: CaptureResult,
    path: Optional[str | Path] = None,
) -> Path:
    """导出 canonical 数组及 JSON metadata 的压缩归档。"""
    output = Path(path) if path is not None else _output_path(result, ".npz")
    output.parent.mkdir(parents=True, exist_ok=True)
    arrays = _canonical_arrays(result)
    arrays["metadata_json"] = json.dumps(
        build_summary(result), ensure_ascii=False, separators=(",", ":")
    )
    np.savez_compressed(output, **arrays)
    return output


def export_mat(
    result: CaptureResult,
    path: Optional[str | Path] = None,
) -> Path:
    """导出 BLE RX canonical MAT，包含 normalized IQ 和原始定点数据。"""
    try:
        from scipy.io import savemat
    except ImportError as exc:
        raise ImportError("导出 MAT 需要安装 scipy") from exc

    output = Path(path) if path is not None else _output_path(result, ".mat")
    output.parent.mkdir(parents=True, exist_ok=True)
    arrays = _canonical_arrays(result)
    arrays["metadata"] = json.dumps(build_summary(result), ensure_ascii=False)
    savemat(output, arrays, do_compression=True, long_field_names=True)
    return output


def export_mem(
    result: CaptureResult,
    path: Optional[str | Path] = None,
) -> Path:
    """导出 Verilog $readmemh；DDR 使用高 I、低 Q 的 packed word。"""
    output = Path(path) if path is not None else _output_path(result, ".mem")
    output.parent.mkdir(parents=True, exist_ok=True)
    width = result.config.bit_width
    mask = (1 << width) - 1

    with output.open("w", encoding="ascii", newline="\n") as handle:
        if result.is_iq:
            if result.data2 is None:
                raise ValueError("IQ CaptureResult 缺少 data2")
            total_width = width * 2
            digits = (total_width + 3) // 4
            for i_value, q_value in zip(result.data1, result.data2):
                packed = ((int(i_value) & mask) << width) | (int(q_value) & mask)
                handle.write(f"{packed:0{digits}X}\n")
        else:
            digits = (width + 3) // 4
            for value in result.data1:
                handle.write(f"{int(value) & mask:0{digits}X}\n")
    return output


def export_outputs(result: CaptureResult) -> Dict[str, Path]:
    """按配置导出所有格式；summary JSON 始终生成。"""
    outputs: Dict[str, Path] = {"json": export_summary_json(result)}
    requested = set(result.config.save_formats)

    exporters = {
        "txt": export_rx_txt,
        "csv": export_debug_csv,
        "npy": export_npy,
        "npz": export_npz,
        "mat": export_mat,
        "mem": export_mem,
    }
    for name, exporter in exporters.items():
        if name in requested:
            outputs[name] = exporter(result)

    if "vcd" in requested:
        from .vcd import export_vcd

        outputs["vcd"] = export_vcd(result)
    if "html" in requested:
        from .visualization import export_html

        outputs["html"] = export_html(result)
    return outputs


# 面向调用方保留直观别名。
export_capture = export_outputs
export_result = export_outputs


__all__ = [
    "build_summary",
    "export_capture",
    "export_debug_csv",
    "export_mat",
    "export_mem",
    "export_npy",
    "export_npz",
    "export_outputs",
    "export_result",
    "export_rx_txt",
    "export_summary_json",
]
