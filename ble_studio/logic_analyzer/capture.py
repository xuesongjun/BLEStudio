"""Kingst 16-channel BIN 解码。"""

from __future__ import annotations

from typing import Iterable

import numpy as np

from .models import LogicAnalyzerConfig, RawCapture


def _extract_channel(words: np.ndarray, channel: int) -> np.ndarray:
    return ((words >> channel) & 1).astype(np.uint8)


def _required_channels(config: LogicAnalyzerConfig) -> Iterable[int]:
    channels = set(config.data_bits)
    channels.update(config.extra_signals.values())
    if config.clk_channel is not None:
        channels.add(config.clk_channel)
    return sorted(channels)


def load_capture(config: LogicAnalyzerConfig) -> RawCapture:
    """读取并校验 Kingst 16-channel 原始 BIN。"""
    raw = np.fromfile(config.input_file, dtype=np.uint8)
    if raw.size == 0:
        raise ValueError(f"逻辑分析仪 BIN 为空: {config.input_file}")
    if raw.size % 2 != 0:
        raise ValueError(
            f"逻辑分析仪 BIN 长度必须是 2 bytes 的整数倍，当前为 {raw.size} bytes"
        )

    byte_pairs = raw.reshape(-1, 2)
    words = (
        byte_pairs[:, 0].astype(np.uint16)
        | (byte_pairs[:, 1].astype(np.uint16) << 8)
    )

    decoded = {
        channel: _extract_channel(words, channel)
        for channel in _required_channels(config)
    }
    data_channels = {channel: decoded[channel] for channel in config.data_bits}
    clock = decoded.get(config.clk_channel) if config.clk_channel is not None else None
    extra_signals = {
        name: decoded[channel]
        for name, channel in config.extra_signals.items()
    }

    return RawCapture(
        channels=data_channels,
        clock=clock,
        extra_signals=extra_signals,
        sample_count=len(words),
        sample_rate=config.sample_rate,
    )
