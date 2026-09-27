"""兼容入口，请迁移到 ``python -m ble_studio.logic_analyzer``。"""

from __future__ import annotations

import argparse
from pathlib import Path

from ble_studio.logic_analyzer.cli import generate_profile_config, main as cli_main


_MOVED_CONFIGS = {
    "logic_analyzer_config.yaml": "configs/logic_analyzer/adc_ddr.yaml",
    "logic_analyzer_config_rssi.yaml": "configs/logic_analyzer/rssi_resampled_sdr.yaml",
    "rssi_config.yaml": "configs/logic_analyzer/rssi_raw_sdr.yaml",
}


def _resolve_legacy_input(value: str) -> str:
    path = Path(value)
    if path.exists():
        return str(path)
    replacement = _MOVED_CONFIGS.get(path.name)
    return replacement or value


def main() -> int:
    parser = argparse.ArgumentParser(description="Legacy BIN to wave wrapper")
    parser.add_argument("input", nargs="?", help="YAML 配置或 Kingst BIN")
    parser.add_argument("--generate-config", "-g", metavar="PATH")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    print("[DEPRECATED] 请使用: python -m ble_studio.logic_analyzer")
    if args.generate_config:
        generate_profile_config("adc-ddr", args.generate_config)
        return 0
    if not args.input:
        parser.print_help()
        return 2

    cli_args = ["convert", _resolve_legacy_input(args.input)]
    if args.no_plot:
        cli_args.append("--no-plot")
    return cli_main(cli_args)


if __name__ == "__main__":
    raise SystemExit(main())
