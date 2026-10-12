"""LE Coded PHY 的卷积编码、pattern mapping 与软判决解码。"""

from __future__ import annotations

import numpy as np


CODED_PREAMBLE = np.tile(np.array([0, 0, 1, 1, 1, 1, 0, 0], dtype=np.uint8), 10)
CODED_BLOCK_ONE_BITS = 37
CODED_BLOCK_ONE_SYMBOLS = 296
CODED_PREFIX_SYMBOLS = len(CODED_PREAMBLE) + CODED_BLOCK_ONE_SYMBOLS
TERM_BITS = 3
_S8_ZERO = np.array([0, 0, 1, 1], dtype=np.uint8)


def _bits(values: np.ndarray) -> np.ndarray:
    bits = np.asarray(values)
    if bits.ndim != 1:
        raise ValueError("bits must be one-dimensional")
    if not np.all((bits == 0) | (bits == 1)):
        raise ValueError("bits must contain only 0 and 1")
    return bits.astype(np.uint8)


def _soft(values: np.ndarray) -> np.ndarray:
    samples = np.asarray(values, dtype=float)
    if samples.ndim != 1 or not np.all(np.isfinite(samples)):
        raise ValueError("soft symbols must be finite and one-dimensional")
    return samples


def _validate_scheme(coding_scheme: int) -> None:
    if coding_scheme not in (2, 8):
        raise ValueError("coding_scheme must be 2 or 8")


def convolutional_encode(bits: np.ndarray) -> np.ndarray:
    """K=4、rate=1/2，G0=1+x+x²+x³，G1=1+x²+x³，初态为零。"""
    bits = _bits(bits)
    output = np.empty(2 * len(bits), dtype=np.uint8)
    state = 0
    for index, bit in enumerate(bits):
        bit = int(bit)
        d1, d2, d3 = state & 1, (state >> 1) & 1, (state >> 2) & 1
        output[2 * index] = bit ^ d1 ^ d2 ^ d3
        output[2 * index + 1] = bit ^ d2 ^ d3
        state = ((state << 1) | bit) & 7
    return output


def pattern_map(bits: np.ndarray, coding_scheme: int) -> np.ndarray:
    _validate_scheme(coding_scheme)
    bits = _bits(bits)
    if coding_scheme == 2:
        return bits.copy()
    return np.bitwise_xor(bits[:, None], _S8_ZERO).reshape(-1)


def pattern_demap(soft_symbols: np.ndarray, coding_scheme: int) -> np.ndarray:
    """正软值表示 air symbol 1；S8 利用四个符号的相关性合并可靠度。"""
    _validate_scheme(coding_scheme)
    soft = _soft(soft_symbols)
    if coding_scheme == 2:
        return soft.copy()
    if len(soft) % 4:
        raise ValueError("S8 symbol count must be a multiple of 4")
    return soft.reshape(-1, 4) @ np.array([1.0, 1.0, -1.0, -1.0])


def viterbi_decode(soft_bits: np.ndarray, *, terminated: bool = True) -> np.ndarray:
    """零初态的 8-state 软判决 Viterbi；header prefix 不强制零终态。"""
    soft = _soft(soft_bits)
    if not len(soft) or len(soft) % 2:
        raise ValueError("FEC soft bit count must be a nonzero multiple of 2")
    # 每个 next state 的两个 predecessor 仅在最旧的延迟位上不同。
    next_states = np.arange(8)
    inputs = next_states & 1
    previous = np.stack((next_states >> 1, (next_states >> 1) | 4))
    d1, d2, d3 = previous & 1, (previous >> 1) & 1, (previous >> 2) & 1
    outputs = np.stack((inputs ^ d1 ^ d2 ^ d3, inputs ^ d2 ^ d3), axis=-1)
    expected = 2.0 * outputs - 1.0
    scores = np.full(8, -np.inf)
    scores[0] = 0.0
    traceback = np.empty((len(soft) // 2, 8), dtype=np.uint8)
    for index, pair in enumerate(soft.reshape(-1, 2)):
        candidates = scores[previous] + np.sum(expected * pair, axis=-1)
        choice = np.argmax(candidates, axis=0)
        traceback[index] = previous[choice, next_states]
        scores = candidates[choice, next_states]
    state = 0 if terminated else int(np.argmax(scores))
    decoded = np.empty(len(traceback), dtype=np.uint8)
    for index in range(len(traceback) - 1, -1, -1):
        decoded[index] = state & 1
        state = int(traceback[index, state])
    return decoded


def coded_symbol_count(payload_length: int, coding_scheme: int) -> int:
    _validate_scheme(coding_scheme)
    if not isinstance(payload_length, (int, np.integer)) or not 0 <= payload_length <= 255:
        raise ValueError("payload_length must be an integer in [0, 255]")
    return CODED_PREFIX_SYMBOLS + coding_scheme * (16 + 8 * payload_length + 24 + TERM_BITS)


def encode_coded_packet(access_address_bits: np.ndarray, pdu_crc_bits: np.ndarray,
                        coding_scheme: int) -> np.ndarray:
    """输入 PDU+CRC 已完成可选 whitening，TERM 不参与 whitening。"""
    _validate_scheme(coding_scheme)
    aa = _bits(access_address_bits)
    data = _bits(pdu_crc_bits)
    if len(aa) != 32:
        raise ValueError("access_address_bits must contain 32 bits")
    if len(data) < 40 or len(data) % 8:
        raise ValueError("pdu_crc_bits must contain complete PDU and CRC octets")
    term = np.zeros(TERM_BITS, dtype=np.uint8)
    ci = np.array([int(coding_scheme == 2), 0], dtype=np.uint8)
    # 两个 block 各自从零初态开始，Block 1 始终使用 S8。
    block_one = pattern_map(convolutional_encode(np.concatenate((aa, ci, term))), 8)
    block_two = pattern_map(convolutional_encode(np.concatenate((data, term))), coding_scheme)
    return np.concatenate((CODED_PREAMBLE, block_one, block_two))
