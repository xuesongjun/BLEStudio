from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from scipy.io import savemat


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPARE_SCRIPT = PROJECT_ROOT / 'scripts' / 'compare_iq.py'


def _run_compare(*arguments):
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    return subprocess.run([sys.executable, str(COMPARE_SCRIPT), *map(str, arguments)],
                          capture_output=True, text=True, encoding='utf-8',
                          env=env, check=False)


def test_compare_cli_help():
    result = _run_compare('--help')
    assert result.returncode == 0, result.stderr
    assert 'tx_file' in result.stdout and 'rx_file' in result.stdout


@pytest.mark.parametrize('extension', ['txt', 'mat'])
def test_compare_cli_accepts_descriptive_file_names(tmp_path, extension):
    tx = tmp_path / f'LE1M_96Msps_PRBS9_37B_TX.{extension}'
    rx = tmp_path / f'LE1M_96Msps_PRBS9_37B_RX.{extension}'
    if extension == 'txt':
        tx.write_text('// IQ samples\n1 -2\n3 4\n', encoding='ascii')
        rx.write_text('1 -2\n3 4\n', encoding='ascii')
    else:
        iq = np.array([0.75 - 0.5j, -0.25 + 0.125j])
        savemat(tx, {'iq': iq})
        savemat(rx, {'iq': iq})
    result = _run_compare(tx, rx)
    assert result.returncode == 0, result.stderr
    assert 'samples=2' in result.stdout
    assert 'identical=True' in result.stdout


def test_compare_cli_reports_missing_input(tmp_path):
    result = _run_compare(tmp_path / 'missing_tx.txt', tmp_path / 'missing_rx.txt')
    assert result.returncode != 0
    assert '[ERROR]' in result.stderr


@pytest.mark.parametrize('extension', ['txt', 'mat'])
def test_compare_cli_rejects_empty_data(tmp_path, extension):
    tx, rx = (tmp_path / f'{name}.{extension}' for name in ('tx', 'rx'))
    if extension == 'txt':
        tx.write_text('// empty\n', encoding='ascii')
        rx.write_text('1 2\n', encoding='ascii')
    else:
        savemat(tx, {'iq': np.array([], dtype=complex)})
        savemat(rx, {'iq': np.array([1 + 0j])})
    result = _run_compare(tx, rx)
    assert result.returncode != 0
    assert '[ERROR]' in result.stderr and 'non-empty' in result.stderr


@pytest.mark.parametrize('extension', ['txt', 'mat'])
def test_compare_cli_rejects_different_sample_counts(tmp_path, extension):
    tx, rx = (tmp_path / f'{name}.{extension}' for name in ('tx', 'rx'))
    if extension == 'txt':
        tx.write_text('1 2\n3 4\n', encoding='ascii')
        rx.write_text('1 2\n', encoding='ascii')
    else:
        savemat(tx, {'iq': np.array([1 + 0j, 0 + 1j])})
        savemat(rx, {'iq': np.array([1 + 0j])})
    result = _run_compare(tx, rx)
    assert result.returncode != 0
    assert '[ERROR]' in result.stderr and 'same number of samples' in result.stderr


def test_compare_cli_rejects_mixed_formats(tmp_path):
    tx, rx = tmp_path / 'tx.txt', tmp_path / 'rx.mat'
    tx.write_text('1 2\n', encoding='ascii')
    savemat(rx, {'iq': np.array([1 + 0j])})
    result = _run_compare(tx, rx)
    assert result.returncode != 0
    assert '[ERROR]' in result.stderr and 'same format' in result.stderr


def test_compare_cli_rejects_nonfinite_mat(tmp_path):
    tx, rx = tmp_path / 'tx.mat', tmp_path / 'rx.mat'
    savemat(tx, {'iq': np.array([complex(np.nan, 0)])})
    savemat(rx, {'iq': np.array([1 + 0j])})
    result = _run_compare(tx, rx)
    assert result.returncode != 0
    assert '[ERROR]' in result.stderr and 'finite' in result.stderr
