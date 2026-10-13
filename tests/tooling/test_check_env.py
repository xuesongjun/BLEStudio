from __future__ import annotations

import ast
from importlib import metadata, util
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = PROJECT_ROOT / 'scripts' / 'check_env.py'


@pytest.fixture
def checker():
    spec = util.spec_from_file_location('ble_studio_check_env_test', CHECK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_python(arguments, cwd):
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return subprocess.run([sys.executable, '-B', '-I', *arguments], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8',
                          env=env, check=False, timeout=30)


def test_check_env_cli_passes_without_pytest(tmp_path):
    # 隔离子进程中阻断 pytest，避免用测试进程已加载的包掩盖运行依赖。
    program = f'''
import runpy
import sys
sys.modules['pytest'] = None
sys.argv = [{str(CHECK_SCRIPT)!r}]
runpy.run_path({str(CHECK_SCRIPT)!r}, run_name='__main__')
'''
    result = _run_python(['-c', program], tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    for label in ('Python', 'numpy', 'scipy', 'plotly', 'PyYAML',
                  'BLEStudio', 'TX/RX loopback', 'Overall'):
        assert f'[PASS] {label}' in result.stdout
    assert str(Path(sys.executable)) in result.stdout
    assert str(PROJECT_ROOT / 'ble_studio' / '__init__.py') in result.stdout
    for detail in ('96 MHz', 'PRBS9', '37 bytes', 'samples=36096',
                   'sync=PASS', 'CRC=PASS', 'PDU=PASS', 'bits=PASS'):
        assert detail in result.stdout
    assert '[FAIL]' not in result.stdout and '[SKIP]' not in result.stdout
    assert not list(tmp_path.iterdir())


def test_check_env_cli_without_site_packages_reports_fail(tmp_path):
    result = _run_python(['-S', str(CHECK_SCRIPT)], tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    for name in ('numpy', 'scipy', 'plotly', 'PyYAML'):
        assert f'[FAIL] {name}' in result.stdout
    assert '[SKIP] BLEStudio' in result.stdout
    assert '[SKIP] TX/RX loopback' in result.stdout
    assert '[FAIL] Overall' in result.stdout
    assert '-m pip install -e .' in result.stdout
    assert 'Traceback' not in result.stdout + result.stderr
    assert not list(tmp_path.iterdir())


def test_check_env_constants_match_project_metadata(checker):
    text = (PROJECT_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    python_requirement = re.search(r'^requires-python = "([^"]+)"$', text, re.MULTILINE)
    assert python_requirement is not None
    assert python_requirement.group(1) == '>=' + '.'.join(map(str, checker.MIN_PYTHON))
    dependencies = re.search(r'^dependencies = \[(.*?)^\]', text,
                             re.MULTILINE | re.DOTALL)
    assert dependencies is not None
    names = [re.split(r'[<>=!~]', requirement, maxsplit=1)[0]
             for requirement in re.findall(r'"([^"]+)"', dependencies.group(1))]
    assert dict(checker.CORE_DEPENDENCIES) == {
        name: 'yaml' if name == 'PyYAML' else name for name in names
    }


def test_check_env_script_keeps_python_38_grammar():
    ast.parse(CHECK_SCRIPT.read_text(encoding='utf-8'), feature_version=(3, 8))


def test_readme_places_quick_check_under_environment():
    text = (PROJECT_ROOT / 'README.md').read_text(encoding='utf-8')
    environment = text.split('## 运行环境', 1)[1].split('## 功能简介', 1)[0]
    assert '### 快速自检' in environment
    assert r'.\venv\Scripts\python.exe scripts\check_env.py' in environment
    assert './venv/bin/python scripts/check_env.py' in environment
    assert '[PASS] Overall' in environment
    assert '[FAIL] Overall' in environment
    assert '退出码' in environment and '不依赖 pytest' in environment
    assert 'pip check' in environment


def test_check_env_rejects_unsupported_python(checker, monkeypatch, capsys):
    with monkeypatch.context() as patch:
        patch.setattr(checker.sys, 'version_info', (3, 7, 0))
        status = checker.main()
    output = capsys.readouterr().out
    assert status == 1
    assert '[FAIL] Python' in output and '>=3.8' in output
    assert '[FAIL] Overall' in output
    assert '[PASS] numpy' not in output


@pytest.mark.parametrize('name,module_name', [
    ('numpy', 'numpy'), ('scipy', 'scipy'), ('plotly', 'plotly'), ('PyYAML', 'yaml'),
])
def test_check_env_reports_missing_dependency_and_continues(
        checker, monkeypatch, capsys, name, module_name):
    original_import = checker.importlib.import_module

    def import_with_missing_module(module, *args, **kwargs):
        if module == module_name:
            raise ModuleNotFoundError(f"No module named '{module}'")
        return original_import(module, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(checker.importlib, 'import_module', import_with_missing_module)
        status = checker.main()
    output = capsys.readouterr().out
    assert status == 1
    assert f'[FAIL] {name}: ModuleNotFoundError' in output
    for other, _ in checker.CORE_DEPENDENCIES:
        if other != name:
            assert f'[PASS] {other}' in output
    assert '[SKIP] BLEStudio' in output and '[SKIP] TX/RX loopback' in output
    assert '[FAIL] Overall' in output and '-m pip install -e .' in output


@pytest.mark.parametrize('error_type', [ImportError, OSError, RuntimeError])
def test_check_env_reports_broken_dependency(checker, monkeypatch, capsys, error_type):
    original_import = checker.importlib.import_module

    def import_broken_scipy(module, *args, **kwargs):
        if module == 'scipy':
            raise error_type('Native library initialization failed')
        return original_import(module, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(checker.importlib, 'import_module', import_broken_scipy)
        status = checker.main()
    output = capsys.readouterr().out
    assert status == 1
    assert f'[FAIL] scipy: {error_type.__name__}: Native library initialization failed' in output
    assert '[PASS] PyYAML' in output and '[FAIL] Overall' in output


def test_check_env_reports_missing_distribution_metadata(checker, monkeypatch, capsys):
    original_version = metadata.version

    def version_without_yaml(name):
        if name == 'PyYAML':
            raise metadata.PackageNotFoundError(name)
        return original_version(name)

    with monkeypatch.context() as patch:
        patch.setattr(metadata, 'version', version_without_yaml)
        status = checker.main()
    output = capsys.readouterr().out
    assert status == 1
    assert '[FAIL] PyYAML: PackageNotFoundError' in output
    assert '[FAIL] Overall' in output


def test_check_env_reports_missing_ble_studio(checker, monkeypatch, capsys):
    original_import = checker.importlib.import_module

    def import_without_studio(module, *args, **kwargs):
        if module == 'ble_studio':
            raise ModuleNotFoundError("No module named 'ble_studio'")
        return original_import(module, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(checker.importlib, 'import_module', import_without_studio)
        status = checker.main()
    output = capsys.readouterr().out
    assert status == 1
    assert '[FAIL] BLEStudio: ModuleNotFoundError' in output
    assert '[SKIP] TX/RX loopback' in output and '[FAIL] Overall' in output
    assert '-m pip install -e .' in output


def test_check_env_rejects_different_checkout(checker, monkeypatch, capsys, tmp_path):
    original_import = checker.importlib.import_module
    other_studio = SimpleNamespace(__version__='0.1.0',
                                  __file__=str(tmp_path / 'ble_studio' / '__init__.py'))

    def import_other_studio(module, *args, **kwargs):
        if module == 'ble_studio':
            return other_studio
        return original_import(module, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(checker.importlib, 'import_module', import_other_studio)
        status = checker.main()
    output = capsys.readouterr().out
    assert status == 1
    assert '[FAIL] BLEStudio' in output and 'different checkout' in output
    assert str(tmp_path) in output
    assert '[SKIP] TX/RX loopback' in output and '[FAIL] Overall' in output


@pytest.mark.parametrize('field,label', [
    ('success', 'demodulation'), ('sync_found', 'sync'), ('crc_valid', 'CRC'),
    ('pdu', 'PDU'), ('bits', 'bits'),
])
def test_check_env_rejects_bad_loopback(checker, monkeypatch, capsys, field, label):
    import ble_studio
    receiver_type = ble_studio.BLEDemodulator

    def damaged_receiver(config):
        receiver = receiver_type(config)

        def receive(signal):
            result = receiver.demodulate(signal)
            if field == 'pdu':
                result.pdu = bytes([result.pdu[0] ^ 1]) + result.pdu[1:]
            elif field == 'bits':
                result.bits = result.bits.copy()
                result.bits[-1] ^= 1
            else:
                setattr(result, field, False)
            return result

        return SimpleNamespace(demodulate=receive)

    with monkeypatch.context() as patch:
        patch.setattr(ble_studio, 'BLEDemodulator', damaged_receiver)
        status = checker.main()
    output = capsys.readouterr().out
    assert status == 1
    failure = next(line for line in output.splitlines()
                   if line.startswith('[FAIL] TX/RX loopback'))
    assert label in failure
    assert '[PASS] TX/RX loopback' not in output and '[FAIL] Overall' in output


def test_check_env_reports_loopback_exception(checker, monkeypatch, capsys):
    import ble_studio

    def rejected_packet(**kwargs):
        raise ValueError('Loopback setup rejected')

    with monkeypatch.context() as patch:
        patch.setattr(ble_studio, 'create_test_packet', rejected_packet)
        status = checker.main()
    output = capsys.readouterr().out
    assert status == 1
    assert '[FAIL] TX/RX loopback: ValueError: Loopback setup rejected' in output
    assert '[FAIL] Overall' in output
