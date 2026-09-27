"""统一的逻辑分析仪命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .config import create_default_config, load_config
from .exporters import build_summary, export_outputs
from .pipeline import process_capture
from .validation import validate_ble_rx


PROFILE_CHOICES = ("adc-ddr", "rssi-raw-sdr", "rssi-resampled-sdr")


def _profile_data(profile: str) -> Dict[str, Any]:
    profiles: Dict[str, Dict[str, Any]] = {
        "adc-ddr": {
            "input": {"file": "capture.bin"},
            "capture": {
                "profile": "iq_ddr",
                "mode": "ddr",
                "sample_rate": 500e6,
                "data_rate": 32e6,
                "data_bits": list(range(10)),
                "bit_width": 10,
                "clock_channel": 10,
                "rising_edge_data": "Q",
                "falling_edge_data": "I",
            },
            "processing": {
                "eye_align": True,
                "search_range": 15,
                "glitch_filter": True,
                "glitch_threshold": 0.2,
                "adaptive_filter": False,
                "output_spike_filter": True,
            },
            "output": {
                "directory": "artifacts/logic_analyzer/adc_ddr",
                "stem": "waveform",
                "formats": ["mat", "txt", "mem", "html", "json"],
                "max_plot_samples": 50_000,
                "show_plot": False,
            },
            "ble_rx": {
                "enabled": True,
                "phy_mode": "LE_1M",
                "access_address": "0x71764129",
                "channel": 0,
                "whitening": False,
                "target_samples_per_symbol": 16,
            },
        },
        "rssi-raw-sdr": {
            "input": {"file": "rssi.bin"},
            "capture": {
                "profile": "rssi_raw_sdr",
                "mode": "sdr",
                "sample_rate": 100e6,
                "data_rate": 100e6,
                "data_bits": list(range(8)),
                "bit_width": 8,
                "extra_signals": {
                    "agc_init": 8,
                    "rampup": 9,
                    "fire_timer": 10,
                },
            },
            "processing": {
                "eye_align": False,
                "search_range": 2,
                "glitch_filter": False,
                "adaptive_filter": False,
                "output_spike_filter": False,
            },
            "output": {
                "directory": "artifacts/logic_analyzer/rssi_raw",
                "stem": "signals",
                "formats": ["npz", "mat", "html", "json"],
                "max_plot_samples": 50_000,
                "show_plot": False,
            },
            "ble_rx": {"enabled": False},
        },
        "rssi-resampled-sdr": {
            "input": {"file": "rssi.bin"},
            "capture": {
                "profile": "rssi_resampled_sdr",
                "mode": "sdr",
                "sample_rate": 100e6,
                "data_rate": 16e6,
                "data_bits": list(range(9)),
                "bit_width": 9,
            },
            "processing": {
                "eye_align": True,
                "search_range": 15,
                "glitch_filter": True,
                "glitch_threshold": 0.3,
                "adaptive_filter": True,
                "output_spike_filter": True,
            },
            "output": {
                "directory": "artifacts/logic_analyzer/rssi_resampled",
                "stem": "signals",
                "formats": ["npz", "mat", "html", "json"],
                "max_plot_samples": 50_000,
                "show_plot": False,
            },
            "ble_rx": {"enabled": False},
        },
    }
    return profiles[profile]


def generate_profile_config(profile: str, output: str | Path) -> Path:
    """生成一个可编辑的 YAML profile。"""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("生成 YAML 配置需要安装 PyYAML") from exc

    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = _profile_data(profile)

    capture_name = "capture.bin" if profile == "adc-ddr" else "rssi.bin"
    capture_path = Path.cwd() / "data" / "logic_analyzer" / "captures" / capture_name
    artifact_name = {
        "adc-ddr": "adc_ddr",
        "rssi-raw-sdr": "rssi_raw",
        "rssi-resampled-sdr": "rssi_resampled",
    }[profile]
    artifact_path = Path.cwd() / "artifacts" / "logic_analyzer" / artifact_name
    data["input"]["file"] = os.path.relpath(
        capture_path.resolve(), output_path.parent
    ).replace("\\", "/")
    data["output"]["directory"] = os.path.relpath(
        artifact_path.resolve(), output_path.parent
    ).replace("\\", "/")

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(
            data,
            handle,
            sort_keys=False,
            allow_unicode=True,
        )
    return output_path


def _load_input(value: str):
    path = Path(value).expanduser()
    if path.suffix.lower() in {".yaml", ".yml"}:
        return load_config(path)
    if path.suffix.lower() == ".bin":
        return create_default_config(path)
    raise ValueError("输入必须是 .yaml/.yml 配置或 Kingst .bin 文件")


def _apply_overrides(config, args: argparse.Namespace) -> None:
    if getattr(args, "formats", None):
        config.save_formats = tuple(value.lower() for value in args.formats)
    if getattr(args, "output_dir", None):
        config.output_dir = Path(args.output_dir).expanduser().resolve()
    if getattr(args, "stem", None):
        config.output_stem = args.stem
    if getattr(args, "no_plot", False):
        config.show_plot = False


def _print_summary(summary: Dict[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _run_convert(args: argparse.Namespace) -> int:
    config = _load_input(args.input)
    _apply_overrides(config, args)
    result = process_capture(config)
    if config.ble_rx.enabled:
        validate_ble_rx(result)
    outputs = export_outputs(result)

    print("\n[SUMMARY]")
    print(
        f"mode={config.mode}, samples={result.sample_count}, "
        f"Fs={result.sample_rate / 1e6:.6f} MHz"
    )
    if result.rx_result:
        print(
            "RX: "
            f"sync={result.rx_result.get('sync_found', False)}, "
            f"crc={result.rx_result.get('crc_valid', False)}, "
            f"success={result.rx_result.get('success', False)}"
        )
    for warning in result.warnings:
        print(f"[WARN] {warning}")
    for name, path in outputs.items():
        print(f"[OUTPUT] {name}: {path}")
    return 0


def _run_diagnose(args: argparse.Namespace) -> int:
    config = _load_input(args.input)
    _apply_overrides(config, args)
    result = process_capture(config)
    if config.ble_rx.enabled and not args.skip_rx:
        validate_ble_rx(result)
    _print_summary(build_summary(result))
    return 0


def _run_config(args: argparse.Namespace) -> int:
    output = args.output_option or args.output
    if not output:
        raise ValueError("config 子命令必须指定输出 YAML 路径")
    path = generate_profile_config(args.profile, output)
    print(f"[OUTPUT] config: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ble-la",
        description="BLE Studio 逻辑分析仪数据恢复工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert = subparsers.add_parser("convert", help="处理 capture 并导出结果")
    convert.add_argument("input", help="YAML 配置或 Kingst BIN")
    convert.add_argument("--formats", nargs="+", help="覆盖输出格式")
    convert.add_argument("--output-dir", help="覆盖输出目录")
    convert.add_argument("--stem", help="覆盖输出文件名前缀")
    convert.add_argument("--no-plot", action="store_true", help="不打开交互图")
    convert.set_defaults(handler=_run_convert)

    diagnose = subparsers.add_parser("diagnose", help="输出处理和 RX 诊断")
    diagnose.add_argument("input", help="YAML 配置或 Kingst BIN")
    diagnose.add_argument("--skip-rx", action="store_true", help="跳过 BLE RX 验证")
    diagnose.add_argument("--no-plot", action="store_true", help="不打开交互图")
    diagnose.set_defaults(handler=_run_diagnose)

    config = subparsers.add_parser("config", help="生成 profile 配置")
    config.add_argument("--profile", required=True, choices=PROFILE_CHOICES)
    config.add_argument("output", nargs="?", help="输出 YAML 路径")
    config.add_argument("-o", "--output", dest="output_option", help="输出 YAML 路径")
    config.set_defaults(handler=_run_config)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ImportError, OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
