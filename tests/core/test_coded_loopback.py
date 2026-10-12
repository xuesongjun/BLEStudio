from __future__ import annotations

import numpy as np
import pytest

from ble_studio.coded_phy import (
    CODED_PREAMBLE, CODED_PREFIX_SYMBOLS, coded_symbol_count,
    convolutional_encode, encode_coded_packet, pattern_map,
)
from ble_studio.demodulator import BLEDemodulator, DemodulatorConfig
from ble_studio.modulator import BLEModulator, ModulatorConfig
from ble_studio.packet import (
    BLEPhyMode, DataChannelPDU, RFTestPayloadType, create_data_packet, create_test_packet,
)
from tests.core.test_coded_phy import VECTOR, reference_air, vector_bits


MODES = [BLEPhyMode.LE_CODED_S2, BLEPhyMode.LE_CODED_S8]


def coding_scheme(mode):
    return 2 if mode == BLEPhyMode.LE_CODED_S2 else 8


def waveform(packet, fs=8e6):
    return BLEModulator(ModulatorConfig(phy_mode=packet.config.phy_mode, sample_rate=fs)).modulate(packet.generate())


def receiver(packet, fs=8e6, *, mode=None):
    cfg = packet.config
    whitening = getattr(packet, 'test_config', None) is None or packet.test_config.whitening
    return BLEDemodulator(DemodulatorConfig(
        phy_mode=mode or cfg.phy_mode, sample_rate=fs, access_address=cfg.access_address,
        channel=cfg.channel, crc_init=cfg.crc_init, whitening=whitening,
    ))


@pytest.mark.parametrize('mode', MODES)
def test_packet_generator_matches_official_air_symbols(mode):
    packet = create_test_packet(phy_mode=mode, payload_length=3, access_address=int(VECTOR['access_address'], 16))
    packet._test_payload = bytes.fromhex(VECTOR['pdu_hex'])[2:]
    np.testing.assert_array_equal(packet.generate(), reference_air(coding_scheme(mode)))
    unpacked = np.unpackbits(np.frombuffer(packet.generate_bytes(), dtype=np.uint8), bitorder='little')
    np.testing.assert_array_equal(unpacked[:len(packet.generate())], packet.generate())


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('fs', [8e6, 96e6])
@pytest.mark.parametrize('length', [0, 1, 37, 255])
def test_coded_dtm_loopback_and_packet_boundaries(mode, fs, length):
    packet = create_test_packet(phy_mode=mode, payload_length=length, channel=32)
    signal = waveform(packet, fs)
    expected_count = coded_symbol_count(length, coding_scheme(mode)) * int(fs / 1e6)
    assert len(signal) == expected_count
    result = receiver(packet, fs).demodulate(signal)
    assert result.success and result.sync_found and result.crc_valid
    assert result.pdu == packet.generate_pdu()
    assert result.failure_reason == ''
    assert result.packet_start_sample == 0
    assert result.packet_sample_count == expected_count
    np.testing.assert_array_equal(result.bits[:len(packet.generate())], packet.generate())


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('payload_type', list(RFTestPayloadType))
@pytest.mark.parametrize('whitening', [False, True])
def test_coded_all_dtm_patterns_with_whitening_and_custom_crc(mode, payload_type, whitening):
    packet = create_test_packet(
        phy_mode=mode, payload_type=payload_type, payload_length=37, channel=17,
        access_address=0xAA08192B, crc_init=0xC4C181, whitening=whitening,
    )
    result = receiver(packet).demodulate(waveform(packet))
    assert result.success and result.pdu == packet.generate_pdu()


@pytest.mark.parametrize('mode', MODES)
def test_coded_arbitrary_data_pdu(mode):
    pdu = DataChannelPDU.create_data_pdu(b'\x00\xFF\x31\x42\x81', md=1)
    packet = create_data_packet(pdu, access_address=0xAA08192B, crc_init=0xC4C181, channel=16, phy_mode=mode)
    result = receiver(packet).demodulate(waveform(packet))
    assert result.success and result.pdu == pdu


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('fs', [8e6, 96e6])
@pytest.mark.parametrize('frequency_offset', [0, -75000, 75000])
def test_coded_idle_fractional_sample_offset_phase_gain_and_cfo(mode, fs, frequency_offset):
    packet = create_test_packet(phy_mode=mode, payload_length=37)
    iq = waveform(packet, fs) * 0.35 * np.exp(1j * 1.234)
    iq *= np.exp(2j * np.pi * frequency_offset * np.arange(len(iq)) / fs)
    lead = 2 * int(fs / 1e6) + 3
    signal = np.pad(iq, (lead, 3 * int(fs / 1e6)))
    result = receiver(packet, fs).demodulate(signal)
    assert result.success and result.pdu == packet.generate_pdu()
    assert result.packet_start_sample == lead
    assert result.packet_sample_count == len(iq)
    assert abs(result.freq_offset - frequency_offset) < 500


def bad_crc_symbols(packet):
    pdu = packet.generate_pdu()
    crc = packet._calculate_crc(pdu, packet.config.crc_init) ^ 1
    data = np.concatenate((packet._bytes_to_bits(pdu), packet._int_to_bits(crc, 24)))
    if packet.test_config.whitening:
        data = packet._apply_whitening(data, packet.config.channel)
    return encode_coded_packet(packet._int_to_bits(packet.config.access_address, 32), data,
                               coding_scheme(packet.config.phy_mode))


@pytest.mark.parametrize('mode', MODES)
def test_coded_crc_error_is_injected_before_fec(mode):
    packet = create_test_packet(phy_mode=mode)
    iq = BLEModulator(ModulatorConfig(phy_mode=mode)).modulate(bad_crc_symbols(packet))
    result = receiver(packet).demodulate(iq)
    assert not result.success and result.sync_found and not result.crc_valid
    assert result.pdu == packet.generate_pdu()
    assert result.failure_reason == 'CRC_FAILED'


