"""检查当前 Python 环境及 BLEStudio 基础 TX/RX，不依赖 pytest。"""

import importlib
from pathlib import Path
import sys
from types import ModuleType
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 8)
CORE_DEPENDENCIES = (
    ('numpy', 'numpy'),
    ('scipy', 'scipy'),
    ('plotly', 'plotly'),
    ('PyYAML', 'yaml'),
)
LOOPBACK_SAMPLE_RATE = 96e6
LOOPBACK_PAYLOAD_LENGTH = 37
LOOPBACK_CHANNEL = 0
LOOPBACK_ACCESS_ADDRESS = 0x71764129
LOOPBACK_CRC_INIT = 0x555555


def check_dependency(name: str, module_name: str) -> bool:
    """逐项检查导入与安装元数据，避免一个缺包掩盖其他诊断。"""
    try:
        # 先检查 Python 版本再使用 3.8 标准库，低版本仍能得到明确 FAIL。
        from importlib import metadata
        module = importlib.import_module(module_name)
        version = metadata.version(name)
        print(f"[PASS] {name}: version={version}, source={module.__file__}")
        return True
    except Exception as exc:
        # DLL/ABI 故障不一定是 ImportError；诊断边界统一记录原因并返回失败。
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        return False


def check_ble_studio() -> Optional[ModuleType]:
    """验证实际导入来源，防止另一份安装让当前工作区产生假 PASS。"""
    try:
        studio = importlib.import_module('ble_studio')
        source = Path(studio.__file__).resolve()
        expected = (PROJECT_ROOT / 'ble_studio' / '__init__.py').resolve()
        if source != expected:
            raise RuntimeError(f"Imported a different checkout: {source}; expected {expected}")
        print(f"[PASS] BLEStudio: version={studio.__version__}, source={source}")
        return studio
    except Exception as exc:
        print(f"[FAIL] BLEStudio: {type(exc).__name__}: {exc}")
        return None


def check_loopback(studio: ModuleType) -> None:
    """复用公开接口做理想单包检查，不生成波形文件或报告。"""
    import numpy as np

    phy_mode = studio.BLEPhyMode.LE_1M
    packet = studio.create_test_packet(
        payload_type=studio.RFTestPayloadType.PRBS9,
        payload_length=LOOPBACK_PAYLOAD_LENGTH,
        channel=LOOPBACK_CHANNEL,
        phy_mode=phy_mode,
        access_address=LOOPBACK_ACCESS_ADDRESS,
        whitening=False,
        crc_init=LOOPBACK_CRC_INIT,
    )
    bits = packet.generate()
    iq = studio.BLEModulator(studio.ModulatorConfig(
        phy_mode=phy_mode, sample_rate=LOOPBACK_SAMPLE_RATE,
    )).modulate(bits)
    result = studio.BLEDemodulator(studio.DemodulatorConfig(
        phy_mode=phy_mode,
        sample_rate=LOOPBACK_SAMPLE_RATE,
        access_address=LOOPBACK_ACCESS_ADDRESS,
        channel=LOOPBACK_CHANNEL,
        whitening=False,
        crc_init=LOOPBACK_CRC_INIT,
    )).demodulate(iq)
    checks = {
        'demodulation': result.success,
        'sync': result.sync_found,
        'CRC': result.crc_valid,
        'PDU': result.pdu == packet.generate_pdu(),
        'bits': np.array_equal(result.bits[:len(bits)], bits),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError('Failed checks: ' + ', '.join(failed))
    print(f"[PASS] TX/RX loopback: LE_1M, {LOOPBACK_SAMPLE_RATE / 1e6:g} MHz, "
          f"PRBS9, {LOOPBACK_PAYLOAD_LENGTH} bytes, channel={LOOPBACK_CHANNEL}, "
          f"samples={len(iq)}, sync=PASS, CRC=PASS, PDU=PASS, bits=PASS")


def main() -> int:
    print(f"[INFO] Python executable: {sys.executable}")
    print(f"[INFO] Project root: {PROJECT_ROOT}")
    version = '.'.join(map(str, sys.version_info[:3]))
    required = '>=' + '.'.join(map(str, MIN_PYTHON))
    if sys.version_info[:2] < MIN_PYTHON:
        print(f"[FAIL] Python: {version}; required {required}")
        print(f"[HINT] Use Python {required}, then create or select its virtual environment.")
        for label in ('Core dependencies', 'BLEStudio', 'TX/RX loopback'):
            print(f"[SKIP] {label}: unsupported Python")
        print('[FAIL] Overall')
        return 1
    print(f"[PASS] Python: {version}; required {required}")

    dependencies_ok = True
    for name, module_name in CORE_DEPENDENCIES:
        if not check_dependency(name, module_name):
            dependencies_ok = False

    studio = check_ble_studio() if dependencies_ok else None
    if not dependencies_ok:
        print('[SKIP] BLEStudio: core dependencies failed')

    passed = False
    if studio is None:
        print('[SKIP] TX/RX loopback: BLEStudio or core dependencies unavailable')
        prefix = '& ' if sys.platform == 'win32' else ''
        print(f'[HINT] From "{PROJECT_ROOT}", run: '
              f'{prefix}"{sys.executable}" -m pip install -e .')
    else:
        try:
            check_loopback(studio)
            passed = True
        except Exception as exc:
            print(f"[FAIL] TX/RX loopback: {type(exc).__name__}: {exc}")
            print('[HINT] Install development tools if needed and run the full pytest regression '
                  'with the same Python; this script itself does not require pytest.')

    print('[PASS] Overall' if passed else '[FAIL] Overall')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
