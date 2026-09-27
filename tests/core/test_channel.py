from __future__ import annotations

import pytest

from ble_studio.channel import (
    AWGNChannel,
    BLEChannel,
    BLEIndoorChannel,
    ChannelConfig,
    ChannelType,
    FlatFadingChannel,
    FrequencyOffset,
    PhaseNoise,
    TimingOffset,
    create_ble_indoor_channel,
)


def _impairment_types(channel: BLEChannel) -> list[type]:
    return [type(impairment) for impairment in channel.impairments]


def test_default_awgn_channel_has_no_hidden_phase_noise() -> None:
    channel = BLEChannel(ChannelConfig(channel_type=ChannelType.AWGN))

    assert _impairment_types(channel) == [AWGNChannel]


def test_explicit_phase_noise_is_added() -> None:
    channel = BLEChannel(ChannelConfig(
        channel_type=ChannelType.AWGN,
        phase_noise_level=-100.0,
    ))

    assert _impairment_types(channel) == [PhaseNoise, AWGNChannel]


def test_flat_fading_channel_type_is_wired() -> None:
    channel = BLEChannel(ChannelConfig(channel_type=ChannelType.FLAT_FADING))

    assert _impairment_types(channel) == [FlatFadingChannel, AWGNChannel]


def test_frequency_and_timing_offsets_are_in_chain() -> None:
    channel = BLEChannel(ChannelConfig(
        frequency_offset=25e3,
        timing_offset=0.5,
    ))

    assert _impairment_types(channel) == [FrequencyOffset, TimingOffset, AWGNChannel]


def test_indoor_environment_parameter_is_used() -> None:
    channel = create_ble_indoor_channel(20, environment="industrial")

    indoor = channel.impairments[0]
    assert isinstance(indoor, BLEIndoorChannel)
    assert indoor.environment == "industrial"


def test_invalid_indoor_environment_is_rejected() -> None:
    with pytest.raises(ValueError, match="indoor_environment"):
        BLEChannel(ChannelConfig(
            channel_type=ChannelType.BLE_INDOOR,
            indoor_environment="invalid",
        ))


def test_multipath_path_lengths_must_match() -> None:
    with pytest.raises(ValueError, match="path_delays.*path_gains"):
        ChannelConfig(
            channel_type=ChannelType.MULTIPATH,
            path_delays=[0.0, 1e-6],
            path_gains=[0.0],
        )
