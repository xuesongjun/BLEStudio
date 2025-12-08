"""
BLE Studio 示例程序
演示 BLE 数据包生成、调制、信道传输、解调的完整流程
支持通过配置文件自定义仿真参数
"""

import os
import yaml
from ble_studio import (
    BLEModulator, BLEDemodulator, ReportGenerator,
    ModulatorConfig, DemodulatorConfig, BLEPhyMode,
    create_advertising_packet,
)


def load_config(config_path: str = "examples/config.yaml") -> dict:
    """加载配置文件"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


def run_simulation(config: dict = None):
    """运行 BLE 仿真"""
    config = config or {}

    # ========== 1. 解析配置 ==========
    tx_cfg = config.get('tx', {})
    mod_cfg = config.get('modulation', {})
    ch_cfg = config.get('channel', {})
    out_cfg = config.get('output', {})

    # 发送端参数
    adv_address = bytes.fromhex(tx_cfg.get('adv_address', '11:22:33:44:55:66').replace(':', ''))
    adv_data = bytes.fromhex(tx_cfg.get('adv_data', '0201060908424c455374756469'))
    channel = tx_cfg.get('channel', 37)

    # 调制参数
    phy_mode = getattr(BLEPhyMode, mod_cfg.get('phy_mode', 'LE_1M'))
    sample_rate = float(mod_cfg.get('sample_rate', 8e6))
    modulation_index = float(mod_cfg.get('modulation_index', 0.5))
    bt = float(mod_cfg.get('bt', 0.5))

    # 信道参数
    snr_db = float(ch_cfg.get('snr_db', 15))
    freq_offset = float(ch_cfg.get('freq_offset', 50e3))

    # 输出配置
    output_dir = out_cfg.get('dir', 'results')

    # ========== 2. 生成数据包 ==========
    print("=" * 50)
    print("BLE Studio 仿真")
    print("=" * 50)

    packet = create_advertising_packet(
        adv_address=adv_address,
        adv_data=adv_data,
        channel=channel
    )
    bits = packet.generate()
    tx_payload = adv_address + adv_data

    print(f"[TX] Payload: {tx_payload.hex()}")
    print(f"[TX] 比特数: {len(bits)}")

    # ========== 3. 调制 ==========
    modulator = BLEModulator(ModulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        modulation_index=modulation_index,
        bt=bt
    ))
    iq_signal = modulator.modulate(bits)

    print(f"[调制] 采样率: {sample_rate/1e6} MHz, IQ长度: {len(iq_signal)}")

    # ========== 4. 添加信道损伤 ==========
    noisy_signal = modulator.add_noise(iq_signal, snr_db)
    impaired_signal = modulator.add_frequency_offset(noisy_signal, freq_offset)

    print(f"[信道] SNR: {snr_db} dB, 频偏: {freq_offset/1e3} kHz")

    # ========== 5. 解调 ==========
    demodulator = BLEDemodulator(DemodulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        access_address=0x8E89BED6,
        channel=channel
    ))
    result = demodulator.demodulate(impaired_signal)

    rx_payload = result.pdu[2:] if result.success and len(result.pdu) > 2 else None
    payload_match = (tx_payload == rx_payload) if rx_payload else False

    print(f"[RX] 解调: {'成功' if result.success else '失败'}, CRC: {'通过' if result.crc_valid else '失败'}")
    print(f"[RX] Payload: {rx_payload.hex() if rx_payload else 'N/A'}")
    print(f"[结果] 数据匹配: {'OK' if payload_match else 'FAIL'}")

    # ========== 6. 生成报告 ==========
    if out_cfg.get('html_report', True):
        results = {
            'tx': {
                'bits': len(bits),
                'payload_len': len(tx_payload),
                'adv_address': tx_cfg.get('adv_address', '11:22:33:44:55:66'),
            },
            'modulation': {
                'sample_rate_mhz': sample_rate / 1e6,
                'symbol_rate_msps': modulator.symbol_rate / 1e6,
                'modulation_index': modulation_index,
                'bt': bt,
            },
            'channel': {
                'snr_db': snr_db,
                'freq_offset_khz': freq_offset / 1e3,
            },
            'demodulation': {
                'success': result.success,
                'crc_valid': result.crc_valid,
                'rssi_db': result.rssi,
                'freq_offset_khz': result.freq_offset / 1e3,
                'tx_payload': tx_payload.hex(),
                'rx_payload': rx_payload.hex() if rx_payload else None,
                'payload_match': payload_match,
            }
        }

        reporter = ReportGenerator(output_dir)
        reporter.generate_all(results, iq_signal, impaired_signal, bits, sample_rate)

    print("=" * 50)
    print(f"完成! 打开 {output_dir}/index.html 查看结果")

    return result


if __name__ == "__main__":
    config = load_config()
    run_simulation(config)
