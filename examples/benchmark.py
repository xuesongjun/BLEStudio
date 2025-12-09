"""
BLE Studio 解调器性能测试工具

测试不同 Eb/N0 下的 PER (Packet Error Rate)，
并与 CEVA BLE IP 指标进行对比。

用法:
    python examples/benchmark.py [选项]

选项:
    --trials N      每个测试点的试验次数 (默认: 50)
    --phy MODE      PHY 模式: 1M, 2M, all (默认: all)
    --quick         快速模式 (10 次试验)
    --verbose       显示详细信息
"""

import sys
import argparse
import numpy as np

sys.path.insert(0, '.')

from ble_studio import (
    BLEModulator, BLEDemodulator, ModulatorConfig, DemodulatorConfig,
    BLEPhyMode, create_test_packet, RFTestPayloadType,
    BLEChannel, ChannelConfig, ChannelType
)


def test_per(phy_mode: BLEPhyMode, ebn0_db: float, num_trials: int = 50,
             verbose: bool = False) -> dict:
    """
    测试指定 Eb/N0 下的 PER

    Args:
        phy_mode: PHY 模式
        ebn0_db: Eb/N0 (dB)
        num_trials: 试验次数
        verbose: 是否显示详细信息

    Returns:
        测试结果字典
    """
    symbol_rate = 2e6 if phy_mode == BLEPhyMode.LE_2M else 1e6
    sample_rate = 8e6

    errors = 0
    crc_errors = 0
    sync_errors = 0

    for trial in range(num_trials):
        np.random.seed(trial * 1000 + int(ebn0_db * 100))

        # 创建测试包
        packet = create_test_packet(
            payload_type=RFTestPayloadType.PRBS9,
            payload_length=37,
            channel=0,
            phy_mode=phy_mode,
            whitening=False
        )
        bits = packet.generate()

        # 调制
        modulator = BLEModulator(ModulatorConfig(
            phy_mode=phy_mode,
            sample_rate=sample_rate,
            modulation_index=0.5,
            bt=0.5
        ))
        tx_signal = modulator.modulate(bits)

        # 添加噪声
        channel = BLEChannel(ChannelConfig(
            channel_type=ChannelType.AWGN,
            sample_rate=sample_rate,
            symbol_rate=symbol_rate,
            snr_db=ebn0_db,
            frequency_offset=0
        ))
        rx_signal = channel.apply(tx_signal)

        # 解调
        demodulator = BLEDemodulator(DemodulatorConfig(
            phy_mode=phy_mode,
            sample_rate=sample_rate,
            access_address=0x71764129,
            channel=0,
            whitening=False,
            use_matched_filter=True,
            bt=0.5
        ))
        result = demodulator.demodulate(rx_signal)

        if not result.success:
            errors += 1
            if not result.crc_valid:
                crc_errors += 1
            else:
                sync_errors += 1

    per = errors / num_trials * 100
    return {
        'per': per,
        'errors': errors,
        'crc_errors': crc_errors,
        'sync_errors': sync_errors,
        'trials': num_trials
    }


def find_threshold(phy_mode: BLEPhyMode, target_per: float = 30.0,
                   num_trials: int = 50) -> float:
    """
    二分查找指定 PER 对应的 Eb/N0 门限

    Args:
        phy_mode: PHY 模式
        target_per: 目标 PER (%)
        num_trials: 每次测试的试验次数

    Returns:
        Eb/N0 门限 (dB)
    """
    low, high = 8.0, 25.0

    while high - low > 0.5:
        mid = (low + high) / 2
        result = test_per(phy_mode, mid, num_trials)
        if result['per'] > target_per:
            low = mid
        else:
            high = mid

    return (low + high) / 2


