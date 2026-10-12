from __future__ import annotations

import json
import numpy as np
import pytest

from ble_studio.demodulator import DemodulatorConfig
from ble_studio.packet import BLEPhyMode
from ble_studio.tx_checker import check_tx_packet
from sim.vcs.generate_fixture import generate_fixture


@pytest.fixture(scope='module')
def fixtures(tmp_path_factory):
    directory = tmp_path_factory.mktemp('vcs_coded_fixtures')
    generate_fixture(directory)
    return directory


@pytest.mark.parametrize(('scheme', 'sample_count'), [(2, 101184), (8, 296448)])
def test_vcs_coded_fixture_good_bad_crc_and_ci_mismatch(fixtures, scheme, sample_count):
    metadata = json.loads((fixtures / 'fixture.json').read_text(encoding='utf-8'))[f'packet_s{scheme}']
    assert metadata['samples'] == sample_count
    config = DemodulatorConfig(
        phy_mode=BLEPhyMode[f'LE_CODED_S{scheme}'], sample_rate=96e6,
        access_address=0x71764129, channel=32, whitening=False,
    )
    pdu = bytes.fromhex((fixtures / f'packet_s{scheme}_pdu.hex').read_text(encoding='ascii').strip())
    for name, expected in [(f'packet_s{scheme}', ''), (f'bad_crc_s{scheme}', 'CRC_FAILED')]:
        iq = np.loadtxt(fixtures / f'{name}.txt')
        result = check_tx_packet(iq[:, 0], iq[:, 1], config=config, expected_pdu=pdu)
        assert result.failure_reason == expected
        assert result.pdu_match and result.sync_found
        assert result.crc_valid is (not expected)
    iq = np.loadtxt(fixtures / f'packet_s{scheme}.txt')
    config.phy_mode = BLEPhyMode.LE_CODED_S8 if scheme == 2 else BLEPhyMode.LE_CODED_S2
    result = check_tx_packet(iq[:, 0], iq[:, 1], config=config, expected_pdu=pdu)
    assert not result.passed and result.failure_reason == 'PHY_CI_MISMATCH'
