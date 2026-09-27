from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ble_studio.logic_analyzer.models import LogicAnalyzerConfig
from ble_studio.logic_analyzer.pipeline import process_capture


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _expected() -> dict:
    return json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))


def _sha256(data: np.ndarray) -> str:
    return hashlib.sha256(data.tobytes()).hexdigest()


def test_adc_ddr_fixture_preserves_current_extraction_behavior(tmp_path: Path) -> None:
    expected = _expected()["adc_ddr"]
    config = LogicAnalyzerConfig(
        input_file=FIXTURE_DIR / "adc_ddr_slice.bin",
        output_dir=tmp_path,
        output_stem="adc",
        profile="iq_ddr",
        sample_rate=500e6,
        data_rate=32e6,
        mode="ddr",
        data_bits=tuple(range(10)),
        clk_channel=10,
        bit_width=10,
        rising_edge_data="Q",
        falling_edge_data="I",
        eye_align=True,
        search_range=15,
        glitch_filter=True,
        glitch_threshold=0.2,
        adaptive_filter=False,
        output_spike_filter=True,
    )

    result = process_capture(config)

    assert result.sample_count == expected["output_samples"]
    assert result.sample_rate_nominal == 16e6
    assert result.sample_rate_measured is not None
    assert abs(result.sample_rate_measured - 16e6) < 2e3
    assert _sha256(result.data1) == expected["i_sha256"]
    assert _sha256(result.data2) == expected["q_sha256"]
    assert result.sample_info["rising_delays"] == {
        int(key): value for key, value in expected["rising_delays"].items()
    }
    assert result.sample_info["falling_delays"] == {
        int(key): value for key, value in expected["falling_delays"].items()
    }


def test_rssi_raw_fixture_preserves_words_and_control_signals(tmp_path: Path) -> None:
    expected = _expected()["rssi_raw"]
    config = LogicAnalyzerConfig(
        input_file=FIXTURE_DIR / "rssi_raw_slice.bin",
        output_dir=tmp_path,
        output_stem="rssi",
        profile="rssi_raw_sdr",
        sample_rate=100e6,
        data_rate=100e6,
        mode="sdr",
        data_bits=tuple(range(8)),
        clk_channel=None,
        bit_width=8,
        eye_align=False,
        search_range=2,
        glitch_filter=False,
        adaptive_filter=False,
        output_spike_filter=False,
        extra_signals={"agc_init": 8, "rampup": 9, "fire_timer": 10},
    )

    result = process_capture(config)

    assert result.sample_count == expected["input_samples"]
    assert _sha256(result.data1.astype(np.uint8)) == expected["signals"]["rssi"]["sha256"]
    for name, values in result.extra_signals.items():
        assert _sha256(values) == expected["signals"][name]["sha256"]