def print_comparison():
    """打印与 CEVA 的对比说明"""
    print("\n" + "=" * 60)
    print("CEVA BLE IP 参考指标 (@ 30.8% PER)")
    print("=" * 60)
    print("  LE 1M: 9.5 dB SNR (带内 1MHz)")
    print("  LE 2M: 9.5 dB SNR (带内 2MHz)")
    print()
    print("转换为 Eb/N0 (8MHz 采样率):")
    print("  LE 1M: 9.5 + 10*log10(8/1) = 18.5 dB")
    print("  LE 2M: 9.5 + 10*log10(8/2) = 15.5 dB")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='BLE Studio 解调器性能测试',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python examples/benchmark.py              # 完整测试
  python examples/benchmark.py --quick      # 快速测试
  python examples/benchmark.py --phy 1M     # 只测试 LE 1M
  python examples/benchmark.py --trials 100 # 100 次试验
        """
    )
    parser.add_argument('--trials', type=int, default=50,
                        help='每个测试点的试验次数 (默认: 50)')
    parser.add_argument('--phy', choices=['1M', '2M', 'all'], default='all',
                        help='PHY 模式 (默认: all)')
    parser.add_argument('--quick', action='store_true',
                        help='快速模式 (10 次试验)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='显示详细信息')
    parser.add_argument('--find-threshold', action='store_true',
                        help='查找 30%% PER 对应的门限')

    args = parser.parse_args()

    num_trials = 10 if args.quick else args.trials

    print("=" * 60)
    print("BLE Studio 解调器性能测试")
    print("=" * 60)
    print(f"试验次数: {num_trials}")
    print()

    # 确定要测试的 PHY 模式
    if args.phy == '1M':
        phy_modes = [(BLEPhyMode.LE_1M, 'LE_1M')]
    elif args.phy == '2M':
        phy_modes = [(BLEPhyMode.LE_2M, 'LE_2M')]
    else:
        phy_modes = [
            (BLEPhyMode.LE_1M, 'LE_1M'),
            (BLEPhyMode.LE_2M, 'LE_2M')
        ]

    results = {}

    for phy_mode, name in phy_modes:
        print(f"\n=== {name} ===")

        # 测试范围
        if phy_mode == BLEPhyMode.LE_1M:
            ebn0_range = [12, 13, 14, 15, 16, 17, 18, 19, 20]
        else:
            ebn0_range = [10, 11, 12, 13, 14, 15, 16, 17, 18]

        print(f"{'Eb/N0(dB)':>10} {'PER':>8} {'错误':>6} {'状态':>8}")
        print("-" * 36)

        mode_results = []
        for ebn0 in ebn0_range:
            result = test_per(phy_mode, ebn0, num_trials, args.verbose)
            per = result['per']
            errors = result['errors']

            # 状态标记
            if per == 0:
                status = "PERFECT"
            elif per < 10:
                status = "GOOD"
            elif per < 30:
                status = "OK"
            elif per < 50:
                status = "MARGINAL"
            else:
                status = "FAIL"

            print(f"{ebn0:>10} {per:>7.1f}% {errors:>6} {status:>8}")
            mode_results.append((ebn0, per))

        results[name] = mode_results

        # 查找门限
        if args.find_threshold:
            print(f"\n正在查找 30% PER 门限...")
            threshold = find_threshold(phy_mode, 30.0, num_trials)
            print(f"  {name} @ 30% PER: {threshold:.1f} dB Eb/N0")

    # 总结
    print("\n" + "=" * 60)
    print("性能总结")
    print("=" * 60)

    for name, mode_results in results.items():
        # 找到 PER < 10% 的最低 Eb/N0
        good_points = [(e, p) for e, p in mode_results if p < 10]
        if good_points:
            threshold = good_points[0][0]
            print(f"  {name}: ~{threshold} dB Eb/N0 @ <10% PER")
        else:
            print(f"  {name}: 未达到 <10% PER")

    # 与 CEVA 对比
    print_comparison()

    print("\n差距分析:")
    if 'LE_1M' in results:
        # 估算 30% PER 点
        le1m_results = results['LE_1M']
        for i, (e, p) in enumerate(le1m_results):
            if p < 30 and i > 0:
                prev_e, prev_p = le1m_results[i-1]
                # 线性插值
                threshold = prev_e + (30 - prev_p) / (p - prev_p) * (e - prev_e)
                gap = threshold - 18.5
                print(f"  LE_1M @ 30% PER: ~{threshold:.1f} dB (vs CEVA 18.5 dB, 差距: {gap:+.1f} dB)")
                break

    if 'LE_2M' in results:
        le2m_results = results['LE_2M']
        for i, (e, p) in enumerate(le2m_results):
            if p < 30 and i > 0:
                prev_e, prev_p = le2m_results[i-1]
                threshold = prev_e + (30 - prev_p) / (p - prev_p) * (e - prev_e)
                gap = threshold - 15.5
                print(f"  LE_2M @ 30% PER: ~{threshold:.1f} dB (vs CEVA 15.5 dB, 差距: {gap:+.1f} dB)")
                break

    print()


if __name__ == '__main__':
    main()
