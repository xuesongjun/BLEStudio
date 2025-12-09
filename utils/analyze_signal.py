"""
BLE Studio 信号质量分析工具

分析 IQ 信号的质量指标，包括：
- 幅度分析
- 频偏分析
- 抖动分析
- 问题诊断
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional


def load_signal(file_path: str) -> Tuple[np.ndarray, float]:
    """
    加载 IQ 信号文件

    Args:
        file_path: 文件路径 (.mat, .bwv)

    Returns:
        (signal, sample_rate)
    """
    from scipy.io import loadmat

    mat = loadmat(file_path)

    # 获取信号数据
    if 'wave' in mat:
        signal = mat['wave'].flatten()
    elif 'iq' in mat:
        signal = mat['iq'].flatten()
    elif 'IQ' in mat:
        signal = mat['IQ'].flatten()
    else:
        # 尝试找复数变量
        for key, val in mat.items():
            if not key.startswith('__') and np.iscomplexobj(val):
                signal = val.flatten()
                break
        else:
            raise ValueError(f"无法找到 IQ 数据，可用变量: {[k for k in mat.keys() if not k.startswith('__')]}")

    # 获取采样率
    sample_rate = 8e6  # 默认值
    if 'info2' in mat:
        try:
            info2 = mat['info2']
            if info2.dtype.names and 'fs' in info2.dtype.names:
                sample_rate = float(info2['fs'][0, 0].flatten()[0])
        except:
            pass
    elif 'fs' in mat:
        sample_rate = float(mat['fs'].flatten()[0])
    elif 'Fs' in mat:
        sample_rate = float(mat['Fs'].flatten()[0])

    return signal, sample_rate


def analyze_amplitude(signal: np.ndarray) -> dict:
    """分析信号幅度"""
    amplitude = np.abs(signal)

    result = {
        'max': float(np.max(amplitude)),
        'min': float(np.min(amplitude)),
        'mean': float(np.mean(amplitude)),
        'std': float(np.std(amplitude)),
    }

    # 低幅度点统计
    for threshold in [0.01, 0.05, 0.1, 0.2]:
        ratio = np.sum(amplitude < threshold * result['max']) / len(amplitude)
        result[f'low_amp_{int(threshold*100)}pct'] = float(ratio)

    return result


def analyze_frequency(signal: np.ndarray, sample_rate: float,
                      symbol_rate: float = 1e6) -> dict:
    """分析瞬时频率"""
    # 计算瞬时频率
    phase = np.unwrap(np.angle(signal))
    freq_inst = np.diff(phase) * sample_rate / (2 * np.pi)

    # 只在高幅度区域分析 (避免相位噪声)
    amplitude = np.abs(signal[:-1])
    valid_mask = amplitude > np.max(amplitude) * 0.3
    freq_valid = freq_inst[valid_mask]

    result = {
        'freq_min': float(np.min(freq_valid)) / 1e3,  # kHz
        'freq_max': float(np.max(freq_valid)) / 1e3,
        'freq_mean': float(np.mean(freq_valid)) / 1e3,
        'freq_std': float(np.std(freq_valid)) / 1e3,
    }

    # 估计调制指数
    f_deviation = (result['freq_max'] - result['freq_min']) / 2
    result['modulation_index'] = f_deviation / (symbol_rate / 1e3 / 2)

    # 高低频区分析
    high_freq = freq_valid[freq_valid > 100e3]  # > 100 kHz
    low_freq = freq_valid[freq_valid < -100e3]  # < -100 kHz

    if len(high_freq) > 0:
        result['high_freq_mean'] = float(np.mean(high_freq)) / 1e3
        result['high_freq_std'] = float(np.std(high_freq)) / 1e3
        result['high_freq_jitter_pct'] = float(np.std(high_freq) / np.abs(np.mean(high_freq)) * 100)
    else:
        result['high_freq_mean'] = 0
        result['high_freq_std'] = 0
        result['high_freq_jitter_pct'] = 0

    if len(low_freq) > 0:
        result['low_freq_mean'] = float(np.mean(low_freq)) / 1e3
        result['low_freq_std'] = float(np.std(low_freq)) / 1e3
        result['low_freq_jitter_pct'] = float(np.std(low_freq) / np.abs(np.mean(low_freq)) * 100)
    else:
        result['low_freq_mean'] = 0
        result['low_freq_std'] = 0
        result['low_freq_jitter_pct'] = 0

    # 载波频偏 (中心频率偏移)
    result['carrier_offset'] = (result['high_freq_mean'] + result['low_freq_mean']) / 2

    # 频率不对称度
    result['freq_asymmetry'] = abs(result['high_freq_mean']) - abs(result['low_freq_mean'])

    return result


def diagnose_issues(amp_result: dict, freq_result: dict) -> list:
    """诊断信号问题"""
    issues = []

    # 1. 低幅度问题
    if amp_result['low_amp_10pct'] > 0.2:
        issues.append({
            'severity': 'warning' if amp_result['low_amp_10pct'] < 0.4 else 'error',
            'type': '低幅度区域过多',
            'detail': f"{amp_result['low_amp_10pct']*100:.1f}% 的点幅度低于 10%",
            'impact': '导致相位计算不稳定，眼图出现尖峰',
        })

    # 2. 载波频偏
    if abs(freq_result['carrier_offset']) > 20:
        issues.append({
            'severity': 'warning' if abs(freq_result['carrier_offset']) < 50 else 'error',
            'type': '载波频偏',
            'detail': f"中心频率偏移 {freq_result['carrier_offset']:+.1f} kHz",
            'impact': '眼图上下不对称',
        })

    # 3. 频率不对称
    if abs(freq_result['freq_asymmetry']) > 30:
        issues.append({
            'severity': 'warning' if abs(freq_result['freq_asymmetry']) < 60 else 'error',
            'type': '频率不对称',
            'detail': f"高频 {abs(freq_result['high_freq_mean']):.1f} kHz vs 低频 {abs(freq_result['low_freq_mean']):.1f} kHz",
            'impact': '调制不平衡，可能影响解调',
        })

    # 4. 高频抖动
    if freq_result['high_freq_jitter_pct'] > 10:
        issues.append({
            'severity': 'warning' if freq_result['high_freq_jitter_pct'] < 20 else 'error',
            'type': '高频区抖动大',
            'detail': f"抖动 {freq_result['high_freq_jitter_pct']:.1f}%",
            'impact': '眼图发散，影响解调裕量',
        })

    # 5. 低频抖动
    if freq_result['low_freq_jitter_pct'] > 10:
        issues.append({
            'severity': 'warning' if freq_result['low_freq_jitter_pct'] < 20 else 'error',
            'type': '低频区抖动大',
            'detail': f"抖动 {freq_result['low_freq_jitter_pct']:.1f}%",
            'impact': '眼图发散，影响解调裕量',
        })

    # 6. 调制指数异常
    h = freq_result['modulation_index']
    if h < 0.45 or h > 0.55:
        issues.append({
            'severity': 'warning' if 0.4 < h < 0.6 else 'error',
            'type': '调制指数异常',
            'detail': f"h = {h:.3f} (BLE 规范: 0.45~0.55)",
            'impact': '不符合 BLE 规范，可能导致兼容性问题',
        })

    return issues


def print_report(file_path: str, signal: np.ndarray, sample_rate: float,
                 symbol_rate: float = 1e6):
    """打印完整分析报告"""
    print("=" * 60)
    print(f"BLE Studio 信号质量分析")
    print("=" * 60)
    print(f"文件: {file_path}")
    print(f"采样率: {sample_rate/1e6:.1f} MHz")
    print(f"符号率: {symbol_rate/1e6:.1f} MHz")
    print(f"样本数: {len(signal)}")
    print(f"时长: {len(signal)/sample_rate*1e6:.1f} μs")
    print()

    # 幅度分析
    amp = analyze_amplitude(signal)
    print("【幅度分析】")
    print(f"  最大幅度: {amp['max']:.4f}")
    print(f"  最小幅度: {amp['min']:.6f}")
    print(f"  平均幅度: {amp['mean']:.4f}")
    print(f"  低幅度点 (<10%): {amp['low_amp_10pct']*100:.1f}%")
    print()

    # 频率分析
    freq = analyze_frequency(signal, sample_rate, symbol_rate)
    print("【频偏分析】")
    print(f"  频率范围: [{freq['freq_min']:.1f}, {freq['freq_max']:.1f}] kHz")
    print(f"  估计调制指数 h: {freq['modulation_index']:.3f}")
    print()

    print("【频率抖动分析】")
    print(f"  高频区 (+): {freq['high_freq_mean']:.1f} ± {freq['high_freq_std']:.1f} kHz "
          f"(抖动 {freq['high_freq_jitter_pct']:.1f}%)")
    print(f"  低频区 (-): {freq['low_freq_mean']:.1f} ± {freq['low_freq_std']:.1f} kHz "
          f"(抖动 {freq['low_freq_jitter_pct']:.1f}%)")
    print(f"  载波频偏: {freq['carrier_offset']:+.1f} kHz")
    print(f"  频率不对称度: {freq['freq_asymmetry']:.1f} kHz")
    print()

    # 问题诊断
    issues = diagnose_issues(amp, freq)
    if issues:
        print("【问题诊断】")
        for i, issue in enumerate(issues, 1):
            severity_icon = "WARN" if issue['severity'] == 'warning' else "ERROR"
            print(f"  {i}. [{severity_icon}] {issue['type']}")
            print(f"     {issue['detail']}")
            print(f"     影响: {issue['impact']}")
        print()

        # 总结
        errors = sum(1 for i in issues if i['severity'] == 'error')
        warnings = sum(1 for i in issues if i['severity'] == 'warning')
        print(f"【总结】发现 {errors} 个严重问题, {warnings} 个警告")
        if errors > 0:
            print("  信号质量较差，可能影响解调性能")
        elif warnings > 0:
            print("  信号质量一般，建议检查信号源")
    else:
        print("【总结】[OK] 信号质量良好，未发现明显问题")

    print()
    print("=" * 60)

    return {'amplitude': amp, 'frequency': freq, 'issues': issues}


def main():
    import sys

    if len(sys.argv) < 2:
        print("用法: python analyze_signal.py <file.mat|file.bwv> [symbol_rate_mhz]")
        print()
        print("示例:")
        print("  python analyze_signal.py template_data/BLE_1M.bwv")
        print("  python analyze_signal.py results/iq_rx.mat 2  # LE 2M")
        sys.exit(1)

    file_path = sys.argv[1]
    symbol_rate = float(sys.argv[2]) * 1e6 if len(sys.argv) > 2 else 1e6

    if not Path(file_path).exists():
        print(f"错误: 文件不存在 - {file_path}")
        sys.exit(1)

    signal, sample_rate = load_signal(file_path)
    print_report(file_path, signal, sample_rate, symbol_rate)


if __name__ == "__main__":
    main()
