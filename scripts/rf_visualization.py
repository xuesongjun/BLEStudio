"""
BLE Studio Visualizer RF 指标测试工具
测试 visualizer 中 RF 指标计算的正确性
"""

import numpy as np
from ble_studio.modulator import BLEModulator, ModulatorConfig
from ble_studio.packet import BLEPhyMode
from ble_studio.visualizer import BLEVisualizer


def test_rf_metrics_visualization(payload_type='PATTERN_10101010',
                                   payload_length=37,
                                   phy_mode=BLEPhyMode.LE_1M,
                                   sample_rate=8e6,
                                   verbose=True):
    """
    测试 visualizer 的 RF 指标计算

    Args:
        payload_type: 负载类型
        payload_length: 负载长度 (bytes)
        phy_mode: PHY 模式
        sample_rate: 采样率
        verbose: 是否打印详细信息

    Returns:
        dict: RF 测试指标
    """
    config = ModulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        modulation_index=0.5,
        bt=0.5
    )
    mod = BLEModulator(config)

    # 构建完整包结构: preamble(8) + AA(32) + header(16) + payload
    preamble = np.array([1, 0, 1, 0, 1, 0, 1, 0])
    # 广播接入地址 0x8E89BED6 (LSB first)
    aa = np.array([0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1,
                   1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 1, 0, 0, 0, 1])
    header = np.array([0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0])

    # 生成 payload
    payload_bits = payload_length * 8
    if 'PATTERN_10101010' in payload_type or 'PATTERN_01010101' in payload_type:
        payload = np.array([0, 1] * (payload_bits // 2))
    elif 'PATTERN_11110000' in payload_type or 'PATTERN_00001111' in payload_type:
        pattern = [1, 1, 1, 1, 0, 0, 0, 0]
        payload = np.array(pattern * (payload_bits // 8))
    elif 'PATTERN_11111111' in payload_type:
        payload = np.ones(payload_bits, dtype=int)
    elif 'PATTERN_00000000' in payload_type:
        payload = np.zeros(payload_bits, dtype=int)
    else:
        # 默认 PRBS9 风格的伪随机
        np.random.seed(42)
        payload = np.random.randint(0, 2, payload_bits)

    bits = np.concatenate([preamble, aa, header, payload])
    iq = mod.modulate(bits)

    # 计算 RF 指标
    viz = BLEVisualizer()
    metrics = viz.calculate_rf_metrics(
        signal=iq,
        sample_rate=sample_rate,
        samples_per_symbol=mod.samples_per_symbol,
        symbol_rate=mod.symbol_rate,
        payload_type=payload_type
    )

    if verbose:
        print('=' * 60)
        print('Visualizer RF 指标测试')
        print('=' * 60)
        print(f'Payload 类型: {payload_type}')
        print(f'Payload 长度: {payload_length} bytes')
        print(f'PHY 模式: {phy_mode.name}')
        print(f'采样率: {sample_rate/1e6:.1f} MHz')
        print()

        print('RF 测试指标:')
        print(f'  ΔF1avg: {metrics["delta_f1_avg"]:.1f} kHz (标准: 225-275 kHz)')
        print(f'  ΔF1max: {metrics["delta_f1_max"]:.1f} kHz')
        print(f'  ΔF1min: {metrics["delta_f1_min"]:.1f} kHz')
        print(f'  ΔF2avg: {metrics["delta_f2_avg"]:.1f} kHz')
        print(f'  ΔF2max: {metrics["delta_f2_max"]:.1f} kHz (标准: >= 185 kHz)')
        print(f'  ΔF2/ΔF1: {metrics["delta_f2_ratio"]:.3f} (标准: >= 0.8)')
        print(f'  ICFT: {metrics["icft"]:.1f} kHz (标准: |ICFT| <= 150 kHz)')
        print(f'  Freq Drift: {metrics["freq_drift"]:.1f} kHz (标准: <= 50 kHz)')
        print(f'  Drift Rate: {metrics["drift_rate"]:.2f} kHz/ms')
        print(f'  P_AVG: {metrics["p_avg_dbm"]:.1f} dBm')
        print(f'  P_PEAK: {metrics["p_peak_dbm"]:.1f} dBm')
        print()

        # 判断是否符合 BLE 标准
        is_55_pattern = 'PATTERN_10101010' in payload_type or 'PATTERN_01010101' in payload_type
        if is_55_pattern:
            f1_pass = 225 <= metrics['delta_f1_avg'] <= 275
            f2_pass = metrics['delta_f2_max'] >= 185
            ratio_pass = metrics['delta_f2_ratio'] >= 0.8
            icft_pass = abs(metrics['icft']) <= 150
            drift_pass = metrics['freq_drift'] <= 50

            print('BLE 标准验证:')
            print(f'  ΔF1avg 在 225-275 kHz: {"PASS" if f1_pass else "FAIL"}')
            print(f'  ΔF2max >= 185 kHz: {"PASS" if f2_pass else "FAIL"}')
            print(f'  ΔF2/ΔF1 >= 0.8: {"PASS" if ratio_pass else "FAIL"}')
            print(f'  |ICFT| <= 150 kHz: {"PASS" if icft_pass else "FAIL"}')
            print(f'  Freq Drift <= 50 kHz: {"PASS" if drift_pass else "FAIL"}')
            print()

            all_pass = f1_pass and f2_pass and ratio_pass and icft_pass and drift_pass
            print('=' * 60)
            print(f'总结: {"所有 BLE RF 指标 PASS" if all_pass else "部分指标 FAIL"}')
            print('=' * 60)

    return metrics


def compare_patterns():
    """比较不同 payload 类型的 RF 指标"""
    print('=' * 70)
    print('不同 Payload 类型的 RF 指标对比')
    print('=' * 70)
    print()

    patterns = [
        ('PATTERN_10101010', '0x55 交替'),
        ('PATTERN_11110000', '0x0F 模式'),
        ('PATTERN_11111111', '全 1'),
        ('PATTERN_00000000', '全 0'),
        ('PRBS9', 'PRBS9'),
    ]

    print(f'{"类型":<20} | {"ΔF1avg (kHz)":<14} | {"ΔF2max (kHz)":<14} | {"ΔF2/ΔF1":<10}')
    print('-' * 70)

    for pattern, name in patterns:
        metrics = test_rf_metrics_visualization(
            payload_type=pattern,
            verbose=False
        )
        print(f'{name:<20} | {metrics["delta_f1_avg"]:<14.1f} | '
              f'{metrics["delta_f2_max"]:<14.1f} | {metrics["delta_f2_ratio"]:<10.3f}')

    print()


def test_different_phy_modes():
    """测试不同 PHY 模式"""
    print('=' * 70)
    print('不同 PHY 模式的 RF 指标对比')
    print('=' * 70)
    print()

    modes = [
        (BLEPhyMode.LE_1M, '1M PHY', 8e6),
        (BLEPhyMode.LE_2M, '2M PHY', 16e6),
    ]

    print(f'{"PHY 模式":<15} | {"ΔF1avg (kHz)":<14} | {"ΔF2max (kHz)":<14} | {"状态":<10}')
    print('-' * 70)

    for mode, name, sample_rate in modes:
        metrics = test_rf_metrics_visualization(
            payload_type='PATTERN_10101010',
            phy_mode=mode,
            sample_rate=sample_rate,
            verbose=False
        )

        # 1M: 225-275 kHz, 2M: 450-550 kHz
        if mode == BLEPhyMode.LE_1M:
            f1_pass = 225 <= metrics['delta_f1_avg'] <= 275
        else:
            f1_pass = 450 <= metrics['delta_f1_avg'] <= 550

        status = 'PASS' if f1_pass else 'FAIL'
        print(f'{name:<15} | {metrics["delta_f1_avg"]:<14.1f} | '
              f'{metrics["delta_f2_max"]:<14.1f} | {status:<10}')

    print()


if __name__ == '__main__':
    # 测试 0x55 pattern
    print()
    test_rf_metrics_visualization(payload_type='PATTERN_10101010')
    print()

    # 比较不同 pattern
    compare_patterns()

    # 测试不同 PHY 模式
    test_different_phy_modes()
