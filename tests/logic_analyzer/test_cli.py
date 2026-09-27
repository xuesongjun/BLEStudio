from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _run_cli(*arguments: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(PROJECT_ROOT), current_pythonpath) if value
    )
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "ble_studio.logic_analyzer", *arguments],
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def test_cli_help_returns_zero() -> None:
    completed = _run_cli("--help")

    assert completed.returncode == 0
    assert "convert" in completed.stdout
    assert "diagnose" in completed.stdout
    assert "config" in completed.stdout


def test_cli_config_generates_profile_yaml(tmp_path: Path) -> None:
    output = tmp_path / "rssi.yaml"

    completed = _run_cli(
        "config", "--profile", "rssi-raw-sdr", str(output)
    )

    assert completed.returncode == 0, completed.stderr
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "profile: rssi_raw_sdr" in content
    assert "mode: sdr" in content


def test_cli_convert_returns_zero_and_writes_requested_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "artifacts"
    fixture = (FIXTURE_DIR / "rssi_raw_slice.bin").resolve().as_posix()
    config = tmp_path / "convert.yaml"
    config.write_text(
        f"""input:
  file: "{fixture}"
capture:
  profile: rssi_raw_sdr
  sample_rate: 100e6
  data_rate: 100e6
  mode: sdr
  data_bits: [0, 1, 2, 3, 4, 5, 6, 7]
  bit_width: 8
  extra_signals:
    agc_init: 8
    rampup: 9
    fire_timer: 10
processing:
  eye_align: false
  search_range: 2
  glitch_filter: false
  adaptive_filter: false
  output_spike_filter: false
output:
  directory: "{output_dir.as_posix()}"
  stem: cli_result
  formats: [json, npy]
  max_plot_samples: 100
ble_rx:
  enabled: false
""",
        encoding="utf-8",
    )

    completed = _run_cli("convert", str(config), "--no-plot")

    assert completed.returncode == 0, completed.stderr
    assert "[SUMMARY]" in completed.stdout
    assert (output_dir / "cli_result.summary.json").exists()
    assert (output_dir / "cli_result.npy").exists()


def test_cli_convert_returns_two_for_invalid_input(tmp_path: Path) -> None:
    invalid = tmp_path / "capture.txt"

    completed = _run_cli("convert", str(invalid))

    assert completed.returncode == 2
    assert "[ERROR]" in completed.stderr
    assert "输入必须是" in completed.stderr
