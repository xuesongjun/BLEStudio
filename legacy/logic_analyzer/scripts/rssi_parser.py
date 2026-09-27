"""
RSSI 数据解析工具

解析 SDR 采样的 RSSI 和控制信号数据。
数据格式: 每个采样点 16 位 (2 字节)
- bit0~bit7: RSSI 数据
- bit8: agc_init
- bit9: rampup
- bit10: fire_timer

用法:
    python utils/rssi_parser.py utils/rssi_config.yaml
"""

import argparse
import numpy as np
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] 需要安装 pyyaml: pip install pyyaml")
    sys.exit(1)


def load_config(config_path: str) -> dict:
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_binary_data(file_path: str) -> np.ndarray:
    """
    加载二进制数据

    格式: 每 2 字节存储一次采样的 16 个通道
    """
    with open(file_path, 'rb') as f:
        raw_data = np.frombuffer(f.read(), dtype=np.uint8)

    n_samples = len(raw_data) // 2
    print(f"[INFO] 读取 {n_samples} 个采样点")

    # 重新整形为 (n_samples, 2)
    raw_data = raw_data[:n_samples * 2].reshape(n_samples, 2)

    # 合并为 16 位数据: 低字节 + 高字节
    data = raw_data[:, 0].astype(np.uint16) | (raw_data[:, 1].astype(np.uint16) << 8)

    return data


def extract_signals(data: np.ndarray, config: dict) -> dict:
    """
    从原始数据中提取各个信号

    Returns:
        dict: {信号名: 数据数组}
    """
    signals = {}

    # 提取 RSSI (bit0~bit7)
    data_bits = config.get('data_bits', [0, 1, 2, 3, 4, 5, 6, 7])
    rssi_mask = sum(1 << b for b in data_bits)
    signals['rssi'] = (data & rssi_mask).astype(np.uint8)

    # 提取额外信号
    extra_signals = config.get('extra_signals', {})
    for name, bit in extra_signals.items():
        signals[name] = ((data >> bit) & 1).astype(np.uint8)

    return signals


def save_results(signals: dict, output_path: str, config: dict):
    """保存结果"""
    sample_rate = float(config.get('sample_rate', 100e6))

    # TXT 格式
    txt_path = f"{output_path}.txt"
    with open(txt_path, 'w') as f:
        f.write(f"# RSSI Data - {len(signals['rssi'])} samples @ {sample_rate/1e6:.1f} MHz\n")

        # 写入表头
        header = ['rssi'] + list(config.get('extra_signals', {}).keys())
        f.write(f"# {', '.join(header)}\n")

        # 写入数据
        rssi = signals['rssi']
        extra_names = list(config.get('extra_signals', {}).keys())
        for i in range(len(rssi)):
            line = f"{rssi[i]:3d}"
            for name in extra_names:
                line += f", {signals[name][i]}"
            f.write(line + "\n")

    print(f"[OUTPUT] TXT: {txt_path}")

    # NPY 格式
    npy_path = f"{output_path}.npy"
    np.save(npy_path, signals['rssi'])
    print(f"[OUTPUT] NPY: {npy_path}")


