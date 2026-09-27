"""使用现有 BLEDemodulator 对 CaptureResult 做可选 RX 验证。"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict, Optional

import numpy as np

from ..demodulator import BLEDemodulator, DemodulatorConfig
from ..packet import BLEPhyMode
from .models import BleRxConfig, CaptureResult


def _phy_mode(name: str) -> BLEPhyMode:
    try:
        return BLEPhyMode[name.upper()]
    except KeyError as exc:
        valid = ", ".join(mode.name for mode in BLEPhyMode)
        raise ValueError(f"未知 BLE PHY {name!r}，可选值: {valid}") from exc


def _symbol_rate(phy_mode: BLEPhyMode) -> float:
    return 2e6 if phy_mode == BLEPhyMode.LE_2M else 1e6


def _resample_iq(
    signal: np.ndarray,
    source_rate: float,
    target_rate: float,
    max_denominator: int,
) -> tuple[np.ndarray, int, int]:
    try:
        from scipy.signal import resample_poly
    except ImportError as exc:
        raise ImportError("BLE RX 重采样需要安装 scipy") from exc

    ratio = Fraction(target_rate / source_rate).limit_denominator(max_denominator)
    up = ratio.numerator
    down = ratio.denominator
    return resample_poly(signal, up, down), up, down


def validate_ble_rx(
    result: CaptureResult,
    config: Optional[BleRxConfig] = None,
    *,
    resample: bool = True,
    max_denominator: int = 10_000,
) -> Dict[str, Any]:
    """运行 BLE RX 验证并把结构化结果写回 ``result.rx_result``。

    解调失败会返回 ``success=False``，不会作为 pipeline 异常抛出。配置、
    输入类型或依赖错误仍会抛出明确异常。
    """
    rx_config = config or result.config.ble_rx
    if not rx_config.enabled:
        output = {
            "enabled": False,
            "attempted": False,
            "reason": "BLE RX validation disabled",
        }
        result.rx_result = output
        return output
    iq = result.iq
    if not result.is_iq or iq is None:
        raise ValueError("BLE RX 验证只支持 DDR complex IQ CaptureResult")
    if result.sample_rate <= 0:
        raise ValueError("BLE RX 验证要求 sample_rate 大于 0")
    if rx_config.target_samples_per_symbol < 2:
        raise ValueError("target_samples_per_symbol 不能小于 2")
    if max_denominator < 1:
        raise ValueError("max_denominator 必须大于 0")

    phy_mode = _phy_mode(rx_config.phy_mode)
    symbol_rate = _symbol_rate(phy_mode)
    source_rate = float(result.sample_rate)
    target_rate = symbol_rate * rx_config.target_samples_per_symbol
    signal = np.asarray(iq, dtype=np.complex128)
    if signal.size == 0:
        raise ValueError("BLE RX 验证不能处理空 IQ")

    effective_rate = source_rate
    up = 1
    down = 1
    resampled = False
    realized_rate = source_rate
    if resample and not np.isclose(source_rate, target_rate, rtol=1e-9, atol=1e-3):
        signal, up, down = _resample_iq(
            signal, source_rate, target_rate, max_denominator
        )
        realized_rate = source_rate * up / down
        # BLEDemodulator 只支持整数 SPS，使用目标 rate 解释重采样结果。
        effective_rate = target_rate
        resampled = True

    demodulator = BLEDemodulator(DemodulatorConfig(
        phy_mode=phy_mode,
        sample_rate=effective_rate,
        access_address=rx_config.access_address,
        channel=rx_config.channel,
        whitening=rx_config.whitening,
    ))

    output: Dict[str, Any] = {
        "enabled": True,
        "attempted": True,
        "phy_mode": phy_mode.name,
        "configured_access_address": int(rx_config.access_address),
        "channel": int(rx_config.channel),
        "whitening": bool(rx_config.whitening),
        "source_sample_rate_hz": source_rate,
        "target_sample_rate_hz": target_rate,
        "effective_sample_rate_hz": effective_rate,
        "resample_realized_rate_hz": realized_rate,
        "target_samples_per_symbol": int(rx_config.target_samples_per_symbol),
        "resampled": resampled,
        "resample_up": up,
        "resample_down": down,
        "input_samples": int(result.sample_count),
        "validation_samples": int(len(signal)),
    }
    if phy_mode in (BLEPhyMode.LE_CODED_S2, BLEPhyMode.LE_CODED_S8):
        output["warning"] = (
            "现有 BLEDemodulator 尚未实现 LE Coded FEC，结果仅供诊断"
        )
    elif not resample and not np.isclose(
        source_rate / symbol_rate,
        round(source_rate / symbol_rate),
        rtol=0,
        atol=1e-9,
    ):
        output["warning"] = (
            "未重采样且 source sample rate 不是整数 SPS，现有 RX 可能产生定时漂移"
        )

    try:
        demodulated = demodulator.demodulate(signal)
    except Exception as exc:  # 解调器错误作为分析结果返回，保留 pipeline 产物。
        output.update({
            "success": False,
            "sync_found": False,
            "crc_valid": False,
            "error": f"{type(exc).__name__}: {exc}",
        })
        result.rx_result = output
        return output

    output.update({
        "success": bool(demodulated.success),
        "sync_found": bool(demodulated.sync_found),
        "crc_valid": bool(demodulated.crc_valid),
        "detected_access_address": int(demodulated.access_address),
        "freq_offset_hz": float(demodulated.freq_offset),
        "timing_offset_symbols": float(demodulated.timing_offset),
        "rssi_db": float(demodulated.rssi),
        "pdu_hex": demodulated.pdu.hex(),
        "decoded_bit_count": int(len(demodulated.bits)),
    })
    result.rx_result = output
    return output


# 简短别名便于 pipeline/CLI 调用。
validate_capture = validate_ble_rx


__all__ = ["validate_ble_rx", "validate_capture"]
