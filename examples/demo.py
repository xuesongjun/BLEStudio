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
import re
import sys
import yaml
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

from ble_studio import (
    __version__ as BLE_STUDIO_VERSION,
    BLEModulator, BLEDemodulator, ReportGenerator,
    ModulatorConfig, DemodulatorConfig, BLEPhyMode,
    create_advertising_packet, create_test_packet,
    RFTestPayloadType,
    BLEChannel, ChannelConfig, ChannelType,
    IQExporter, IQExportConfig, IQFormat, NumberFormat,
    import_iq_txt, import_iq_mat, frequency_shift,
    calculate_rf_metrics,
)
from ble_studio.iq_io import describe_file, write_pretty_json


WAVEFORM_SCHEMA = "ble_studio.waveform.v1"
WAVEFORM_SCHEMA_VERSION = 1
CRC_POLYNOMIAL = "z^24+z^10+z^9+z^6+z^4+z^3+z+1"

PHY_FILENAME_TOKENS = {
    BLEPhyMode.LE_1M: "LE1M",
    BLEPhyMode.LE_2M: "LE2M",
    BLEPhyMode.LE_CODED_S8: "LE125K",
    BLEPhyMode.LE_CODED_S2: "LE500K",
}

PAYLOAD_FILENAME_TOKENS = {
    RFTestPayloadType.PRBS9: "PRBS9",
    RFTestPayloadType.PRBS15: "PRBS15",
    RFTestPayloadType.PATTERN_11110000: "PATTERN_F0",
    RFTestPayloadType.PATTERN_10101010: "PATTERN_55",
    RFTestPayloadType.PATTERN_11111111: "PATTERN_FF",
    RFTestPayloadType.PATTERN_00000000: "PATTERN_00",
    RFTestPayloadType.PATTERN_00001111: "PATTERN_0F",
    RFTestPayloadType.PATTERN_01010101: "PATTERN_AA",
}

ADVERTISING_FREQUENCIES_MHZ = {37: 2402, 38: 2426, 39: 2480}


def _canonical_phy_name(phy_mode: BLEPhyMode) -> str:
    """返回与 MATLAB reference 一致的 PHY token。"""
    try:
        return PHY_FILENAME_TOKENS[BLEPhyMode(phy_mode)]
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError(f"Unsupported phy_mode for waveform export: {phy_mode}") from exc


def _sample_rate_token(sample_rate: float) -> str:
    """把实际采样率格式化为稳定、可读的文件名片段。"""
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive finite value")
    rate_msps = float(sample_rate) / 1e6
    nearest_integer = round(rate_msps)
    if np.isclose(rate_msps, nearest_integer, rtol=0.0, atol=1e-9):
        value = str(int(nearest_integer))
    else:
        value = f"{rate_msps:.9f}".rstrip("0").rstrip(".")
    return f"{value}Msps"


def _sanitize_filename_token(value: str) -> str:
    """清理外部输入 stem，防止路径字符进入导出文件名。"""
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return token or "imported_iq"


def _generated_waveform_basename(
    cfg: 'SimConfig', sample_rate: float, direction: str
) -> str:
    phy = _canonical_phy_name(cfg.phy_mode)
    if cfg.mode == "advertising":
        payload = "ADV"
        payload_length = len(cfg.adv_address) + len(cfg.adv_data)
    else:
        payload = PAYLOAD_FILENAME_TOKENS[RFTestPayloadType(cfg.payload_type)]
        payload_length = cfg.payload_length
    return (
        f"{phy}_{_sample_rate_token(sample_rate)}_"
        f"{payload}_{payload_length}B_{direction}"
    )


