"""兼容诊断入口，请使用 ``ble-la diagnose``。"""

from __future__ import annotations

import sys
from pathlib import Path

from ble_studio.logic_analyzer.cli import main as cli_main


def main() -> int:
    value = sys.argv[1] if len(sys.argv) > 1 else "configs/logic_analyzer/adc_ddr.yaml"
    path = Path(value)
    if not path.exists() and path.name == "logic_analyzer_config.yaml":
        path = Path("configs/logic_analyzer/adc_ddr.yaml")
    print("[DEPRECATED] 请使用: ble-la diagnose <config>")
    return cli_main(["diagnose", str(path)])


if __name__ == "__main__":
    raise SystemExit(main())
