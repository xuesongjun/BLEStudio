"""
逻辑分析仪采样数据转 IQ 数据工具

将逻辑分析仪采样得到的并行数据恢复成 IQ 数据。
- clk 上升沿采样 I 路数据 (或 Q，取决于 --iq-swap)
- clk 下降沿采样 Q 路数据 (或 I，取决于 --iq-swap)

由于逻辑分析仪各通道存在时序偏差，支持对每个通道进行延迟调整。

文件格式:
- BIN: 16通道二进制格式 (每2字节存储16通道，低字节=ch0-7，高字节=ch8-15)

用法:
    python utils/logic_analyzer_to_iq.py <input_file.bin> [options]

示例:
    python utils/logic_analyzer_to_iq.py test.bin --sample-rate 500e6 --eye-align
    python utils/logic_analyzer_to_iq.py test.bin --eye-align --iq-swap
"""

import argparse
import numpy as np
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_binary_data(file_path: str, sample_rate: float = 500e6) -> tuple:
    """
    加载逻辑分析仪二进制数据

    BIN文件格式 (16通道):
    - 每2字节存储一次采样的16个通道
    - 第1字节: 通道0-7 (低位=通道0)
    - 第2字节: 通道8-15 (低位=通道8)

    Args:
        file_path: 二进制文件路径
        sample_rate: 采样率 (Hz)

    Returns:
        (data_dict, clk_array, bit_width): 数据字典, 时钟数组, 位宽
    """
    with open(file_path, 'rb') as f:
        raw_data = f.read()

    n_samples = len(raw_data) // 2
    print(f"[INFO] 读取 {n_samples} 个采样点 (采样率 {sample_rate/1e6:.1f} MHz)")

    # 解析二进制数据
    data = np.frombuffer(raw_data, dtype=np.uint8).reshape(-1, 2)

    # 提取各通道 (通道0-7在第一字节，通道8-15在第二字节)
    low_byte = data[:, 0]   # ch0-7
    high_byte = data[:, 1]  # ch8-15

    # 创建数据字典
    data_dict = {}
    for ch in range(10):  # data0-data9
        if ch < 8:
            data_dict[ch] = (low_byte >> ch) & 1
        else:
            data_dict[ch] = (high_byte >> (ch - 8)) & 1

    # 时钟在通道10
    clk_array = (high_byte >> 2) & 1  # ch10 = high_byte bit2

    print(f"[INFO] 数据位宽: 10 (data0-data9)")
    print(f"[INFO] 时钟通道: ch10")

    # 计算时间信息
    duration = n_samples / sample_rate
    print(f"[INFO] 采样时长: {duration*1e6:.1f} us")

    return data_dict, clk_array, 10, sample_rate


