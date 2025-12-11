"""
将逻辑分析仪 BIN 数据转换为 VCD 格式

VCD (Value Change Dump) 是标准的波形格式，可以用 GTKWave 等工具打开查看。

**重要**: 本脚本不做任何数据处理，只负责将 logic_analyzer_bin2wave.py
处理好的数据转换为 VCD 格式，确保 HTML 和 VCD 完全同步。

用法:
    python utils/bin_to_vcd.py utils/logic_analyzer_config.yaml
    python utils/bin_to_vcd.py template_data/test.bin  # 使用默认配置
"""

import numpy as np
import argparse
from pathlib import Path
from datetime import datetime

# 导入 logic_analyzer_bin2wave 中的函数
from logic_analyzer_bin2wave import (
    Config,
    load_config,
    create_default_config,
    load_binary_data,
    filter_glitches,
    analyze_eye_diagram,
    adaptive_glitch_filter,
    extract_data,
    unsigned_to_signed,
    plot_data,
)


def bin_to_vcd(config: Config, output_path: str):
    """
    将 BIN 文件转换为 VCD 格式

    数据处理完全复用 logic_analyzer_bin2wave.py 的逻辑，
    本函数只负责格式转换。
    """
    # === 1. 加载数据 ===
    print("=" * 60)
    print("Load Binary Data")
    print("=" * 60)
    data_dict, clk_array, n_samples = load_binary_data(config.input_file, config)

    # 保存原始数据 (用于 VCD 对比)
    raw_data_dict = {k: v.copy() for k, v in data_dict.items()}

    # === 2. 数据清洗 ===
    if config.glitch_filter:
        print("\n" + "=" * 60)
        print("Glitch Filter")
        print("=" * 60)
        data_dict = filter_glitches(data_dict, config, clk_array)

    # 保存清洗后的数据 (用于 VCD 对比)
    cleaned_data_dict = {k: v.copy() for k, v in data_dict.items()}

    # === 3. 眼图分析 ===
    if config.eye_align:
        print("\n" + "=" * 60)
        print("Eye Diagram Analysis")
        print("=" * 60)
        rising_delays, falling_delays, rising_edges, falling_edges = analyze_eye_diagram(
            data_dict, clk_array, config
        )
        print(f"\n[INFO] Rising edge delays: {rising_delays}")
        print(f"[INFO] Falling edge delays: {falling_delays}")

        # 自适应过滤
        if config.adaptive_filter:
            if config.rising_edge_data == "I":
                rising_name = "I (rising edge)"
                falling_name = "Q (falling edge)"
            else:
                rising_name = "Q (rising edge)"
                falling_name = "I (falling edge)"

            max_rounds = 5
            for round_num in range(max_rounds):
                prev_data_dict = {k: v.copy() for k, v in data_dict.items()}

                data_dict = adaptive_glitch_filter(
                    data_dict, clk_array, rising_edges, rising_delays,
                    rising_name, config
                )
                data_dict = adaptive_glitch_filter(
                    data_dict, clk_array, falling_edges, falling_delays,
                    falling_name, config
                )

                changed = any(not np.array_equal(data_dict[k], prev_data_dict[k])
                             for k in data_dict)

                if not changed:
                    print(f"\n[Adaptive] Round {round_num + 1}: No changes, stopping")
                    break

            # 重新眼图分析
            rising_delays, falling_delays, rising_edges, falling_edges = analyze_eye_diagram(
                data_dict, clk_array, config
            )
    else:
        rising_delays = {bit: 0 for bit in config.data_bits}
        falling_delays = {bit: 0 for bit in config.data_bits}
        clk_diff = np.diff(clk_array.astype(np.int8))
        rising_edges = np.where(clk_diff == 1)[0] + 1
        falling_edges = np.where(clk_diff == -1)[0] + 1

    # === 4. 提取 IQ 数据 (使用 logic_analyzer_bin2wave.py 的 extract_data) ===
    print("\n" + "=" * 60)
    print("Data Extraction")
    print("=" * 60)
    i_data, q_data, actual_sample_rate, sample_info = extract_data(
        data_dict, clk_array, rising_delays, falling_delays, config
    )

    # === 5. 生成 VCD 文件 ===
    print("\n" + "=" * 60)
    print("Generate VCD")
    print("=" * 60)

    # 从 sample_info 获取实际采样位置
    i_edges = sample_info['i_edges']
    q_edges = sample_info['q_edges']
    i_sample_positions = sample_info['i_sample_positions']  # 每个采样的 {bit_idx: position}
    q_sample_positions = sample_info['q_sample_positions']

    # 生成采样脉冲数组 - 直接使用 extract_data 返回的位置
    sample_pulses_i = {bit_idx: np.zeros(n_samples, dtype=np.uint8) for bit_idx in config.data_bits}

    for i, positions in enumerate(i_sample_positions):
        for bit_idx, pos in positions.items():
            if pos < n_samples:
                sample_pulses_i[bit_idx][pos] = 1

    # 统计采样位置
    print(f"[VCD] 使用 extract_data 返回的实际采样位置")
    for bit_idx in sorted(config.data_bits):
        offsets = []
        for i, positions in enumerate(i_sample_positions):
            if bit_idx in positions and i < len(i_edges):
                offsets.append(positions[bit_idx] - i_edges[i])
        if offsets:
            print(f"[VCD] smp{bit_idx}: 平均偏移 {np.mean(offsets):.1f}, 范围 [{min(offsets)}, {max(offsets)}]")

    # 生成 I/Q 采样时刻脉冲 (取各 bit 位置的最小值，即最早的)
    debug_i = np.zeros(n_samples, dtype=np.uint8)
    debug_q = np.zeros(n_samples, dtype=np.uint8)

    i_sample_times = []
    for positions in i_sample_positions:
        if positions:
            min_pos = min(positions.values())
            if min_pos < n_samples:
                debug_i[min_pos] = 1
                i_sample_times.append(min_pos)

    q_sample_times = []
    for positions in q_sample_positions:
        if positions:
            min_pos = min(positions.values())
            if min_pos < n_samples:
                debug_q[min_pos] = 1
                q_sample_times.append(min_pos)

    # 构建 IQ 时间到值的映射
    i_time_to_val = {}
    for i, sample_time in enumerate(i_sample_times):
        if i < len(i_data):
            i_time_to_val[sample_time] = int(i_data[i])

    q_time_to_val = {}
    for i, sample_time in enumerate(q_sample_times):
        if i < len(q_data):
            q_time_to_val[sample_time] = int(q_data[i])

    # 找到所有变化点
    all_changes = set([0])

    for ch in config.data_bits:
        diff = np.diff(raw_data_dict[ch].astype(np.int8))
        all_changes.update((np.where(diff != 0)[0] + 1).tolist())

        diff = np.diff(cleaned_data_dict[ch].astype(np.int8))
        all_changes.update((np.where(diff != 0)[0] + 1).tolist())

        diff = np.diff(sample_pulses_i[ch].astype(np.int8))
        all_changes.update((np.where(diff != 0)[0] + 1).tolist())

    diff = np.diff(clk_array.astype(np.int8))
    all_changes.update((np.where(diff != 0)[0] + 1).tolist())

    diff = np.diff(debug_i.astype(np.int8))
    all_changes.update((np.where(diff != 0)[0] + 1).tolist())

    diff = np.diff(debug_q.astype(np.int8))
    all_changes.update((np.where(diff != 0)[0] + 1).tolist())

    all_changes.update(i_time_to_val.keys())
    all_changes.update(q_time_to_val.keys())

    all_changes = sorted(all_changes)
    print(f"[VCD] Total change points: {len(all_changes)}")

    # VCD 符号分配
    raw_symbols = [chr(33 + i) for i in range(10)]
    cleaned_symbols = [chr(33 + 10 + i) for i in range(10)]
    smp_symbols = [chr(33 + 20 + i) for i in range(10)]
    sym_clk = chr(33 + 30)
    sym_sample_i = chr(33 + 31)
    sym_sample_q = chr(33 + 32)
    sym_I = chr(33 + 33)
    sym_Q = chr(33 + 34)

    timescale_ns = int(1e9 / config.sample_rate)

    with open(output_path, 'w') as f:
        # VCD 头部
        f.write(f"$date {datetime.now().isoformat()} $end\n")
        f.write(f"$version BIN to VCD converter $end\n")
        f.write(f"$timescale {timescale_ns}ns $end\n")

        # 分组定义
        f.write("$scope module raw $end\n")
        for i in range(10):
            f.write(f"$var wire 1 {raw_symbols[i]} data{i} $end\n")
        f.write(f"$var wire 1 {sym_clk} clk $end\n")
        f.write(f"$var wire 1 {sym_sample_i} sample_I $end\n")
        f.write(f"$var wire 1 {sym_sample_q} sample_Q $end\n")
        f.write("$upscope $end\n")

        f.write("$scope module cl $end\n")
        for i in range(10):
            f.write(f"$var wire 1 {cleaned_symbols[i]} data{i}_cl $end\n")
        f.write("$upscope $end\n")

        f.write("$scope module smp $end\n")
        for i in range(10):
            f.write(f"$var wire 1 {smp_symbols[i]} smp{i} $end\n")
        f.write("$upscope $end\n")

        f.write("$scope module iq $end\n")
        f.write(f"$var wire {config.bit_width} {sym_I} I_data[{config.bit_width-1}:0] $end\n")
        f.write(f"$var wire {config.bit_width} {sym_Q} Q_data[{config.bit_width-1}:0] $end\n")
        f.write("$upscope $end\n")

        f.write("$enddefinitions $end\n")
        f.write("$dumpvars\n")

        # 初始值
        for i, ch in enumerate(config.data_bits):
            f.write(f"{raw_data_dict[ch][0]}{raw_symbols[i]}\n")
        f.write(f"{clk_array[0]}{sym_clk}\n")
        f.write(f"{debug_i[0]}{sym_sample_i}\n")
        f.write(f"{debug_q[0]}{sym_sample_q}\n")

        for i, ch in enumerate(config.data_bits):
            f.write(f"{cleaned_data_dict[ch][0]}{cleaned_symbols[i]}\n")

        for i, ch in enumerate(config.data_bits):
            f.write(f"{sample_pulses_i[ch][0]}{smp_symbols[i]}\n")

        zero_bits = '0' * config.bit_width
        f.write(f"b{zero_bits} {sym_I}\n")
        f.write(f"b{zero_bits} {sym_Q}\n")
        f.write("$end\n")

        # 变化点
        prev_raw = {ch: raw_data_dict[ch][0] for ch in config.data_bits}
        prev_cleaned = {ch: cleaned_data_dict[ch][0] for ch in config.data_bits}
        prev_smp = {ch: sample_pulses_i[ch][0] for ch in config.data_bits}
        prev_clk = clk_array[0]
        prev_sample_i = debug_i[0]
        prev_sample_q = debug_q[0]
        prev_I = 0
        prev_Q = 0

        for t in all_changes[1:]:
            has_change = False
            output_lines = []

            for i, ch in enumerate(config.data_bits):
                if t < len(raw_data_dict[ch]):
                    val = raw_data_dict[ch][t]
                    if val != prev_raw[ch]:
                        output_lines.append(f"{val}{raw_symbols[i]}")
                        prev_raw[ch] = val
                        has_change = True

            for i, ch in enumerate(config.data_bits):
                if t < len(cleaned_data_dict[ch]):
                    val = cleaned_data_dict[ch][t]
                    if val != prev_cleaned[ch]:
                        output_lines.append(f"{val}{cleaned_symbols[i]}")
                        prev_cleaned[ch] = val
                        has_change = True

            for i, ch in enumerate(config.data_bits):
                if t < len(sample_pulses_i[ch]):
                    val = sample_pulses_i[ch][t]
                    if val != prev_smp[ch]:
                        output_lines.append(f"{val}{smp_symbols[i]}")
                        prev_smp[ch] = val
                        has_change = True

            if t < len(clk_array):
                val = clk_array[t]
                if val != prev_clk:
                    output_lines.append(f"{val}{sym_clk}")
                    prev_clk = val
                    has_change = True

            if t < len(debug_i):
                val = debug_i[t]
                if val != prev_sample_i:
                    output_lines.append(f"{val}{sym_sample_i}")
                    prev_sample_i = val
                    has_change = True

            if t < len(debug_q):
                val = debug_q[t]
                if val != prev_sample_q:
                    output_lines.append(f"{val}{sym_sample_q}")
                    prev_sample_q = val
                    has_change = True

            if t in i_time_to_val:
                val = i_time_to_val[t]
                if val != prev_I:
                    output_lines.append(f"b{val:0{config.bit_width}b} {sym_I}")
                    prev_I = val
                    has_change = True

            if t in q_time_to_val:
                val = q_time_to_val[t]
                if val != prev_Q:
                    output_lines.append(f"b{val:0{config.bit_width}b} {sym_Q}")
                    prev_Q = val
                    has_change = True

            if has_change:
                f.write(f"#{t}\n")
                for line in output_lines:
                    f.write(f"{line}\n")

    print(f"[OUTPUT] VCD: {output_path}")
    print(f"[INFO] I samples: {len(i_time_to_val)}, Q samples: {len(q_time_to_val)}")

    # === 6. 生成 HTML 图表 ===
    print("\n" + "=" * 60)
    print("Generate HTML")
    print("=" * 60)
    html_output_path = str(Path(output_path).with_suffix(''))
    orig_plot = config.plot
    orig_formats = config.save_formats
    config.plot = False
    config.save_formats = ["html"]
    plot_data(i_data, q_data, actual_sample_rate, config, html_output_path)
    config.plot = orig_plot
    config.save_formats = orig_formats


def main():
    parser = argparse.ArgumentParser(description='BIN to VCD converter')
    parser.add_argument('input', help='Config file (.yaml) or data file (.bin)')
    parser.add_argument('-o', '--output', help='Output VCD file')

    args = parser.parse_args()
    input_path = Path(args.input)

    if input_path.suffix.lower() in ['.yaml', '.yml']:
        config = load_config(args.input)
    elif input_path.suffix.lower() == '.bin':
        config = create_default_config(args.input)
    else:
        print(f"[ERROR] Unsupported file type: {input_path.suffix}")
        return

    if args.output is None:
        input_p = Path(config.input_file)
        args.output = str(input_p.parent / f"{input_p.stem}_debug.vcd")

    bin_to_vcd(config, args.output)


if __name__ == '__main__':
    main()
