from __future__ import annotations

from pathlib import Path

import numpy as np

from ble_studio.logic_analyzer.models import LogicAnalyzerConfig
from ble_studio.logic_analyzer.pipeline import process_capture


def _write_words(path: Path, words: list[int]) -> None:
    path.write_bytes(b"".join(word.to_bytes(2, "little") for word in words))


def _sdr_config(
    input_file: Path,
    *,
    sample_rate: float,
    data_rate: float,
    bit_width: int,
    glitch_filter: bool = False,
    output_spike_filter: bool = False,
) -> LogicAnalyzerConfig:
    return LogicAnalyzerConfig(
        input_file=input_file,
        output_dir=input_file.parent,
        output_stem="result",
        profile="parallel_sdr",
        sample_rate=sample_rate,
        data_rate=data_rate,
        mode="sdr",
        data_bits=tuple(range(bit_width)),
        clk_channel=None,
        bit_width=bit_width,
        eye_align=False,
        search_range=1,
        glitch_filter=glitch_filter,
        glitch_threshold=0.3,
        adaptive_filter=False,
        output_spike_filter=output_spike_filter,
    )


def test_pipeline_glitch_filter_switch_controls_raw_pulse_repair(
    tmp_path: Path,
) -> None:
    input_file = tmp_path / "glitch.bin"
    words = [0] * 30
    words[10] = 1
    _write_words(input_file, words)

    without_filter = process_capture(_sdr_config(
        input_file,
        sample_rate=10,
        data_rate=1,
        bit_width=1,
        glitch_filter=False,
    ))
    with_filter = process_capture(_sdr_config(
        input_file,
        sample_rate=10,
        data_rate=1,
        bit_width=1,
        glitch_filter=True,
    ))

    np.testing.assert_array_equal(without_filter.data1, [0, 1, 0])
    np.testing.assert_array_equal(with_filter.data1, [0, 0, 0])
    assert without_filter.cleaned_channels[0][10] == 1
    assert with_filter.cleaned_channels[0][10] == 0


def test_pipeline_output_spike_filter_switch_controls_extracted_samples(
    tmp_path: Path,
) -> None:
    input_file = tmp_path / "spike.bin"
    _write_words(input_file, [0, 0, 100, 0, 0, 0])

    without_filter = process_capture(_sdr_config(
        input_file,
        sample_rate=1,
        data_rate=1,
        bit_width=8,
        output_spike_filter=False,
    ))
    with_filter = process_capture(_sdr_config(
        input_file,
        sample_rate=1,
        data_rate=1,
        bit_width=8,
        output_spike_filter=True,
    ))

    np.testing.assert_array_equal(without_filter.data1, [0, 0, 100, 0, 0, 0])
    np.testing.assert_array_equal(with_filter.data1, [0, 0, 0, 0, 0, 0])
    np.testing.assert_array_equal(
        without_filter.cleaned_channels[2], with_filter.cleaned_channels[2]
    )
