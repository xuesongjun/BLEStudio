"""
BLE Studio 仿真程序

数据流: TX → [信道入口] → 信道模型 → [信道出口] → RX

配置结构:
    common   - 公共参数 (模式、信道号)
    tx       - 发送端参数
    channel  - 信道模型参数
    rx       - 接收端参数 (预留)
    io       - 数据导入导出
    output   - 输出配置
"""

import os
import sys
import yaml
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple

from ble_studio import (
    BLEModulator, BLEDemodulator, ReportGenerator,
    ModulatorConfig, DemodulatorConfig, BLEPhyMode,
    create_advertising_packet, create_test_packet,
    RFTestPayloadType,
    BLEChannel, ChannelConfig, ChannelType,
    IQExporter, IQExportConfig, IQFormat, NumberFormat,
    import_iq_txt, import_iq_mat,
    calculate_rf_metrics,
)


# ============================================================
# 配置解析
# ============================================================
@dataclass
class SimConfig:
    """仿真配置"""
    # 公共参数
    mode: str = "rf_test"
    channel: int = 0

    # TX 参数
    phy_mode: BLEPhyMode = BLEPhyMode.LE_1M
    sample_rate: float = 8e6
    modulation_index: float = 0.5
    bt: float = 0.5

    # TX - 广播模式
    adv_address: bytes = b'\x11\x22\x33\x44\x55\x66'
    adv_data: bytes = b'\x02\x01\x06\x09\x08BLEStudi'

    # TX - RF Test 模式
    payload_type: RFTestPayloadType = RFTestPayloadType.PRBS9
    payload_length: int = 37
    whitening: bool = False

    # 信道参数
    channel_type: ChannelType = ChannelType.AWGN
    snr_db: float = 15.0
    freq_offset: float = 0.0
    doppler_freq: float = 1.0      # 多普勒频率 (Hz)
    k_factor: float = 4.0          # 莱斯 K 因子

    # 输出配置
    output_dir: str = "results"
    html_report: bool = True
    theme: str = "instrument"

    # IO 配置
    io_input: dict = None
    io_output: dict = None

    @classmethod
    def from_dict(cls, cfg: dict) -> 'SimConfig':
        """从配置字典创建"""
        common = cfg.get('common', {})
        tx = cfg.get('tx', {})
        ch = cfg.get('channel', {})
        out = cfg.get('output', {})
        io_cfg = cfg.get('io', {})

        return cls(
            mode=common.get('mode', 'rf_test'),
            channel=common.get('channel', 0),
            phy_mode=getattr(BLEPhyMode, tx.get('phy_mode', 'LE_1M')),
            sample_rate=float(tx.get('sample_rate', 8e6)),
            modulation_index=float(tx.get('modulation_index', 0.5)),
            bt=float(tx.get('bt', 0.5)),
            adv_address=bytes.fromhex(tx.get('adv_address', '11:22:33:44:55:66').replace(':', '')),
            adv_data=bytes.fromhex(tx.get('adv_data', '0201060908424c455374756469')),
            payload_type=getattr(RFTestPayloadType, tx.get('payload_type', 'PRBS9')),
            payload_length=int(tx.get('payload_length', 37)),
            whitening=bool(tx.get('whitening', False)),
            channel_type=ChannelType(ch.get('type', 'awgn')),
            # 支持 ebn0_db (新) 或 snr_db (旧) 字段名
            snr_db=float(ch.get('ebn0_db', ch.get('snr_db', 15))),
            freq_offset=float(ch.get('freq_offset', 0)),
            doppler_freq=float(ch.get('doppler_freq', 1.0)),
            k_factor=float(ch.get('k_factor', 4.0)),
            output_dir=out.get('dir', 'results'),
            html_report=out.get('html_report', True),
            theme=out.get('theme', 'instrument'),
            io_input=io_cfg.get('input', {}),
            io_output=io_cfg.get('output', {}),
        )


