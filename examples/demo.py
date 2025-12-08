"""
BLE Studio 示例程序
演示 BLE 数据包生成、调制、信道传输、解调的完整流程
支持通过配置文件自定义仿真参数
支持 IQ 数据导入导出 (Verilog 仿真 / MATLAB)
"""

import os
import sys
import yaml
from pathlib import Path
from ble_studio import (
    BLEModulator, BLEDemodulator, ReportGenerator,
    ModulatorConfig, DemodulatorConfig, BLEPhyMode,
    create_advertising_packet,
    # RF Test
    RFTestPayloadType, create_test_packet,
    # IQ 导入导出
    IQExporter, IQImporter, IQExportConfig, IQImportConfig,
    IQFormat, NumberFormat,
    export_iq_txt, export_iq_verilog, import_iq_txt, import_iq_mat,
)


def load_config(config_path: str = "examples/config.yaml") -> dict:
    """加载配置文件"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


def export_iq_data(tx_signal, rx_signal, output_dir: str, cfg: dict, sample_rate: float):
    """导出 IQ 数据到文件 (用于 Verilog 硬件仿真)"""
    bit_width = int(cfg.get('bit_width', 12))
    frac_bits = int(cfg.get('frac_bits', 0))
    iq_format = cfg.get('iq_format', 'two_column')
    number_format = cfg.get('number_format', 'signed')
    add_header = cfg.get('add_header', True)
    verilog_mem = cfg.get('verilog_mem', True)

    # 创建导出配置
    export_config = IQExportConfig(
        bit_width=bit_width,
        frac_bits=frac_bits,
        iq_format=IQFormat(iq_format),
        number_format=NumberFormat(number_format),
        add_header=add_header,
    )
    exporter = IQExporter(export_config)

    q_format = f"Q{bit_width - frac_bits}.{frac_bits}"
    print(f"[IQ导出] 位宽: {bit_width}, 格式: {q_format}")

    # 导出发送端 IQ (无噪声)
    tx_file = os.path.join(output_dir, 'iq_tx.txt')
    info = exporter.export_txt(tx_signal, tx_file)
    print(f"[IQ导出] TX IQ: {tx_file} ({info['samples']} samples)")

    # 导出接收端 IQ (带噪声)
    rx_file = os.path.join(output_dir, 'iq_rx.txt')
    info = exporter.export_txt(rx_signal, rx_file)
    print(f"[IQ导出] RX IQ: {rx_file} ({info['samples']} samples)")

    # 导出 Verilog $readmemh 格式
    if verilog_mem:
        tx_mem_file = os.path.join(output_dir, 'iq_tx.mem')
        exporter.export_verilog_mem(tx_signal, tx_mem_file)
        print(f"[IQ导出] TX Verilog: {tx_mem_file}")

        rx_mem_file = os.path.join(output_dir, 'iq_rx.mem')
        exporter.export_verilog_mem(rx_signal, rx_mem_file)
        print(f"[IQ导出] RX Verilog: {rx_mem_file}")

    # 导出分离的 I/Q 文件 (某些仿真器需要)
    i_file = os.path.join(output_dir, 'iq_tx_i.txt')
    q_file = os.path.join(output_dir, 'iq_tx_q.txt')
    exporter.export_separate_files(tx_signal, i_file, q_file)
    print(f"[IQ导出] TX I/Q 分离文件: {i_file}, {q_file}")


def import_and_demodulate(config: dict):
    """导入外部 IQ 数据并解调"""
    iq_import_cfg = config.get('iq_import', {})
    mod_cfg = config.get('modulation', {})
    tx_cfg = config.get('tx', {})
    out_cfg = config.get('output', {})

    file_path = iq_import_cfg.get('file', '')
    if not file_path or not os.path.exists(file_path):
        print(f"[错误] IQ 导入文件不存在: {file_path}")
        return None

    file_type = iq_import_cfg.get('file_type', 'txt')
    bit_width = int(iq_import_cfg.get('bit_width', 12))
    frac_bits = int(iq_import_cfg.get('frac_bits', 0))
    sample_rate = float(mod_cfg.get('sample_rate', 8e6))

    print("=" * 50)
    print("BLE Studio - IQ 数据导入解调")
    print("=" * 50)
    print(f"[导入] 文件: {file_path}")
    print(f"[导入] 类型: {file_type}, 位宽: {bit_width}, Q格式: Q{bit_width-frac_bits}.{frac_bits}")

    # 导入 IQ 数据
    if file_type == 'mat':
        i_var = iq_import_cfg.get('mat_i_var', 'I')
        q_var = iq_import_cfg.get('mat_q_var', 'Q')
        complex_var = iq_import_cfg.get('mat_complex_var', '') or None
        signal, fs = import_iq_mat(file_path, i_var, q_var, complex_var)
        if fs:
            sample_rate = fs
        print(f"[导入] 采样率: {sample_rate/1e6} MHz (从 MAT 文件)")
    else:
        iq_format = iq_import_cfg.get('iq_format', 'two_column')
        number_format = iq_import_cfg.get('number_format', 'signed')
        skip_lines = int(iq_import_cfg.get('skip_lines', 0))

        signal = import_iq_txt(
            file_path,
            bit_width=bit_width,
            frac_bits=frac_bits,
            iq_format=iq_format,
            number_format=number_format,
            skip_lines=skip_lines
        )

    print(f"[导入] IQ 长度: {len(signal)} samples")

    # 解调参数
    phy_mode = getattr(BLEPhyMode, mod_cfg.get('phy_mode', 'LE_1M'))
    channel = tx_cfg.get('channel', 37)

    # 创建解调器
    demodulator = BLEDemodulator(DemodulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        access_address=0x8E89BED6,
        channel=channel
    ))

    # 解调
    result = demodulator.demodulate(signal)

    print(f"[RX] 解调: {'成功' if result.success else '失败'}, CRC: {'通过' if result.crc_valid else '失败'}")
    if result.success and result.pdu:
        print(f"[RX] PDU: {result.pdu.hex()}")
        print(f"[RX] RSSI: {result.rssi:.2f} dB")
        print(f"[RX] 频偏: {result.freq_offset/1e3:.2f} kHz")

    # 生成报告
    output_dir = out_cfg.get('dir', 'results')
    if out_cfg.get('html_report', True):
        results = {
            'import': {
                'file': file_path,
                'file_type': file_type,
                'samples': len(signal),
                'bit_width': bit_width,
            },
            'modulation': {
                'sample_rate_mhz': sample_rate / 1e6,
            },
            'demodulation': {
                'success': result.success,
                'crc_valid': result.crc_valid,
                'rssi_db': result.rssi,
                'freq_offset_khz': result.freq_offset / 1e3,
                'pdu': result.pdu.hex() if result.pdu else None,
            }
        }

        reporter = ReportGenerator(output_dir, theme=out_cfg.get('theme', 'instrument'))
        # 使用导入的信号生成图表
        reporter.generate_all(results, signal, signal, None, sample_rate)

    print("=" * 50)
    print(f"完成! 打开 {output_dir}/index.html 查看结果")

    return result


def run_simulation(config: dict = None):
    """运行 BLE 仿真"""
    config = config or {}

    # ========== 1. 解析配置 ==========
    tx_cfg = config.get('tx', {})
    mod_cfg = config.get('modulation', {})
    ch_cfg = config.get('channel', {})
    out_cfg = config.get('output', {})
    iq_export_cfg = config.get('iq_export', {})
    iq_import_cfg = config.get('iq_import', {})

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
    os.makedirs(output_dir, exist_ok=True)

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

    # ========== 5. 导出 IQ 数据 (Verilog 仿真) ==========
    if iq_export_cfg.get('enabled', False):
        export_iq_data(iq_signal, impaired_signal, output_dir, iq_export_cfg, sample_rate)

    # ========== 6. 解调 ==========
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

    # ========== 7. 生成报告 ==========
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

        reporter = ReportGenerator(output_dir, theme=out_cfg.get('theme', 'instrument'))
        reporter.generate_all(results, iq_signal, impaired_signal, bits, sample_rate)

    print(f"输出目录: {output_dir}")
    print("=" * 50)
    print(f"完成! 打开 {output_dir}/index.html 查看结果")

    return result


def run_rf_test(config: dict = None):
    """运行 BLE RF Test (DTM) 仿真"""
    config = config or {}

    # ========== 1. 解析配置 ==========
    test_cfg = config.get('rf_test', {})
    mod_cfg = config.get('modulation', {})
    ch_cfg = config.get('channel', {})
    out_cfg = config.get('output', {})

    # 测试包参数
    payload_type_str = test_cfg.get('payload_type', 'PRBS9')
    payload_type = getattr(RFTestPayloadType, payload_type_str, RFTestPayloadType.PRBS9)
    payload_length = int(test_cfg.get('payload_length', 37))
    test_channel = test_cfg.get('channel', 0)
    whitening = bool(test_cfg.get('whitening', False))

    # 调制参数
    phy_mode = getattr(BLEPhyMode, mod_cfg.get('phy_mode', 'LE_1M'))
    sample_rate = float(mod_cfg.get('sample_rate', 8e6))
    modulation_index = float(mod_cfg.get('modulation_index', 0.5))
    bt = float(mod_cfg.get('bt', 0.5))

    # 信道参数
    snr_db = float(ch_cfg.get('snr_db', 20))
    freq_offset = float(ch_cfg.get('freq_offset', 0))

    # 输出配置
    output_dir = out_cfg.get('dir', 'results')

    # ========== 2. 生成测试数据包 ==========
    print("=" * 50)
    print("BLE RF Test (DTM) 仿真")
    print("=" * 50)

    packet = create_test_packet(
        payload_type=payload_type,
        payload_length=payload_length,
        channel=test_channel,
        phy_mode=phy_mode,
        whitening=whitening
    )
    bits = packet.generate()
    test_info = packet.get_test_info()

    print(f"[DTM] 测试模式: {test_info['payload_type']}")
    print(f"[DTM] 负载长度: {test_info['payload_length']} bytes")
    print(f"[DTM] PHY: {test_info['phy_mode']}")
    print(f"[DTM] 信道: {test_info['channel']} ({test_info['frequency_mhz']} MHz)")
    print(f"[DTM] 接入地址: {test_info['access_address']}")
    print(f"[DTM] 白化: {'开启' if whitening else '关闭'}")
    print(f"[DTM] 比特数: {len(bits)}")

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
        access_address=0x71764129,  # DTM 接入地址
        channel=test_channel,
        whitening=whitening  # 与 TX 保持一致
    ))
    result = demodulator.demodulate(impaired_signal)

    # 验证测试负载
    tx_payload = packet.test_payload
    rx_payload = result.pdu[2:] if result.success and len(result.pdu) > 2 else None
    payload_match = (tx_payload == rx_payload) if rx_payload else False

    print(f"[RX] 解调: {'成功' if result.success else '失败'}, CRC: {'通过' if result.crc_valid else '失败'}")
    print(f"[RX] Payload 前16字节: {rx_payload[:16].hex() if rx_payload else 'N/A'}")
    print(f"[结果] 数据匹配: {'OK' if payload_match else 'FAIL'}")

    # ========== 6. 生成报告 ==========
    if out_cfg.get('html_report', True):
        results = {
            'tx': {
                'bits': len(bits),
                'payload_len': payload_length,
                'test_mode': test_info['payload_type'],
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
                'tx_payload': tx_payload[:32].hex() + ('...' if len(tx_payload) > 32 else ''),
                'rx_payload': (rx_payload[:32].hex() + ('...' if len(rx_payload) > 32 else '')) if rx_payload else None,
                'payload_match': payload_match,
            },
            'rf_test': test_info,
        }

        reporter = ReportGenerator(output_dir, theme=out_cfg.get('theme', 'instrument'))
        reporter.generate_all(results, iq_signal, impaired_signal, bits, sample_rate)

    print("=" * 50)
    print(f"完成! 打开 {output_dir}/index.html 查看结果")

    return result


if __name__ == "__main__":
    # 支持命令行指定配置文件
    config_path = sys.argv[1] if len(sys.argv) > 1 else "examples/config.yaml"
    config = load_config(config_path)

    # 检查是否为 IQ 导入模式
    iq_import_cfg = config.get('iq_import', {})
    if iq_import_cfg.get('file', ''):
        # IQ 数据导入解调模式
        import_and_demodulate(config)
    else:
        # 根据配置选择仿真模式
        mode = config.get('mode', 'advertising')
        if mode == 'rf_test' or mode == 'dtm':
            run_rf_test(config)
        else:
            run_simulation(config)
