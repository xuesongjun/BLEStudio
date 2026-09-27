from __future__ import annotations

import numpy as np
import pytest

from examples.demo import SimConfig, run_simulation


def test_dtm_demo_passes_custom_access_address(tmp_path) -> None:
    config = SimConfig(
        mode="dtm",
        access_address=0x12345678,
        snr_db=np.inf,
        html_report=False,
        output_dir=str(tmp_path),
    )

    result = run_simulation(config, {})

    assert result.success is True
    assert result.access_address == 0x12345678


def test_demo_rejects_unknown_mode(tmp_path) -> None:
    config = SimConfig(
        mode="unknown",
        html_report=False,
        output_dir=str(tmp_path),
    )

    with pytest.raises(ValueError, match="Unsupported mode"):
        run_simulation(config, {})


def test_advertising_rejects_custom_access_address(tmp_path) -> None:
    config = SimConfig(
        mode="advertising",
        access_address=0x12345678,
        html_report=False,
        output_dir=str(tmp_path),
    )

    with pytest.raises(ValueError, match="fixed Access Address"):
        run_simulation(config, {})
