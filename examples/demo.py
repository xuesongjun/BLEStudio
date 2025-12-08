"""
BLE Studio 示例程序
演示 BLE 数据包生成、调制、信道传输、解调的完整流程

数据流架构:
    BLE TX → [信道入口: 可导入外部IQ] → 信道模型 → [信道出口: 可导出IQ] → BLE RX

支持:
- 通过配置文件自定义仿真参数
- 信道入口: 导入 IQ 数据 (txt/mat) 替代 TX 输出
- 信道出口: 导出 IQ 数据 (txt/mat) 给外部使用
"""

import os
import sys
import yaml
import numpy as np
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


def export_iq_to_mat(signal: np.ndarray, file_path: str, sample_rate: float,
                     var_name: str = 'iq'):
    """导出 IQ 数据到 MATLAB .mat 文件"""
    try:
        from scipy.io import savemat
        mat_data = {
            var_name: signal,
            'I': signal.real,
            'Q': signal.imag,
            'fs': sample_rate,
            'sample_rate': sample_rate,
        }
        savemat(file_path, mat_data)
        return True
    except ImportError:
        print("[警告] scipy 未安装, 无法导出 .mat 文件")
        return False


def import_channel_input(config: dict, sample_rate: float) -> tuple:
    """
    信道入口: 导入 IQ 数据替代 TX 输出

    Args:
        config: channel_input 配置
        sample_rate: 采样率

    Returns:
        (iq_signal, actual_sample_rate) 或 (None, None) 如果未配置导入
    """
    if not config.get('enabled', False):
        return None, sample_rate

    file_path = config.get('file', '')
    if not file_path or not os.path.exists(file_path):
        print(f"[信道入口] 文件不存在: {file_path}")
        return None, sample_rate

    file_type = config.get('file_type', 'auto')
    if file_type == 'auto':
        # 根据扩展名自动判断
        ext = Path(file_path).suffix.lower()
        file_type = 'mat' if ext == '.mat' else 'txt'

    print(f"[信道入口] 导入文件: {file_path} ({file_type})")

    if file_type == 'mat':
        # MATLAB .mat 文件
        i_var = config.get('mat_i_var', 'I')
        q_var = config.get('mat_q_var', 'Q')
        complex_var = config.get('mat_complex_var', '') or None
        signal, fs = import_iq_mat(file_path, i_var, q_var, complex_var)
        if fs:
            sample_rate = fs
        print(f"[信道入口] 导入 {len(signal)} samples, 采样率: {sample_rate/1e6:.2f} MHz")
    else:
        # 文本文件 (txt)
        bit_width = int(config.get('bit_width', 12))
        frac_bits = int(config.get('frac_bits', 0))
        iq_format = config.get('iq_format', 'two_column')
        number_format = config.get('number_format', 'signed')
        skip_lines = int(config.get('skip_lines', 0))

        signal = import_iq_txt(
            file_path,
            bit_width=bit_width,
            frac_bits=frac_bits,
            iq_format=iq_format,
            number_format=number_format,
            skip_lines=skip_lines
        )
        print(f"[信道入口] 导入 {len(signal)} samples (位宽: {bit_width}, Q{bit_width-frac_bits}.{frac_bits})")

    return signal, sample_rate


