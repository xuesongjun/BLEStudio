"""
将逻辑分析仪 BIN 数据转换为 VCD 格式

VCD (Value Change Dump) 是标准的波形格式，可以用 GTKWave 等工具打开查看。
同时支持添加调试脉冲和提取的 IQ 数据。

直接调用 logic_analyzer_bin2wave.py 的核心函数，确保 IQ 数据一致。

用法:
    python utils/bin_to_vcd.py utils/logic_analyzer_config.yaml -o output.vcd
    python utils/bin_to_vcd.py template_data/test.bin -o output.vcd  # 使用默认配置
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
    将 BIN 文件转换为 VCD 格式，使用与 logic_analyzer_bin2wave.py 相同的处理流程

    Args:
        config: 配置对象 (来自 YAML 或默认配置)
        output_path: 输出 VCD 文件路径
    """
    # === 1. 加载数据 (与 logic_analyzer_bin2wave.py 完全相同) ===
    print("=" * 60)
    print("Load Binary Data")
    print("=" * 60)
    data_dict, clk_array, n_samples = load_binary_data(config.input_file, config)

    # 保存原始数据 (用于 VCD 对比)
    raw_data_dict = {k: v.copy() for k, v in data_dict.items()}

    # === 2. 数据清洗 (与 logic_analyzer_bin2wave.py 完全相同) ===
    if config.glitch_filter:
        print("\n" + "=" * 60)
        print("Glitch Filter")
        print("=" * 60)
        data_dict = filter_glitches(data_dict, config)

    # 保存清洗后的数据 (用于 VCD 对比)
    cleaned_data_dict = {k: v.copy() for k, v in data_dict.items()}

    # === 3. 眼图分析 (与 logic_analyzer_bin2wave.py 完全相同) ===
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
            print("\n" + "=" * 60)
            print("Adaptive Glitch Filter")
            print("=" * 60)

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

                changed = False
                for k in data_dict:
                    if not np.array_equal(data_dict[k], prev_data_dict[k]):
                        changed = True
                        break

                if not changed:
                    print(f"\n[Adaptive] Round {round_num + 1}: No changes, stopping")
                    break
                else:
                    print(f"\n[Adaptive] Round {round_num + 1}: Complete, continuing...")

            # 重新眼图分析
            print("\n[Verify] Re-analyzing eye diagram...")
            rising_delays, falling_delays, rising_edges, falling_edges = analyze_eye_diagram(
                data_dict, clk_array, config
            )
            print(f"\n[INFO] Rising edge delays: {rising_delays}")
            print(f"[INFO] Falling edge delays: {falling_delays}")
    else:
        # 使用默认延迟
        rising_delays = {bit: 0 for bit in config.data_bits}
        falling_delays = {bit: 0 for bit in config.data_bits}
        # 计算边沿
        clk_diff = np.diff(clk_array.astype(np.int8))
        rising_edges = np.where(clk_diff == 1)[0] + 1
        falling_edges = np.where(clk_diff == -1)[0] + 1

    # === 4. 提取 IQ 数据 (与 logic_analyzer_bin2wave.py 完全相同) ===
    print("\n" + "=" * 60)
    print("Data Extraction")
    print("=" * 60)
    i_data, q_data, actual_sample_rate = extract_data(
        data_dict, clk_array, rising_delays, falling_delays, config
    )

    # 转换为有符号数
    i_signed = unsigned_to_signed(i_data, config.bit_width)
    q_signed = unsigned_to_signed(q_data, config.bit_width)

    # === 5. 生成 VCD 文件 ===
    print("\n" + "=" * 60)
    print("Generate VCD")
    print("=" * 60)

    # 根据配置决定 I/Q 对应的边沿
    if config.rising_edge_data == "I":
        i_edges, i_delays = rising_edges, rising_delays
        q_edges, q_delays = falling_edges, falling_delays
    else:
        q_edges, q_delays = rising_edges, rising_delays
        i_edges, i_delays = falling_edges, falling_delays

    # 计算平均延迟
    avg_i_delay = int(np.mean(list(i_delays.values())))
    avg_q_delay = int(np.mean(list(q_delays.values())))

    # 每个 bit 的采样脉冲 (在各自的 delay 位置)
    # sample_I[bit] 在 edge + i_delays[bit] 位置为 1
    sample_pulses = {bit_idx: np.zeros(n_samples, dtype=np.uint8) for bit_idx in config.data_bits}
    for edge in i_edges:
        for bit_idx in config.data_bits:
            delay = i_delays.get(bit_idx, 0)
            idx = edge + delay
            if idx < n_samples:
                sample_pulses[bit_idx][idx] = 1

    # 平均采样脉冲 (用于参考)
    debug_i = np.zeros(n_samples, dtype=np.uint8)
    debug_q = np.zeros(n_samples, dtype=np.uint8)

    for edge in i_edges:
        idx = edge + avg_i_delay
        if idx < n_samples:
            debug_i[idx] = 1

    for edge in q_edges:
        idx = edge + avg_q_delay
        if idx < n_samples:
            debug_q[idx] = 1

    print(f"[VCD] sample_I: edge + {avg_i_delay} (average)")
    print(f"[VCD] sample_Q: edge + {avg_q_delay} (average)")
    print(f"[VCD] smp0~smp9: per-bit sample pulses at edge + delay[bit]")

    # 构建 IQ 时间到值的映射 (无符号值用于 VCD)
    i_time_to_val = {}
    for i, edge in enumerate(i_edges):
        if edge + config.search_range < len(clk_array) and i < len(i_data):
            i_time_to_val[edge + avg_i_delay] = int(i_data[i])

    q_time_to_val = {}
    for i, edge in enumerate(q_edges):
        if edge + config.search_range < len(clk_array) and i < len(q_data):
            q_time_to_val[edge + avg_q_delay] = int(q_data[i])

    # 找到所有变化点
    all_changes = set([0])
    # 原始数据变化点
    for ch in config.data_bits:
        diff = np.diff(raw_data_dict[ch].astype(np.int8))
        change_points = np.where(diff != 0)[0] + 1
        all_changes.update(change_points.tolist())
    # 清洗后数据变化点
    for ch in config.data_bits:
        diff = np.diff(cleaned_data_dict[ch].astype(np.int8))
        change_points = np.where(diff != 0)[0] + 1
        all_changes.update(change_points.tolist())
    # 每个 bit 的采样脉冲变化点
    for ch in sample_pulses:
        diff = np.diff(sample_pulses[ch].astype(np.int8))
        change_points = np.where(diff != 0)[0] + 1
        all_changes.update(change_points.tolist())
    # 时钟变化点
    diff = np.diff(clk_array.astype(np.int8))
    change_points = np.where(diff != 0)[0] + 1
    all_changes.update(change_points.tolist())
    # 平均采样脉冲变化点
    diff = np.diff(debug_i.astype(np.int8))
    change_points = np.where(diff != 0)[0] + 1
    all_changes.update(change_points.tolist())
    diff = np.diff(debug_q.astype(np.int8))
    change_points = np.where(diff != 0)[0] + 1
    all_changes.update(change_points.tolist())

    # 添加 IQ 采样时刻
    all_changes.update(i_time_to_val.keys())
    all_changes.update(q_time_to_val.keys())

    all_changes = sorted(all_changes)
    print(f"[VCD] Total change points: {len(all_changes)}")

    # VCD 时基
    timescale_ns = int(1e9 / config.sample_rate)

    # VCD 符号分配 (使用 module 分组)
    # 0-9: 原始数据 data0~data9
    # 10-19: 清洗后数据 data0_cl~data9_cl
    # 20-29: 每个 bit 的采样脉冲 smp0~smp9
    # 30: clk
    # 31: sample_I (平均)
    # 32: sample_Q (平均)
    # 33: I_data
    # 34: Q_data
    raw_symbols = [chr(33 + i) for i in range(10)]
    cleaned_symbols = [chr(33 + 10 + i) for i in range(10)]
    smp_symbols = [chr(33 + 20 + i) for i in range(10)]
    sym_clk = chr(33 + 30)
    sym_sample_i = chr(33 + 31)
    sym_sample_q = chr(33 + 32)
    sym_I = chr(33 + 33)
    sym_Q = chr(33 + 34)

    with open(output_path, 'w') as f:
        # VCD 头部
        f.write(f"$date {datetime.now().isoformat()} $end\n")
        f.write(f"$version BIN to VCD converter (raw/cl/smp) $end\n")
        f.write(f"$timescale {timescale_ns}ns $end\n")

        # 原始数据分组 (raw)
        f.write("$scope module raw $end\n")
        for i in range(10):
            f.write(f"$var wire 1 {raw_symbols[i]} data{i} $end\n")
        f.write(f"$var wire 1 {sym_clk} clk $end\n")
        f.write(f"$var wire 1 {sym_sample_i} sample_I $end\n")
        f.write(f"$var wire 1 {sym_sample_q} sample_Q $end\n")
        f.write("$upscope $end\n")

        # 清洗后数据分组 (cl)
        f.write("$scope module cl $end\n")
        for i in range(10):
            f.write(f"$var wire 1 {cleaned_symbols[i]} data{i}_cl $end\n")
        f.write("$upscope $end\n")

        # 每个 bit 的采样脉冲分组 (smp)
        f.write("$scope module smp $end\n")
        for i in range(10):
            f.write(f"$var wire 1 {smp_symbols[i]} smp{i} $end\n")
        f.write("$upscope $end\n")

        # IQ 数据分组
        f.write("$scope module iq $end\n")
        f.write(f"$var wire {config.bit_width} {sym_I} I_data[{config.bit_width-1}:0] $end\n")
        f.write(f"$var wire {config.bit_width} {sym_Q} Q_data[{config.bit_width-1}:0] $end\n")
        f.write("$upscope $end\n")

        f.write("$enddefinitions $end\n")
        f.write("$dumpvars\n")

        # 初始值 - 原始数据
        for i, ch in enumerate(config.data_bits):
            f.write(f"{raw_data_dict[ch][0]}{raw_symbols[i]}\n")
        f.write(f"{clk_array[0]}{sym_clk}\n")
        f.write(f"{debug_i[0]}{sym_sample_i}\n")
        f.write(f"{debug_q[0]}{sym_sample_q}\n")

        # 初始值 - 清洗后数据
        for i, ch in enumerate(config.data_bits):
            f.write(f"{cleaned_data_dict[ch][0]}{cleaned_symbols[i]}\n")

        # 初始值 - 每个 bit 的采样脉冲
        for i, ch in enumerate(config.data_bits):
            f.write(f"{sample_pulses[ch][0]}{smp_symbols[i]}\n")

        # 初始值 - IQ
        zero_bits = '0' * config.bit_width
        f.write(f"b{zero_bits} {sym_I}\n")
        f.write(f"b{zero_bits} {sym_Q}\n")

        f.write("$end\n")

        # 变化点
        prev_raw = {ch: raw_data_dict[ch][0] for ch in config.data_bits}
        prev_cleaned = {ch: cleaned_data_dict[ch][0] for ch in config.data_bits}
        prev_smp = {ch: sample_pulses[ch][0] for ch in config.data_bits}
        prev_clk = clk_array[0]
        prev_sample_i = debug_i[0]
        prev_sample_q = debug_q[0]
        prev_I = 0
        prev_Q = 0

        for t in all_changes[1:]:
            has_change = False
            output_lines = []

            # 检查原始数据变化
            for i, ch in enumerate(config.data_bits):
                if t < len(raw_data_dict[ch]):
                    val = raw_data_dict[ch][t]
                    if val != prev_raw[ch]:
                        output_lines.append(f"{val}{raw_symbols[i]}")
                        prev_raw[ch] = val
                        has_change = True

            # 检查清洗后数据变化
            for i, ch in enumerate(config.data_bits):
                if t < len(cleaned_data_dict[ch]):
                    val = cleaned_data_dict[ch][t]
                    if val != prev_cleaned[ch]:
                        output_lines.append(f"{val}{cleaned_symbols[i]}")
                        prev_cleaned[ch] = val
                        has_change = True

            # 检查每个 bit 的采样脉冲变化
            for i, ch in enumerate(config.data_bits):
                if t < len(sample_pulses[ch]):
                    val = sample_pulses[ch][t]
                    if val != prev_smp[ch]:
                        output_lines.append(f"{val}{smp_symbols[i]}")
                        prev_smp[ch] = val
                        has_change = True

            # 检查时钟变化
            if t < len(clk_array):
                val = clk_array[t]
                if val != prev_clk:
                    output_lines.append(f"{val}{sym_clk}")
                    prev_clk = val
                    has_change = True

            # 检查平均采样脉冲变化
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

            # 检查 IQ 变化
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
    print(f"[INFO] Open with GTKWave")
    print(f"[INFO] Contains:")
    print(f"       - raw: 原始数据 (data0-9, clk, sample_I/Q)")
    print(f"       - cleaned: 清洗后数据 (data0-9)")
    print(f"       - delayed: 延迟调整后数据 (data0-9)")
    print(f"       - iq_data: I_data[{config.bit_width-1}:0], Q_data[{config.bit_width-1}:0]")
    print(f"[INFO] I samples: {len(i_time_to_val)}, Q samples: {len(q_time_to_val)}")

    # === 6. 生成 HTML 图表 (与 logic_analyzer_bin2wave.py 完全相同) ===
    print("\n" + "=" * 60)
    print("Generate HTML")
    print("=" * 60)
    html_output_path = str(Path(output_path).with_suffix(''))
    # 临时修改配置，只输出 HTML，不显示图表
    orig_plot = config.plot
    orig_formats = config.save_formats
    config.plot = False
    config.save_formats = ["html"]
    plot_data(i_data, q_data, actual_sample_rate, config, html_output_path)
    config.plot = orig_plot
    config.save_formats = orig_formats


def main():
    parser = argparse.ArgumentParser(
        description='BIN to VCD converter (uses logic_analyzer_bin2wave.py)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Use YAML config (same as logic_analyzer_bin2wave.py)
    python utils/bin_to_vcd.py utils/logic_analyzer_config.yaml -o output.vcd

    # Use BIN file with default config
    python utils/bin_to_vcd.py template_data/test.bin -o output.vcd
        """
    )
    parser.add_argument('input', help='Config file (.yaml) or data file (.bin)')
    parser.add_argument('-o', '--output', help='Output VCD file')

    args = parser.parse_args()

    input_path = Path(args.input)

    # 判断输入类型
    if input_path.suffix.lower() in ['.yaml', '.yml']:
        config = load_config(args.input)
    elif input_path.suffix.lower() == '.bin':
        config = create_default_config(args.input)
    else:
        print(f"[ERROR] Unsupported file type: {input_path.suffix}")
        print("        Supported: .yaml/.yml (config) or .bin (data)")
        return

    # 确定输出路径
    if args.output is None:
        input_p = Path(config.input_file)
        args.output = str(input_p.parent / f"{input_p.stem}_debug.vcd")

    bin_to_vcd(config, args.output)


if __name__ == '__main__':
    main()
