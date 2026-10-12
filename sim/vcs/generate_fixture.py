"""生成 VCS smoke 的可再生 real IQ、CRC 错误波形和独立期望 PDU。"""

import argparse
from pathlib import Path

import numpy as np

from ble_studio.iq_io import write_pretty_json
from ble_studio.modulator import BLEModulator, ModulatorConfig
from ble_studio.packet import BLEPhyMode, RFTestPayloadType, create_test_packet
from ble_studio.coded_phy import encode_coded_packet


def generate_fixture(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    metadata = {}
    for name, phy, length, whitening, crc in [
        ('packet', BLEPhyMode.LE_1M, 37, False, 0x555555),
        ('packet2', BLEPhyMode.LE_2M, 12, True, 0xC4C181),
        ('packet_s2', BLEPhyMode.LE_CODED_S2, 37, False, 0x555555),
        ('packet_s8', BLEPhyMode.LE_CODED_S8, 37, False, 0x555555),
    ]:
        packet = create_test_packet(
            payload_type=RFTestPayloadType.PRBS9, payload_length=length,
            phy_mode=phy, channel=32, whitening=whitening, crc_init=crc,
        )
        bits = packet.generate()
        modulator = BLEModulator(ModulatorConfig(phy_mode=phy, sample_rate=96e6))
        iq = modulator.modulate(bits)
        np.savetxt(output / f'{name}.txt', np.column_stack((iq.real, iq.imag)), fmt='%.17g')
        (output / f'{name}_pdu.hex').write_text(packet.generate_pdu().hex() + '\n', encoding='ascii')
        metadata[name] = {
            'sample_rate_hz': 96e6, 'samples': len(iq), 'phy_mode': phy.name,
            'channel': 32, 'whitening': whitening, 'crc_init': crc,
            'expected_pdu_hex': packet.generate_pdu().hex(),
        }
        if name in ('packet', 'packet_s2', 'packet_s8'):
            # 只破坏 CRC，保留 Header/Payload，验证 CRC gate 不被 PDU match 绕过。
            if name == 'packet':
                bits[-24] ^= 1
                bad_name = 'bad_crc'
            else:
                # Coded 必须在 FEC 前破坏 CRC，不能把可纠正的 air bit 当作 CRC 负例。
                pdu = packet.generate_pdu()
                bad_crc = packet._calculate_crc(pdu, crc) ^ 1
                data = np.concatenate((packet._bytes_to_bits(pdu), packet._int_to_bits(bad_crc, 24)))
                if whitening:
                    data = packet._apply_whitening(data, 32)
                scheme = 2 if phy == BLEPhyMode.LE_CODED_S2 else 8
                bits = encode_coded_packet(packet._int_to_bits(packet.config.access_address, 32), data, scheme)
                bad_name = f'bad_crc_s{scheme}'
            corrupt = modulator.modulate(bits)
            np.savetxt(output / f'{bad_name}.txt', np.column_stack((corrupt.real, corrupt.imag)), fmt='%.17g')
    write_pretty_json(output / 'fixture.json', metadata)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate BLE DAC real-IQ smoke fixtures')
    parser.add_argument('output', type=Path)
    generate_fixture(parser.parse_args().output)
