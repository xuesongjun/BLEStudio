"""
BLE Studio RF 测试指标验证工具
验证调制器输出是否符合 BLE Core Spec RF 测试要求

BLE RF 测试指标:
- ΔF1avg (01010101 模式): 225-275 kHz
- ΔF2max (11110000 模式): >= 185 kHz
- ΔF2avg / ΔF1avg >= 0.8
"""

import numpy as np
from ble_studio.modulator import BLEModulator, ModulatorConfig
from ble_studio.packet import BLEPhyMode


def test_rf_metrics(phy_mode=BLEPhyMode.LE_1M, sample_rate=8e6,
                    modulation_index=0.5, bt=0.5, verbose=True):
    """
    测试 BLE RF 指标

    Args:
        phy_mode: PHY 模式
        sample_rate: 采样率
        modulation_index: 调制指数
        bt: 高斯滤波器 BT 积
        verbose: 是否打印详细信息

    Returns:
        dict: 测试结果
    """
    config = ModulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        modulation_index=modulation_index,
        bt=bt
    )
    mod = BLEModulator(config)

    N = mod.samples_per_symbol

    if verbose:
        print('=' * 60)
        print('BLE RF 测试指标验证')
        print('=' * 60)
        print(f'PHY 模式: {phy_mode.name}')
        print(f'采样率: {sample_rate/1e6:.1f} MHz')
        print(f'调制指数: {modulation_index}')
        print(f'BT: {bt}')
        print(f'脉冲长度: {len(mod.freq_pulse)} 采样点')
        print()

    # 测试 01010101 模式 (ΔF1)
    bits_0101 = np.array([0, 1] * 64)
    iq = mod.modulate(bits_0101)
    phase = np.unwrap(np.angle(iq))
    freq_inst = np.diff(phase) / (2 * np.pi) * sample_rate

    skip = 4 * N
    freq_stable = freq_inst[skip:-skip]
    delta_f1_avg = np.mean(np.abs(freq_stable))
    delta_f1_max = np.max(np.abs(freq_stable))

    # 测试 11110000 模式 (ΔF2)
    bits_f0 = np.array([1, 1, 1, 1, 0, 0, 0, 0] * 16)
    iq = mod.modulate(bits_f0)
    phase = np.unwrap(np.angle(iq))
    freq_inst = np.diff(phase) / (2 * np.pi) * sample_rate

    freq_stable = freq_inst[skip:-skip]
    delta_f2_max = np.max(np.abs(freq_stable))
    delta_f2_avg = np.mean(np.abs(freq_stable))

    # 判断结果
    f1_pass = 225e3 <= delta_f1_avg <= 275e3
    f2_pass = delta_f2_max >= 185e3
    ratio = delta_f2_avg / delta_f1_avg if delta_f1_avg > 0 else 0
    ratio_pass = ratio >= 0.8

    all_pass = f1_pass and f2_pass and ratio_pass

    if verbose:
        print('ΔF1 (01010101 模式):')
        print(f'  ΔF1avg = {delta_f1_avg/1e3:.1f} kHz (标准: 225-275 kHz)')
        print(f'  ΔF1max = {delta_f1_max/1e3:.1f} kHz')
        print(f'  结果: {"PASS" if f1_pass else "FAIL"}')
        print()

        print('ΔF2 (11110000 模式):')
        print(f'  ΔF2max = {delta_f2_max/1e3:.1f} kHz (标准: >= 185 kHz)')
        print(f'  ΔF2avg = {delta_f2_avg/1e3:.1f} kHz')
        print(f'  结果: {"PASS" if f2_pass else "FAIL"}')
        print()

        print(f'ΔF2avg / ΔF1avg = {ratio:.3f} (标准: >= 0.8)')
        print(f'  结果: {"PASS" if ratio_pass else "FAIL"}')
        print()

        print('=' * 60)
        print(f'总结: {"所有 BLE RF 指标 PASS" if all_pass else "部分指标 FAIL"}')
        print('=' * 60)

    return {
        'delta_f1_avg': delta_f1_avg,
        'delta_f1_max': delta_f1_max,
        'delta_f2_avg': delta_f2_avg,
        'delta_f2_max': delta_f2_max,
        'ratio': ratio,
        'f1_pass': f1_pass,
        'f2_pass': f2_pass,
        'ratio_pass': ratio_pass,
        'all_pass': all_pass
    }