# ============================================================
# IO 操作
# ============================================================
def import_iq(config: dict, default_sample_rate: float) -> Tuple[Optional[np.ndarray], float]:
    """导入 IQ 数据"""
    if not config or not config.get('enabled', False):
        return None, default_sample_rate

    file_path = config.get('file', '')
    if not file_path or not os.path.exists(file_path):
        print(f"[IO] 文件不存在: {file_path}")
        return None, default_sample_rate

    # 自动判断文件类型
    file_type = config.get('file_type', 'auto')
    if file_type == 'auto':
        ext = Path(file_path).suffix.lower()
        file_type = 'mat' if ext in ('.mat', '.bwv') else 'txt'

    print(f"[IO] 导入: {file_path}")

    if file_type == 'mat':
        complex_var = config.get('mat_complex_var', '') or None
        signal, fs = import_iq_mat(
            file_path,
            config.get('mat_i_var', 'I'),
            config.get('mat_q_var', 'Q'),
            complex_var
        )
        sample_rate = fs if fs else default_sample_rate
    else:
        signal = import_iq_txt(
            file_path,
            bit_width=int(config.get('bit_width', 12)),
            iq_format=config.get('iq_format', 'two_column'),
            number_format=config.get('number_format', 'signed'),
            skip_lines=int(config.get('skip_lines', 0))
        )
        sample_rate = default_sample_rate

    print(f"[IO] 已导入 {len(signal)} samples @ {sample_rate/1e6:.2f} MHz")

    # 检测并裁剪前导空白区域 (仅当空白超过一定比例时)
    amplitude = np.abs(signal)
    threshold = np.max(amplitude) * 0.01  # 1% 阈值
    signal_start = np.argmax(amplitude > threshold)

    # 只有当空白占比超过 5% 时才裁剪
    if signal_start > len(signal) * 0.05:
        original_len = len(signal)
        signal = signal[signal_start:]
        print(f"[IO] 裁剪前导空白: 跳过 {signal_start} samples ({signal_start/sample_rate*1e6:.1f} μs)")
    elif signal_start > 0:
        print(f"[IO] 检测到前导空白 {signal_start} samples ({signal_start/sample_rate*1e6:.1f} μs), 保留用于解调")

    return signal, sample_rate


def export_iq(signal: np.ndarray, config: dict, output_dir: str,
              sample_rate: float, prefix: str):
    """导出 IQ 数据"""
    if not config or not config.get('enabled', False):
        return

    os.makedirs(output_dir, exist_ok=True)

    export_cfg = IQExportConfig(
        bit_width=int(config.get('bit_width', 12)),
        iq_format=IQFormat(config.get('iq_format', 'two_column')),
        number_format=NumberFormat(config.get('number_format', 'signed')),
        add_header=config.get('add_header', True),
        scale_to_full=config.get('scale_to_full', True),
    )
    exporter = IQExporter(export_cfg)

    # TXT
    if config.get('export_txt', True):
        exporter.export_txt(signal, os.path.join(output_dir, f'{prefix}.txt'))

    # MAT
    if config.get('export_mat', True):
        try:
            from scipy.io import savemat
            savemat(os.path.join(output_dir, f'{prefix}.mat'), {
                'iq': signal, 'I': signal.real, 'Q': signal.imag, 'fs': sample_rate
            })
        except ImportError:
            pass

    # Verilog
    if config.get('export_verilog', False):
        exporter.export_verilog_mem(signal, os.path.join(output_dir, f'{prefix}.mem'))

    print(f"[IO] 导出: {prefix}.* ({len(signal)} samples)")


