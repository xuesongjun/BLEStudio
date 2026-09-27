"""逻辑分析仪数据恢复的统一编排 API。"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from .capture import load_capture
from .extraction import extract_data, unsigned_to_signed
from .models import CaptureResult, LogicAnalyzerConfig, RawCapture
from .processing import (
    adaptive_glitch_filter,
    analyze_eye_diagram,
    filter_data_spikes,
    filter_glitches,
    filter_iq_spikes,
)


def _default_edges(
    capture: RawCapture,
    config: LogicAnalyzerConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    if config.mode == "sdr":
        if not config.eye_align and np.isclose(config.sample_rate, config.data_rate):
            return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
        samples_per_word = config.sample_rate / config.data_rate
        word_count = int(capture.sample_count / samples_per_word)
        rising = np.array(
            [int(index * samples_per_word) for index in range(word_count)],
            dtype=np.int64,
        )
        return rising, np.array([], dtype=np.int64)

    if capture.clock is None:
        raise ValueError("DDR 模式需要时钟通道")
    clock_diff = np.diff(capture.clock.astype(np.int8))
    rising = np.where(clock_diff == 1)[0] + 1
    falling = np.where(clock_diff == -1)[0] + 1
    return rising, falling


def _run_adaptive_filter(
    channels: Dict[int, np.ndarray],
    capture: RawCapture,
    config: LogicAnalyzerConfig,
    rising_delays: Dict[int, int],
    falling_delays: Dict[int, int],
    rising_edges: np.ndarray,
    falling_edges: np.ndarray,
) -> Dict[int, np.ndarray]:
    if not config.adaptive_filter:
        return channels

    if capture.clock is None:
        clock = np.zeros(capture.sample_count, dtype=np.uint8)
    else:
        clock = capture.clock

    filtered = channels
    for round_index in range(5):
        previous = {channel: values.copy() for channel, values in filtered.items()}

        if config.mode == "sdr":
            filtered = adaptive_glitch_filter(
                filtered,
                clock,
                rising_edges,
                rising_delays,
                "数据",
                config,
            )
        else:
            rising_name = f"{config.rising_edge_data}路 (上升沿)"
            falling_name = f"{config.falling_edge_data}路 (下降沿)"
            filtered = adaptive_glitch_filter(
                filtered,
                clock,
                rising_edges,
                rising_delays,
                rising_name,
                config,
            )
            filtered = adaptive_glitch_filter(
                filtered,
                clock,
                falling_edges,
                falling_delays,
                falling_name,
                config,
            )

        changed = any(
            not np.array_equal(filtered[channel], previous[channel])
            for channel in filtered
        )
        if not changed:
            print(f"[自适应过滤] 第 {round_index + 1} 轮无改进，停止迭代")
            break

    return filtered


def _sample_extra_signals(
    capture: RawCapture,
    sample_info: dict,
    output_length: int,
    config: LogicAnalyzerConfig,
) -> Dict[str, np.ndarray]:
    if not capture.extra_signals:
        return {}

    if config.mode == "sdr":
        regular = sample_info.get("regular_sampling")
        if regular:
            start = int(regular.get("start", 0))
            step = int(regular.get("step", 1))
            count = min(int(regular.get("count", output_length)), output_length)
            return {
                name: values[start : start + count * step : step]
                for name, values in capture.extra_signals.items()
            }
        positions = np.asarray(sample_info.get("edges", []), dtype=np.int64)
    else:
        positions = np.asarray(sample_info.get("i_edges", []), dtype=np.int64)

    positions = positions[:output_length]
    return {
        name: values[positions]
        for name, values in capture.extra_signals.items()
        if len(positions) == 0 or positions[-1] < len(values)
    }


def process_capture(config: LogicAnalyzerConfig) -> CaptureResult:
    """运行一次无文件输出的逻辑分析仪恢复 pipeline。"""
    capture = load_capture(config)
    cleaned_channels = filter_glitches(capture, config)

    if config.eye_align:
        rising_delays, falling_delays, rising_edges, falling_edges = (
            analyze_eye_diagram(cleaned_channels, capture, config)
        )
    else:
        rising_delays = {channel: 0 for channel in config.data_bits}
        falling_delays = {channel: 0 for channel in config.data_bits}
        rising_edges, falling_edges = _default_edges(capture, config)

    cleaned_channels = _run_adaptive_filter(
        cleaned_channels,
        capture,
        config,
        rising_delays,
        falling_delays,
        rising_edges,
        falling_edges,
    )

    if config.adaptive_filter and config.eye_align:
        rising_delays, falling_delays, rising_edges, falling_edges = (
            analyze_eye_diagram(cleaned_channels, capture, config)
        )

    data1, data2, nominal_rate, measured_rate, sample_info = extract_data(
        cleaned_channels,
        capture,
        rising_delays,
        falling_delays,
        config,
        rising_edges,
        falling_edges,
    )

    if config.output_spike_filter:
        if data2 is None:
            data1 = filter_data_spikes(data1, config)
        else:
            data1, data2 = filter_iq_spikes(data1, data2, config)

    signed_data1 = unsigned_to_signed(data1, config.bit_width)
    signed_data2 = (
        unsigned_to_signed(data2, config.bit_width)
        if data2 is not None
        else None
    )

    sample_info = dict(sample_info)
    sample_info["rising_delays"] = dict(rising_delays)
    sample_info["falling_delays"] = dict(falling_delays)

    warnings = list(config.warnings)
    if measured_rate is not None and nominal_rate > 0:
        error_ppm = abs(measured_rate - nominal_rate) / nominal_rate * 1e6
        if error_ppm > 1000:
            warnings.append(
                "measured sample rate 与 nominal rate 偏差 "
                f"{error_ppm:.1f} ppm，请检查时钟 gap 或 data_rate 配置"
            )

    return CaptureResult(
        config=config,
        raw_capture=capture,
        cleaned_channels=cleaned_channels,
        data1=data1,
        data2=data2,
        signed_data1=signed_data1,
        signed_data2=signed_data2,
        sample_rate_nominal=nominal_rate,
        sample_rate_measured=measured_rate,
        sample_info=sample_info,
        extra_signals=_sample_extra_signals(
            capture,
            sample_info,
            len(data1),
            config,
        ),
        warnings=warnings,
    )
