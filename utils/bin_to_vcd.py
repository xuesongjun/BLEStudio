"""兼容 VCD 入口，处理逻辑已合并到统一 exporter。"""

from __future__ import annotations

import argparse
from pathlib import Path

from ble_studio.logic_analyzer.config import create_default_config, load_config
from ble_studio.logic_analyzer.exporters import export_summary_json
from ble_studio.logic_analyzer.pipeline import process_capture
from ble_studio.logic_analyzer.vcd import export_vcd


_MOVED_CONFIGS = {
    "logic_analyzer_config.yaml": "configs/logic_analyzer/adc_ddr.yaml",
    "logic_analyzer_config_rssi.yaml": "configs/logic_analyzer/rssi_resampled_sdr.yaml",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Legacy BIN to VCD wrapper")
    parser.add_argument("input", help="YAML 配置或 Kingst BIN")
    parser.add_argument("-o", "--output", help="输出 VCD 文件")
    args = parser.parse_args()

    print("[DEPRECATED] 请使用 ble-la convert <config> --formats vcd")
    input_path = Path(args.input)
    if not input_path.exists() and input_path.name in _MOVED_CONFIGS:
        input_path = Path(_MOVED_CONFIGS[input_path.name])

    config = (
        load_config(input_path)
        if input_path.suffix.lower() in {".yaml", ".yml"}
        else create_default_config(input_path)
    )
    result = process_capture(config)
    output = export_vcd(result, args.output)
    export_summary_json(result, output.with_suffix(".summary.json"))
    print(f"[OUTPUT] vcd: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