# ============================================================
# 仿真核心
# ============================================================
def run_simulation(cfg: SimConfig, raw_config: dict):
    """运行仿真"""
    print("=" * 60)
    print(f"BLE Studio - {cfg.mode.upper()} 模式")
    print("=" * 60)

    # 1. TX: 生成数据包
    if cfg.mode == 'rf_test' or cfg.mode == 'dtm':
        packet = create_test_packet(
            payload_type=cfg.payload_type,
            payload_length=cfg.payload_length,
            channel=cfg.channel,
            phy_mode=cfg.phy_mode,
            whitening=cfg.whitening
        )
        test_info = packet.get_test_info()
        tx_payload = packet.test_payload
        access_address = 0x71764129  # DTM
        print(f"[TX] {test_info['payload_type']}, {cfg.payload_length} bytes, "
              f"CH{cfg.channel} ({test_info['frequency_mhz']} MHz)")
    else:
        packet = create_advertising_packet(
            adv_address=cfg.adv_address,
            adv_data=cfg.adv_data,
            channel=cfg.channel
        )
        test_info = {'payload_type': 'ADV'}
        tx_payload = cfg.adv_address + cfg.adv_data
        access_address = 0x8E89BED6  # 广播
        print(f"[TX] 广播包, CH{cfg.channel}")

    bits = packet.generate()

    # 2. TX: 调制
    modulator = BLEModulator(ModulatorConfig(
        phy_mode=cfg.phy_mode,
        sample_rate=cfg.sample_rate,
        modulation_index=cfg.modulation_index,
        bt=cfg.bt
    ))
    tx_signal = modulator.modulate(bits)
    print(f"[TX] {len(tx_signal)} samples @ {cfg.sample_rate/1e6:.1f} MHz")

    # 3. 信道入口: 导入外部 IQ (可选)
    imported_signal, sample_rate = import_iq(cfg.io_input, cfg.sample_rate)
    if imported_signal is not None:
        channel_in = imported_signal
        print(f"[信道] 使用外部 IQ")
    else:
        channel_in = tx_signal
        sample_rate = cfg.sample_rate

    # 4. 信道模型
    if np.isinf(cfg.snr_db) and cfg.freq_offset == 0 and cfg.channel_type == ChannelType.AWGN:
        channel_out = channel_in.copy()
        print(f"[信道] Bypass")
    else:
        channel_model = BLEChannel(ChannelConfig(
            channel_type=cfg.channel_type,
            sample_rate=sample_rate,
            symbol_rate=modulator.symbol_rate,  # 传递符号率用于 Eb/N0 计算
            snr_db=cfg.snr_db if not np.isinf(cfg.snr_db) else 100,
            frequency_offset=cfg.freq_offset,
            doppler_freq=cfg.doppler_freq,
            k_factor=cfg.k_factor,
        ))
        channel_out = channel_model.apply(channel_in)
        ch_info = f"[信道] {cfg.channel_type.value.upper()}, Eb/N0={cfg.snr_db} dB"
        if cfg.freq_offset != 0:
            ch_info += f", 频偏={cfg.freq_offset/1e3:.1f} kHz"
        if cfg.channel_type in (ChannelType.RAYLEIGH, ChannelType.RICIAN):
            ch_info += f", Doppler={cfg.doppler_freq} Hz"
        if cfg.channel_type == ChannelType.RICIAN:
            ch_info += f", K={cfg.k_factor}"
        print(ch_info)

    # 5. 信道出口: 导出 IQ (可选)
    if cfg.io_output and cfg.io_output.get('export_tx', False):
        export_iq(tx_signal, cfg.io_output, cfg.output_dir, sample_rate, 'iq_tx')
    export_iq(channel_out, cfg.io_output, cfg.output_dir, sample_rate, 'iq_rx')

    # 6. RX: 解调
    demodulator = BLEDemodulator(DemodulatorConfig(
        phy_mode=cfg.phy_mode,
        sample_rate=sample_rate,
        access_address=access_address,
        channel=cfg.channel,
        whitening=cfg.whitening if cfg.mode == 'rf_test' else True
    ))
    result = demodulator.demodulate(channel_out)

    rx_payload = result.pdu[2:] if result.success and len(result.pdu) > 2 else None
    payload_match = (tx_payload == rx_payload) if rx_payload else False

    print(f"[RX] {'成功' if result.success else '失败'}, "
          f"CRC={'OK' if result.crc_valid else 'FAIL'}, "
          f"匹配={'OK' if payload_match else 'FAIL'}")

    # 7. RF 指标 (仅 RF Test 模式)
    if cfg.mode == 'rf_test':
        # 根据实际采样率计算 samples_per_symbol
        actual_sps = int(sample_rate / modulator.symbol_rate)
        rf_metrics = calculate_rf_metrics(
            channel_out, sample_rate, actual_sps,
            payload_type=test_info['payload_type']
        )
        print(f"[RF] ΔF1={rf_metrics['delta_f1_avg']:.1f}kHz, "
              f"ΔF2={rf_metrics['delta_f2_avg']:.1f}kHz, "
              f"Ratio={rf_metrics['delta_f2_ratio']:.2f}")
    else:
        rf_metrics = {}

    # 8. 生成报告
    if cfg.html_report:
        os.makedirs(cfg.output_dir, exist_ok=True)
        results = {
            'tx': {'bits': len(bits), 'payload_len': len(tx_payload), 'test_mode': test_info['payload_type']},
            'modulation': {
                'sample_rate_mhz': sample_rate / 1e6,
                'symbol_rate_msps': modulator.symbol_rate / 1e6,
                'modulation_index': cfg.modulation_index,
                'bt': cfg.bt,
            },
            'channel': {
                'type': cfg.channel_type.value,
                'snr_db': cfg.snr_db,
                'freq_offset_khz': cfg.freq_offset / 1e3,
                'doppler_freq': cfg.doppler_freq,
                'k_factor': cfg.k_factor,
            },
            'demodulation': {
                'success': result.success, 'crc_valid': result.crc_valid,
                'rssi_db': result.rssi, 'freq_offset_khz': result.freq_offset / 1e3,
                'tx_payload': tx_payload[:32].hex(), 'rx_payload': rx_payload[:32].hex() if rx_payload else None,
                'payload_match': payload_match,
            },
            'rf_test': test_info,
        }
        reporter = ReportGenerator(cfg.output_dir, theme=cfg.theme)
        reporter.generate_all(results, tx_signal, channel_out, bits, sample_rate)
        print(f"\n报告: {cfg.output_dir}/index.html")

    print("=" * 60)
    return result


# ============================================================
# 入口
# ============================================================
def load_config(path: str) -> dict:
    """加载配置文件"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "examples/config.yaml"
    raw_config = load_config(config_path)
    cfg = SimConfig.from_dict(raw_config)
    run_simulation(cfg, raw_config)
