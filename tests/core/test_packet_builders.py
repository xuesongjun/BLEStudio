from __future__ import annotations

import numpy as np
import pytest

from ble_studio.packet import (
    AdvertisingPDUType,
    BLEPacket,
    BLEPacketConfig,
    BLEPhyMode,
    DataChannelPDU,
    create_advertising_packet,
    create_connect_ind,
    create_data_packet,
)


@pytest.mark.parametrize(
    ("phy_mode", "access_address", "expected"),
    [
        (BLEPhyMode.LE_1M, 0x8E89BED6, [0, 1] * 4),
        (BLEPhyMode.LE_1M, 0x71764129, [1, 0] * 4),
        (BLEPhyMode.LE_2M, 0x8E89BED6, [0, 1] * 8),
        (BLEPhyMode.LE_2M, 0x71764129, [1, 0] * 8),
    ],
)
def test_preamble_follows_access_address_lsb(
    phy_mode: BLEPhyMode,
    access_address: int,
    expected: list[int],
) -> None:
    packet = BLEPacket(BLEPacketConfig(
        phy_mode=phy_mode,
        access_address=access_address,
        payload=b"",
    ))

    actual = packet.generate()[:len(expected)]

    np.testing.assert_array_equal(actual, np.array(expected, dtype=np.uint8))


def test_create_data_packet_preserves_complete_pdu() -> None:
    pdu = DataChannelPDU.create_data_pdu(
        b"\x01\x02\x03",
        nesn=0,
        sn=0,
        md=0,
        is_start=True,
    )

    packet = create_data_packet(
        pdu=pdu,
        access_address=0x12345678,
        crc_init=0xA1B2C3,
        channel=0,
    )

    assert pdu == bytes.fromhex("0203010203")
    assert packet.generate_pdu() == pdu


def test_packet_generation_uses_configured_crc_init() -> None:
    pdu = DataChannelPDU.create_data_pdu(b"\x01\x02\x03\x04\x05", md=1)
    packet = create_data_packet(
        pdu=pdu,
        access_address=0xAA08192B,
        crc_init=0xC4C181,
        channel=16,
    )

    bits = packet.generate()
    expected_crc = BLEPacket()._int_to_bits(
        BLEPacket()._calculate_crc(pdu, init=0xC4C181),
        24,
    )
    whitened_data = bits[-(len(pdu) * 8 + 24):]
    data = packet._apply_whitening(whitened_data, 16)

    np.testing.assert_array_equal(data[-24:], expected_crc)


def test_create_connect_ind_keeps_full_payload() -> None:
    init_address = bytes.fromhex("010203040506")
    adv_address = bytes.fromhex("112233445566")

    packet = create_connect_ind(
        init_address=init_address,
        adv_address=adv_address,
        access_address=0x12345678,
        crc_init=0xA1B2C3,
    )

    pdu = packet.generate_pdu()
    assert pdu[0] & 0x0F == AdvertisingPDUType.CONNECT_IND
    assert pdu[1] == 34
    assert pdu[2:8] == init_address
    assert pdu[8:14] == adv_address
    assert pdu[14:18] == bytes.fromhex("78563412")
    assert pdu[18:21] == bytes.fromhex("c3b2a1")
    assert len(pdu) == 36


def test_create_advertising_packet_rejects_invalid_address_length() -> None:
    with pytest.raises(ValueError, match="adv_address"):
        create_advertising_packet(b"\x01\x02")


def test_create_data_packet_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="length"):
        create_data_packet(
            pdu=bytes.fromhex("0205010203"),
            access_address=0x12345678,
            crc_init=0xA1B2C3,
            channel=0,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("channel", 40, "channel"),
        ("access_address", 1 << 32, "access_address"),
        ("crc_init", 1 << 24, "crc_init"),
        ("channel_type", 99, "channel_type"),
    ],
)
def test_packet_rejects_out_of_range_config(
    field: str,
    value: int,
    message: str,
) -> None:
    config = BLEPacketConfig()
    setattr(config, field, value)

    with pytest.raises(ValueError, match=message):
        BLEPacket(config)
