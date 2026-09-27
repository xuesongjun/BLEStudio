"""兼容 RSSI 入口，现由通用 SDR profile 处理。"""

from __future__ import annotations

import argparse
from pathlib import Path

from ble_studio.logic_analyzer.cli import main as cli_main


def main() -> int:
    parser = argparse.ArgumentParser(description="Legacy RSSI parser wrapper")
    parser.add_argument("config", help="YAML 配置")
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument("--vcd", action="store_true")
    args = parser.parse_args()

    print("[DEPRECATED] 请使用 configs/logic_analyzer/rssi_raw_sdr.yaml")
    config_path = Path(args.config)
    if not config_path.exists() and config_path.name == "rssi_config.yaml":
        config_path = Path("configs/logic_analyzer/rssi_raw_sdr.yaml")

    cli_args = ["convert", str(config_path)]
    if args.no_plot:
        cli_args.append("--no-plot")
    if args.vcd:
        cli_args.extend(["--formats", "npz", "mat", "json", "vcd"])
    return cli_main(cli_args)


if __name__ == "__main__":
    raise SystemExit(main())
