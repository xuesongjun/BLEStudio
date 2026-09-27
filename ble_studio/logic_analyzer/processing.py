"""逻辑分析仪数字通道的清洗、deskew 和输出毛刺过滤。"""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Tuple

import numpy as np

from .extraction import unsigned_to_signed
from .models import LogicAnalyzerConfig, RawCapture


ChannelData = Dict[int, np.ndarray]
DelayMap = Dict[int, int]
EyeAnalysisResult = Tuple[DelayMap, DelayMap, np.ndarray, np.ndarray]


def filter_glitches(
    capture: RawCapture,
    config: LogicAnalyzerConfig,
) -> ChannelData:
    """过滤短脉冲，并保留时钟边沿后前半周期内的候选有效脉冲。"""
    channels = capture.channels
    clock = capture.clock

    if not config.glitch_filter:
        return channels

    data_period_samples = config.sample_rate / config.data_rate
    min_pulse_width = int(data_period_samples * config.glitch_threshold)
    if min_pulse_width < 1:
        min_pulse_width = 1

    print(f"\n[数据清洗] 数据翻转周期: {data_period_samples:.1f} 采样点")
    print(
        f"[数据清洗] 毛刺阈值: < {min_pulse_width} 采样点 "
        f"(< {config.glitch_threshold * 100:.0f}% 数据周期)"
    )

    clock_rising_edges = None
    clock_falling_edges = None
    half_period = int(data_period_samples / 2)

    if clock is not None:
        clock_diff = np.diff(clock.astype(np.int8))
        clock_rising_edges = np.where(clock_diff == 1)[0] + 1
        clock_falling_edges = np.where(clock_diff == -1)[0] + 1
        print(
            "[数据清洗] 启用前半段保护: "
            f"时钟边沿后 {half_period} 采样点内的短脉冲不过滤"
        )

    def is_in_first_half(pulse_start: int, pulse_end: int) -> bool:
        if clock_rising_edges is None or clock_falling_edges is None:
            return False

        pulse_mid = (pulse_start + pulse_end) // 2
        for edge in clock_rising_edges:
            if edge <= pulse_mid < edge + half_period:
                return True
        for edge in clock_falling_edges:
            if edge <= pulse_mid < edge + half_period:
                return True
        return False

    filtered_channels: ChannelData = {}
    total_glitches = 0
    protected_count = 0

    for channel, data in channels.items():
        filtered_data = data.copy()
        glitch_count = 0
        channel_protected = 0

        for _ in range(100):
            edges = np.where(np.diff(filtered_data.astype(np.int8)) != 0)[0]
            if len(edges) < 2:
                break

            intervals = np.diff(edges)
            glitch_mask = intervals < min_pulse_width
            if not np.any(glitch_mask):
                break

            to_fix = []
            index = 0
            while index < len(glitch_mask):
                if glitch_mask[index]:
                    start_idx = int(edges[index])
                    end_idx = (
                        int(edges[index + 1])
                        if index + 1 < len(edges)
                        else len(filtered_data) - 1
                    )
                    if is_in_first_half(start_idx, end_idx):
                        channel_protected += 1
                        index += 2
                        continue

                    original_value = filtered_data[start_idx]
                    to_fix.append((start_idx, end_idx, original_value))
                    index += 2
                else:
                    index += 1

            if not to_fix:
                break

            for start_idx, end_idx, original_value in to_fix:
                filtered_data[start_idx + 1 : end_idx + 1] = original_value
                glitch_count += 1

        filtered_channels[channel] = filtered_data
        total_glitches += glitch_count
        protected_count += channel_protected

        if glitch_count > 0 or channel_protected > 0:
            message = f"[数据清洗] ch{channel}: 修复 {glitch_count} 个毛刺"
            if channel_protected > 0:
                message += f", 保护 {channel_protected} 个前半段脉冲"
            print(message)

    print(
        f"[数据清洗] 总计修复 {total_glitches} 个毛刺, "
        f"保护 {protected_count} 个前半段脉冲"
    )
    return filtered_channels


