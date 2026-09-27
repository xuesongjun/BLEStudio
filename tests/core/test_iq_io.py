from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from ble_studio.iq_io import (
    IQExportConfig,
    IQExporter,
    describe_file,
    write_pretty_json,
)


def test_quantize_rounds_half_lsb_away_from_zero_for_i_and_q() -> None:
    exporter = IQExporter(
        IQExportConfig(bit_width=4, frac_bits=3, scale_to_full=False)
    )
    signal = np.array(
        [
            0.0625 + 0.0625j,
            -0.0625 - 0.0625j,
            0.1875 + 0.1875j,
            -0.1875 - 0.1875j,
        ]
    )

    i_quant, q_quant = exporter.quantize(signal)

    np.testing.assert_array_equal(i_quant, [1, -1, 2, -2])
    np.testing.assert_array_equal(q_quant, [1, -1, 2, -2])


def test_quantization_details_report_scale_clip_and_saturation() -> None:
    exporter = IQExporter(
        IQExportConfig(bit_width=4, frac_bits=2, scale_to_full=False)
    )
    signal = np.array([2.0 + 2.0j, -2.25 - 2.25j, 0.0 + 0.0j])

    i_quant, q_quant = exporter.quantize(signal)
    details = exporter.quantization_details(signal)

    np.testing.assert_array_equal(i_quant, [7, -8, 0])
    np.testing.assert_array_equal(q_quant, [7, -8, 0])
    assert details == {
        "bit_width": 4,
        "frac_bits": 2,
        "scale_to_full": False,
        "scale_factor": 4.0,
        "rounding": "ties_away_from_zero",
        "signed_min": -8,
        "signed_max": 7,
        "saturation_i": 2,
        "saturation_q": 2,
        "q_format": "Q2.2",
    }


def test_dynamic_full_scale_reports_actual_factor_without_q_format() -> None:
    exporter = IQExporter(
        IQExportConfig(bit_width=12, frac_bits=0, scale_to_full=True)
    )
    signal = np.array([0.25 + 0.5j])

    i_quant, q_quant = exporter.quantize(signal)
    details = exporter.quantization_details(signal)

    np.testing.assert_array_equal(i_quant, [1024])
    np.testing.assert_array_equal(q_quant, [2047])
    assert details["scale_factor"] == 4096.0
    assert details["q_format"] is None
    assert details["saturation_i"] == 0
    assert details["saturation_q"] == 1


def test_export_verilog_mem_uses_fixed_width_i_high_q_low(tmp_path) -> None:
    exporter = IQExporter(
        IQExportConfig(bit_width=12, frac_bits=1, scale_to_full=False)
    )
    output = tmp_path / "waveform.mem"

    result = exporter.export_verilog_mem(
        np.array([0.5 - 0.5j, -1.0 + 0.0j]), output
    )

    assert output.read_text(encoding="ascii").splitlines() == [
        "001FFF",
        "FFE000",
    ]
    assert result["packed_width"] == 24
    assert result["quantization"]["scale_factor"] == 2.0
    assert result["quantization"]["rounding"] == "ties_away_from_zero"


def test_txt_header_reports_dynamic_scale_without_false_q_format(tmp_path) -> None:
    exporter = IQExporter(
        IQExportConfig(
            bit_width=12,
            frac_bits=0,
            scale_to_full=True,
            add_header=True,
        )
    )
    output = tmp_path / "waveform.txt"

    result = exporter.export_txt(np.array([0.25 + 0.5j]), output)

    text = output.read_text(encoding="ascii")
    assert "// Scale Factor: 4096" in text
    assert "// Rounding: ties_away_from_zero" in text
    assert "// Q Format:" not in text
    assert result["q_format"] is None
    assert result["quantization"]["scale_factor"] == 4096.0


def test_write_pretty_json_is_multiline_strict_and_ends_with_newline(tmp_path) -> None:
    output = tmp_path / "waveform.json"
    metadata = {
        "schema": "ble_studio.waveform.v1",
        "signal": {"sample_count": np.int64(2)},
    }

    result = write_pretty_json(output, metadata)

    text = output.read_text(encoding="utf-8")
    assert result == output
    assert text.endswith("\n")
    assert len(text.splitlines()) > 3
    assert json.loads(text)["signal"]["sample_count"] == 2

    invalid_output = tmp_path / "invalid.json"
    with pytest.raises(ValueError, match="Out of range float values"):
        write_pretty_json(invalid_output, {"ebn0_db": np.inf})
    assert not invalid_output.exists()

    output.write_text("existing metadata\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Out of range float values"):
        write_pretty_json(output, {"ebn0_db": -np.inf})
    assert output.read_text(encoding="utf-8") == "existing metadata\n"


def test_describe_file_reports_name_size_and_sha256(tmp_path) -> None:
    output = tmp_path / "waveform.mem"
    content = b"001FFF\nFFE000\n"
    output.write_bytes(content)

    assert describe_file(output) == {
        "name": "waveform.mem",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
