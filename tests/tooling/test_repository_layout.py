from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote

import pytest
from examples.demo import SimConfig, load_config


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_NAMES = (
    'default', 'advertising', 'import_bwv', 'import_mat', 'channel_scan',
    'ideal', 'low_snr', 'rayleigh', 'rftest_1m_prbs9_96m',
    'rftest_2m_prbs15', 'rftest_df1', 'rftest_df2', 'rftest_pattern',
    'rftest_prbs9', 'rftest_s2_prbs9_96m', 'rftest_s8_prbs9_96m',
)


@pytest.mark.parametrize('name', CONFIG_NAMES)
def test_waveform_configs_have_one_location_and_artifact_outputs(name):
    path = PROJECT_ROOT / 'configs' / 'waveforms' / f'{name}.yaml'
    assert path.is_file()
    raw = load_config(str(path))
    config = SimConfig.from_dict(raw)
    assert Path(config.output_dir).parts[:2] == ('artifacts', 'waveforms')
    source = raw.get('io', {}).get('input', {})
    if source.get('enabled'):
        assert (PROJECT_ROOT / source['file']).is_file()


def test_examples_only_contain_python_entry_points():
    assert sorted(path.name for path in (PROJECT_ROOT / 'examples').glob('*.py')) == [
        'benchmark.py', 'demo.py',
    ]
    assert not list((PROJECT_ROOT / 'examples').glob('*.yaml'))


def test_package_and_default_tests_target_core():
    text = (PROJECT_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'include = ["ble_studio*"]' in text
    assert 'exclude = ["tests*", "examples*"]' in text
    assert 'namespaces = false' in text
    assert 'testpaths = ["tests"]' in text


def test_core_demo_and_checker_work_from_isolated_sources(tmp_path):
    # 只复制核心包和示例，确认运行不依赖工作区的其他目录。
    shutil.copytree(PROJECT_ROOT / 'ble_studio', tmp_path / 'ble_studio',
                    ignore=shutil.ignore_patterns('__pycache__'))
    (tmp_path / 'examples').mkdir()
    shutil.copyfile(PROJECT_ROOT / 'examples' / 'demo.py', tmp_path / 'examples' / 'demo.py')
    program = f'''
import sys
sys.path.insert(0, {str(tmp_path)!r})
import ble_studio
from pathlib import Path
from examples.demo import SimConfig
from ble_studio.tx_checker import check_tx_packet
assert Path(ble_studio.__file__).resolve().is_relative_to(Path({str(tmp_path)!r}))
packet = ble_studio.create_test_packet(payload_length=1)
iq = ble_studio.BLEModulator().modulate(packet.generate())
config = ble_studio.DemodulatorConfig(access_address=0x71764129, whitening=False)
assert check_tx_packet(iq.real, iq.imag, config=config, expected_pdu=packet.generate_pdu()).passed
assert SimConfig().output_dir.startswith('artifacts/')
'''
    result = subprocess.run([sys.executable, '-I', '-c', program], cwd=tmp_path,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_readme_starts_with_declared_environment_requirements():
    readme = (PROJECT_ROOT / 'README.md').read_text(encoding='utf-8')
    metadata = (PROJECT_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert readme.startswith('# BLE Studio\n\n## 运行环境\n')
    intro = readme.split('## 功能简介', 1)[0]
    requirement = re.search(r'^requires-python = "([^"]+)"$', metadata, re.MULTILINE)
    assert requirement is not None
    assert f'`Python {requirement.group(1)}`' in intro
    dependencies = re.search(r'^dependencies = \[(.*?)^\]', metadata,
                             re.MULTILINE | re.DOTALL)
    assert dependencies is not None
    for dependency in re.findall(r'"([^"]+)"', dependencies.group(1)):
        assert f'`{dependency}`' in intro
    assert '项目声明' in intro
    assert '3.13.7' in intro
    assert '可选开发依赖' in intro


def test_readme_relative_links_exist():
    readme = (PROJECT_ROOT / 'README.md').read_text(encoding='utf-8')
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', readme):
        target = target.strip('<>').split('#', 1)[0]
        if target and '://' not in target:
            assert (PROJECT_ROOT / unquote(target)).exists(), target
    assert 'configs/waveforms/' in readme
    assert 'docs/development/' in readme


def test_vcs_manifest_has_existing_unique_paths():
    path = PROJECT_ROOT / 'docs' / 'integration' / 'vcs' / 'ic_server_upload_files.txt'
    paths = path.read_text(encoding='utf-8').splitlines()
    assert len(paths) == len(set(paths))
    for relative in paths:
        assert relative and (PROJECT_ROOT / relative).is_file(), relative
        assert not relative.startswith(('doc/', 'examples/config'))
    assert 'configs/waveforms/default.yaml' in paths
    for scheme in (2, 8):
        assert f'configs/waveforms/rftest_s{scheme}_prbs9_96m.yaml' in paths


def test_reference_and_script_directories_replace_old_paths():
    for relative in ('docs/algorithms', 'docs/development', 'reference/matlab',
                     'reference/vectors', 'reference/specifications', 'scripts'):
        assert (PROJECT_ROOT / relative).is_dir()
    for relative in ('doc', 'utils', 'data', 'reference/BLE_PKT', 'plan.md', 'research.md',
                     'requirements.txt'):
        assert not (PROJECT_ROOT / relative).exists(), relative
    assert (PROJECT_ROOT / 'reference' / 'vectors' / 'BLE_1M.bwv').is_file()
    assert len(list((PROJECT_ROOT / 'reference' / 'vectors').glob('*'))) == 10
