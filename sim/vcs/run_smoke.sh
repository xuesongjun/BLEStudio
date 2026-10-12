#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${PYTHON:-python3.10}
python_config=${PYTHON_CONFIG:-python3.10-config}
vcs_bin=${VCS:-vcs}
for tool in "$python_bin" "$python_config" "$vcs_bin"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Required tool not found: %s\n' "$tool" >&2
        exit 2
    fi
done
vcs_include=${VCS_INCLUDE:-${VCS_HOME:+$VCS_HOME/include}}
if [[ -z $vcs_include ]]; then
    vcs_path=$(readlink -f "$(command -v "$vcs_bin")")
    vcs_include="$(dirname -- "$(dirname -- "$vcs_path")")/include"
fi
if [[ ! -f $vcs_include/svdpi.h ]]; then
    printf 'Set VCS_INCLUDE to the directory containing the VCS svdpi.h\n' >&2
    exit 2
fi
python_bin=$("$python_bin" -c 'import sys; print(sys.executable)')
"$python_bin" -c 'import sys; assert sys.version_info[:2] == (3, 10), "Python 3.10 is required for the VCS target"; import ble_studio.tx_checker'
site_packages=$("$python_bin" -c 'import sysconfig; print(sysconfig.get_path("platlib"))')
python_libdir=$("$python_bin" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
python_cflags=$("$python_config" --cflags)
python_ldflags=$("$python_config" --ldflags --embed)
if [[ $python_cflags != *python3.10* || $python_ldflags != *python3.10* ]]; then
    printf 'PYTHON_CONFIG must belong to the Python 3.10 installation used by PYTHON\n' >&2
    exit 2
fi
python_base=$("$python_bin" -c 'import sys; print(sys.base_prefix)')
config_base=$("$python_config" --prefix)
if [[ $(cd "$python_base" && pwd -P) != $(cd "$config_base" && pwd -P) ]]; then
    printf 'PYTHON and PYTHON_CONFIG belong to different Python installations\n' >&2
    exit 2
fi
out_dir="$repo_root/artifacts/vcs_tx_checker/$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$out_dir/build" "$out_dir/fixtures"
"$python_bin" "$repo_root/sim/vcs/generate_fixture.py" "$out_dir/fixtures"
export LD_LIBRARY_PATH="$python_libdir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONNOUSERSITE=1
cd "$out_dir/build"

# VCS 自带 svdpi.h；真实 simulator ABI 由 VCS 编译与 smoke 联调核对。
"$vcs_bin" -full64 -sverilog -top tb_ble_tx_monitor \
    "$repo_root/sim/vcs/ble_python_dpi_pkg.sv" \
    "$repo_root/sim/vcs/ble_tx_monitor.sv" \
    "$repo_root/sim/vcs/tb_ble_tx_monitor.sv" \
    "$repo_root/sim/vcs/ble_python_dpi.cpp" \
    -CFLAGS "-std=c++11 -pthread -I$vcs_include $python_cflags" \
    -LDFLAGS "-pthread $python_ldflags -Wl,-rpath,$python_libdir" \
    -o "$out_dir/build/simv" -l "$out_dir/compile.log"

log_has() {
    local needle=$1 log_file=$2 line
    while IFS= read -r line || [[ -n $line ]]; do
        if [[ $line == *"$needle"* ]]; then
            return 0
        fi
    done < "$log_file"
    return 1
}

run_case() {
    local scenario=$1 expected_failure=$2
    local case_dir="$out_dir/$scenario"
    local status=0
    local module_root="$repo_root"
    local failure_marker="[SMOKE] NEGATIVE_CASE_CONFIRMED $scenario"
    if [[ $scenario == init_error ]]; then
        module_root="$out_dir/nonexistent_module_root"
        failure_marker='BRIDGE_INIT_ERROR'
    fi
    mkdir -p "$case_dir"
    (
        cd "$case_dir"
        "$out_dir/build/simv" \
            "+BLE_PYTHON=$python_bin" \
            "+BLE_MODULE_ROOT=$module_root" \
            "+BLE_SITE_PACKAGES=$site_packages" \
            "+FIXTURE_DIR=$out_dir/fixtures" "+SCENARIO=$scenario"
    ) >"$case_dir/simulation.log" 2>&1 || status=$?
    if [[ $expected_failure == yes ]]; then
        if [[ $status -eq 0 ]] || ! log_has "$failure_marker" "$case_dir/simulation.log"; then
            printf 'Negative smoke case did not fail as expected: %s\n' "$scenario" >&2
            return 1
        fi
    elif [[ $status -ne 0 ]] || ! log_has "[SMOKE] PASS $scenario" "$case_dir/simulation.log"; then
        printf 'Smoke case failed: %s; see %s\n' "$scenario" "$case_dir/simulation.log" >&2
        return 1
    fi
    printf '[SMOKE] verified %s\n' "$scenario"
}

for scenario in good two_packets mismatch crc reset unknown \
    coded_s2 coded_s8 coded_s2_mismatch coded_s8_mismatch \
    coded_s2_crc coded_s8_crc coded_ci_mismatch coded_modes; do
    run_case "$scenario" no
done
for scenario in bridge_error missing unfinished stuck init_error; do
    run_case "$scenario" yes
done

printf 'VCS TX checker smoke passed. Artifacts: %s\n' "$out_dir"
