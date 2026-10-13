"""
BLE Studio 调制器分析工具
分析 GFSK 调制器的频率脉冲、瞬时频率、相位等特性
"""

import numpy as np
from ble_studio.modulator import BLEModulator, ModulatorConfig
from ble_studio.packet import BLEPhyMode


def analyze_modulator(phy_mode=BLEPhyMode.LE_1M, sample_rate=8e6,
                      modulation_index=0.5, bt=0.5):
    """
    分析调制器参数

    Args:
        phy_mode: PHY 模式
        sample_rate: 采样率
        modulation_index: 调制指数
        bt: 高斯滤波器 BT 积
    """
    config = ModulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        modulation_index=modulation_index,
        bt=bt
    )
    mod = BLEModulator(config)

    print('=' * 60)
    print('BLE GFSK 调制器分析')
    print('=' * 60)
    print()

    print('配置参数:')
    print(f'  PHY 模式: {phy_mode.name}')
    print(f'  符号率: {mod.symbol_rate/1e6:.1f} MHz')
    print(f'  采样率: {sample_rate/1e6:.1f} MHz')
    print(f'  每符号采样数: {mod.samples_per_symbol}')
    print(f'  调制指数 h: {modulation_index}')
    print(f'  BT 积: {bt}')
    print(f'  理论频偏: ±{mod.freq_deviation/1e3:.1f} kHz')
    print()

    print('频率脉冲:')
    print(f'  长度: {len(mod.freq_pulse)} 采样点')
    print(f'  总和: {np.sum(mod.freq_pulse):.6f} (应为 1.0)')
    print(f'  最大值: {mod.freq_pulse.max():.6f}')
    print(f'  最小值: {mod.freq_pulse.min():.6f}')
    print()

    return mod


def test_phase_accumulation(mod, pattern='all_ones', num_symbols=32):
    """
    测试相位累积

    Args:
        mod: 调制器实例
        pattern: 测试模式 ('all_ones', 'all_zeros', 'alternating')
        num_symbols: 符号数
    """
    h = mod.config.modulation_index

    if pattern == 'all_ones':
        bits = np.array([1] * num_symbols)
        expected_phase = num_symbols * h * np.pi
    elif pattern == 'all_zeros':
        bits = np.array([0] * num_symbols)
        expected_phase = -num_symbols * h * np.pi
    else:  # alternating
        bits = np.array([0, 1] * (num_symbols // 2))
        expected_phase = 0  # 交替模式相位应该在 0 附近振荡

    iq = mod.modulate(bits)
    phase = np.unwrap(np.angle(iq))
    actual_phase = phase[-1] - phase[0]

    print(f'相位累积测试 ({pattern}, {num_symbols} 符号):')
    print(f'  实际相位变化: {actual_phase/np.pi:.4f}π')
    print(f'  理论相位变化: {expected_phase/np.pi:.4f}π')
    print(f'  每符号相位: {actual_phase/num_symbols/np.pi:.4f}π (理论 {h:.2f}π)')
    print()

    return actual_phase, expected_phase


def test_instantaneous_frequency(mod, pattern='all_ones', num_symbols=64):
    """
    测试瞬时频率

    Args:
        mod: 调制器实例
        pattern: 测试模式
        num_symbols: 符号数
    """
    sample_rate = mod.config.sample_rate
    N = mod.samples_per_symbol

    if pattern == 'all_ones':
        bits = np.array([1] * num_symbols)
    elif pattern == 'all_zeros':
        bits = np.array([0] * num_symbols)
    else:  # alternating
        bits = np.array([0, 1] * (num_symbols // 2))

    iq = mod.modulate(bits)
    phase = np.unwrap(np.angle(iq))
    freq_inst = np.diff(phase) / (2 * np.pi) * sample_rate

    # 稳态区域 (跳过前后各 4 个符号)
    skip = 4 * N
    freq_stable = freq_inst[skip:-skip] if len(freq_inst) > 2*skip else freq_inst

    print(f'瞬时频率测试 ({pattern}, {num_symbols} 符号):')
    print(f'  全程最小: {freq_inst.min()/1e3:.1f} kHz')
    print(f'  全程最大: {freq_inst.max()/1e3:.1f} kHz')
    print(f'  稳态平均: {freq_stable.mean()/1e3:.1f} kHz')
    print(f'  稳态标准差: {freq_stable.std()/1e3:.2f} kHz')
    print(f'  理论频偏: ±{mod.freq_deviation/1e3:.1f} kHz')
    print()

    return freq_inst, freq_stable


def test_iq_range(mod, pattern='alternating', num_symbols=64):
    """
    测试 IQ 信号范围

    Args:
        mod: 调制器实例
        pattern: 测试模式
        num_symbols: 符号数
    """
    if pattern == 'all_ones':
        bits = np.array([1] * num_symbols)
    elif pattern == 'all_zeros':
        bits = np.array([0] * num_symbols)
    else:  # alternating
        bits = np.array([0, 1] * (num_symbols // 2))

    iq = mod.modulate(bits)

    print(f'IQ 信号范围 ({pattern}, {num_symbols} 符号):')
    print(f'  I 范围: [{iq.real.min():.4f}, {iq.real.max():.4f}]')
    print(f'  Q 范围: [{iq.imag.min():.4f}, {iq.imag.max():.4f}]')
    print(f'  幅度范围: [{np.abs(iq).min():.4f}, {np.abs(iq).max():.4f}]')

    # 检查是否为恒包络
    amplitude_var = np.std(np.abs(iq))
    is_constant_envelope = amplitude_var < 0.01
    print(f'  恒包络: {"是" if is_constant_envelope else "否"} (幅度标准差: {amplitude_var:.6f})')
    print()

    return iq


def run_full_analysis():
    """运行完整分析"""
    # 分析 1M PHY
    print('\n' + '=' * 60)
    print('LE 1M PHY 分析')
    print('=' * 60 + '\n')

    mod = analyze_modulator(phy_mode=BLEPhyMode.LE_1M)

    # 相位测试
    test_phase_accumulation(mod, 'all_ones', 32)
    test_phase_accumulation(mod, 'all_zeros', 32)
    test_phase_accumulation(mod, 'alternating', 32)

    # 瞬时频率测试
    test_instantaneous_frequency(mod, 'all_ones', 64)
    test_instantaneous_frequency(mod, 'all_zeros', 64)
    test_instantaneous_frequency(mod, 'alternating', 64)

    # IQ 范围测试
    test_iq_range(mod, 'all_ones', 64)
    test_iq_range(mod, 'alternating', 64)

    # 分析 2M PHY
    print('\n' + '=' * 60)
    print('LE 2M PHY 分析')
    print('=' * 60 + '\n')

    mod_2m = analyze_modulator(phy_mode=BLEPhyMode.LE_2M)
    test_instantaneous_frequency(mod_2m, 'all_ones', 64)
    test_iq_range(mod_2m, 'alternating', 64)


if __name__ == '__main__':
    run_full_analysis()