@pytest.mark.parametrize('mode', MODES)
def test_coded_phy_ci_mismatch(mode):
    packet = create_test_packet(phy_mode=mode)
    other = MODES[1] if mode == MODES[0] else MODES[0]
    result = receiver(packet, mode=other).demodulate(waveform(packet))
    assert not result.success and result.sync_found and not result.crc_valid
    assert result.failure_reason == 'PHY_CI_MISMATCH'


@pytest.mark.parametrize('ci', [[0, 1], [1, 1]])
def test_coded_reserved_ci_cannot_pass(ci):
    packet = create_test_packet(phy_mode=MODES[0])
    info = np.concatenate((packet._int_to_bits(packet.config.access_address, 32), ci, [0, 0, 0]))
    bits = np.concatenate((CODED_PREAMBLE, pattern_map(convolutional_encode(info), 8),
                           packet.generate()[CODED_PREFIX_SYMBOLS:]))
    iq = BLEModulator(ModulatorConfig(phy_mode=MODES[0])).modulate(bits)
    result = receiver(packet).demodulate(iq)
    assert not result.success and result.failure_reason == 'INVALID_CI'


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('missing_symbols', [1, 12, 100])
def test_coded_truncated_packet_cannot_pass(mode, missing_symbols):
    packet = create_test_packet(phy_mode=mode)
    iq = waveform(packet)[:-missing_symbols * 8]
    result = receiver(packet).demodulate(iq)
    assert not result.success and result.failure_reason == 'TRUNCATED_PACKET'


@pytest.mark.parametrize('mode', MODES)
def test_coded_no_signal_cannot_pass(mode):
    packet = create_test_packet(phy_mode=mode)
    result = receiver(packet).demodulate(np.zeros(30000, dtype=complex))
    assert not result.success and not result.sync_found
    assert result.failure_reason == 'NO_SIGNAL'


@pytest.mark.parametrize('mode', MODES)
def test_receiver_decodes_independent_official_air_vector(mode):
    config = DemodulatorConfig(phy_mode=mode, whitening=False)
    iq = BLEModulator(ModulatorConfig(phy_mode=mode)).modulate(reference_air(coding_scheme(mode)))
    result = BLEDemodulator(config).demodulate(iq)
    assert result.success and result.pdu.hex() == VECTOR['pdu_hex']


@pytest.mark.parametrize('mode', MODES)
def test_coded_correctable_air_symbol_error(mode):
    packet = create_test_packet(phy_mode=mode)
    bits = packet.generate()
    bits[CODED_PREFIX_SYMBOLS + 47] ^= 1
    iq = BLEModulator(ModulatorConfig(phy_mode=mode)).modulate(bits)
    result = receiver(packet).demodulate(iq)
    assert result.success and result.pdu == packet.generate_pdu()


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('gap', [0, 43, 800])
@pytest.mark.parametrize('first_length', [1, 255])
def test_coded_find_packets_uses_exact_long_packet_length(mode, gap, first_length):
    first = create_test_packet(phy_mode=mode, payload_length=first_length)
    second = create_test_packet(phy_mode=mode, payload_length=255 if first_length == 1 else 37)
    first_iq, second_iq = waveform(first), waveform(second)
    lead = 19
    signal = np.concatenate((np.zeros(lead), first_iq, np.zeros(gap), second_iq))
    results = receiver(first).find_packets(signal)
    assert [item.pdu for item in results] == [first.generate_pdu(), second.generate_pdu()]
    assert [item.packet_start_sample for item in results] == [lead, lead + len(first_iq) + gap]
    assert [item.packet_sample_count for item in results] == [len(first_iq), len(second_iq)]
    assert len(receiver(first).find_packets(signal, max_packets=1)) == 1


def test_truncated_block_one_after_long_idle_returns_diagnostic():
    packet = create_test_packet(phy_mode=MODES[0])
    signal = np.pad(waveform(packet)[:340 * 8], (1000, 0))
    result = receiver(packet).demodulate(signal)
    assert not result.success and result.failure_reason == 'TRUNCATED_PACKET'


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('fs', [1e6, 2e6, 3e6, 16e6])
def test_coded_integer_sps_at_low_and_intermediate_rates(mode, fs):
    packet = create_test_packet(phy_mode=mode)
    signal = waveform(packet, fs)
    result = receiver(packet, fs).demodulate(signal)
    assert result.success and result.pdu == packet.generate_pdu()
    assert result.packet_sample_count == len(signal)


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('cfo', [0, 1000, 75000, 250000])
def test_unmodulated_carrier_has_no_coded_sync(mode, cfo):
    packet = create_test_packet(phy_mode=mode, payload_length=0, access_address=0, crc_init=0)
    signal = np.exp(2j * np.pi * cfo * np.arange(len(waveform(packet))) / 8e6)
    result = receiver(packet).demodulate(signal)
    assert not result.success and not result.sync_found
    assert result.failure_reason == 'SYNC_NOT_FOUND'


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('lead', [7, 19])
def test_coded_adjacent_packets_with_half_symbol_clock_shift(mode, lead):
    first = create_test_packet(phy_mode=mode, payload_length=1)
    second = create_test_packet(phy_mode=mode, payload_length=37)
    a, b = waveform(first), waveform(second)
    signal = np.concatenate((np.zeros(lead), a, np.zeros(4), b))
    results = receiver(first).find_packets(signal)
    assert [item.pdu for item in results] == [first.generate_pdu(), second.generate_pdu()]
    assert [item.packet_start_sample for item in results] == [lead, lead + len(a) + 4]
