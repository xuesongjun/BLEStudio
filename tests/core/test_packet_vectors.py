from __future__ import annotations

import numpy as np

from ble_studio.packet import (
    BLEPacket,
    RFTestPayloadGenerator,
    RFTestPayloadType,
    create_test_packet,
)


def _bit_string(bits: np.ndarray) -> str:
    return "".join(str(int(bit)) for bit in bits)


def test_whitening_channel_zero_matches_core_6_2_vector() -> None:
    expected = (
        "00000010"
        "01001101"
        "00111101"
        "11000011"
        "11111000"
        "11101100"
        "01010010"
        "11111010"
    )

    actual = BLEPacket()._get_whitening_sequence(0, 64)

    assert _bit_string(actual) == expected


def test_whitening_channel_one_matches_core_6_2_vector() -> None:
    expected = (
        "10010001"
        "00000010"
        "01001101"
        "00111101"
        "11000011"
        "11111000"
        "11101100"
        "01010010"
    )

    actual = BLEPacket()._get_whitening_sequence(1, 64)

    assert _bit_string(actual) == expected


def test_data_channel_crc_matches_core_6_2_vector() -> None:
    packet = BLEPacket()
    pdu = bytes([0x16, 0x05, 0x01, 0x02, 0x03, 0x04, 0x05])

    crc = packet._calculate_crc(pdu, init=0xC4C181)
    crc_bits = packet._int_to_bits(crc, 24)

    assert _bit_string(crc_bits) == "101000100000101101001011"


def test_prbs9_prefix_matches_core_6_2_vector() -> None:
    payload = RFTestPayloadGenerator.generate_prbs9(4)
    bits = BLEPacket()._bytes_to_bits(payload)

    assert _bit_string(bits).startswith("11111111100000111101")


def test_dtm_pattern_header_matches_core_6_2_example() -> None:
    packet = create_test_packet(
        payload_type=RFTestPayloadType.PATTERN_11110000,
        payload_length=37,
    )

    pdu = packet.generate_pdu()
    header_bits = packet._bytes_to_bits(pdu[:2])

    assert pdu == bytes([0x01, 0x25]) + bytes([0xF0] * 37)
    assert _bit_string(header_bits) == "1000000010100100"
