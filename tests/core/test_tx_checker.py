from __future__ import annotations

import json

import numpy as np
import pytest

from ble_studio.demodulator import DemodulatorConfig
from ble_studio.modulator import BLEModulator, ModulatorConfig
from ble_studio.packet import BLEPhyMode, RFTestPayloadType, create_test_packet
from ble_studio.tx_checker import check_tx_packet, check_tx_packet_dpi
from tests.core.test_coded_loopback import bad_crc_symbols


def _packet_iq(phy=BLEPhyMode.LE_1M, whitening=False, crc_init=0x555555,
               access_address=0x71764129, corrupt_crc=False, payload_length=37):
    packet = create_test_packet(
        payload_type=RFTestPayloadType.PRBS9,
        payload_length=payload_length,
        channel=32,
        phy_mode=phy,
        whitening=whitening,
        crc_init=crc_init,
        access_address=access_address,
    )
    bits = packet.generate()
    if corrupt_crc:
        if phy in (BLEPhyMode.LE_CODED_S2, BLEPhyMode.LE_CODED_S8):
            bits = bad_crc_symbols(packet)
        else:
            bits[-24] ^= 1
    iq = BLEModulator(ModulatorConfig(phy_mode=phy, sample_rate=96e6)).modulate(bits)
    config = DemodulatorConfig(
        phy_mode=phy, sample_rate=96e6, channel=32, whitening=whitening,
        crc_init=crc_init, access_address=access_address,
    )
    return iq, packet.generate_pdu(), config


@pytest.mark.parametrize('phy', list(BLEPhyMode))
@pytest.mark.parametrize('whitening', [False, True])
def test_real_iq_decodes_complete_expected_pdu(phy, whitening):
    iq, pdu, config = _packet_iq(phy, whitening)
    result = check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu)
    assert result.passed
    assert result.sync_found and result.crc_valid and result.pdu_match
    assert result.received_pdu_hex == pdu.hex()
    assert result.expected_pdu_hex == pdu.hex()
    assert result.sample_count == len(iq)
    assert result.failure_reason == ''


def test_custom_crc_and_access_address():
    iq, pdu, config = _packet_iq(crc_init=0xC4C181, access_address=0xAA08192B)
    assert check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu).passed


@pytest.mark.parametrize('phy', list(BLEPhyMode))
def test_crc_correct_but_wrong_expected_payload_fails(phy):
    iq, pdu, config = _packet_iq(phy=phy)
    expected = pdu[:-1] + bytes([pdu[-1] ^ 1])
    result = check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=expected)
    assert result.sync_found and result.crc_valid
    assert not result.pdu_match and not result.passed
    assert result.failure_reason == 'PDU_MISMATCH'


@pytest.mark.parametrize('phy', list(BLEPhyMode))
def test_incorrect_crc_fails_even_when_pdu_matches(phy):
    iq, pdu, config = _packet_iq(phy=phy, corrupt_crc=True)
    result = check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu)
    assert result.sync_found and result.pdu_match
    assert not result.crc_valid and not result.passed
    assert result.failure_reason == 'CRC_FAILED'


@pytest.mark.parametrize('padding', [(0, 0), (97, 193), (960, 960)])
def test_phase_scale_and_idle_padding(padding):
    iq, pdu, config = _packet_iq()
    iq = np.pad(iq * 0.2 * np.exp(0.73j), padding)
    assert check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu).passed


def test_empty_payload_is_checked():
    iq, pdu, config = _packet_iq(payload_length=0)
    assert check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu).passed


@pytest.mark.parametrize(('i_data', 'q_data', 'error'), [
    ([], [], 'non-empty'),
    ([0, 1], [0], 'same length'),
    ([[1, 2]], [[1, 2]], 'one-dimensional'),
    ([np.nan], [0], 'finite'),
    ([0], [np.inf], 'finite'),
    ([1j], [0], 'real'),
])
def test_invalid_iq_is_rejected(i_data, q_data, error):
    _, pdu, config = _packet_iq()
    with pytest.raises((ValueError, TypeError), match=error):
        check_tx_packet(i_data, q_data, config=config, expected_pdu=pdu)


