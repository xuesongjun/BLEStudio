"""
BLE Studio IQ 数据比较工具

用于比较 TX 和 RX 的 IQ 数据，分析差异来源
"""

import argparse
from pathlib import Path
import sys

import numpy as np


def load_iq_txt(path: str) -> np.ndarray:
    """从 TXT 文件加载 IQ 数据（整数）"""
    data = []
    with open(path, 'r', encoding='utf-8') as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if line.startswith('//') or not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"{path}:{line_number}: expected two integer I/Q columns")
            data.append([int(parts[0]), int(parts[1])])
    if not data:
        raise ValueError(f"IQ data must be non-empty: {path}")
    return np.array(data)


def load_iq_mat(path: str) -> np.ndarray:
    """从 MAT 文件加载 IQ 数据（浮点复数）"""
    from scipy.io import loadmat
    mat = loadmat(path)
    if 'iq' in mat:
        iq = mat['iq'].flatten()
    elif 'IQ' in mat:
        iq = mat['IQ'].flatten()
    else:
        raise ValueError(f"MAT file must contain an 'iq' or 'IQ' variable: {path}")
    if iq.size == 0:
        raise ValueError(f"IQ data must be non-empty: {path}")
    if not np.issubdtype(iq.dtype, np.number) or not np.all(np.isfinite(iq)):
        raise ValueError(f"IQ data must contain finite numeric samples: {path}")
    return iq


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
    if len(tx) != len(rx):
        raise ValueError("TX and RX must contain the same number of samples")

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

    if len(tx) != len(rx):
        raise ValueError("TX and RX must contain the same number of samples")

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


def print_comparison_report(tx_file: str, rx_file: str, bit_width: int = 12):
    """
    打印完整的 TX vs RX 比较报告

    Args:
        tx_file: 明确指定的 TX TXT 或 MAT 文件
        rx_file: 与 TX 同格式的 RX 文件
        bit_width: 量化位宽
    """
    extension = Path(tx_file).suffix.lower()
    if extension != Path(rx_file).suffix.lower():
        raise ValueError("TX and RX must use the same format (.txt or .mat)")
    if extension not in ('.txt', '.mat'):
        raise ValueError("Supported IQ formats are .txt and .mat")
    if bit_width < 1:
        raise ValueError("bit_width must be positive")

    if extension == '.txt':
        result = compare_txt_files(tx_file, rx_file)
        print(f"[TXT] samples={result['samples']} identical={result['is_identical']}")
        print(f"  I difference: [{result['i_diff_min']}, {result['i_diff_max']}]")
        print(f"  Q difference: [{result['q_diff_min']}, {result['q_diff_max']}]")
        print(f"  Matched: {result['match_count']}/{result['samples']} "
              f"({result['match_ratio'] * 100:.1f}%)")
        return

    result = compare_mat_files(tx_file, rx_file)
    print(f"[MAT] samples={result['samples']} identical={result['is_identical']}")
    print(f"  Complex difference: max={result['diff_max']:.2e} mean={result['diff_mean']:.2e}")

    scale = analyze_scale_difference(tx_file, rx_file, bit_width)
    print(f"[Scale] TX={scale['scale_tx']:.6f} RX={scale['scale_rx']:.6f} "
          f"difference={scale['scale_diff_percent']:.4f}%")
    print(f"  Amplitude: TX={scale['tx_max_amplitude']:.10f} RX={scale['rx_max_amplitude']:.10f}")
    print(f"  Difference in TX LSB: max={scale['lsb_diff_max']:.2f} mean={scale['lsb_diff_mean']:.2f}")
    # 延续旧脚本的数值分析规则，不把探索性量化报告当作 RF 或 testcase 判定。
    for same_scale in (False, True):
        quant = analyze_quantization(tx_file, rx_file, bit_width, same_scale)
        print(f"[Quantization] same_scale={same_scale} "
              f"I_difference={quant['i_diff_range']} Q_difference={quant['q_diff_range']} "
              f"matched={quant['match_count']}/{quant['samples']} "
              f"({quant['match_ratio'] * 100:.1f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description='Compare explicit TX/RX IQ files (TXT or MAT).')
    parser.add_argument('tx_file', help='TX IQ file')
    parser.add_argument('rx_file', help='RX IQ file in the same format')
    parser.add_argument('--bit-width', type=int, default=12, help='Quantization analysis width (default: 12)')
    arguments = parser.parse_args()
    try:
        print_comparison_report(arguments.tx_file, arguments.rx_file, arguments.bit_width)
    except (OSError, ValueError, OverflowError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
