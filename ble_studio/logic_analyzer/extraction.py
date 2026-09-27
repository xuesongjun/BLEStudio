"""从清洗后的数字通道恢复 DDR IQ 或 SDR 并行数据。"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np

from .models import LogicAnalyzerConfig, RawCapture


ExtractionResult = Tuple[
    np.ndarray,
    Optional[np.ndarray],
    float,
    Optional[float],
    Dict[str, Any],
]


def _estimate_rate(edges: np.ndarray, sample_rate: float) -> Optional[float]:
    """用排除 burst gap 后的平均边沿周期估算采样率。"""
    if len(edges) < 2:
        return None

    intervals = np.diff(edges).astype(np.float64)
    median_interval = float(np.median(intervals))
    if median_interval <= 0:
        return None

    in_burst = intervals[intervals <= median_interval * 1.5]
    if len(in_burst) == 0:
        return None
    return float(sample_rate / np.mean(in_burst))


def unsigned_to_signed(data: np.ndarray, bit_width: int) -> np.ndarray:
    """将无符号整数按二进制补码转换为有符号整数。"""
    signed_data = data.astype(np.int32)
    max_val = 1 << (bit_width - 1)
    signed_data[signed_data >= max_val] -= 1 << bit_width
    return signed_data


def extract_data(
    channels: Mapping[int, np.ndarray],
    capture: RawCapture,
    rising_delays: Mapping[int, int],
    falling_delays: Mapping[int, int],
    config: LogicAnalyzerConfig,
    rising_edges: Optional[np.ndarray] = None,
    falling_edges: Optional[np.ndarray] = None,
) -> ExtractionResult:
    """从清洗后的通道数据恢复波形，并保留实际采样位置。"""
    clock = capture.clock

    # 原始 SDR profile 是一采样一 word，不需要构造数百万个 edge/position dict。
    if (
        config.mode == "sdr"
        and not config.eye_align
        and np.isclose(config.sample_rate, config.data_rate)
    ):
        data = np.zeros(capture.sample_count, dtype=np.uint16)
        for bit_position, bit_idx in enumerate(config.data_bits):
            data |= channels[bit_idx].astype(np.uint16) << bit_position
        sample_info = {
            "regular_sampling": {
                "start": 0,
                "step": 1,
                "count": int(capture.sample_count),
            }
        }
        print(f"[INFO] 检测到 {len(data)} 个规则 SDR 采样点")
        print(f"[INFO] 采样率: {config.data_rate / 1e6:.3f} MHz")
        return data, None, config.data_rate, config.sample_rate, sample_info

    if config.mode == "sdr":
        if rising_edges is None or len(rising_edges) == 0:
            print("[ERROR] SDR 模式需要提供采样边沿")
            return np.array([]), None, config.data_rate, None, {}

        edges = rising_edges
        delays = rising_delays
    else:
        if clock is None:
            raise ValueError("DDR 模式需要时钟通道")

        clock_diff = np.diff(clock.astype(np.int8))
        rising_edges = np.where(clock_diff == 1)[0] + 1
        falling_edges = np.where(clock_diff == -1)[0] + 1

    def extract_value(
        edge_idx: int,
        delays: Mapping[int, int],
        next_edge_idx: Optional[int] = None,
        prev_values: Optional[Mapping[int, int]] = None,
    ) -> Tuple[int, Dict[int, int]]:
        """按眼图延迟提取一个并行采样值。"""
        del prev_values  # 保留兼容参数，当前 baseline 不使用历史值。

        value = 0
        sample_positions: Dict[int, int] = {}

        if next_edge_idx is None:
            avg_delay = int(np.mean(list(delays.values()))) if delays else 8
            period_end = edge_idx + avg_delay + 5
        else:
            period_end = next_edge_idx

        for bit_idx in config.data_bits:
            if bit_idx not in channels:
                continue

            data = channels[bit_idx]
            delay = delays.get(bit_idx, 0)
            default_sample_idx = edge_idx + delay

            if default_sample_idx >= len(data):
                continue

            search_end = min(period_end, len(data) - 1)

            # 保留当前采样规则：眼图最佳延迟是最终采样位置。
            # 这些上下文值暂不参与判决，后续算法变更需由 characterization test 驱动。
            before_edge_val = int(data[edge_idx - 1]) if edge_idx > 0 else None
            start_val = int(data[edge_idx])
            transitions = []
            for index in range(edge_idx, search_end - 1):
                if int(data[index]) != int(data[index + 1]):
                    transitions.append(index + 1)
            del before_edge_val, start_val, transitions

            bit_val = int(data[default_sample_idx])
            bit_position = config.data_bits.index(bit_idx)
            value |= bit_val << bit_position
            sample_positions[bit_idx] = default_sample_idx

        return value, sample_positions

    if config.mode == "ddr":
        assert rising_edges is not None
        assert falling_edges is not None
        assert clock is not None

        if config.rising_edge_data == "I":
            i_edges, i_delays = rising_edges, rising_delays
            q_edges, q_delays = falling_edges, falling_delays
        else:
            q_edges, q_delays = rising_edges, rising_delays
            i_edges, i_delays = falling_edges, falling_delays

        print(
            f"[INFO] 检测到 {len(i_edges)} 个 I 采样点, "
            f"{len(q_edges)} 个 Q 采样点"
        )

        all_edges_sorted = np.sort(np.concatenate([rising_edges, falling_edges]))

        def get_next_edge(edge_idx: int) -> Optional[int]:
            position = np.searchsorted(all_edges_sorted, edge_idx, side="right")
            if position < len(all_edges_sorted):
                return int(all_edges_sorted[position])
            return None

        i_values = []
        i_sample_positions = []
        prev_i_bits: Dict[int, int] = {}
        for edge_idx in i_edges:
            if edge_idx + config.search_range < len(clock):
                value, positions = extract_value(
                    int(edge_idx), i_delays, get_next_edge(int(edge_idx)), prev_i_bits
                )
                i_values.append(value)
                i_sample_positions.append(positions)
                for bit_idx in config.data_bits:
                    if bit_idx in positions:
                        prev_i_bits[bit_idx] = int(
                            channels[bit_idx][positions[bit_idx]]
                        )

        q_values = []
        q_sample_positions = []
        prev_q_bits: Dict[int, int] = {}
        for edge_idx in q_edges:
            if edge_idx + config.search_range < len(clock):
                value, positions = extract_value(
                    int(edge_idx), q_delays, get_next_edge(int(edge_idx)), prev_q_bits
                )
                q_values.append(value)
                q_sample_positions.append(positions)
                for bit_idx in config.data_bits:
                    if bit_idx in positions:
                        prev_q_bits[bit_idx] = int(
                            channels[bit_idx][positions[bit_idx]]
                        )

        sample_count = min(len(i_values), len(q_values))
        i_data = np.array(i_values[:sample_count], dtype=np.uint16)
        q_data = np.array(q_values[:sample_count], dtype=np.uint16)
        i_sample_positions = i_sample_positions[:sample_count]
        q_sample_positions = q_sample_positions[:sample_count]

        nominal_sample_rate = config.data_rate / 2
        measured_sample_rate = None
        if len(rising_edges) >= 2:
            measured_sample_rate = _estimate_rate(rising_edges, capture.sample_rate)
        if measured_sample_rate is not None:
            print(
                "[INFO] 测量时钟频率: "
                f"{measured_sample_rate / 1e6:.3f} MHz (上升沿)"
            )

        display_sample_rate = measured_sample_rate or nominal_sample_rate
        print(f"[INFO] IQ 采样率: {display_sample_rate / 1e6:.3f} MHz")
        print(f"[INFO] 提取 {sample_count} 个 IQ 采样点")

        sample_info = {
            "i_edges": i_edges[:sample_count],
            "q_edges": q_edges[:sample_count],
            "i_sample_positions": i_sample_positions,
            "q_sample_positions": q_sample_positions,
        }
        return (
            i_data,
            q_data,
            nominal_sample_rate,
            measured_sample_rate,
            sample_info,
        )

    print(f"[INFO] 检测到 {len(edges)} 个采样点")
    all_edges_sorted = edges

    def get_next_sdr_edge(edge_idx: int) -> Optional[int]:
        position = np.searchsorted(all_edges_sorted, edge_idx, side="right")
        if position < len(all_edges_sorted):
            return int(all_edges_sorted[position])
        return None

    values = []
    sample_positions = []
    prev_bits: Dict[int, int] = {}
    extraction_margin = config.search_range if config.eye_align else 0
    for edge_idx in edges:
        if edge_idx + extraction_margin < capture.sample_count:
            value, positions = extract_value(
                int(edge_idx),
                delays,
                get_next_sdr_edge(int(edge_idx)),
                prev_bits,
            )
            values.append(value)
            sample_positions.append(positions)
            for bit_idx in config.data_bits:
                if bit_idx in positions:
                    prev_bits[bit_idx] = int(channels[bit_idx][positions[bit_idx]])

    data = np.array(values, dtype=np.uint16)
    nominal_sample_rate = config.data_rate
    measured_sample_rate = None
    if len(edges) >= 2:
        measured_sample_rate = _estimate_rate(edges, capture.sample_rate)

    display_sample_rate = measured_sample_rate or nominal_sample_rate
    print(f"[INFO] 采样率: {display_sample_rate / 1e6:.3f} MHz")
    print(f"[INFO] 提取 {len(data)} 个采样点")

    sample_info = {
        "edges": edges[: len(data)],
        "sample_positions": sample_positions,
    }
    return data, None, nominal_sample_rate, measured_sample_rate, sample_info
