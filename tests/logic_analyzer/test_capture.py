from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ble_studio.logic_analyzer.capture import load_capture
from ble_studio.logic_analyzer.models import LogicAnalyzerConfig


def _config(
    input_file: Path,
    *,
    data_bits: tuple[int, ...] = (0, 7, 8, 15),
    clk_channel: int | None = None,
    extra_signals: dict[str, int] | None = None,
) -> LogicAnalyzerConfig:
    return LogicAnalyzerConfig(
        input_file=input_file,
        output_dir=input_file.parent,
        output_stem="capture",
        mode="sdr" if clk_channel is None else "ddr",
        data_bits=data_bits,
        bit_width=len(data_bits),
        clk_channel=clk_channel,
        extra_signals=extra_signals or {},
        sample_rate=100e6,
    )


def _write_words(path: Path, words: list[int]) -> None:
    path.write_bytes(b"".join(word.to_bytes(2, "little") for word in words))


def test_load_capture_decodes_boundary_channels(tmp_path: Path) -> None:
    input_file = tmp_path / "capture.bin"
    _write_words(input_file, [0x0001, 0x0080, 0x0100, 0x8000, 0x8181])

    capture = load_capture(_config(input_file))

    np.testing.assert_array_equal(capture.channels[0], [1, 0, 0, 0, 1])
    np.testing.assert_array_equal(capture.channels[7], [0, 1, 0, 0, 1])
    np.testing.assert_array_equal(capture.channels[8], [0, 0, 1, 0, 1])
    np.testing.assert_array_equal(capture.channels[15], [0, 0, 0, 1, 1])
    assert all(channel.dtype == np.uint8 for channel in capture.channels.values())
    assert capture.sample_count == 5
    assert capture.sample_rate == 100e6
    assert capture.clock is None


def test_load_capture_decodes_clock_and_extra_signals(tmp_path: Path) -> None:
    input_file = tmp_path / "capture.bin"
    _write_words(input_file, [0x0000, 0x0181, 0x8000])
    config = _config(
        input_file,
        data_bits=(0, 15),
        clk_channel=7,
        extra_signals={"marker": 8},
    )

    capture = load_capture(config)

    np.testing.assert_array_equal(capture.channels[0], [0, 1, 0])
    np.testing.assert_array_equal(capture.channels[15], [0, 0, 1])
    np.testing.assert_array_equal(capture.clock, [0, 1, 0])
    np.testing.assert_array_equal(capture.extra_signals["marker"], [0, 1, 0])


def test_load_capture_rejects_empty_file(tmp_path: Path) -> None:
    input_file = tmp_path / "empty.bin"
    input_file.write_bytes(b"")

    with pytest.raises(ValueError, match="BIN 为空"):
        load_capture(_config(input_file))


def test_load_capture_rejects_odd_byte_count(tmp_path: Path) -> None:
    input_file = tmp_path / "odd.bin"
    input_file.write_bytes(b"\x01\x02\x03")

    with pytest.raises(ValueError, match="2 bytes 的整数倍"):
        load_capture(_config(input_file))
