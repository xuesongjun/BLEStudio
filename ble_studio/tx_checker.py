"""DAC real I/Q 的独立整包检查入口，供 Python 和仿真 DPI 调用。"""

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, Optional, Sequence, Union

import numpy as np

from .demodulator import BLEDemodulator, DemodulatorConfig
from .iq_io import write_pretty_json
from .packet import BLEPhyMode
from .coded_phy import coded_symbol_count


@dataclass(frozen=True)
class TxCheckResult:
    """完整数据核对结果；不包含未经校准的 RF 合规判定。"""

    passed: bool
    sync_found: bool
    crc_valid: bool
    pdu_match: bool
    failure_reason: str
    sample_count: int
    sample_rate_hz: float
    phy_mode: str
    access_address: int
    channel: int
    whitening: bool
    crc_init: int
    expected_pdu_hex: str
    received_pdu_hex: str
    freq_offset_hz: float
    timing_offset_symbols: float

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def check_tx_packet(
    i_samples: Sequence[float],
    q_samples: Sequence[float],
    *,
    config: DemodulatorConfig,
    expected_pdu: bytes,
    report_path: Optional[Union[str, Path]] = None,
) -> TxCheckResult:
    """检查单包 DAC 数据；输入/配置错误抛异常，接收或数据核对失败返回 FAIL。

    expected_pdu 为 case 的 Header + Payload，不含 CRC。I/Q 保留原始幅度、
    极性和通道顺序，不自动修复 DUT 数据。四种 PHY 均要求整数 SPS。
    """
    if not isinstance(expected_pdu, bytes):
        raise TypeError('expected_pdu must be bytes containing Header + Payload')
    if len(expected_pdu) < 2 or len(expected_pdu) != 2 + expected_pdu[1]:
        raise ValueError('expected_pdu length must match its two-byte header')
    if not isinstance(config, DemodulatorConfig):
        raise TypeError('config must be DemodulatorConfig')

    i_raw, q_raw = np.asarray(i_samples), np.asarray(q_samples)
    if not np.isrealobj(i_raw) or not np.isrealobj(q_raw):
        raise TypeError('I/Q samples must be real numbers')
    i_data = np.asarray(i_raw, dtype=np.float64)
    q_data = np.asarray(q_raw, dtype=np.float64)
    if i_data.ndim != 1 or q_data.ndim != 1:
        raise ValueError('I/Q samples must be one-dimensional')
    if i_data.size != q_data.size:
        raise ValueError('I/Q samples must have the same length')
    if i_data.size == 0:
        raise ValueError('I/Q samples must be non-empty')
    if not np.all(np.isfinite(i_data)) or not np.all(np.isfinite(q_data)):
        raise ValueError('I/Q samples must be finite')

    # RX 会校验并规范化配置；复制配置避免改变调用方正在使用的对象。
    receiver = BLEDemodulator(replace(config))
    cfg = receiver.config
    preamble_bits = 16 if cfg.phy_mode == BLEPhyMode.LE_2M else 8
    min_samples = (preamble_bits + 32 + 16 + 24) * receiver.samples_per_symbol
    if cfg.phy_mode in (BLEPhyMode.LE_CODED_S2, BLEPhyMode.LE_CODED_S8):
        scheme = 2 if cfg.phy_mode == BLEPhyMode.LE_CODED_S2 else 8
        min_samples = coded_symbol_count(0, scheme) * receiver.samples_per_symbol
    received = b''
    sync_found = crc_valid = False
    freq_offset = timing_offset = 0.0
    if not np.any(i_data) and not np.any(q_data):
        reason = 'NO_SIGNAL'
    elif i_data.size < min_samples:
        # 防止 RX 对过短数组卷积时扩展输出，导致虚假的可解调长度。
        reason = 'INSUFFICIENT_SAMPLES'
    else:
        decoded = receiver.demodulate(i_data + 1j * q_data)
        received = decoded.pdu
        sync_found, crc_valid = decoded.sync_found, decoded.crc_valid
        freq_offset, timing_offset = decoded.freq_offset, decoded.timing_offset
        if decoded.failure_reason:
            reason = decoded.failure_reason
        elif not sync_found:
            reason = 'SYNC_NOT_FOUND'
        elif not crc_valid:
            reason = 'CRC_FAILED'
        elif received != expected_pdu:
            reason = 'PDU_MISMATCH'
        else:
            reason = ''

    result = TxCheckResult(
        passed=not reason,
        sync_found=bool(sync_found),
        crc_valid=bool(crc_valid),
        pdu_match=received == expected_pdu,
        failure_reason=reason,
        sample_count=int(i_data.size),
        sample_rate_hz=float(cfg.sample_rate),
        phy_mode=cfg.phy_mode.name,
        access_address=cfg.access_address,
        channel=cfg.channel,
        whitening=cfg.whitening,
        crc_init=cfg.crc_init,
        expected_pdu_hex=expected_pdu.hex(),
        received_pdu_hex=received.hex(),
        freq_offset_hz=float(freq_offset),
        timing_offset_symbols=float(timing_offset),
    )
    if report_path is not None:
        write_pretty_json(report_path, result.to_dict())
    return result


def check_tx_packet_dpi(
    i_samples: Sequence[float], q_samples: Sequence[float],
    sample_rate: float, phy_mode: int, access_address: int, channel: int,
    whitening: int, crc_init: int, expected_pdu_hex: str, report_path: str,
) -> Dict[str, object]:
    """DPI 的标量参数适配层；异常原样传播给 C++ bridge。"""
    if whitening not in (0, 1):
        raise ValueError('whitening must be 0 or 1')
    expected = bytes.fromhex(expected_pdu_hex)
    config = DemodulatorConfig(
        sample_rate=sample_rate, phy_mode=BLEPhyMode(phy_mode),
        access_address=access_address, channel=channel, whitening=bool(whitening),
        crc_init=crc_init,
    )
    return check_tx_packet(
        i_samples, q_samples, config=config, expected_pdu=expected,
        report_path=report_path or None,
    ).to_dict()