def adaptive_glitch_filter(
    channels: Mapping[int, np.ndarray],
    clock: Optional[np.ndarray],
    edges: np.ndarray,
    delays: Mapping[int, int],
    edge_name: str,
    config: LogicAnalyzerConfig,
    verbose: bool = False,
) -> ChannelData:
    """依据眼图采样位置，用局部多数表决修复不稳定数字通道。"""
    del clock, config  # 当前 baseline 保留参数但不参与判决。

    if len(edges) < 2:
        return dict(channels)

    half_period = int(np.median(np.diff(edges)))
    print(f"\n[自适应过滤] {edge_name}")
    print(f"[自适应过滤] 时钟半周期: {half_period} 采样点")

    filtered_channels: ChannelData = {}
    total_fixes = 0

    for bit_idx, data in channels.items():
        filtered_data = data.copy()
        delay = delays.get(bit_idx, 0)
        fixes = 0
        unstable_samples = []

        for index, edge in enumerate(edges):
            sample_idx = int(edge) + delay
            if sample_idx < 2 or sample_idx >= len(data) - 2:
                continue

            window = filtered_data[sample_idx - 2 : sample_idx + 3]
            value = filtered_data[sample_idx]
            same_count = np.sum(window == value)

            if same_count < 4:
                unstable_samples.append((index, sample_idx, same_count))
                start_idx = int(edge)
                end_idx = (
                    int(edges[index + 1])
                    if index + 1 < len(edges)
                    else int(edge) + half_period
                )
                end_idx = min(end_idx, len(filtered_data))

                segment = filtered_data[start_idx:end_idx]
                if len(segment) > 0:
                    ones = np.sum(segment)
                    zeros = len(segment) - ones
                    dominant_value = 1 if ones > zeros else 0
                    ratio = max(ones, zeros) / len(segment)
                    if ratio > 0.6:
                        for sample in range(start_idx, end_idx):
                            if filtered_data[sample] != dominant_value:
                                filtered_data[sample] = dominant_value
                                fixes += 1

        for index, edge in enumerate(edges):
            sample_idx = int(edge) + delay
            if sample_idx < 3 or sample_idx >= len(filtered_data) - 3:
                continue

            value = filtered_data[sample_idx]
            extended_window = filtered_data[sample_idx - 3 : sample_idx + 4]
            same_count = np.sum(extended_window == value)
            if same_count < 5:
                previous_index = index - 1 if index > 0 else 0
                next_index = index + 1 if index + 1 < len(edges) else index
                previous_sample = int(edges[previous_index]) + delay
                next_sample = int(edges[next_index]) + delay

                votes = []
                if 0 <= previous_sample < len(filtered_data) and previous_sample != sample_idx:
                    votes.append(filtered_data[previous_sample])
                if 0 <= next_sample < len(filtered_data) and next_sample != sample_idx:
                    votes.append(filtered_data[next_sample])

                if len(votes) >= 2 and votes[0] == votes[1] and votes[0] != value:
                    start_idx = int(edge)
                    end_idx = (
                        int(edges[index + 1])
                        if index + 1 < len(edges)
                        else int(edge) + half_period
                    )
                    end_idx = min(end_idx, len(filtered_data))
                    expected_value = votes[0]
                    for sample in range(start_idx, end_idx):
                        if filtered_data[sample] != expected_value:
                            filtered_data[sample] = expected_value
                            fixes += 1

        for edge in edges:
            sample_idx = int(edge) + delay
            if sample_idx < 1 or sample_idx >= len(filtered_data) - 1:
                continue

            previous_value = filtered_data[sample_idx - 1]
            current_value = filtered_data[sample_idx]
            next_value = filtered_data[sample_idx + 1]
            if not (previous_value == current_value == next_value):
                window_start = max(0, sample_idx - 4)
                window_end = min(len(filtered_data), sample_idx + 5)
                window = filtered_data[window_start:window_end]
                ones = np.sum(window)
                zeros = len(window) - ones
                dominant_value = 1 if ones > zeros else 0
                fix_start = max(0, sample_idx - 2)
                fix_end = min(len(filtered_data), sample_idx + 3)
                for sample in range(fix_start, fix_end):
                    if filtered_data[sample] != dominant_value:
                        filtered_data[sample] = dominant_value
                        fixes += 1

        filtered_channels[bit_idx] = filtered_data
        total_fixes += fixes
        if fixes > 0:
            print(f"[自适应过滤] data{bit_idx}: 修复 {fixes} 个采样点")
        if verbose and unstable_samples:
            print(
                f"[自适应过滤] data{bit_idx}: "
                f"发现 {len(unstable_samples)} 个不稳定采样位置"
            )

    print(f"[自适应过滤] {edge_name} 总计修复 {total_fixes} 个采样点")
    return filtered_channels