def generate_html(signals: dict, output_path: str, config: dict):
    """生成 HTML 可视化"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("[WARN] plotly 未安装，跳过 HTML 生成")
        return

    sample_rate = float(config.get('sample_rate', 100e6))
    n_samples = len(signals['rssi'])
    t = np.arange(n_samples) / sample_rate * 1e6  # 转换为 us

    extra_names = list(config.get('extra_signals', {}).keys())
    n_extra = len(extra_names)

    # 创建子图
    fig = make_subplots(
        rows=2 + n_extra, cols=1,
        subplot_titles=['RSSI', 'RSSI Spectrum'] + extra_names,
        vertical_spacing=0.08,
        row_heights=[0.4, 0.3] + [0.1] * n_extra
    )

    # RSSI 时域
    fig.add_trace(
        go.Scattergl(x=t, y=signals['rssi'].astype(np.int8),
                     mode='lines', name='RSSI',
                     line=dict(color='blue', width=1)),
        row=1, col=1
    )
    fig.update_xaxes(title_text='Time (us)', row=1, col=1)
    fig.update_yaxes(title_text='RSSI', row=1, col=1)

    # RSSI 频谱
    fft_data = np.fft.fft(signals['rssi'].astype(np.float32) - np.mean(signals['rssi']))
    freqs = np.fft.fftfreq(len(fft_data), 1/sample_rate)
    fft_mag = 20 * np.log10(np.abs(fft_data[:len(fft_data)//2]) + 1e-10)
    freqs_pos = freqs[:len(freqs)//2] / 1e6

    fig.add_trace(
        go.Scattergl(x=freqs_pos, y=fft_mag,
                     mode='lines', name='Spectrum',
                     line=dict(color='orange', width=1)),
        row=2, col=1
    )
    fig.update_xaxes(title_text='Frequency (MHz)', row=2, col=1)
    fig.update_yaxes(title_text='Magnitude (dB)', row=2, col=1)

    # 额外信号
    colors = ['green', 'red', 'purple', 'brown', 'pink']
    for i, name in enumerate(extra_names):
        fig.add_trace(
            go.Scattergl(x=t, y=signals[name],
                         mode='lines', name=name,
                         line=dict(color=colors[i % len(colors)], width=1)),
            row=3 + i, col=1
        )
        fig.update_xaxes(title_text='Time (us)', row=3 + i, col=1)
        fig.update_yaxes(title_text=name, row=3 + i, col=1)

    fig.update_layout(
        title=f'RSSI Analysis ({n_samples} samples @ {sample_rate/1e6:.1f} MHz)',
        height=300 + 200 * n_extra,
        showlegend=False
    )

    html_path = f"{output_path}.html"
    fig.write_html(html_path)
    print(f"[OUTPUT] HTML: {html_path}")


def generate_vcd(signals: dict, output_path: str, config: dict):
    """生成 VCD 波形文件"""
    sample_rate = float(config.get('sample_rate', 100e6))
    timescale_ns = 1  # 1ns 时间单位
    sample_period_ns = int(1e9 / sample_rate)

    vcd_path = f"{output_path}.vcd"

    with open(vcd_path, 'w') as f:
        # VCD 头
        f.write("$timescale 1ns $end\n")
        f.write("$scope module rssi_data $end\n")

        # 定义信号
        f.write("$var wire 8 r rssi [7:0] $end\n")

        extra_names = list(config.get('extra_signals', {}).keys())
        symbols = {}
        for i, name in enumerate(extra_names):
            symbol = chr(ord('a') + i)
            symbols[name] = symbol
            f.write(f"$var wire 1 {symbol} {name} $end\n")

        f.write("$upscope $end\n")
        f.write("$enddefinitions $end\n")

        # 初始值
        f.write("#0\n")
        f.write(f"b{signals['rssi'][0]:08b} r\n")
        for name in extra_names:
            f.write(f"{signals[name][0]}{symbols[name]}\n")

        # 写入变化点
        prev_rssi = signals['rssi'][0]
        prev_extra = {name: signals[name][0] for name in extra_names}

        for i in range(1, len(signals['rssi'])):
            time_ns = i * sample_period_ns
            changed = False

            rssi = signals['rssi'][i]
            if rssi != prev_rssi:
                if not changed:
                    f.write(f"#{time_ns}\n")
                    changed = True
                f.write(f"b{rssi:08b} r\n")
                prev_rssi = rssi

            for name in extra_names:
                val = signals[name][i]
                if val != prev_extra[name]:
                    if not changed:
                        f.write(f"#{time_ns}\n")
                        changed = True
                    f.write(f"{val}{symbols[name]}\n")
                    prev_extra[name] = val

    print(f"[OUTPUT] VCD: {vcd_path}")


def main():
    parser = argparse.ArgumentParser(description='RSSI 数据解析工具')
    parser.add_argument('config', help='配置文件路径 (YAML)')
    parser.add_argument('--no-plot', action='store_true', help='不生成 HTML')
    parser.add_argument('--vcd', action='store_true', help='生成 VCD 波形文件')
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    print("=" * 60)
    print("Load Binary Data")
    print("=" * 60)

    # 加载数据
    input_file = config['input_file']
    data = load_binary_data(input_file)

    sample_rate = float(config.get('sample_rate', 100e6))
    duration = len(data) / sample_rate
    print(f"[INFO] 采样率: {sample_rate/1e6:.1f} MHz")
    print(f"[INFO] 采样时长: {duration*1e6:.1f} us")

    # 提取信号
    print("\n" + "=" * 60)
    print("Extract Signals")
    print("=" * 60)

    signals = extract_signals(data, config)

    print(f"[INFO] RSSI 范围: {signals['rssi'].min()} ~ {signals['rssi'].max()}")
    for name in config.get('extra_signals', {}).keys():
        high_count = np.sum(signals[name] == 1)
        print(f"[INFO] {name}: {high_count} 个高电平 ({high_count/len(data)*100:.2f}%)")

    # 保存结果
    print("\n" + "=" * 60)
    print("Save Results")
    print("=" * 60)

    output_path = config.get('output_file', input_file.replace('.bin', '_wave'))
    save_results(signals, output_path, config)

    # 生成 VCD
    if args.vcd:
        generate_vcd(signals, output_path, config)

    # 生成 HTML
    if not args.no_plot and 'html' in config.get('save_formats', []):
        print("\n" + "=" * 60)
        print("Generate HTML")
        print("=" * 60)
        generate_html(signals, output_path, config)

    print("\n[DONE]")


if __name__ == '__main__':
    main()
