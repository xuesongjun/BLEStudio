from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ble_studio.coded_phy import (
    CODED_PREAMBLE,
    coded_symbol_count,
    convolutional_encode,
    encode_coded_packet,
    pattern_demap,
    pattern_map,
    viterbi_decode,
)


VECTOR = json.loads((Path(__file__).parent / 'fixtures/le_coded_core_6_2.json').read_text())


def vector_bits(key: str) -> np.ndarray:
    return np.fromiter((int(bit) for bit in ''.join(VECTOR[key].split())), dtype=np.uint8)


def byte_bits(hex_string: str) -> np.ndarray:
    return np.unpackbits(np.frombuffer(bytes.fromhex(hex_string), dtype=np.uint8), bitorder='little')


def reference_air(scheme: int) -> np.ndarray:
    # 直接拼接规范提供的固定输出，不调用被测 encoder 生成 expected。
    keys = ['preamble_air', 'aa_air', f'ci{scheme}_air', f'term1_s{scheme}_air']
    keys += ['pdu_output', 'crc_output', 'term2_output'] if scheme == 2 else [
        's8_pdu_air', 's8_crc_air', 's8_term2_air',
    ]
    return np.concatenate([vector_bits(key) for key in keys])


@pytest.mark.parametrize('scheme', [2, 8])
def test_fec_block_one_matches_core_vector(scheme):
    information = np.concatenate([vector_bits('aa_input'), [int(scheme == 2), 0, 0, 0, 0]])
    expected = np.concatenate([
        vector_bits('aa_output'), vector_bits(f'ci{scheme}_output'),
        vector_bits(f'term1_s{scheme}_output'),
    ])
    np.testing.assert_array_equal(convolutional_encode(information), expected)
    np.testing.assert_array_equal(viterbi_decode(2.0 * expected - 1), information)


def test_fec_block_two_matches_core_vector():
    information = np.concatenate([byte_bits(VECTOR['pdu_hex'] + VECTOR['crc_hex']), [0, 0, 0]])
    expected = np.concatenate([vector_bits(key) for key in ['pdu_output', 'crc_output', 'term2_output']])
    np.testing.assert_array_equal(convolutional_encode(information), expected)
    np.testing.assert_array_equal(viterbi_decode(2.0 * expected - 1), information)


@pytest.mark.parametrize('field', ['aa', 'pdu', 'crc', 'term2'])
def test_s8_mapper_matches_independent_transmitted_symbols(field):
    output = 'aa_air' if field == 'aa' else f's8_{field}_air'
    np.testing.assert_array_equal(pattern_map(vector_bits(f'{field}_output'), 8), vector_bits(output))
    soft = pattern_demap(2.0 * vector_bits(output) - 1, 8)
    np.testing.assert_array_equal(soft > 0, vector_bits(f'{field}_output'))


@pytest.mark.parametrize(('scheme', 'length'), [(2, 510), (8, 912)])
def test_complete_air_packet_matches_core_vector(scheme, length):
    np.testing.assert_array_equal(CODED_PREAMBLE, vector_bits('preamble_air'))
    actual = encode_coded_packet(vector_bits('aa_input'), byte_bits(VECTOR['pdu_hex'] + VECTOR['crc_hex']), scheme)
    np.testing.assert_array_equal(actual, reference_air(scheme))
    assert len(actual) == length == coded_symbol_count(3, scheme)


def test_s2_mapper_does_not_repeat_symbols():
    bits = vector_bits('pdu_output')
    np.testing.assert_array_equal(pattern_map(bits, 2), bits)
    np.testing.assert_array_equal(pattern_demap(2.0 * bits - 1, 2), 2.0 * bits - 1)


def test_viterbi_corrects_a_damaged_fec_bit():
    expected = np.concatenate([vector_bits(key) for key in ['pdu_output', 'crc_output', 'term2_output']])
    soft = 2.0 * expected - 1
    soft[43] *= -1
    information = np.concatenate([byte_bits(VECTOR['pdu_hex'] + VECTOR['crc_hex']), [0, 0, 0]])
    np.testing.assert_array_equal(viterbi_decode(soft), information)


def test_partial_header_decoder_does_not_force_zero_terminal_state():
    bits = byte_bits('0025')
    # prefix 在包中不是 TERM，最后三个信息 bits 也不一定为 0。
    bits[-3:] = [1, 0, 1]
    np.testing.assert_array_equal(viterbi_decode(2.0 * convolutional_encode(bits) - 1, terminated=False), bits)


@pytest.mark.parametrize(('bits', 'error'), [([[0, 1]], 'one-dimensional'), ([0, 2], '0 and 1'), ([np.nan], '0 and 1')])
def test_encoder_rejects_invalid_input(bits, error):
    with pytest.raises(ValueError, match=error):
        convolutional_encode(bits)


@pytest.mark.parametrize('values', [[], [1.0], [np.nan, 1.0], [[1.0, -1.0]]])
def test_decoder_rejects_invalid_soft_input(values):
    with pytest.raises(ValueError):
        viterbi_decode(values)


@pytest.mark.parametrize('scheme', [0, 1, 4, 16])
def test_mapper_rejects_invalid_coding_scheme(scheme):
    with pytest.raises(ValueError, match='coding_scheme'):
        pattern_map([0, 1], scheme)


def test_demapper_rejects_incomplete_s8_pattern():
    with pytest.raises(ValueError, match='multiple'):
        pattern_demap([-1, -1, 1], 8)


@pytest.mark.parametrize(('scheme', 'count'), [(2, 1054), (8, 3088)])
def test_37_byte_packet_air_length(scheme, count):
    assert coded_symbol_count(37, scheme) == count