def _imported_waveform_basename(
    input_config: dict, sample_rate: float
) -> str:
    input_stem = Path(str(input_config.get("file", ""))).stem
    return (
        f"{_sanitize_filename_token(input_stem)}_"
        f"{_sample_rate_token(sample_rate)}_RX"
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
    access_address: int = 0  # 0 = 自动 (rf_test: 0x71764129, advertising: 0x8E89BED6)

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
    crc_init: int = 0x555555

    @classmethod
    def from_dict(cls, cfg: dict) -> 'SimConfig':
        """从配置字典创建"""
        common = cfg.get('common', {})
        tx = cfg.get('tx', {})
        ch = cfg.get('channel', {})
        out = cfg.get('output', {})
        io_cfg = cfg.get('io', {})

        return cls(
            mode=str(common.get('mode', 'rf_test')).lower(),
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
            access_address=int(tx.get('access_address', 0), 16) if isinstance(tx.get('access_address', 0), str) else int(tx.get('access_address', 0)),
            crc_init=int(tx.get('crc_init', 0x555555), 16) if isinstance(tx.get('crc_init', 0x555555), str) else int(tx.get('crc_init', 0x555555)),
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

    # 使用配置中指定的采样率 (如果有)
    if config.get('sample_rate'):
        sample_rate = float(config['sample_rate'])

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


def _json_number(value: float) -> Union[int, float]:
    """整数值不写多余小数，非整数值保留浮点语义。"""
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _build_packet_metadata(
    packet: Any,
    cfg: SimConfig,
    bits: np.ndarray,
    test_info: dict,
    tx_payload: bytes,
) -> Dict[str, Any]:
    """从实际 packet object 提取协议事实，不重复实现 CRC/PRBS。"""
    pdu = packet.generate_pdu()
    crc_value = packet._calculate_crc(pdu, packet.config.crc_init)
    crc_bytes = int(crc_value).to_bytes(3, byteorder="little")
    if cfg.mode == "advertising":
        payload_type = "ADV"
        whitening = True
        frequency_mhz = ADVERTISING_FREQUENCIES_MHZ.get(cfg.channel)
    else:
        payload_type = RFTestPayloadType(cfg.payload_type).name
        whitening = bool(cfg.whitening)
        frequency_mhz = test_info.get("frequency_mhz")

    return {
        "phy_mode": _canonical_phy_name(cfg.phy_mode),
        "channel_index": int(cfg.channel),
        "frequency_mhz": frequency_mhz,
        "access_address": f"0x{int(packet.config.access_address):08X}",
        "header_value": int(pdu[0]),
        "payload_type": payload_type,
        "payload_length_bytes": len(tx_payload),
        "payload_hex": bytes(tx_payload).hex(),
        "pdu_hex": pdu.hex(),
        "crc_hex": crc_bytes.hex(),
        "pdu_with_crc_hex": (pdu + crc_bytes).hex(),
        "crc_init": f"0x{int(packet.config.crc_init):06X}",
        "crc_polynomial": CRC_POLYNOMIAL,
        "whitening": whitening,
        "packet_bit_count": int(len(bits)),
    }


def _build_signal_metadata(
    signal: np.ndarray,
    sample_rate: float,
    symbol_rate: float,
    active_samples: Optional[int],
) -> Dict[str, Any]:
    sample_count = int(len(signal))
    samples_per_symbol = float(sample_rate) / float(symbol_rate)
    if np.isclose(samples_per_symbol, round(samples_per_symbol), rtol=0.0, atol=1e-9):
        samples_per_symbol = int(round(samples_per_symbol))
    padding_samples = (
        sample_count - int(active_samples) if active_samples is not None else None
    )
    return {
        "sample_rate_hz": _json_number(sample_rate),
        "symbol_rate_hz": _json_number(symbol_rate),
        "samples_per_symbol": samples_per_symbol,
        "sample_count": sample_count,
        "duration_us": sample_count / float(sample_rate) * 1e6,
        "active_samples": int(active_samples) if active_samples is not None else None,
        "padding_samples": padding_samples,
    }


def _build_channel_metadata(cfg: SimConfig, bypass: bool) -> Dict[str, Any]:
    if bypass:
        effective_ebn0_db = None
    elif np.isfinite(cfg.snr_db):
        effective_ebn0_db = float(cfg.snr_db)
    else:
        # 非 AWGN impairment 配置 inf 时，当前 channel pipeline 实际使用 100 dB。
        effective_ebn0_db = 100.0
    return {
        "type": cfg.channel_type.value,
        "bypass": bool(bypass),
        "ebn0_db": effective_ebn0_db,
        "frequency_offset_hz": _json_number(cfg.freq_offset),
        "doppler_hz": _json_number(cfg.doppler_freq),
        "k_factor": float(cfg.k_factor),
        "random_seed": None,
    }


def _build_waveform_metadata(
    *,
    cfg: SimConfig,
    signal: np.ndarray,
    sample_rate: float,
    symbol_rate: float,
    pulse_length: int,
    output_kind: str,
    source_kind: str,
    packet_metadata: Optional[Dict[str, Any]],
    active_samples: Optional[int],
    channel_metadata: Optional[Dict[str, Any]],
    receiver_expectation: Optional[Dict[str, Any]] = None,
    input_file: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "schema": WAVEFORM_SCHEMA,
        "schema_version": WAVEFORM_SCHEMA_VERSION,
        "generator": {
            "name": "BLEStudio",
            "version": BLE_STUDIO_VERSION,
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        },
        "output_kind": output_kind,
        "source_kind": source_kind,
        "mode": cfg.mode,
        "signal": _build_signal_metadata(
            signal, sample_rate, symbol_rate, active_samples
        ),
        "packet": packet_metadata,
        "modulation": {
            "modulation_index": float(cfg.modulation_index),
            "bt": float(cfg.bt),
            "pulse_length": int(pulse_length),
        },
        "channel": channel_metadata,
    }
    if receiver_expectation is not None:
        metadata["receiver_expectation"] = receiver_expectation
    if input_file is not None:
        metadata["input_file"] = input_file
        metadata["input_frequency_shift_hz"] = _json_number(
            float(cfg.io_input.get("freq_shift", 0))
        )
    return metadata


def export_iq(signal: np.ndarray, config: dict, output_dir: str,
              sample_rate: float, basename: str,
              metadata: Dict[str, Any]) -> Optional[Path]:
    """导出 IQ 数据及同 basename 的 JSON sidecar。"""
    if not config or not config.get('enabled', False):
        return None

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    export_cfg = IQExportConfig(
        bit_width=int(config.get('bit_width', 12)),
        frac_bits=int(config.get('frac_bits', 0)),
        iq_format=IQFormat(config.get('iq_format', 'two_column')),
        number_format=NumberFormat(config.get('number_format', 'signed')),
        add_header=config.get('add_header', True),
        scale_to_full=config.get('scale_to_full', True),
    )
    exporter = IQExporter(export_cfg)
    files: Dict[str, Dict[str, Any]] = {}
    quantized_formats = []

    # TXT
    if config.get('export_txt', True):
        txt_path = output_path / f'{basename}.txt'
        exporter.export_txt(signal, txt_path)
        files["txt"] = describe_file(txt_path)
        quantized_formats.append("txt")

    # MAT
    if config.get('export_mat', True):
        try:
            from scipy.io import savemat
        except ImportError as exc:
            raise ImportError("导出 MAT 需要安装 scipy") from exc
        mat_path = output_path / f'{basename}.mat'
        savemat(mat_path, {
            'iq': signal, 'I': signal.real, 'Q': signal.imag, 'fs': sample_rate
        })
        files["mat"] = describe_file(mat_path)

    # Verilog
    if config.get('export_verilog', False):
        mem_path = output_path / f'{basename}.mem'
        exporter.export_verilog_mem(signal, mem_path)
        files["mem"] = describe_file(mem_path)
        quantized_formats.append("mem")

    quantization = exporter.quantization_details(signal)
    quantization.update({
        "applies_to": quantized_formats,
        "iq_format": export_cfg.iq_format.value,
        "number_format": export_cfg.number_format.value,
        "txt_layout": "I and Q in configured text layout",
        "mem_layout": (
            f"I high {export_cfg.bit_width} bits, "
            f"Q low {export_cfg.bit_width} bits"
        ),
        "packed_width_bits": export_cfg.bit_width * 2,
    })
    manifest = dict(metadata)
    manifest["quantization"] = quantization
    manifest["files"] = files
    manifest_path = output_path / f'{basename}.json'
    write_pretty_json(manifest_path, manifest)

    print(f"[IO] 导出: {basename}.* ({len(signal)} samples)")
    return manifest_path


# ============================================================
# 仿真核心
# ============================================================
def run_simulation(cfg: SimConfig, raw_config: dict):
    """运行仿真"""
    supported_modes = {'rf_test', 'dtm', 'advertising'}
    if cfg.mode not in supported_modes:
        raise ValueError(
            f"Unsupported mode '{cfg.mode}', expected one of: "
            f"{', '.join(sorted(supported_modes))}"
        )

    print("=" * 60)
    print(f"BLE Studio - {cfg.mode.upper()} 模式")
    print("=" * 60)

    # 1. TX: 生成数据包
    if cfg.mode == 'rf_test' or cfg.mode == 'dtm':
        access_address = cfg.access_address if cfg.access_address != 0 else 0x71764129
        packet = create_test_packet(
            payload_type=cfg.payload_type,
            payload_length=cfg.payload_length,
            channel=cfg.channel,
            phy_mode=cfg.phy_mode,
            access_address=access_address,
            whitening=cfg.whitening,
            crc_init=cfg.crc_init,
        )
        test_info = packet.get_test_info()
        tx_payload = packet.test_payload
        print(f"[TX] {test_info['payload_type']}, {cfg.payload_length} bytes, "
              f"CH{cfg.channel} ({test_info['frequency_mhz']} MHz)")
    else:
        if cfg.access_address not in (0, 0x8E89BED6):
            raise ValueError(
                "Advertising mode uses the fixed Access Address 0x8E89BED6"
            )
        packet = create_advertising_packet(
            adv_address=cfg.adv_address,
            adv_data=cfg.adv_data,
            channel=cfg.channel
        )
        test_info = {'payload_type': 'ADV'}
        tx_payload = cfg.adv_address + cfg.adv_data
        access_address = 0x8E89BED6
        print(f"[TX] 广播包, CH{cfg.channel}")

    bits = packet.generate()
    packet_metadata = _build_packet_metadata(
        packet, cfg, bits, test_info, tx_payload
    )

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

        # 变频处理 (将信号搬移到零频)
        freq_shift_hz = float(cfg.io_input.get('freq_shift', 0))
        if freq_shift_hz != 0:
            channel_in = frequency_shift(channel_in, freq_shift_hz, sample_rate)
            direction = "上变频" if freq_shift_hz > 0 else "下变频"
            print(f"[信道] {direction}: {abs(freq_shift_hz)/1e6:.3f} MHz")
    else:
        channel_in = tx_signal
        sample_rate = cfg.sample_rate

    # 4. 信道模型
    channel_bypass = (
        np.isinf(cfg.snr_db)
        and cfg.freq_offset == 0
        and cfg.channel_type == ChannelType.AWGN
    )
    if channel_bypass:
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

    # 5. 信道出口: 导出 IQ 和可追溯 sidecar (可选)
    output_enabled = bool(cfg.io_output and cfg.io_output.get('enabled', False))
    if output_enabled:
        if cfg.io_output.get('export_tx', False):
            tx_basename = _generated_waveform_basename(
                cfg, cfg.sample_rate, "TX"
            )
            tx_metadata = _build_waveform_metadata(
                cfg=cfg,
                signal=tx_signal,
                sample_rate=cfg.sample_rate,
                symbol_rate=modulator.symbol_rate,
                pulse_length=modulator.config.pulse_length,
                output_kind="clean_tx",
                source_kind="generated_packet",
                packet_metadata=packet_metadata,
                active_samples=len(tx_signal),
                channel_metadata=None,
            )
            export_iq(
                tx_signal,
                cfg.io_output,
                cfg.output_dir,
                cfg.sample_rate,
                tx_basename,
                tx_metadata,
            )

        channel_metadata = _build_channel_metadata(cfg, channel_bypass)
        if imported_signal is not None:
            rx_basename = _imported_waveform_basename(cfg.io_input, sample_rate)
            rx_packet_metadata = None
            receiver_expectation = packet_metadata
            input_descriptor = describe_file(cfg.io_input['file'])
            source_kind = "imported_iq"
            active_samples = None
        else:
            rx_basename = _generated_waveform_basename(cfg, sample_rate, "RX")
            rx_packet_metadata = packet_metadata
            receiver_expectation = None
            input_descriptor = None
            source_kind = "generated_tx"
            active_samples = len(tx_signal)

        rx_metadata = _build_waveform_metadata(
            cfg=cfg,
            signal=channel_out,
            sample_rate=sample_rate,
            symbol_rate=modulator.symbol_rate,
            pulse_length=modulator.config.pulse_length,
            output_kind="channel_output",
            source_kind=source_kind,
            packet_metadata=rx_packet_metadata,
            active_samples=active_samples,
            channel_metadata=channel_metadata,
            receiver_expectation=receiver_expectation,
            input_file=input_descriptor,
        )
        export_iq(
            channel_out,
            cfg.io_output,
            cfg.output_dir,
            sample_rate,
            rx_basename,
            rx_metadata,
        )

    # 6. RX: 解调
    demodulator = BLEDemodulator(DemodulatorConfig(
        phy_mode=cfg.phy_mode,
        sample_rate=sample_rate,
        access_address=access_address,
        channel=cfg.channel,
        whitening=cfg.whitening if cfg.mode in ('rf_test', 'dtm') else True,
        crc_init=cfg.crc_init if cfg.mode in ('rf_test', 'dtm') else 0x555555,
    ))
    result = demodulator.demodulate(channel_out)

    # 打印同步状态
    if result.sync_found:
        print(f"[RX] access_code: 0x{result.access_address:08X}, sync found")
    else:
        print(f"[RX] sync NOT found")

    rx_payload = result.pdu[2:] if result.success and len(result.pdu) > 2 else None
    payload_match = (tx_payload == rx_payload) if rx_payload else False

    print(f"[RX] {'成功' if result.success else '失败'}, "
          f"CRC={'OK' if result.crc_valid else 'FAIL'}, "
          f"匹配={'OK' if payload_match else 'FAIL'}")

    # 7. RF 指标 (仅 RF Test 模式)
    if cfg.mode in ('rf_test', 'dtm'):
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