def export_channel_output(signal: np.ndarray, config: dict, output_dir: str,
                          sample_rate: float, prefix: str = 'channel_out'):
    """
    信道出口: 导出 IQ 数据

    Args:
        signal: IQ 信号
        config: channel_output 配置
        output_dir: 输出目录
        sample_rate: 采样率
        prefix: 文件名前缀
    """
    if not config.get('enabled', False):
        return

    os.makedirs(output_dir, exist_ok=True)

    # 导出配置
    bit_width = int(config.get('bit_width', 12))
    frac_bits = int(config.get('frac_bits', 0))
    iq_format = config.get('iq_format', 'two_column')
    number_format = config.get('number_format', 'signed')
    add_header = config.get('add_header', True)

    export_config = IQExportConfig(
        bit_width=bit_width,
        frac_bits=frac_bits,
        iq_format=IQFormat(iq_format),
        number_format=NumberFormat(number_format),
        add_header=add_header,
    )
    exporter = IQExporter(export_config)

    q_format = f"Q{bit_width - frac_bits}.{frac_bits}"
    print(f"[信道出口] 导出配置: 位宽={bit_width}, 格式={q_format}")

    # 导出 txt 文件
    if config.get('export_txt', True):
        txt_file = os.path.join(output_dir, f'{prefix}.txt')
        info = exporter.export_txt(signal, txt_file)
        print(f"[信道出口] TXT: {txt_file} ({info['samples']} samples)")

    # 导出 Verilog $readmemh 格式
    if config.get('export_verilog', False):
        mem_file = os.path.join(output_dir, f'{prefix}.mem')
        exporter.export_verilog_mem(signal, mem_file)
        print(f"[信道出口] Verilog MEM: {mem_file}")

    # 导出 MATLAB .mat 文件
    if config.get('export_mat', True):
        mat_file = os.path.join(output_dir, f'{prefix}.mat')
        if export_iq_to_mat(signal, mat_file, sample_rate):
            print(f"[信道出口] MAT: {mat_file}")

    # 导出分离的 I/Q 文件
    if config.get('export_separate', False):
        i_file = os.path.join(output_dir, f'{prefix}_i.txt')
        q_file = os.path.join(output_dir, f'{prefix}_q.txt')
        exporter.export_separate_files(signal, i_file, q_file)
        print(f"[信道出口] 分离文件: {i_file}, {q_file}")


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
    """
    运行 BLE RF Test (DTM) 仿真

    数据流:
        TX → [信道入口] → 信道模型 → [信道出口] → RX
    """
    config = config or {}

    # ========== 1. 解析配置 ==========
    test_cfg = config.get('rf_test', {})
    mod_cfg = config.get('modulation', {})
    ch_cfg = config.get('channel', {})
    out_cfg = config.get('output', {})
    ch_input_cfg = config.get('channel_input', {})   # 信道入口配置
    ch_output_cfg = config.get('channel_output', {})  # 信道出口配置

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
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("BLE RF Test (DTM) 仿真")
    print("=" * 60)

    # ========== 2. TX: 生成测试数据包 ==========
    packet = create_test_packet(
        payload_type=payload_type,
        payload_length=payload_length,
        channel=test_channel,
        phy_mode=phy_mode,
        whitening=whitening
    )
    bits = packet.generate()
    test_info = packet.get_test_info()
    tx_payload = packet.test_payload

    print(f"[TX] 测试模式: {test_info['payload_type']}")
    print(f"[TX] 负载长度: {test_info['payload_length']} bytes")
    print(f"[TX] PHY: {test_info['phy_mode']}")
    print(f"[TX] 信道: {test_info['channel']} ({test_info['frequency_mhz']} MHz)")
    print(f"[TX] 白化: {'开启' if whitening else '关闭'}")

    # ========== 3. 调制 ==========
    modulator = BLEModulator(ModulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        modulation_index=modulation_index,
        bt=bt
    ))
    tx_iq_signal = modulator.modulate(bits)
    print(f"[TX] IQ 长度: {len(tx_iq_signal)} samples")

    # ========== 4. 信道入口: 检查是否导入外部 IQ 数据 ==========
    imported_signal, sample_rate = import_channel_input(ch_input_cfg, sample_rate)
    if imported_signal is not None:
        # 使用导入的 IQ 数据替代 TX 输出
        channel_input_signal = imported_signal
        print(f"[信道入口] 使用外部 IQ 数据替代 TX 输出")
        # 如果是导入模式，TX 信号仍保留用于对比
        tx_iq_signal_for_display = tx_iq_signal
    else:
        # 使用 TX 产生的 IQ 数据
        channel_input_signal = tx_iq_signal
        tx_iq_signal_for_display = tx_iq_signal
        print(f"[信道入口] 使用 TX 输出")

    # ========== 5. 信道模型: 添加损伤 ==========
    print(f"[信道] SNR: {snr_db} dB, 频偏: {freq_offset/1e3} kHz")
    noisy_signal = modulator.add_noise(channel_input_signal, snr_db)
    channel_output_signal = modulator.add_frequency_offset(noisy_signal, freq_offset)

    # ========== 6. 信道出口: 导出 IQ 数据 ==========
    # 导出 TX 理想信号 (信道传输前)
    if ch_output_cfg.get('export_tx', True):
        export_channel_output(
            tx_iq_signal_for_display,
            ch_output_cfg,
            output_dir,
            sample_rate,
            prefix='iq_tx_ideal'
        )

    # 导出信道输出 (送给 RX 的损伤信号)
    export_channel_output(
        channel_output_signal,
        ch_output_cfg,
        output_dir,
        sample_rate,
        prefix='iq_channel_out'
    )

    # ========== 7. RX: 解调 ==========
    demodulator = BLEDemodulator(DemodulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        access_address=0x71764129,  # DTM 接入地址
        channel=test_channel,
        whitening=whitening
    ))
    result = demodulator.demodulate(channel_output_signal)

    # 验证测试负载
    rx_payload = result.pdu[2:] if result.success and len(result.pdu) > 2 else None
    payload_match = (tx_payload == rx_payload) if rx_payload else False

    print(f"[RX] 解调: {'成功' if result.success else '失败'}, CRC: {'通过' if result.crc_valid else '失败'}")
    print(f"[RX] RSSI: {result.rssi:.1f} dB, 频偏估计: {result.freq_offset/1e3:.1f} kHz")
    if rx_payload:
        print(f"[RX] Payload 前16字节: {rx_payload[:16].hex()}")
    print(f"[结果] 数据匹配: {'OK' if payload_match else 'FAIL'}")

    # ========== 8. 生成报告 ==========
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
                'input_source': '外部导入' if imported_signal is not None else 'TX 输出',
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
        reporter.generate_all(results, tx_iq_signal_for_display, channel_output_signal, bits, sample_rate)

    print("=" * 60)
    print(f"完成! 输出目录: {output_dir}")
    print(f"打开 {output_dir}/index.html 查看结果")

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
