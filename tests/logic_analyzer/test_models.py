from __future__ import annotations

from pathlib import Path

import numpy as np

from ble_studio.logic_analyzer.models import (
    CaptureResult,
    LogicAnalyzerConfig,
    RawCapture,
)


def _config(tmp_path: Path, *, mode: str = "ddr") -> LogicAnalyzerConfig:
    return LogicAnalyzerConfig(
        input_file=tmp_path / "capture.bin",
        output_dir=tmp_path / "output",
        output_stem="result",
        mode=mode,
        bit_width=10,
    )


def _raw_capture() -> RawCapture:
    return RawCapture(
        channels={},
        clock=None,
        extra_signals={},
        sample_count=3,
        sample_rate=500e6,
    )


def test_logic_analyzer_config_properties(tmp_path: Path) -> None:
    ddr_config = _config(tmp_path, mode="ddr")
    sdr_config = _config(tmp_path, mode="sdr")

    assert ddr_config.is_iq is True
    assert sdr_config.is_iq is False
    assert ddr_config.output_base == tmp_path / "output" / "result"


def test_capture_result_builds_normalized_iq_from_signed_data(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = CaptureResult(
        config=config,
        raw_capture=_raw_capture(),
        cleaned_channels={},
        data1=np.array([512, 0, 511], dtype=np.uint16),
        data2=np.array([0, 1023, 512], dtype=np.uint16),
        signed_data1=np.array([-512, 0, 511], dtype=np.int32),
        signed_data2=np.array([0, -1, -512], dtype=np.int32),
        sample_rate_nominal=16e6,
        sample_rate_measured=16.1e6,
    )

    expected = np.array([-1 + 0j, -1j / 512, 511 / 512 - 1j])
    np.testing.assert_allclose(result.iq, expected)
    assert result.is_iq is True
    assert result.sample_rate == 16e6
    assert result.sample_count == 3


def test_capture_result_without_second_channel_is_not_iq(tmp_path: Path) -> None:
    config = _config(tmp_path, mode="sdr")
    result = CaptureResult(
        config=config,
        raw_capture=_raw_capture(),
        cleaned_channels={},
        data1=np.array([1, 2, 3], dtype=np.uint16),
        data2=None,
        signed_data1=np.array([1, 2, 3], dtype=np.int32),
        signed_data2=None,
        sample_rate_nominal=100e6,
        sample_rate_measured=None,
    )

    assert result.is_iq is False
    assert result.iq is None
    assert result.sample_count == 3