def analyze_eye_diagram(data_dict: dict, clk_array: np.ndarray,
                        sample_rate: float, search_range: int = 15,
                        plot_eye: bool = False, iq_swap: bool = False) -> tuple:
    """
    基于眼图分析找到每路数据的最佳采样延迟

    原理: 在时钟边沿后的一段时间内，找到数据最稳定的位置 (眼睛张开最大处)

    注意: I 和 Q 分别在上升沿和下降沿采样，需要分别分析最佳延迟

    Args:
        data_dict: 数据字典 {bit_idx: data_array}
        clk_array: 时钟数组
        sample_rate: 采样率 (Hz)
        search_range: 搜索范围 (采样点)
        plot_eye: 是否绘制眼图
        iq_swap: 是否交换IQ (True: 上升沿->Q, 下降沿->I)

    Returns:
        (i_delays, q_delays): I 和 Q 的最佳延迟字典
    """
    clk_diff = np.diff(clk_array.astype(np.int8))

    # 找到上升沿和下降沿
    rising_edges = np.where(clk_diff == 1)[0] + 1
    falling_edges = np.where(clk_diff == -1)[0] + 1
    all_edges = np.sort(np.concatenate([rising_edges, falling_edges]))

    if len(all_edges) < 2:
        print("[ERROR] 时钟边沿数量不足")
        return {}, {}

    # 计算时钟半周期
    edge_intervals = np.diff(all_edges)
    half_period_samples = int(np.median(edge_intervals))
    half_period_ns = half_period_samples / sample_rate * 1e9

    print(f"\n[眼图分析] 时钟半周期: ~{half_period_ns:.1f} ns ({half_period_samples} samples)")
    print(f"[眼图分析] 检测到 {len(rising_edges)} 个上升沿, {len(falling_edges)} 个下降沿")

    # 限制搜索范围不超过半周期
    actual_search_range = min(search_range, half_period_samples - 1)
    print(f"[眼图分析] 搜索范围: 边沿后 0 ~ {actual_search_range} 采样点")

    # 分别对上升沿和下降沿进行分析
    def analyze_edges(edges, edge_name):
        """对指定边沿进行眼图分析"""
        delays = {'clk': 0}

        print(f"\n  === {edge_name} ===")

        for bit_idx in sorted(data_dict.keys()):
            data = data_dict[bit_idx]

            # 统计每个偏移位置的数据稳定性
            offset_scores = {}

            for offset in range(0, actual_search_range):
                stable = 0
                total = 0

                for edge in edges:
                    sample_idx = edge + offset
                    if sample_idx < 1 or sample_idx >= len(data) - 1:
                        continue

                    # 检查该位置数据与相邻位置是否一致 (稳定)
                    if data[sample_idx - 1] == data[sample_idx] == data[sample_idx + 1]:
                        stable += 1
                    total += 1

                if total > 0:
                    offset_scores[offset] = stable / total

            # 找最佳偏移 (选择第一个稳定区域的中心)
            if offset_scores:
                best_score = max(offset_scores.values())
                # 找出所有达到最高稳定性的偏移
                best_offsets = sorted([off for off, score in offset_scores.items()
                                      if score >= best_score - 0.001])

                # 找第一个连续区域
                first_region = [best_offsets[0]]
                for i in range(1, len(best_offsets)):
                    if best_offsets[i] == best_offsets[i-1] + 1:
                        first_region.append(best_offsets[i])
                    else:
                        break  # 遇到不连续的，停止

                # 选择第一个连续区域的中心
                best_offset = first_region[len(first_region) // 2]
                delays[f'data{bit_idx}'] = best_offset

                # ASCII 眼图
                bar = ""
                for off in range(actual_search_range):
                    score = offset_scores.get(off, 0)
                    if score >= 0.95:
                        bar += "#"
                    elif score >= 0.85:
                        bar += "="
                    elif score >= 0.7:
                        bar += "+"
                    elif score >= 0.5:
                        bar += "-"
                    else:
                        bar += " "

                print(f"  data{bit_idx}: delay +{best_offset:2d}, stability {best_score*100:.1f}%  |{bar}|")
            else:
                delays[f'data{bit_idx}'] = 0
                print(f"  data{bit_idx}: unable to analyze")

        return delays

    # 分别分析 I 和 Q (根据 iq_swap 决定边沿分配)
    if iq_swap:
        # IQ Swap: 上升沿->Q, 下降沿->I
        i_delays = analyze_edges(falling_edges, "下降沿 (I)")
        q_delays = analyze_edges(rising_edges, "上升沿 (Q)")
    else:
        # 正常: 上升沿->I, 下降沿->Q
        i_delays = analyze_edges(rising_edges, "上升沿 (I)")
        q_delays = analyze_edges(falling_edges, "下降沿 (Q)")

    # 绘制眼图
    if plot_eye:
        try:
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(4, 5, figsize=(15, 10))

            if iq_swap:
                plot_config = [
                    (falling_edges, i_delays, "I (Falling)"),
                    (rising_edges, q_delays, "Q (Rising)")
                ]
            else:
                plot_config = [
                    (rising_edges, i_delays, "I (Rising)"),
                    (falling_edges, q_delays, "Q (Falling)")
                ]

            for row_offset, (edges, delays, title) in enumerate(plot_config):
                for bit_idx in sorted(data_dict.keys()):
                    if bit_idx >= 10:
                        continue

                    ax = axes[row_offset * 2 + bit_idx // 5, bit_idx % 5]
                    data = data_dict[bit_idx]

                    # 收集眼图轨迹
                    for edge in edges[:300]:
                        if edge + actual_search_range < len(data):
                            trace = data[edge:edge + actual_search_range].astype(float)
                            ax.plot(trace, 'b-', alpha=0.1, linewidth=0.3)

                    # 最佳采样点
                    best_offset = delays.get(f'data{bit_idx}', 0)
                    ax.axvline(x=best_offset, color='r', linewidth=2)

                    ax.set_title(f'{title} data{bit_idx} (+{best_offset})', fontsize=8)
                    ax.set_ylim(-0.2, 1.2)
                    ax.set_xlim(0, actual_search_range)

            plt.tight_layout()
            plt.savefig('eye_diagram_analysis.png', dpi=150, bbox_inches='tight')
            print(f"\n[OUTPUT] Eye diagram saved: eye_diagram_analysis.png")
            plt.show()
        except ImportError:
            print("[WARN] matplotlib unavailable, skip plotting")

    return i_delays, q_delays


def extract_iq_data(data_dict: dict, clk_array: np.ndarray,
                    i_delays: dict, q_delays: dict,
                    sample_rate: float, iq_swap: bool = False) -> tuple:
    """
    从二进制数据提取 IQ 数据

    Args:
        data_dict: 数据字典 {bit_idx: data_array}
        clk_array: 时钟数组
        i_delays: I 通道每路数据的延迟字典
        q_delays: Q 通道每路数据的延迟字典
        sample_rate: 采样率 (Hz)
        iq_swap: 是否交换IQ (True: 上升沿->Q, 下降沿->I)

    Returns:
        (i_data, q_data, iq_sample_rate)
    """
    clk_diff = np.diff(clk_array.astype(np.int8))

    # 找时钟边沿
    rising_edges = np.where(clk_diff == 1)[0] + 1
    falling_edges = np.where(clk_diff == -1)[0] + 1

    if iq_swap:
        print(f"[INFO] 检测到 {len(falling_edges)} 个下降沿 (I), {len(rising_edges)} 个上升沿 (Q)")
    else:
        print(f"[INFO] 检测到 {len(rising_edges)} 个上升沿 (I), {len(falling_edges)} 个下降沿 (Q)")

    # 组装 IQ 数据
    def extract_value(edge_idx: int, delays: dict) -> int:
        value = 0
        for bit_idx in range(10):
            delay = delays.get(f'data{bit_idx}', 0)
            sample_idx = edge_idx + delay
            if 0 <= sample_idx < len(data_dict[bit_idx]):
                bit_val = int(data_dict[bit_idx][sample_idx])
                value |= (bit_val << bit_idx)
        return value

    # 根据 iq_swap 决定边沿分配
    if iq_swap:
        # IQ Swap: 下降沿->I, 上升沿->Q
        i_edges = falling_edges
        q_edges = rising_edges
    else:
        # 正常: 上升沿->I, 下降沿->Q
        i_edges = rising_edges
        q_edges = falling_edges

    i_values = [extract_value(idx, i_delays) for idx in i_edges if idx + 15 < len(clk_array)]
    q_values = [extract_value(idx, q_delays) for idx in q_edges if idx + 15 < len(clk_array)]

    # 对齐长度
    min_len = min(len(i_values), len(q_values))
    i_data = np.array(i_values[:min_len], dtype=np.uint16)
    q_data = np.array(q_values[:min_len], dtype=np.uint16)

    # 估算 IQ 采样率
    # DDR模式: 上升沿采I, 下降沿采Q, 所以IQ采样率 = 时钟频率 × 2
    if len(rising_edges) >= 2:
        clk_freq = sample_rate / np.median(np.diff(rising_edges))
        iq_sample_rate = clk_freq * 2  # DDR: 每个时钟周期输出一对IQ
        print(f"[INFO] 时钟频率: {clk_freq/1e6:.3f} MHz (DDR)")
        print(f"[INFO] IQ 采样率: {iq_sample_rate/1e6:.3f} MHz")
    else:
        iq_sample_rate = 32e6

    print(f"[INFO] 提取 {min_len} 个 IQ 采样点")

    return i_data, q_data, iq_sample_rate


def unsigned_to_signed(data: np.ndarray, bit_width: int) -> np.ndarray:
    """将无符号整数转换为有符号整数 (补码格式)"""
    signed_data = data.astype(np.int32)
    max_val = 1 << (bit_width - 1)
    signed_data[signed_data >= max_val] -= (1 << bit_width)
    return signed_data


def save_iq_data(i_data: np.ndarray, q_data: np.ndarray,
                 output_path: str, sample_rate: float = 32e6,
                 bit_width: int = 10):
    """保存 IQ 数据"""
    i_signed = unsigned_to_signed(i_data, bit_width)
    q_signed = unsigned_to_signed(q_data, bit_width)

    # TXT
    txt_path = f"{output_path}.txt"
    hex_width = (bit_width + 3) // 4
    with open(txt_path, 'w') as f:
        f.write(f"# IQ Data - {len(i_data)} samples @ {sample_rate/1e6:.3f} MHz\n")
        f.write(f"# Format: I (hex), Q (hex), I (signed), Q (signed)\n")
        f.write(f"# Bit width: {bit_width}, signed (MSB is sign bit)\n")
        for i_u, q_u, i_s, q_s in zip(i_data, q_data, i_signed, q_signed):
            f.write(f"0x{i_u:0{hex_width}X}, 0x{q_u:0{hex_width}X}, {i_s:5d}, {q_s:5d}\n")
    print(f"[OUTPUT] TXT: {txt_path}")

    # NPY
    npy_path = f"{output_path}.npy"
    np.save(npy_path, np.column_stack([i_data, q_data]))
    print(f"[OUTPUT] NPY: {npy_path}")

    # MAT
    try:
        from scipy.io import savemat
        mat_path = f"{output_path}.mat"
        savemat(mat_path, {
            'I': i_data, 'Q': q_data,
            'I_signed': i_signed, 'Q_signed': q_signed,
            'fs': sample_rate, 'bit_width': bit_width,
        })
        print(f"[OUTPUT] MAT: {mat_path}")
    except ImportError:
        pass

    return i_data, q_data


def plot_iq_data(i_data: np.ndarray, q_data: np.ndarray,
                 sample_rate: float, bit_width: int,
                 output_path: str = None, title_suffix: str = ""):
    """绘制 IQ 数据图表 (使用 Plotly)"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("[WARN] plotly 不可用，跳过绘图")
        return

    i_signed = unsigned_to_signed(i_data, bit_width)
    q_signed = unsigned_to_signed(q_data, bit_width)

    t = np.arange(len(i_data)) / sample_rate * 1e6

    # 创建 2x2 子图
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            f'IQ Time Domain ({bit_width}-bit signed){title_suffix}',
            'IQ Constellation',
            'Spectrum',
            'Instantaneous Frequency'
        ),
        specs=[
            [{"type": "scatter"}, {"type": "scatter"}],
            [{"type": "scatter"}, {"type": "scatter"}]
        ],
        row_heights=[0.5, 0.5],
        column_widths=[0.6, 0.4],
        horizontal_spacing=0.08,
        vertical_spacing=0.12
    )

    # I/Q 时域波形
    fig.add_trace(
        go.Scattergl(x=t, y=i_signed, mode='lines+markers', name='I',
                     line=dict(color='blue', width=1), marker=dict(size=2)),
        row=1, col=1
    )
    fig.add_trace(
        go.Scattergl(x=t, y=q_signed, mode='lines+markers', name='Q',
                     line=dict(color='red', width=1), marker=dict(size=2)),
        row=1, col=1
    )
    fig.update_xaxes(title_text='Time (us)', row=1, col=1)
    fig.update_yaxes(title_text='Value', row=1, col=1)

    # IQ 星座图
    fig.add_trace(
        go.Scattergl(x=i_signed, y=q_signed, mode='markers', name='IQ',
                     marker=dict(size=3, color=np.arange(len(i_signed)),
                                 colorscale='Viridis', opacity=0.7),
                     showlegend=False),
        row=1, col=2
    )
    fig.update_xaxes(title_text='I', row=1, col=2)
    fig.update_yaxes(title_text='Q', scaleanchor="x2", scaleratio=1, row=1, col=2)

    # 频谱
    max_val = 1 << (bit_width - 1)
    iq_signal = (i_signed + 1j * q_signed) / max_val

    fft_size = min(4096, len(iq_signal))
    if fft_size > 0:
        spectrum = np.fft.fftshift(np.fft.fft(iq_signal[:fft_size]))
        freq = np.fft.fftshift(np.fft.fftfreq(fft_size, 1/sample_rate)) / 1e6
        psd = 20 * np.log10(np.abs(spectrum) + 1e-10)
        psd = psd - np.max(psd)
        fig.add_trace(
            go.Scattergl(x=freq, y=psd, mode='lines', name='Spectrum',
                         line=dict(color='green', width=1), showlegend=False),
            row=2, col=1
        )
    fig.update_xaxes(title_text='Frequency (MHz)', row=2, col=1)
    fig.update_yaxes(title_text='Power (dB)', range=[-80, 5], row=2, col=1)

    # 瞬时频率
    if len(iq_signal) > 1:
        phase = np.unwrap(np.angle(iq_signal))
        freq_inst = np.diff(phase) * sample_rate / (2 * np.pi) / 1e3
        t_freq = t[:-1]
        fig.add_trace(
            go.Scattergl(x=t_freq, y=freq_inst, mode='lines', name='Inst Freq',
                         line=dict(color='magenta', width=1),
                         showlegend=False),
            row=2, col=2
        )
    fig.update_xaxes(title_text='Time (us)', row=2, col=2)
    fig.update_yaxes(title_text='Frequency (kHz)', row=2, col=2)

    # 更新布局
    fig.update_layout(
        height=900,
        title_text=f"IQ Analysis{title_suffix}",
        title_x=0.5,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.3),
        margin=dict(l=60, r=40, t=80, b=60),
        autosize=True
    )

    # 保存和显示
    if output_path:
        html_path = f"{output_path}.html"
        fig.write_html(
            html_path,
            full_html=True,
            include_plotlyjs=True,
            config={'responsive': True}
        )
        print(f"[OUTPUT] HTML: {html_path}")

        # 也保存 PNG (需要 kaleido)
        try:
            png_path = f"{output_path}.png"
            fig.write_image(png_path, width=1600, height=900, scale=2)
            print(f"[OUTPUT] PNG: {png_path}")
        except Exception:
            pass

    fig.show()


def parse_delays(delay_str: str) -> dict:
    """
    解析延迟字符串

    格式: "clk:0,data0:1,data1:-1,data2:2"
    """
    delays = {}
    if not delay_str:
        return delays

    for item in delay_str.split(','):
        item = item.strip()
        if ':' in item:
            name, value = item.split(':')
            delays[name.strip()] = int(value.strip())
    return delays


def main():
    parser = argparse.ArgumentParser(
        description='将逻辑分析仪 BIN 数据转换为 IQ 数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 基本用法 (自动眼图对齐)
    python utils/logic_analyzer_to_iq.py test.bin --eye-align

    # 指定采样率
    python utils/logic_analyzer_to_iq.py test.bin --sample-rate 500e6 --eye-align

    # IQ 交换 (上升沿->Q, 下降沿->I)
    python utils/logic_analyzer_to_iq.py test.bin --eye-align --iq-swap

    # 手动指定延迟
    python utils/logic_analyzer_to_iq.py test.bin --delays "data0:3,data1:2,data2:10"

通道延迟说明:
    由于逻辑分析仪各探针到达芯片的延迟不同，在时钟边沿采样时可能采到
    不稳定的数据。使用 --eye-align 自动分析最佳采样延迟。
        """
    )

    parser.add_argument('input', help='输入 BIN 文件路径')
    parser.add_argument('--output', '-o', help='输出文件路径 (不含扩展名)', default=None)
    parser.add_argument('--sample-rate', '-s', type=float, default=500e6,
                        help='逻辑分析仪采样率 (Hz), 默认 500e6')
    parser.add_argument('--delays', '-d', type=str, default='',
                        help='通道延迟设置，格式: "data0:1,data1:2"')
    parser.add_argument('--eye-align', action='store_true',
                        help='基于眼图分析找到每路数据的最佳采样延迟 (推荐)')
    parser.add_argument('--plot-eye', action='store_true',
                        help='绘制眼图分析图表')
    parser.add_argument('--no-plot', action='store_true',
                        help='不显示 IQ 图表')
    parser.add_argument('--iq-swap', action='store_true',
                        help='交换 I/Q 通道 (上升沿->Q, 下降沿->I)')

    args = parser.parse_args()

    # 检查文件类型
    input_path = Path(args.input)
    if input_path.suffix.lower() != '.bin':
        print(f"[ERROR] 只支持 BIN 文件格式，当前文件: {input_path.suffix}")
        sys.exit(1)

    # 确定输出路径
    if args.output is None:
        args.output = str(input_path.parent / f"{input_path.stem}_iq")

    print("=" * 60)
    print("Logic Analyzer BIN to IQ Converter")
    print("=" * 60)

    # 加载二进制数据
    data_dict, clk_array, bit_width, la_sample_rate = load_binary_data(
        args.input, args.sample_rate
    )

    # 解析延迟
    delays = parse_delays(args.delays)

    # 眼图分析
    if args.eye_align:
        print("\n" + "=" * 60)
        print("Eye Diagram Analysis (Separate I/Q)")
        if args.iq_swap:
            print("  [IQ Swap: 上升沿->Q, 下降沿->I]")
        print("=" * 60)
        i_delays, q_delays = analyze_eye_diagram(
            data_dict, clk_array, la_sample_rate,
            search_range=15, plot_eye=args.plot_eye,
            iq_swap=args.iq_swap
        )
        print(f"\n[INFO] Applied eye diagram results")
    else:
        # 使用手动延迟或默认延迟
        if not delays:
            delays = {'clk': 0}
            for i in range(10):
                delays[f'data{i}'] = 0
        i_delays = delays
        q_delays = delays

    print(f"\n[INFO] I delays: {i_delays}")
    print(f"[INFO] Q delays: {q_delays}")

    # 提取 IQ 数据
    i_data, q_data, iq_sample_rate = extract_iq_data(
        data_dict, clk_array, i_delays, q_delays, la_sample_rate,
        iq_swap=args.iq_swap
    )

    # 保存数据
    save_iq_data(i_data, q_data, args.output, iq_sample_rate, bit_width)

    # 绘图
    if not args.no_plot:
        title_suffix = ""
        if args.eye_align:
            title_suffix += " (eye-aligned)"
        if args.iq_swap:
            title_suffix += " (IQ swapped)"
        plot_iq_data(i_data, q_data, iq_sample_rate, bit_width, args.output, title_suffix)

    print(f"\n[DONE] Conversion complete, {len(i_data)} IQ samples")


if __name__ == '__main__':
    main()
