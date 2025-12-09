"""
RF 指标测试脚本 - 验证 ΔF1/ΔF2 计算是否符合 BLE RF-PHY 规范

BLE RF-PHY 规范要求:
- ΔF1: 使用 0x0F (11110000) pattern 测量
  - f1_ccf: 每个 00001111 序列的中心频率
  - ΔF1_max: 第 2,3,6,7 bit 的平均频率相对于 f1_ccf 的偏移
  - 要求: 225 kHz ≤ ΔF1_avg ≤ 275 kHz (modulation index = 0.5)

- ΔF2: 使用 0x55 (10101010) pattern 测量
  - f2_ccf: 每个 10101010 序列的中心频率
  - ΔF2_max: 每个 bit 的最大采样值相对于 f2_ccf 的偏移
  - 要求: ΔF2_avg ≥ 185 kHz, ΔF2/ΔF1 ≥ 0.8
"""

import numpy as np
from ble_studio import (
    BLEModulator, ModulatorConfig, BLEPhyMode,
    create_test_packet, RFTestPayloadType,
    BLEVisualizer
)

def test_rf_metrics():
    # 配置
    sample_rate = 8e6
    phy_mode = BLEPhyMode.LE_1M
    symbol_rate = 1e6
    samples_per_symbol = int(sample_rate / symbol_rate)
    modulation_index = 0.5

    # 理论频偏: Δf = h × symbol_rate / 2 = 0.5 × 1e6 / 2 = 250 kHz
    theoretical_deviation = modulation_index * symbol_rate / 2
    print(f"理论频偏: ±{theoretical_deviation/1e3:.0f} kHz")
    print(f"采样率: {sample_rate/1e6} MHz, 每符号采样数: {samples_per_symbol}")
    print()

    # 创建调制器
    modulator = BLEModulator(ModulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        modulation_index=modulation_index,
        bt=0.5
    ))

    viz = BLEVisualizer()

    # ========== 分析频率脉冲 ==========
    print("=" * 60)
    print("频率脉冲分析")
    print("=" * 60)

    # 频率脉冲形状
    freq_pulse = modulator.freq_pulse
    phase_pulse = modulator.phase_pulse

    print(f"频率脉冲长度: {len(freq_pulse)} samples ({len(freq_pulse)/samples_per_symbol} symbols)")
    print(f"频率脉冲峰值: {np.max(freq_pulse):.4f}")
    print(f"频率脉冲总和: {np.sum(freq_pulse):.4f}")

    # 计算实际瞬时频率峰值
    # 瞬时频率 = d(phase)/dt = d(h * phase_pulse * 2π) / (1/fs) = h * freq_pulse * 2π * fs
    # 但 freq_pulse 已经是归一化的，需要乘以 symbol_rate
    actual_freq_peak = np.max(freq_pulse) * symbol_rate * modulation_index
    print(f"实际频率峰值 (单符号): {actual_freq_peak/1e3:.1f} kHz")
    print()

    # ========== 测试 ΔF1 (0x0F pattern) ==========
    print("=" * 60)
    print("ΔF1 测试 (PATTERN_11110000 / 0x0F)")
    print("=" * 60)

    packet_f0 = create_test_packet(
        payload_type=RFTestPayloadType.PATTERN_11110000,
        payload_length=37,
        channel=0,
        phy_mode=phy_mode,
        whitening=False
    )
    bits_f0 = packet_f0.generate()
    signal_f0 = modulator.modulate(bits_f0)

    metrics_f0 = viz.calculate_rf_metrics(
        signal_f0, sample_rate, samples_per_symbol,
        'PATTERN_11110000'
    )

    print(f"ΔF1_avg: {metrics_f0['delta_f1_avg']:.1f} kHz")
    print(f"ΔF1_max: {metrics_f0['delta_f1_max']:.1f} kHz")
    print(f"ΔF1_min: {metrics_f0['delta_f1_min']:.1f} kHz")
    print(f"规范要求: 225 kHz ≤ ΔF1_avg ≤ 275 kHz")
    print(f"PASS: {metrics_f0['delta_f1_pass']}")
    print()

    # ========== 测试 ΔF2 (0x55 pattern) ==========
    print("=" * 60)
    print("ΔF2 测试 (PATTERN_10101010 / 0x55)")
    print("=" * 60)

    packet_55 = create_test_packet(
        payload_type=RFTestPayloadType.PATTERN_10101010,
        payload_length=37,
        channel=0,
        phy_mode=phy_mode,
        whitening=False
    )
    bits_55 = packet_55.generate()
    signal_55 = modulator.modulate(bits_55)

    metrics_55 = viz.calculate_rf_metrics(
        signal_55, sample_rate, samples_per_symbol,
        'PATTERN_10101010'
    )

    print(f"ΔF2_avg: {metrics_55['delta_f2_avg']:.1f} kHz")
    print(f"ΔF2_max: {metrics_55['delta_f2_max']:.1f} kHz")
    print(f"规范要求: ΔF2_avg ≥ 185 kHz")
    print(f"PASS: {metrics_55['delta_f2_pass']}")
    print()

    # ========== 分析 0x0F pattern 的详细频率 ==========
    print("=" * 60)
    print("0x0F Pattern 详细分析")
    print("=" * 60)

    # 计算瞬时频率
    phase = np.unwrap(np.angle(signal_f0))
    freq_inst = np.diff(phase) * sample_rate / (2 * np.pi)

    # 跳过头部: 前导码(8) + 接入地址(32) + PDU头(16) = 56 bits
    header_samples = 56 * samples_per_symbol
    freq_payload = freq_inst[header_samples:]

    # 跳过前 4 bits，取第一个 8-bit 序列
    measure_start = 4 * samples_per_symbol
    seq_freq = freq_payload[measure_start:measure_start + 8*samples_per_symbol]

    print("第一个 00001111 序列 (8 bits):")
    print("Bit 模式: 1 1 1 1 0 0 0 0 (transmission order)")
    print()

    for bit_idx in range(8):
        bit_start = bit_idx * samples_per_symbol
        bit_end = bit_start + samples_per_symbol
        bit_freq = seq_freq[bit_start:bit_end]
        bit_avg = np.mean(bit_freq)
        bit_max = bit_freq[np.argmax(np.abs(bit_freq))]
        expected_bit = 1 if bit_idx < 4 else 0
        print(f"  Bit {bit_idx+1} (expected={expected_bit}): avg={bit_avg/1e3:+.1f} kHz, max={bit_max/1e3:+.1f} kHz")

    # 计算 f1_ccf
    f1_ccf = np.mean(seq_freq)
    print(f"\nf1_ccf (序列中心频率): {f1_ccf/1e3:.1f} kHz")

    # 计算 ΔF1_max (第 2,3,6,7 bit)
    delta_f1_bits = []
    for bit_idx in [1, 2, 5, 6]:  # 0-indexed
        bit_start = bit_idx * samples_per_symbol
        bit_end = bit_start + samples_per_symbol
        bit_freq = seq_freq[bit_start:bit_end]
        bit_avg = np.mean(bit_freq)
        delta = abs(bit_avg - f1_ccf)
        delta_f1_bits.append(delta)
        print(f"  Bit {bit_idx+1}: |avg - f1_ccf| = {delta/1e3:.1f} kHz")

    delta_f1_max = np.mean(delta_f1_bits)
    print(f"\nΔF1_max (平均): {delta_f1_max/1e3:.1f} kHz")


if __name__ == "__main__":
    test_rf_metrics()
