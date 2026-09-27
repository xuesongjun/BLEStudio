from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ble_studio import BLEModulator, ModulatorConfig, create_test_packet
from ble_studio.logic_analyzer.models import (
    BleRxConfig,
    CaptureResult,
    LogicAnalyzerConfig,
    RawCapture,
)
from ble_studio.logic_analyzer.validation import validate_ble_rx


def _to_unsigned(values: np.ndarray, bit_width: int) -> np.ndarray:
    return (
        values.astype(np.int64) & ((1 << bit_width) - 1)
    ).astype(np.uint16)


def _ideal_dtm_result(tmp_path: Path) -> CaptureResult:
    packet = create_test_packet(payload_length=37)
    signal = BLEModulator(
        ModulatorConfig(sample_rate=8e6)
    ).modulate(packet.generate())
    bit_width = 14
    scale = (1 << (bit_width - 1)) - 1
    i_signed = np.round(signal.real * scale).astype(np.int32)
    q_signed = np.round(signal.imag * scale).astype(np.int32)
    config = LogicAnalyzerConfig(
        input_file=tmp_path / "ideal.bin",
        output_dir=tmp_path,
        output_stem="ideal",
        sample_rate=8e6,
        data_rate=16e6,
        mode="ddr",
        data_bits=tuple(range(bit_width)),
        clk_channel=15,
        bit_width=bit_width,
        ble_rx=BleRxConfig(
            enabled=True,
            phy_mode="LE_1M",
            access_address=0x71764129,
            channel=0,
            whitening=False,
            target_samples_per_symbol=16,
        ),
    )
    return CaptureResult(
        config=config,
        raw_capture=RawCapture(
            channels={},
            clock=None,
            extra_signals={},
            sample_count=len(signal),
            sample_rate=8e6,
        ),
        cleaned_channels={},
        data1=_to_unsigned(i_signed, bit_width),
        data2=_to_unsigned(q_signed, bit_width),
        signed_data1=i_signed,
        signed_data2=q_signed,
        sample_rate_nominal=8e6,
        sample_rate_measured=None,
    )


def test_ideal_dtm_rx_validation_resamples_to_integer_sps(tmp_path: Path) -> None:
    result = _ideal_dtm_result(tmp_path)

    validation = validate_ble_rx(result)

    assert validation["attempted"] is True
    assert validation["resampled"] is True
    assert validation["effective_sample_rate_hz"] == 16e6
    assert validation["target_samples_per_symbol"] == 16
    assert validation["success"] is True
    assert validation["sync_found"] is True
    assert validation["crc_valid"] is True
    assert result.rx_result == validation


def test_disabled_rx_validation_returns_structured_result(tmp_path: Path) -> None:
    result = _ideal_dtm_result(tmp_path)
    result.config.ble_rx.enabled = False

    validation = validate_ble_rx(result)

    assert validation == {
        "enabled": False,
        "attempted": False,
        "reason": "BLE RX validation disabled",
    }


def test_rx_validation_rejects_sdr_result(tmp_path: Path) -> None:
    config = LogicAnalyzerConfig(
        input_file=tmp_path / "sdr.bin",
        output_dir=tmp_path,
        output_stem="sdr",
        mode="sdr",
        data_bits=(0,),
        clk_channel=None,
        bit_width=1,
        ble_rx=BleRxConfig(enabled=True),
    )
    result = CaptureResult(
        config=config,
        raw_capture=RawCapture({}, None, {}, 3, 1e6),
        cleaned_channels={},
        data1=np.array([0, 1, 0], dtype=np.uint16),
        data2=None,
        signed_data1=np.array([0, -1, 0], dtype=np.int32),
        signed_data2=None,
        sample_rate_nominal=1e6,
        sample_rate_measured=None,
    )

    with pytest.raises(ValueError, match="只支持 DDR complex IQ"):
        validate_ble_rx(result)
