"""
BLE Studio IQ 数据比较工具

用于比较 TX 和 RX 的 IQ 数据，分析差异来源
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional


def load_iq_txt(path: str) -> np.ndarray:
    """从 TXT 文件加载 IQ 数据（整数）"""
    data = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('//') or not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                data.append([int(parts[0]), int(parts[1])])
    return np.array(data)


def load_iq_mat(path: str) -> np.ndarray:
    """从 MAT 文件加载 IQ 数据（浮点复数）"""
    from scipy.io import loadmat
    mat = loadmat(path)
    if 'iq' in mat:
        return mat['iq'].flatten()
    elif 'IQ' in mat:
        return mat['IQ'].flatten()
    else:
        raise ValueError(f"MAT 文件中找不到 'iq' 或 'IQ' 变量")


def compare_txt_files(tx_path: str, rx_path: str) -> dict:
    """
    比较两个 TXT 格式的 IQ 文件

    Args:
        tx_path: TX IQ 文件路径
        rx_path: RX IQ 文件路径

    Returns:
        比较结果字典
    """
    tx = load_iq_txt(tx_path)
    rx = load_iq_txt(rx_path)

    tx_i, tx_q = tx[:, 0], tx[:, 1]
    rx_i, rx_q = rx[:, 0], rx[:, 1]

    i_diff = tx_i - rx_i
    q_diff = tx_q - rx_q

    total_match = np.sum((i_diff == 0) & (q_diff == 0))

    return {
        'samples': len(tx),
        'i_diff_min': int(np.min(i_diff)),
        'i_diff_max': int(np.max(i_diff)),
        'q_diff_min': int(np.min(q_diff)),
        'q_diff_max': int(np.max(q_diff)),
        'match_count': int(total_match),
        'match_ratio': total_match / len(tx),
        'is_identical': total_match == len(tx),
    }


def compare_mat_files(tx_path: str, rx_path: str) -> dict:
    """
    比较两个 MAT 格式的 IQ 文件

    Args:
        tx_path: TX IQ 文件路径
        rx_path: RX IQ 文件路径

    Returns:
        比较结果字典
    """
    tx = load_iq_mat(tx_path)
    rx = load_iq_mat(rx_path)

    diff = np.abs(tx - rx)

    return {
        'samples': len(tx),
        'diff_max': float(np.max(diff)),
        'diff_mean': float(np.mean(diff)),
        'diff_std': float(np.std(diff)),
        'is_identical': np.allclose(tx, rx, rtol=1e-10),
    }


def analyze_scale_difference(tx_path: str, rx_path: str, bit_width: int = 12) -> dict:
    """
    分析 scale_to_full 导致的量化差异

    Args:
        tx_path: TX MAT 文件路径
        rx_path: RX MAT 文件路径
        bit_width: 量化位宽

    Returns:
        分析结果字典
    """
    tx = load_iq_mat(tx_path)
    rx = load_iq_mat(rx_path)

    full_scale = 2 ** (bit_width - 1)

    # 计算各自的 scale 因子
    tx_max = max(np.max(np.abs(tx.real)), np.max(np.abs(tx.imag)))
    rx_max = max(np.max(np.abs(rx.real)), np.max(np.abs(rx.imag)))

    scale_tx = full_scale / tx_max if tx_max > 0 else full_scale
    scale_rx = full_scale / rx_max if rx_max > 0 else full_scale

    # 浮点差异
    raw_diff = np.abs(tx - rx)

    # 差异换算成 LSB
    diff_lsb = raw_diff * scale_tx

    return {
        'tx_max_amplitude': float(tx_max),
        'rx_max_amplitude': float(rx_max),
        'amplitude_diff': float(rx_max - tx_max),
        'scale_tx': float(scale_tx),
        'scale_rx': float(scale_rx),
        'scale_diff_percent': float((scale_rx - scale_tx) / scale_tx * 100) if scale_tx != 0 else 0,
        'raw_diff_max': float(np.max(raw_diff)),
        'raw_diff_mean': float(np.mean(raw_diff)),
        'lsb_diff_max': float(np.max(diff_lsb)),
        'lsb_diff_mean': float(np.mean(diff_lsb)),
    }


def analyze_quantization(tx_path: str, rx_path: str, bit_width: int = 12,
                         use_same_scale: bool = False) -> dict:
    """
    分析量化后的差异

    Args:
        tx_path: TX MAT 文件路径
        rx_path: RX MAT 文件路径
        bit_width: 量化位宽
        use_same_scale: 是否使用相同的 scale 因子

    Returns:
        分析结果字典
    """
    tx = load_iq_mat(tx_path)
    rx = load_iq_mat(rx_path)

    full_scale = 2 ** (bit_width - 1)

    tx_max = max(np.max(np.abs(tx.real)), np.max(np.abs(tx.imag)))
    rx_max = max(np.max(np.abs(rx.real)), np.max(np.abs(rx.imag)))

    scale_tx = full_scale / tx_max if tx_max > 0 else full_scale
    scale_rx = scale_tx if use_same_scale else (full_scale / rx_max if rx_max > 0 else full_scale)

    # 量化
    tx_i_q = np.round(tx.real * scale_tx).astype(int)
    tx_q_q = np.round(tx.imag * scale_tx).astype(int)
    rx_i_q = np.round(rx.real * scale_rx).astype(int)
    rx_q_q = np.round(rx.imag * scale_rx).astype(int)

    i_diff = tx_i_q - rx_i_q
    q_diff = tx_q_q - rx_q_q

    match = np.sum((i_diff == 0) & (q_diff == 0))

    return {
        'samples': len(tx),
        'i_diff_range': (int(np.min(i_diff)), int(np.max(i_diff))),
        'q_diff_range': (int(np.min(q_diff)), int(np.max(q_diff))),
        'match_count': int(match),
        'match_ratio': match / len(tx),
        'use_same_scale': use_same_scale,
    }


def print_comparison_report(results_dir: str = "results", bit_width: int = 12):
    """
    打印完整的 TX vs RX 比较报告

    Args:
        results_dir: 结果目录
        bit_width: 量化位宽
    """
    results_dir = Path(results_dir)

    tx_txt = results_dir / "iq_tx.txt"
    rx_txt = results_dir / "iq_rx.txt"
    tx_mat = results_dir / "iq_tx.mat"
    rx_mat = results_dir / "iq_rx.mat"

    print("=" * 60)
    print("BLE Studio TX vs RX 比较报告")
    print("=" * 60)

    # TXT 文件比较
    if tx_txt.exists() and rx_txt.exists():
        print("\n[TXT 文件比较 (量化后整数)]")
        txt_result = compare_txt_files(str(tx_txt), str(rx_txt))
        print(f"  样本数: {txt_result['samples']}")
        print(f"  I 差异范围: [{txt_result['i_diff_min']}, {txt_result['i_diff_max']}]")
        print(f"  Q 差异范围: [{txt_result['q_diff_min']}, {txt_result['q_diff_max']}]")
        print(f"  完全匹配: {txt_result['match_count']}/{txt_result['samples']} "
              f"({txt_result['match_ratio']*100:.1f}%)")
        if txt_result['is_identical']:
            print("  结论: TX == RX (完全一致)")
        else:
            print("  结论: TX != RX")

    # MAT 文件比较
    if tx_mat.exists() and rx_mat.exists():
        print("\n[MAT 文件比较 (浮点复数)]")
        mat_result = compare_mat_files(str(tx_mat), str(rx_mat))
        print(f"  样本数: {mat_result['samples']}")
        print(f"  最大差异: {mat_result['diff_max']:.2e}")
        print(f"  平均差异: {mat_result['diff_mean']:.2e}")

        # Scale 分析
        print("\n[Scale 因子分析]")
        scale_result = analyze_scale_difference(str(tx_mat), str(rx_mat), bit_width)
        print(f"  TX 最大幅度: {scale_result['tx_max_amplitude']:.10f}")
        print(f"  RX 最大幅度: {scale_result['rx_max_amplitude']:.10f}")
        print(f"  幅度差异: {scale_result['amplitude_diff']:.2e}")
        print(f"  TX scale: {scale_result['scale_tx']:.6f}")
        print(f"  RX scale: {scale_result['scale_rx']:.6f}")
        print(f"  Scale 差异: {scale_result['scale_diff_percent']:.4f}%")
        print(f"  原始差异 → LSB: max={scale_result['lsb_diff_max']:.1f}, "
              f"mean={scale_result['lsb_diff_mean']:.2f}")

        # 量化分析
        print("\n[量化分析 (各自 scale)]")
        quant_result = analyze_quantization(str(tx_mat), str(rx_mat), bit_width, False)
        print(f"  I 差异范围: {quant_result['i_diff_range']}")
        print(f"  Q 差异范围: {quant_result['q_diff_range']}")
        print(f"  完全匹配: {quant_result['match_count']}/{quant_result['samples']} "
              f"({quant_result['match_ratio']*100:.1f}%)")

        print("\n[量化分析 (相同 scale)]")
        quant_same = analyze_quantization(str(tx_mat), str(rx_mat), bit_width, True)
        print(f"  I 差异范围: {quant_same['i_diff_range']}")
        print(f"  Q 差异范围: {quant_same['q_diff_range']}")
        print(f"  完全匹配: {quant_same['match_count']}/{quant_same['samples']} "
              f"({quant_same['match_ratio']*100:.1f}%)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        results_dir = sys.argv[1]
    else:
        results_dir = "results"

    print_comparison_report(results_dir)