@pytest.mark.parametrize('sample_rate', [0, 7.5e6, np.inf, np.nan])
def test_invalid_sample_rate_is_rejected(sample_rate):
    iq, pdu, config = _packet_iq()
    config.sample_rate = sample_rate
    with pytest.raises(ValueError, match='sample_rate'):
        check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu)


@pytest.mark.parametrize('pdu', [b'', b'\x00', b'\x00\x02\x01'])
def test_invalid_expected_pdu_is_rejected(pdu):
    iq, _, config = _packet_iq()
    with pytest.raises(ValueError, match='expected_pdu'):
        check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu)


def test_missing_or_non_bytes_expected_pdu_is_rejected():
    iq, _, config = _packet_iq()
    with pytest.raises(TypeError, match='expected_pdu'):
        check_tx_packet(iq.real, iq.imag, config=config, expected_pdu='0025')


@pytest.mark.parametrize(('iq', 'reason'), [
    (np.zeros(36096, dtype=complex), 'NO_SIGNAL'),
    (np.ones(12, dtype=complex), 'INSUFFICIENT_SAMPLES'),
    (np.ones(36096, dtype=complex), 'SYNC_NOT_FOUND'),
])
def test_absent_or_truncated_packet_cannot_pass(iq, reason):
    _, pdu, config = _packet_iq()
    result = check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu)
    assert not result.passed
    assert result.failure_reason == reason


def test_repeated_different_packets_do_not_share_results():
    for phy, length in [(BLEPhyMode.LE_1M, 37), (BLEPhyMode.LE_2M, 12),
                        (BLEPhyMode.LE_CODED_S2, 37), (BLEPhyMode.LE_CODED_S8, 37),
                        (BLEPhyMode.LE_1M, 0)]:
        iq, pdu, config = _packet_iq(phy=phy, payload_length=length)
        assert check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu).passed


@pytest.mark.parametrize('phy', list(BLEPhyMode))
def test_pretty_json_contains_full_packet_and_configuration(tmp_path, phy):
    iq, pdu, config = _packet_iq(phy=phy)
    path = tmp_path / 'packet_0001.json'
    result = check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu, report_path=path)
    text = path.read_text(encoding='utf-8')
    report = json.loads(text)
    assert report == result.to_dict()
    assert '\n  "' in text and text.endswith('\n')
    assert report['expected_pdu_hex'] == pdu.hex()
    assert report['sample_rate_hz'] == 96e6
    assert report['access_address'] == 0x71764129


@pytest.mark.parametrize('phy', list(BLEPhyMode))
def test_dpi_callable_uses_explicit_protocol_parameters(tmp_path, phy):
    iq, pdu, config = _packet_iq(phy=phy, whitening=True, crc_init=0xC4C181)
    result = check_tx_packet_dpi(
        iq.real.tolist(), iq.imag.tolist(), config.sample_rate, int(config.phy_mode),
        config.access_address, config.channel, int(config.whitening), config.crc_init,
        pdu.hex(), str(tmp_path / 'dpi.json'),
    )
    assert result['passed'] and result['crc_valid'] and result['pdu_match']
    assert result['received_pdu_hex'] == pdu.hex()


@pytest.mark.parametrize('phy', [BLEPhyMode.LE_CODED_S2, BLEPhyMode.LE_CODED_S8])
def test_checker_preserves_coded_ci_mismatch(phy):
    iq, pdu, config = _packet_iq(phy=phy)
    config.phy_mode = BLEPhyMode.LE_CODED_S8 if phy == BLEPhyMode.LE_CODED_S2 else BLEPhyMode.LE_CODED_S2
    result = check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu)
    assert not result.passed and result.failure_reason == 'PHY_CI_MISMATCH'


@pytest.mark.parametrize('phy', [BLEPhyMode.LE_CODED_S2, BLEPhyMode.LE_CODED_S8])
def test_checker_preserves_coded_truncation(phy):
    iq, pdu, config = _packet_iq(phy=phy)
    iq = iq[:-96]
    result = check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=pdu)
    assert not result.passed and result.failure_reason == 'TRUNCATED_PACKET'


@pytest.mark.parametrize('whitening', [-1, 2])
def test_dpi_callable_rejects_invalid_boolean(whitening):
    with pytest.raises(ValueError, match='whitening'):
        check_tx_packet_dpi([1.0], [0.0], 96e6, 1, 0x71764129, 32, whitening, 0x555555, '0000', '')
