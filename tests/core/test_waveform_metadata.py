from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat, savemat

from ble_studio import (
    BLEModulator,
    BLEPhyMode,
    ChannelType,
    ModulatorConfig,
    RFTestPayloadType,
    create_test_packet,
)
from examples.demo import (
    SimConfig,
    _canonical_phy_name,
    _generated_waveform_basename,
    _imported_waveform_basename,
    _sample_rate_token,
    run_simulation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = PROJECT_ROOT / "reference" / "BLE_PKT"
TX_STEM_96M = "LE1M_96Msps_PRBS9_37B_TX"
RX_STEM_96M = "LE1M_96Msps_PRBS9_37B_RX"


def _output_config(*, export_tx: bool, export_files: bool = True) -> dict:
    return {
        "enabled": True,
        "bit_width": 12,
        "iq_format": "two_column",
        "number_format": "signed",
        "scale_to_full": True,
        "add_header": True,
        "export_txt": export_files,
        "export_mat": export_files,
        "export_verilog": export_files,
        "export_tx": export_tx,
    }


def _strict_json(path: Path) -> tuple[dict, str]:
    assert path.is_file(), f"缺少 waveform metadata: {path.name}"
    raw = path.read_text(encoding="utf-8")

    def reject_non_finite(value: str) -> None:
        raise ValueError(f"strict JSON 不允许 {value}")

    return json.loads(raw, parse_constant=reject_non_finite), raw


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module")
def generated_96m(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("waveform_96m")
    config = SimConfig(
        mode="rf_test",
        channel=32,
        phy_mode=BLEPhyMode.LE_1M,
        sample_rate=96e6,
        payload_type=RFTestPayloadType.PRBS9,
        payload_length=37,
        whitening=False,
        access_address=0x71764129,
        crc_init=0x555555,
        channel_type=ChannelType.AWGN,
        snr_db=np.inf,
        freq_offset=0.0,
        html_report=False,
        output_dir=str(output_dir),
        io_output=_output_config(export_tx=True),
    )

    result = run_simulation(config, {})

    assert result.success is True
    return output_dir


def test_generated_waveforms_use_descriptive_matlab_style_basename(
    generated_96m: Path,
) -> None:
    expected = {
        f"{stem}.{suffix}"
        for stem in (TX_STEM_96M, RX_STEM_96M)
        for suffix in ("txt", "mat", "mem", "json")
    }
    actual = {path.name for path in generated_96m.iterdir()}

    assert expected <= actual
    assert not {"iq_tx.txt", "iq_tx.mat", "iq_tx.mem", "iq_tx.json"} & actual
    assert not {"iq_rx.txt", "iq_rx.mat", "iq_rx.mem", "iq_rx.json"} & actual


def test_tx_manifest_is_pretty_strict_json_with_96m_prbs9_metadata(
    generated_96m: Path,
) -> None:
    metadata, raw = _strict_json(generated_96m / f"{TX_STEM_96M}.json")

    assert raw.endswith("\n")
    assert len(raw.splitlines()) > 20
    assert '\n  "schema_version"' in raw
    assert "Infinity" not in raw
    assert "NaN" not in raw

    assert metadata["schema"] == "ble_studio.waveform.v1"
    assert metadata["schema_version"] == 1
    assert metadata["output_kind"] == "clean_tx"
    assert metadata["source_kind"] == "generated_packet"
    assert metadata["mode"] == "rf_test"

    signal = metadata["signal"]
    assert signal["sample_rate_hz"] == 96_000_000
    assert signal["symbol_rate_hz"] == 1_000_000
    assert signal["samples_per_symbol"] == 96
    assert signal["sample_count"] == 36_096
    assert signal["active_samples"] == 36_096
    assert signal["padding_samples"] == 0
    assert signal["duration_us"] == pytest.approx(376.0)

    packet = metadata["packet"]
    assert packet["phy_mode"] == "LE1M"
    assert packet["channel_index"] == 32
    assert packet["access_address"] == "0x71764129"
    assert packet["header_value"] == 0
    assert packet["payload_type"] == "PRBS9"
    assert packet["payload_length_bytes"] == 37
    assert packet["crc_init"] == "0x555555"
    assert packet["whitening"] is False
    assert packet["packet_bit_count"] == 376

    assert metadata["channel"] is None
    assert metadata["modulation"] == {
        "modulation_index": 0.5,
        "bt": 0.5,
        "pulse_length": 1,
    }


def test_tx_protocol_metadata_matches_matlab_golden(generated_96m: Path) -> None:
    metadata, _ = _strict_json(generated_96m / f"{TX_STEM_96M}.json")
    golden, _ = _strict_json(GOLDEN_DIR / "LE1M_96Msps.json")
    packet = metadata["packet"]
    signal = metadata["signal"]

    assert packet["phy_mode"] == golden["phy_mode"]
    assert signal["sample_rate_hz"] == golden["sample_rate_hz"]
    assert signal["samples_per_symbol"] == golden["samples_per_symbol"]
    assert signal["sample_count"] == golden["sample_count"]
    assert packet["channel_index"] == golden["channel_index"]
    assert packet["access_address"] == golden["access_address"]
    assert packet["header_value"] == golden["header_value"]
    assert packet["payload_type"] == golden["payload_type"]
    assert packet["payload_length_bytes"] == golden["payload_length_bytes"]
    assert packet["payload_hex"] == golden["payload_hex"]
    assert packet["pdu_hex"] == golden["pdu_hex"]
    assert packet["pdu_with_crc_hex"] == golden["pdu_with_crc_hex"]
    assert packet["crc_init"] == golden["crc_init"]


def test_manifest_files_match_exported_waveform_and_matlab_packed_mem(
    generated_96m: Path,
) -> None:
    metadata, _ = _strict_json(generated_96m / f"{TX_STEM_96M}.json")
    sample_count = metadata["signal"]["sample_count"]
    files = metadata["files"]

    assert set(files) == {"txt", "mat", "mem"}
    for suffix, descriptor in files.items():
        path = generated_96m / f"{TX_STEM_96M}.{suffix}"
        assert descriptor["name"] == path.name
        assert descriptor["size_bytes"] == path.stat().st_size
        assert descriptor["sha256"] == _sha256(path)

    txt_rows = [
        line
        for line in (generated_96m / f"{TX_STEM_96M}.txt").read_text(
            encoding="ascii"
        ).splitlines()
        if line and not line.startswith("//")
    ]
    mem_rows = (generated_96m / f"{TX_STEM_96M}.mem").read_text(
        encoding="ascii"
    ).splitlines()
    mat_iq = loadmat(generated_96m / f"{TX_STEM_96M}.mat")["iq"]

    assert len(txt_rows) == sample_count
    assert len(mem_rows) == sample_count
    assert np.asarray(mat_iq).size == sample_count
    assert all(re.fullmatch(r"[0-9A-F]{6}", row) for row in mem_rows)
    assert mem_rows == (
        GOLDEN_DIR / "LE1M_96Msps.txt"
    ).read_text(encoding="ascii").splitlines()

    quantization = metadata["quantization"]
    assert set(quantization["applies_to"]) == {"txt", "mem"}
    assert quantization["bit_width"] == 12
    assert quantization["rounding"] == "ties_away_from_zero"
    assert quantization["mem_layout"] == "I high 12 bits, Q low 12 bits"


def test_bypass_rx_manifest_keeps_channel_provenance(generated_96m: Path) -> None:
    tx_metadata, _ = _strict_json(generated_96m / f"{TX_STEM_96M}.json")
    rx_metadata, raw = _strict_json(generated_96m / f"{RX_STEM_96M}.json")

    assert rx_metadata["output_kind"] == "channel_output"
    assert rx_metadata["source_kind"] == "generated_tx"
    assert rx_metadata["signal"] == tx_metadata["signal"]
    assert rx_metadata["packet"] == tx_metadata["packet"]
    assert rx_metadata["channel"]["type"] == "awgn"
    assert rx_metadata["channel"]["bypass"] is True
    assert rx_metadata["channel"]["ebn0_db"] is None
    assert rx_metadata["channel"]["frequency_offset_hz"] == 0
    assert "Infinity" not in raw
    assert (
        generated_96m / f"{RX_STEM_96M}.mem"
    ).read_bytes() == (generated_96m / f"{TX_STEM_96M}.mem").read_bytes()


def test_export_tx_false_only_creates_descriptive_rx_sidecar(tmp_path: Path) -> None:
    config = SimConfig(
        mode="rf_test",
        phy_mode=BLEPhyMode.LE_1M,
        sample_rate=8e6,
        payload_type=RFTestPayloadType.PRBS9,
        payload_length=37,
        snr_db=np.inf,
        html_report=False,
        output_dir=str(tmp_path),
        io_output=_output_config(export_tx=False, export_files=False),
    )

    run_simulation(config, {})

    assert not list(tmp_path.glob("*_TX.*"))
    assert (tmp_path / "LE1M_8Msps_PRBS9_37B_RX.json").is_file()


def test_imported_rx_uses_actual_sample_rate_without_changing_tx_name(
    tmp_path: Path,
) -> None:
    packet = create_test_packet(
        payload_type=RFTestPayloadType.PRBS9,
        payload_length=37,
        channel=0,
        phy_mode=BLEPhyMode.LE_1M,
        access_address=0x71764129,
        whitening=False,
        crc_init=0x555555,
    )
    imported_iq = BLEModulator(ModulatorConfig(
        phy_mode=BLEPhyMode.LE_1M,
        sample_rate=8e6,
    )).modulate(packet.generate())
    input_path = tmp_path / "captured_ble.mat"
    savemat(input_path, {"iq": imported_iq, "fs": 8e6})

    output_dir = tmp_path / "output"
    config = SimConfig(
        mode="rf_test",
        channel=0,
        phy_mode=BLEPhyMode.LE_1M,
        sample_rate=96e6,
        payload_type=RFTestPayloadType.PRBS9,
        payload_length=37,
        whitening=False,
        access_address=0x71764129,
        crc_init=0x555555,
        snr_db=np.inf,
        html_report=False,
        output_dir=str(output_dir),
        io_input={
            "enabled": True,
            "file": str(input_path),
            "file_type": "mat",
            "mat_complex_var": "iq",
        },
        io_output=_output_config(export_tx=True, export_files=False),
    )

    result = run_simulation(config, {})

    assert result.success is True
    tx_path = output_dir / "LE1M_96Msps_PRBS9_37B_TX.json"
    rx_path = output_dir / "captured_ble_8Msps_RX.json"
    tx_metadata, _ = _strict_json(tx_path)
    rx_metadata, _ = _strict_json(rx_path)

    assert tx_metadata["signal"]["sample_rate_hz"] == 96_000_000
    assert tx_metadata["source_kind"] == "generated_packet"
    assert rx_metadata["signal"]["sample_rate_hz"] == 8_000_000
    assert rx_metadata["source_kind"] == "imported_iq"
    assert rx_metadata["packet"] is None
    assert rx_metadata["receiver_expectation"]["payload_type"] == "PRBS9"
    assert rx_metadata["input_file"]["name"] == input_path.name
    assert rx_metadata["input_file"]["sha256"] == _sha256(input_path)


@pytest.mark.parametrize(
    ("phy_mode", "expected"),
    [
        (BLEPhyMode.LE_1M, "LE1M"),
        (BLEPhyMode.LE_2M, "LE2M"),
        (BLEPhyMode.LE_CODED_S8, "LE125K"),
        (BLEPhyMode.LE_CODED_S2, "LE500K"),
    ],
)
def test_filename_phy_tokens_match_matlab_names(
    phy_mode: BLEPhyMode, expected: str
) -> None:
    assert _canonical_phy_name(phy_mode) == expected


def test_filename_formatter_uses_stable_actual_rate_and_safe_input_stem() -> None:
    assert _sample_rate_token(96e6) == "96Msps"
    assert _sample_rate_token(7.5e6) == "7.5Msps"
    assert _imported_waveform_basename(
        {"file": "captures/实验 capture #1.mat"}, 7.5e6
    ) == "capture_1_7.5Msps_RX"

    advertising = SimConfig(mode="advertising", channel=37)
    assert _generated_waveform_basename(
        advertising, 8e6, "TX"
    ) == "LE1M_8Msps_ADV_19B_TX"


def test_finite_awgn_rx_manifest_records_applied_channel(tmp_path: Path) -> None:
    config = SimConfig(
        mode="rf_test",
        phy_mode=BLEPhyMode.LE_1M,
        sample_rate=8e6,
        payload_type=RFTestPayloadType.PRBS9,
        payload_length=37,
        channel_type=ChannelType.AWGN,
        snr_db=100.0,
        html_report=False,
        output_dir=str(tmp_path),
        io_output=_output_config(export_tx=True, export_files=False),
    )

    run_simulation(config, {})

    tx_metadata, _ = _strict_json(
        tmp_path / "LE1M_8Msps_PRBS9_37B_TX.json"
    )
    rx_metadata, raw = _strict_json(
        tmp_path / "LE1M_8Msps_PRBS9_37B_RX.json"
    )
    assert tx_metadata["channel"] is None
    assert rx_metadata["channel"] == {
        "type": "awgn",
        "bypass": False,
        "ebn0_db": 100.0,
        "frequency_offset_hz": 0,
        "doppler_hz": 1,
        "k_factor": 4.0,
        "random_seed": None,
    }
    assert "Infinity" not in raw