def test_all_modes(sample_rate=8e6):
    """测试所有 PHY 模式"""
    print('=' * 70)
    print('BLE RF 指标 - 全模式测试')
    print('=' * 70)
    print()

    modes = [
        (BLEPhyMode.LE_1M, '1M PHY'),
        (BLEPhyMode.LE_2M, '2M PHY'),
    ]

    results = []
    for mode, name in modes:
        print(f'--- {name} ---')
        result = test_rf_metrics(phy_mode=mode, sample_rate=sample_rate, verbose=False)
        results.append((name, result))

        status = "PASS" if result['all_pass'] else "FAIL"
        print(f'  ΔF1avg: {result["delta_f1_avg"]/1e3:6.1f} kHz  '
              f'ΔF2max: {result["delta_f2_max"]/1e3:6.1f} kHz  '
              f'Ratio: {result["ratio"]:.3f}  [{status}]')

    print()
    return results


def compare_pulse_lengths(sample_rate=8e6):
    """比较不同脉冲跨度对 RF 指标的影响"""
    from scipy.special import erf

    def qfunc(t):
        return 0.5 * (1 - erf(t / np.sqrt(2)))

    symbol_rate = 1e6
    N = int(sample_rate / symbol_rate)
    BT = 0.5
    h = 0.5

    print('=' * 70)
    print('不同脉冲跨度 L 对 RF 指标的影响')
    print('=' * 70)
    print()
    print(f'{"L (symbols)":<12} | {"ΔF1avg (kHz)":<14} | {"ΔF2max (kHz)":<14} | {"结果":<6}')
    print('-' * 70)

    for L in [1, 2, 3, 4]:
        # 生成脉冲
        min_os_ratio = 64
        R_up = max(1, int(np.ceil(min_os_ratio / N)))

        tSym = 1.0
        Ts = tSym / (N * R_up)

        num_samples = L * N * R_up
        t = np.arange(num_samples) * Ts + Ts/2
        t = t - tSym * (L / 2)

        K = 2 * np.pi * BT / np.sqrt(np.log(2))
        g = (1 / (2 * tSym)) * (qfunc(K * (t - tSym / 2)) - qfunc(K * (t + tSym / 2)))

        q = Ts * np.cumsum(g)
        if q[-1] != 0:
            g = g * 0.5 / q[-1]

        g_reshaped = g[:num_samples // R_up * R_up].reshape(-1, R_up)
        freq_pulse = np.mean(g_reshaped, axis=1) * R_up
        freq_pulse = freq_pulse / np.sum(freq_pulse)

        # 测试 01010101
        bits_0101 = np.array([0, 1] * 64)
        symbols = 2 * bits_0101.astype(np.float64) - 1
        upsampled = np.zeros(len(symbols) * N)
        upsampled[::N] = symbols

        freq_shaped = np.convolve(upsampled, freq_pulse, mode='same')
        phase_inc = h * np.pi * freq_shaped
        phase = np.cumsum(phase_inc)

        iq = np.exp(1j * phase)
        phase_unwrap = np.unwrap(np.angle(iq))
        freq_inst = np.diff(phase_unwrap) / (2 * np.pi) * sample_rate

        skip = max(L, 4) * N
        freq_stable = freq_inst[skip:-skip]
        df1_avg = np.mean(np.abs(freq_stable))

        # 测试 11110000
        bits_f0 = np.array([1, 1, 1, 1, 0, 0, 0, 0] * 16)
        symbols = 2 * bits_f0.astype(np.float64) - 1
        upsampled = np.zeros(len(symbols) * N)
        upsampled[::N] = symbols

        freq_shaped = np.convolve(upsampled, freq_pulse, mode='same')
        phase_inc = h * np.pi * freq_shaped
        phase = np.cumsum(phase_inc)

        iq = np.exp(1j * phase)
        phase_unwrap = np.unwrap(np.angle(iq))
        freq_inst = np.diff(phase_unwrap) / (2 * np.pi) * sample_rate

        freq_stable = freq_inst[skip:-skip]
        df2_max = np.max(np.abs(freq_stable))

        # 判断
        f1_pass = 225e3 <= df1_avg <= 275e3
        f2_pass = df2_max >= 185e3
        status = 'PASS' if f1_pass and f2_pass else 'FAIL'

        print(f'{L:<12} | {df1_avg/1e3:<14.1f} | {df2_max/1e3:<14.1f} | {status:<6}')

    print()
    print('BLE 标准要求: ΔF1avg 225-275 kHz, ΔF2max >= 185 kHz')
    print('结论: L=1 (MATLAB 默认) 是唯一满足 BLE 标准的配置')
    print()


if __name__ == '__main__':
    # 测试当前配置
    test_rf_metrics()
    print()

    # 测试所有 PHY 模式
    test_all_modes()
    print()

    # 比较不同脉冲跨度
    compare_pulse_lengths()
