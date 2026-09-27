from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ble_studio import import_iq_mat
from ble_studio.demodulator import BLEDemodulator, DemodulatorConfig
from ble_studio.modulator import BLEModulator, ModulatorConfig
from ble_studio.packet import (
    BLEPhyMode,
    DataChannelPDU,
    RFTestPayloadType,
    create_advertising_packet,
    create_data_packet,
    create_test_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _loopback(
    packet,
    *,
    phy_mode: BLEPhyMode,
    access_address: int,
    channel: int,
    whitening: bool,
    crc_init: int = 0x555555,
    sample_rate: float = 8e6,
):
    bits = packet.generate()
    signal = BLEModulator(ModulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
    )).modulate(bits)
    result = BLEDemodulator(DemodulatorConfig(
        phy_mode=phy_mode,
        sample_rate=sample_rate,
        access_address=access_address,
        channel=channel,
        whitening=whitening,
        crc_init=crc_init,
    )).demodulate(signal)
    return bits, result


@pytest.mark.parametrize("phy_mode", [BLEPhyMode.LE_1M, BLEPhyMode.LE_2M])
def test_dtm_ideal_loopback(phy_mode: BLEPhyMode) -> None:
    packet = create_test_packet(
        payload_type=RFTestPayloadType.PRBS9,
        payload_length=37,
        channel=0,
        phy_mode=phy_mode,
        whitening=False,
    )

    bits, result = _loopback(
        packet,
        phy_mode=phy_mode,
        access_address=0x71764129,
        channel=0,
        whitening=False,
    )

    assert result.success is True
    assert result.sync_found is True
    assert result.crc_valid is True
    np.testing.assert_array_equal(result.bits[:len(bits)], bits)


def test_advertising_ideal_loopback_with_even_access_address() -> None:
    packet = create_advertising_packet(
        adv_address=bytes.fromhex("112233445566"),
        adv_data=bytes.fromhex("020106"),
        channel=37,
    )

    _, result = _loopback(
        packet,
        phy_mode=BLEPhyMode.LE_1M,
        access_address=0x8E89BED6,
        channel=37,
        whitening=True,
    )

    assert result.success is True
    assert result.sync_found is True
    assert result.crc_valid is True
    assert result.pdu == packet.generate_pdu()


def test_data_channel_custom_crc_and_whitening_loopback() -> None:
    pdu = DataChannelPDU.create_data_pdu(b"\x01\x02\x03\x04\x05", md=1)
    packet = create_data_packet(
        pdu=pdu,
        access_address=0xAA08192B,
        crc_init=0xC4C181,
        channel=16,
    )

    _, result = _loopback(
        packet,
        phy_mode=BLEPhyMode.LE_1M,
        access_address=0xAA08192B,
        channel=16,
        whitening=True,
        crc_init=0xC4C181,
    )

    assert result.success is True
    assert result.crc_valid is True
    assert result.pdu == pdu


def test_matlab_bwv_reference_still_decodes() -> None:
    signal, sample_rate = import_iq_mat(
        PROJECT_ROOT / "data" / "iq" / "BLE_1M.bwv",
        complex_var="wave",
    )
    result = BLEDemodulator(DemodulatorConfig(
        phy_mode=BLEPhyMode.LE_1M,
        sample_rate=sample_rate,
        access_address=0x71764129,
        channel=0,
        whitening=False,
    )).demodulate(signal)

    assert result.success is True
    assert result.sync_found is True
    assert result.crc_valid is True


@pytest.mark.parametrize("phy_mode", [BLEPhyMode.LE_CODED_S2, BLEPhyMode.LE_CODED_S8])
def test_coded_phy_is_rejected_explicitly(phy_mode: BLEPhyMode) -> None:
    with pytest.raises(NotImplementedError, match="LE Coded"):
        create_test_packet(phy_mode=phy_mode)
    with pytest.raises(NotImplementedError, match="LE Coded"):
        BLEModulator(ModulatorConfig(phy_mode=phy_mode))
    with pytest.raises(NotImplementedError, match="LE Coded"):
        BLEDemodulator(DemodulatorConfig(phy_mode=phy_mode))


@pytest.mark.parametrize("sample_rate", [7.5e6, 0.5e6, 0.0])
def test_invalid_samples_per_symbol_is_rejected(sample_rate: float) -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        BLEModulator(ModulatorConfig(sample_rate=sample_rate))
    with pytest.raises(ValueError, match="sample_rate"):
        BLEDemodulator(DemodulatorConfig(sample_rate=sample_rate))