def analyze_eye_diagram(
    channels: Mapping[int, np.ndarray],
    capture: RawCapture,
    config: LogicAnalyzerConfig,
) -> EyeAnalysisResult:
    """为每个数据位分析上升沿和下降沿后的最佳采样延迟。"""
    if config.mode == "sdr":
        samples_per_bit = config.sample_rate / config.data_rate
        bit_count = int(capture.sample_count / samples_per_bit)
        rising_edges = np.array(
            [int(index * samples_per_bit) for index in range(bit_count)]
        )
        falling_edges = np.array([], dtype=np.int64)
        half_period_samples = int(samples_per_bit)
        half_period_ns = half_period_samples / config.sample_rate * 1e9
        print(
            "\n[眼图分析] SDR 模式 - 数据周期: "
            f"~{half_period_ns:.1f} ns ({half_period_samples} samples)"
        )
        print(f"[眼图分析] 生成 {len(rising_edges)} 个虚拟采样边沿")
    else:
        if capture.clock is None:
            raise ValueError("DDR 模式需要时钟通道")

        clock_diff = np.diff(capture.clock.astype(np.int8))
        rising_edges = np.where(clock_diff == 1)[0] + 1
        falling_edges = np.where(clock_diff == -1)[0] + 1
        all_edges = np.sort(np.concatenate([rising_edges, falling_edges]))
        if len(all_edges) < 2:
            print("[ERROR] 时钟边沿数量不足")
            empty = np.array([], dtype=np.int64)
            return {}, {}, empty, empty

        half_period_samples = int(np.median(np.diff(all_edges)))
        half_period_ns = half_period_samples / config.sample_rate * 1e9
        print(
            f"\n[眼图分析] 时钟半周期: ~{half_period_ns:.1f} ns "
            f"({half_period_samples} samples)"
        )
        print(
            f"[眼图分析] 检测到 {len(rising_edges)} 个上升沿, "
            f"{len(falling_edges)} 个下降沿"
        )

    actual_search_range = min(config.search_range, half_period_samples - 1)
    print(f"[眼图分析] 搜索范围: 边沿后 0 ~ {actual_search_range} 采样点")

    def analyze_edges(edges: np.ndarray, edge_name: str) -> DelayMap:
        delays: DelayMap = {}
        all_offset_scores: Dict[int, Dict[int, float]] = {}
        print(f"\n  === {edge_name} ===")

        for bit_idx in sorted(channels.keys()):
            data = channels[bit_idx]
            offset_scores: Dict[int, float] = {}
            for offset in range(actual_search_range):
                stable = 0
                total = 0
                for edge in edges:
                    sample_idx = int(edge) + offset
                    if sample_idx < 1 or sample_idx >= len(data) - 1:
                        continue
                    if data[sample_idx - 1] == data[sample_idx] == data[sample_idx + 1]:
                        stable += 1
                    total += 1
                if total > 0:
                    offset_scores[offset] = stable / total
            all_offset_scores[bit_idx] = offset_scores

        combined_scores: Dict[int, float] = {}
        for offset in range(actual_search_range):
            minimum_score = 1.0
            for bit_idx in channels.keys():
                minimum_score = min(
                    minimum_score,
                    all_offset_scores[bit_idx].get(offset, 0),
                )
            combined_scores[offset] = minimum_score

        base_offset = 0
        if combined_scores:
            best_combined_score = max(combined_scores.values())
            good_offsets = sorted(
                offset
                for offset, score in combined_scores.items()
                if score >= best_combined_score - 0.05
            )
            if good_offsets:
                regions = []
                current_region = [good_offsets[0]]
                for index in range(1, len(good_offsets)):
                    if good_offsets[index] == good_offsets[index - 1] + 1:
                        current_region.append(good_offsets[index])
                    else:
                        regions.append(current_region)
                        current_region = [good_offsets[index]]
                regions.append(current_region)

                first_region = regions[0]
                base_offset = first_region[len(first_region) // 2]
                if len(regions) > 1:
                    print(
                        f"  [最佳窗口] 发现 {len(regions)} 个稳定区域，选择第一个: "
                        f"偏移 {first_region[0]}-{first_region[-1]}, "
                        f"中心={base_offset}, 综合稳定性={best_combined_score * 100:.1f}%"
                    )
                else:
                    print(
                        f"  [最佳窗口] 偏移 {first_region[0]}-{first_region[-1]}, "
                        f"中心={base_offset}, 综合稳定性={best_combined_score * 100:.1f}%"
                    )

        for bit_idx in sorted(channels.keys()):
            offset_scores = all_offset_scores[bit_idx]
            if offset_scores:
                search_start = max(0, base_offset - 3)
                search_end = min(actual_search_range, base_offset + 4)
                best_offset = base_offset
                best_local_score = offset_scores.get(base_offset, 0)
                for offset in range(search_start, search_end):
                    score = offset_scores.get(offset, 0)
                    if score > best_local_score:
                        best_local_score = score
                        best_offset = offset
                delays[bit_idx] = best_offset

                eye_bar = ""
                for offset in range(actual_search_range):
                    score = offset_scores.get(offset, 0)
                    if score >= 0.95:
                        eye_bar += "#"
                    elif score >= 0.85:
                        eye_bar += "="
                    elif score >= 0.7:
                        eye_bar += "+"
                    elif score >= 0.5:
                        eye_bar += "-"
                    else:
                        eye_bar += " "
                print(
                    f"  data{bit_idx}: delay +{best_offset:2d}, "
                    f"stability {best_local_score * 100:.1f}%  |{eye_bar}|"
                )
            else:
                delays[bit_idx] = 0
                print(f"  data{bit_idx}: unable to analyze")
        return delays

    if config.mode == "sdr":
        rising_delays = analyze_edges(rising_edges, "数据边沿")
        return rising_delays, {}, rising_edges, falling_edges

    rising_name = f"上升沿 ({config.rising_edge_data})"
    falling_name = f"下降沿 ({config.falling_edge_data})"
    rising_delays = analyze_edges(rising_edges, rising_name)
    falling_delays = analyze_edges(falling_edges, falling_name)
    return rising_delays, falling_delays, rising_edges, falling_edges


def filter_iq_spikes(
    i_data: np.ndarray,
    q_data: np.ndarray,
    config: LogicAnalyzerConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    """修复 I/Q 中前后邻居一致的孤立尖刺。"""
    i_signed = unsigned_to_signed(i_data.copy(), config.bit_width)
    q_signed = unsigned_to_signed(q_data.copy(), config.bit_width)

    max_value = 1 << (config.bit_width - 1)
    threshold = max(int(max_value * 0.03), 15)
    print(f"[IQ过滤] 毛刺检测阈值: {threshold}")

    def fix_spikes(data: np.ndarray, name: str) -> np.ndarray:
        result = data.copy()
        total_fixed = 0
        for _ in range(10):
            fixed = 0
            for index in range(2, len(result) - 2):
                diff_previous = abs(result[index] - result[index - 1])
                diff_next = abs(result[index] - result[index + 1])
                neighbor_diff = abs(result[index - 1] - result[index + 1])
                neighbor_average = (result[index - 1] + result[index + 1]) // 2
                deviation = abs(result[index] - neighbor_average)
                if diff_previous > threshold and diff_next > threshold:
                    if neighbor_diff < threshold // 3 and deviation > threshold:
                        result[index] = neighbor_average
                        fixed += 1
            total_fixed += fixed
            if fixed == 0:
                break
        if total_fixed > 0:
            print(f"[IQ过滤] {name}: 修复 {total_fixed} 个毛刺")
        return result

    i_filtered = fix_spikes(i_signed, "I路")
    q_filtered = fix_spikes(q_signed, "Q路")
    i_filtered[i_filtered < 0] += 1 << config.bit_width
    q_filtered[q_filtered < 0] += 1 << config.bit_width
    return i_filtered.astype(np.uint16), q_filtered.astype(np.uint16)


def filter_data_spikes(
    data: np.ndarray,
    config: LogicAnalyzerConfig,
) -> np.ndarray:
    """修复单路并行数据中前后邻居一致的孤立尖刺。"""
    result = unsigned_to_signed(data.copy(), config.bit_width)
    max_value = 1 << (config.bit_width - 1)
    threshold = max(int(max_value * 0.03), 5)
    print(f"[数据过滤] 毛刺检测阈值: {threshold}")

    total_fixed = 0
    for _ in range(10):
        fixed = 0
        for index in range(2, len(result) - 2):
            diff_previous = abs(result[index] - result[index - 1])
            diff_next = abs(result[index] - result[index + 1])
            neighbor_diff = abs(result[index - 1] - result[index + 1])
            neighbor_average = (result[index - 1] + result[index + 1]) // 2
            deviation = abs(result[index] - neighbor_average)
            if diff_previous > threshold and diff_next > threshold:
                if neighbor_diff < threshold // 3 and deviation > threshold:
                    result[index] = neighbor_average
                    fixed += 1
        total_fixed += fixed
        if fixed == 0:
            break

    print(f"[数据过滤] 修复 {total_fixed} 个毛刺")
    result[result < 0] += 1 << config.bit_width
    return result.astype(np.uint16)
