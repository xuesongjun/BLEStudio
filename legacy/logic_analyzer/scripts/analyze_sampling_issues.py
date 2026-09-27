#!/usr/bin/env python3
"""
分析 I 路采样不稳定的具体位置

找出哪些边沿的采样不稳定，以便在 VCD 中定位问题
"""

import numpy as np
import sys
sys.path.insert(0, '.')

from utils.logic_analyzer_bin2wave import (
    Config,
    load_config,
    load_binary_data,
    filter_glitches,
)


def analyze_sampling_issues(config_path: str):
    """分析采样不稳定的位置"""

    # 加载配置和数据
    config = load_config(config_path)
    data_dict, clk_array, n_samples = load_binary_data(config.input_file, config)

    # 数据清洗
    if config.glitch_filter:
        data_dict = filter_glitches(data_dict, config, clk_array)

    # 找到时钟边沿
    clk_diff = np.diff(clk_array.astype(np.int8))
    rising_edges = np.where(clk_diff == 1)[0] + 1
    falling_edges = np.where(clk_diff == -1)[0] + 1

    print(f"总共 {len(rising_edges)} 个上升沿 (I), {len(falling_edges)} 个下降沿 (Q)")

    # 分析上升沿 (I 路)
    # 使用最新的延迟配置
    i_delays = {0: 3, 1: 10, 2: 10, 3: 10, 4: 9, 5: 2, 6: 10, 7: 10, 8: 11, 9: 11}

    print("\n" + "=" * 60)
    print("分析 I 路采样不稳定位置")
    print("=" * 60)

    # 统计每个边沿的不稳定 bit 数量
    unstable_edges = []

    for edge_idx, edge in enumerate(rising_edges):
        unstable_bits = []

        for bit_idx in sorted(data_dict.keys()):
            data = data_dict[bit_idx]
            delay = i_delays.get(bit_idx, 10)
            sample_idx = edge + delay

            if sample_idx < 1 or sample_idx >= len(data) - 1:
                continue

            # 检查稳定性
            if not (data[sample_idx - 1] == data[sample_idx] == data[sample_idx + 1]):
                unstable_bits.append(bit_idx)

        if unstable_bits:
            unstable_edges.append((edge_idx, edge, unstable_bits))

    print(f"\n不稳定边沿数量: {len(unstable_edges)} / {len(rising_edges)} ({100*len(unstable_edges)/len(rising_edges):.2f}%)")

    # 显示前 20 个不稳定边沿
    print("\n前 20 个不稳定边沿:")
    print("-" * 60)
    for i, (edge_idx, edge, unstable_bits) in enumerate(unstable_edges[:20]):
        time_ns = edge * 2  # 500MHz = 2ns per sample
        print(f"  边沿 #{edge_idx}: 采样点 {edge}, 时间 {time_ns} ns, 不稳定 bit: {unstable_bits}")

    # 统计每个 bit 的不稳定次数
    print("\n每个 bit 的不稳定次数:")
    print("-" * 60)
    bit_unstable_count = {i: 0 for i in range(10)}
    for _, _, unstable_bits in unstable_edges:
        for bit in unstable_bits:
            bit_unstable_count[bit] += 1

    for bit, count in sorted(bit_unstable_count.items()):
        pct = 100 * count / len(rising_edges)
        bar = "#" * int(pct * 2)
        print(f"  data{bit}: {count:4d} 次 ({pct:.2f}%)  |{bar}|")

    # 分析不稳定边沿的模式
    print("\n" + "=" * 60)
    print("分析不稳定模式")
    print("=" * 60)

    # 检查不稳定边沿是否有规律（比如周期性）
    if len(unstable_edges) >= 2:
        intervals = []
        for i in range(1, min(100, len(unstable_edges))):
            interval = unstable_edges[i][0] - unstable_edges[i-1][0]
            intervals.append(interval)

        if intervals:
            avg_interval = np.mean(intervals)
            std_interval = np.std(intervals)
            print(f"不稳定边沿间隔: 平均 {avg_interval:.1f}, 标准差 {std_interval:.1f}")

            # 检查是否周期性
            common_intervals = {}
            for interval in intervals:
                common_intervals[interval] = common_intervals.get(interval, 0) + 1

            print("\n常见间隔:")
            for interval, count in sorted(common_intervals.items(), key=lambda x: -x[1])[:5]:
                print(f"  间隔 {interval}: {count} 次")

    # 详细分析最不稳定的 bit (data0)
    print("\n" + "=" * 60)
    print("详细分析 data0 (最不稳定)")
    print("=" * 60)

    data0 = data_dict[0]
    delay0 = i_delays[0]

    unstable_data0 = []
    for edge_idx, edge in enumerate(rising_edges):
        sample_idx = edge + delay0
        if sample_idx < 1 or sample_idx >= len(data0) - 1:
            continue

        v_prev = data0[sample_idx - 1]
        v_curr = data0[sample_idx]
        v_next = data0[sample_idx + 1]

        if not (v_prev == v_curr == v_next):
            # 记录详细信息
            pattern = f"{v_prev}{v_curr}{v_next}"
            unstable_data0.append((edge_idx, edge, sample_idx, pattern))

    print(f"data0 不稳定采样: {len(unstable_data0)} 次")

    # 统计不稳定模式
    pattern_counts = {}
    for _, _, _, pattern in unstable_data0:
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

    print("\n不稳定模式统计:")
    for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        desc = ""
        if pattern == "010":
            desc = "(0→1→0 毛刺)"
        elif pattern == "101":
            desc = "(1→0→1 毛刺)"
        elif pattern == "001":
            desc = "(上升沿)"
        elif pattern == "110":
            desc = "(下降沿)"
        elif pattern == "011":
            desc = "(上升沿后)"
        elif pattern == "100":
            desc = "(下降沿后)"
        print(f"  {pattern}: {count} 次 {desc}")

    # 输出前 10 个不稳定位置的详细信息
    print("\n前 10 个 data0 不稳定位置:")
    for i, (edge_idx, edge, sample_idx, pattern) in enumerate(unstable_data0[:10]):
        time_ns = sample_idx * 2
        print(f"  边沿 #{edge_idx}: 采样点 {sample_idx}, 时间 {time_ns} ns, 模式 {pattern}")

        # 显示更多上下文
        start = max(0, sample_idx - 5)
        end = min(len(data0), sample_idx + 6)
        context = "".join(str(data0[j]) for j in range(start, end))
        marker = " " * (sample_idx - start) + "^"
        print(f"        数据: {context}")
        print(f"              {marker}")

    # 检查 clk 和 data0 的相位关系
    print("\n" + "=" * 60)
    print("分析时钟与数据的相位关系")
    print("=" * 60)

    # 对于每个不稳定位置，检查时钟边沿前后数据的变化
    edge_to_data_delay = []
    for edge_idx, edge in enumerate(rising_edges[:1000]):  # 只分析前 1000 个
        # 找到数据翻转的位置
        for offset in range(-5, 16):
            idx = edge + offset
            if idx < 1 or idx >= len(data0):
                continue
            if data0[idx] != data0[idx - 1]:
                edge_to_data_delay.append(offset)
                break

    if edge_to_data_delay:
        delay_counts = {}
        for d in edge_to_data_delay:
            delay_counts[d] = delay_counts.get(d, 0) + 1

        print("时钟边沿到 data0 翻转的延迟分布:")
        for d in sorted(delay_counts.keys()):
            count = delay_counts[d]
            pct = 100 * count / len(edge_to_data_delay)
            bar = "#" * int(pct)
            print(f"  +{d:2d}: {count:4d} ({pct:5.1f}%)  |{bar}|")


if __name__ == '__main__':
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'utils/logic_analyzer_config.yaml'
    analyze_sampling_issues(config_path)
