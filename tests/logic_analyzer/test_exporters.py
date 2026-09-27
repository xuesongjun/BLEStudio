from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from ble_studio.iq_io import (
    IQImportConfig,
    IQImporter,
    import_iq_mat,
    import_iq_txt,
)
from ble_studio.logic_analyzer.exporters import export_outputs
from ble_studio.logic_analyzer.models import (
    CaptureResult,
    LogicAnalyzerConfig,
    RawCapture,
)
from ble_studio.logic_analyzer.visualization import create_figure


def _to_unsigned(values: np.ndarray, bit_width: int) -> np.ndarray:
    mask = (1 << bit_width) - 1
    return (values.astype(np.int64) & mask).astype(np.uint16)


def _result(tmp_path: Path, *, max_plot_samples: int = 3) -> CaptureResult:
    bit_width = 10
    i_signed = np.array([-5, -1, 0, 7, 12], dtype=np.int32)
    q_signed = np.array([3, 2, -4, -8, 1], dtype=np.int32)
    raw_count = 30
    raw_extra = {
        "marker": (np.arange(raw_count) >= 10).astype(np.uint8),
    }
    sampled_extra = {
        "marker": np.array([0, 0, 1, 1, 1], dtype=np.uint8),
    }
    config = LogicAnalyzerConfig(
        input_file=tmp_path / "capture.bin",
        output_dir=tmp_path,
        output_stem="capture",
        sample_rate=100e6,
        data_rate=20e6,
        mode="ddr",
        data_bits=tuple(range(bit_width)),
        clk_channel=10,
        bit_width=bit_width,
        save_formats=(
            "txt", "csv", "npy", "npz", "mat", "mem", "vcd", "html",
        ),
        max_plot_samples=max_plot_samples,
    )
    positions = [
        {channel: 2 + index * 5 for channel in range(bit_width)}
        for index in range(len(i_signed))
    ]
    return CaptureResult(
        config=config,
        raw_capture=RawCapture(
            channels={0: np.zeros(raw_count, dtype=np.uint8)},
            clock=(np.arange(raw_count) % 2).astype(np.uint8),
            extra_signals=raw_extra,
            sample_count=raw_count,
            sample_rate=100e6,
        ),
        cleaned_channels={0: np.zeros(raw_count, dtype=np.uint8)},
        data1=_to_unsigned(i_signed, bit_width),
        data2=_to_unsigned(q_signed, bit_width),
        signed_data1=i_signed,
        signed_data2=q_signed,
        sample_rate_nominal=10e6,
        sample_rate_measured=10.01e6,
        sample_info={
            "i_edges": np.arange(2, 27, 5),
            "q_edges": np.arange(4, 29, 5),
            "i_sample_positions": positions,
            "q_sample_positions": positions,
        },
        extra_signals=sampled_extra,
    )


def test_all_exporters_round_trip_canonical_iq(tmp_path: Path) -> None:
    result = _result(tmp_path)
    outputs = export_outputs(result)

    assert set(outputs) == {
        "json", "txt", "csv", "npy", "npz", "mat", "mem", "vcd", "html",
    }
    assert all(path.exists() for path in outputs.values())

    expected_iq = result.iq
    assert expected_iq is not None

    mat_iq, mat_fs = import_iq_mat(outputs["mat"])
    mem_iq = IQImporter(
        IQImportConfig(bit_width=result.config.bit_width)
    ).import_verilog_mem(outputs["mem"])
    npy_iq = np.load(outputs["npy"])
    npz = np.load(outputs["npz"])

    np.testing.assert_array_equal(mat_iq, expected_iq)
    np.testing.assert_array_equal(mem_iq, expected_iq)
    np.testing.assert_array_equal(npy_iq, expected_iq)
    np.testing.assert_array_equal(npz["iq"], expected_iq)
    assert mat_fs == result.sample_rate

    mat = loadmat(outputs["mat"])
    np.testing.assert_array_equal(mat["I_signed"].reshape(-1), result.signed_data1)
    np.testing.assert_array_equal(mat["Q_signed"].reshape(-1), result.signed_data2)
    np.testing.assert_array_equal(mat["I_raw"].reshape(-1), result.data1)
    np.testing.assert_array_equal(mat["Q_raw"].reshape(-1), result.data2)
    assert mat["sample_positions"].shape == (
        2,
        result.sample_count,
        result.config.bit_width,
    )
    assert "extra_marker" in mat

    txt_iq = import_iq_txt(
        outputs["txt"],
        bit_width=result.config.bit_width,
        number_format="signed",
    )
    correlation = abs(np.vdot(txt_iq, expected_iq)) / np.sqrt(
        np.vdot(txt_iq, txt_iq).real * np.vdot(expected_iq, expected_iq).real
    )
    assert np.isclose(correlation, 1.0)

    data_lines = [
        line
        for line in outputs["txt"].read_text(encoding="ascii").splitlines()
        if line and not line.startswith("//")
    ]
    parsed = np.array([[int(value) for value in line.split()] for line in data_lines])
    np.testing.assert_array_equal(parsed[:, 0], result.signed_data1)
    np.testing.assert_array_equal(parsed[:, 1], result.signed_data2)

    summary = json.loads(outputs["json"].read_text(encoding="utf-8"))
    assert summary["sample_count"] == result.sample_count
    assert summary["sample_rate_hz"] == result.sample_rate
    assert summary["visualization"]["plot_sample_count"] == 3
    assert summary["sample_info"]["i_edges"]["shape"] == [result.sample_count]


def test_html_uses_bounded_sampling(tmp_path: Path) -> None:
    result = _result(tmp_path, max_plot_samples=2)

    figure = create_figure(result)

    assert figure.data
    assert all(len(trace.x) <= 2 for trace in figure.data)


def test_vcd_timestamps_are_monotonic_and_include_raw_extra_signal(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    vcd_path = export_outputs(result)["vcd"]
    content = vcd_path.read_text(encoding="ascii")
    timestamps = [
        int(line[1:])
        for line in content.splitlines()
        if line.startswith("#")
    ]

    assert timestamps == sorted(timestamps)
    assert "marker" in content
    assert "I_unsigned" in content
    assert "Q_unsigned" in content
