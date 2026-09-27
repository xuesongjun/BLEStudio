from __future__ import annotations

from pathlib import Path

import pytest

from ble_studio.logic_analyzer.config import load_config


def _write_new_config(
    path: Path,
    *,
    input_file: str = "data/capture.bin",
    capture_overrides: str = "",
    output_overrides: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""input:
  file: "{input_file}"
capture:
  profile: iq_ddr
  sample_rate: 500e6
  data_rate: 32e6
  mode: ddr
  data_bits: [0, 1, 2, 3]
  clock_channel: 10
  bit_width: 4
  rising_edge_data: I
  falling_edge_data: Q
{capture_overrides}processing:
  eye_align: true
  search_range: 8
output:
  directory: ../artifacts
  stem: converted
  formats: [txt, npy]
  max_plot_samples: 1000
{output_overrides}ble_rx:
  enabled: true
  access_address: "0x71764129"
  target_samples_per_symbol: 8
""",
        encoding="utf-8",
    )
    return path


def test_load_new_yaml_resolves_paths_relative_to_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    input_file = config_dir / "data" / "capture.bin"
    input_file.parent.mkdir(parents=True)
    input_file.write_bytes(b"\x00\x00")
    config_file = _write_new_config(config_dir / "logic.yaml")

    config = load_config(config_file)

    assert config.input_file == input_file.resolve()
    assert config.output_dir == (tmp_path / "artifacts").resolve()
    assert config.output_base == (tmp_path / "artifacts" / "converted").resolve()
    assert config.data_bits == (0, 1, 2, 3)
    assert config.clk_channel == 10
    assert config.save_formats == ("txt", "npy")
    assert config.ble_rx.access_address == 0x71764129
    assert config.warnings == []


def test_load_legacy_yaml_supports_aliases_and_cwd_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "work"
    config_dir = tmp_path / "configs"
    cwd.mkdir()
    config_dir.mkdir()
    input_file = config_dir / "capture.bin"
    input_file.write_bytes(b"\x00\x00")
    config_file = config_dir / "legacy.yaml"
    config_file.write_text(
        """input_file: capture.bin
output_file: generated/legacy_iq
sample_rate: 400e6
data_rate: 20e6
mode: ddr
data_bits: [0, 1]
data_indicator: 9
bit_width: 2
rising_edge_data: q
falling_edge_data: i
save_formats: [MEM, HTML]
plot: true
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(cwd)

    config = load_config(config_file)

    assert config.input_file == input_file.resolve()
    assert config.output_dir == (cwd / "generated").resolve()
    assert config.output_stem == "legacy_iq"
    assert config.clk_channel == 9
    assert config.rising_edge_data == "Q"
    assert config.falling_edge_data == "I"
    assert config.save_formats == ("mem", "html")
    assert config.show_plot is True
    assert config.warnings == ["已加载 legacy flat YAML 配置"]


def test_load_legacy_yaml_falls_back_to_cwd_for_existing_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "work"
    config_dir = tmp_path / "configs"
    cwd.mkdir()
    config_dir.mkdir()
    input_file = cwd / "legacy.bin"
    input_file.write_bytes(b"\x00\x00")
    config_file = config_dir / "legacy.yaml"
    config_file.write_text(
        """input_file: legacy.bin
mode: sdr
data_bits: [0]
bit_width: 1
save_formats: [txt]
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(cwd)

    config = load_config(config_file)

    assert config.input_file == input_file.resolve()
    assert any("旧 CWD 规则" in warning for warning in config.warnings)
    assert "已加载 legacy flat YAML 配置" in config.warnings


@pytest.mark.parametrize(
    ("capture_overrides", "output_overrides", "expected_error"),
    [
        ("  mode: invalid\n", "", "mode 必须是"),
        ("  sample_rate: 0\n", "", "sample_rate 必须大于 0"),
        ("  bit_width: 3\n", "", "data_bits 数量必须与 bit_width 一致"),
        ("  data_bits: [0, 1, 2, 16]\n", "", "Kingst channel 必须在 0-15"),
        ("  clock_channel: null\n", "", "DDR 模式必须配置 clk_channel"),
        ("  falling_edge_data: I\n", "", "必须分别映射到 I/Q"),
        ("", "  formats: [txt, unsupported]\n", "不支持的输出格式"),
    ],
)
def test_load_new_yaml_rejects_invalid_configuration(
    tmp_path: Path,
    capture_overrides: str,
    output_overrides: str,
    expected_error: str,
) -> None:
    config_dir = tmp_path / "configs"
    input_file = config_dir / "data" / "capture.bin"
    input_file.parent.mkdir(parents=True)
    input_file.write_bytes(b"\x00\x00")
    config_file = _write_new_config(
        config_dir / "invalid.yaml",
        capture_overrides=capture_overrides,
        output_overrides=output_overrides,
    )

    with pytest.raises(ValueError, match=expected_error):
        load_config(config_file)


def test_load_new_yaml_rejects_missing_input_file(tmp_path: Path) -> None:
    config_file = _write_new_config(tmp_path / "configs" / "missing.yaml")

    with pytest.raises(ValueError, match="输入文件不存在"):
        load_config(config_file)
