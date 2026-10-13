"""
BLE Studio SNR 扫描脚本
测试不同 SNR 下的解调性能
"""

from ble_studio import (
    BLEModulator, BLEDemodulator,
    ModulatorConfig, DemodulatorConfig, BLEPhyMode,
    create_advertising_packet,
)


def snr_sweep(snr_range=None, num_trials=10):
    """
    扫描不同 SNR 下的解调成功率

    Args:
        snr_range: SNR 范围列表，默认 [0, 5, 8, 10, 12, 15, 20, 25]
        num_trials: 每个 SNR 点的测试次数
    """
    if snr_range is None:
        snr_range = [0, 5, 8, 10, 12, 15, 20, 25]

    # 创建数据包
    adv_address = bytes.fromhex('112233445566')
    adv_data = bytes.fromhex('0201060908424c455374756469')
    packet = create_advertising_packet(
        adv_address=adv_address,
        adv_data=adv_data,
        channel=37
    )
    bits = packet.generate()
    tx_payload = adv_address + adv_data

    # 调制器
    modulator = BLEModulator(ModulatorConfig(
        phy_mode=BLEPhyMode.LE_1M,
        sample_rate=8e6,
        modulation_index=0.5,
        bt=0.5
    ))
    iq_signal = modulator.modulate(bits)

    # 解调器
    demodulator = BLEDemodulator(DemodulatorConfig(
        phy_mode=BLEPhyMode.LE_1M,
        sample_rate=8e6,
        access_address=0x8E89BED6,
        channel=37
    ))

    # 打印表头
    print("=" * 60)
    print("BLE Studio - SNR 扫描测试")
    print("=" * 60)
    print(f"测试次数: {num_trials} 次/SNR点")
    print(f"频偏: 50 kHz")
    print("-" * 60)
    print(f"{'SNR (dB)':>10} | {'成功率':>10} | {'CRC通过率':>10} | {'数据匹配率':>10}")
    print("-" * 60)

    results = []

    for snr in snr_range:
        success_count = 0
        crc_count = 0
        match_count = 0

        for _ in range(num_trials):
            # 添加噪声和频偏
            noisy_signal = modulator.add_noise(iq_signal, snr)
            impaired_signal = modulator.add_frequency_offset(noisy_signal, 50e3)

            # 解调
            result = demodulator.demodulate(impaired_signal)

            if result.success:
                success_count += 1
            if result.crc_valid:
                crc_count += 1

            # 检查数据匹配
            if result.success and len(result.pdu) > 2:
                rx_payload = result.pdu[2:]
                if tx_payload == rx_payload:
                    match_count += 1

        success_rate = success_count / num_trials * 100
        crc_rate = crc_count / num_trials * 100
        match_rate = match_count / num_trials * 100

        print(f"{snr:>10} | {success_rate:>9.1f}% | {crc_rate:>9.1f}% | {match_rate:>9.1f}%")

        results.append({
            'snr_db': snr,
            'success_rate': success_rate,
            'crc_rate': crc_rate,
            'match_rate': match_rate
        })

    print("-" * 60)
    print("完成!")

    return results


if __name__ == "__main__":
    # 可自定义 SNR 范围和测试次数
    snr_sweep(
        snr_range=[0, 5, 8, 10, 12, 14, 16, 18, 20],
        num_trials=20
    )
