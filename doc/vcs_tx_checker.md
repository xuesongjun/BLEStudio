# VCS DAC TX 整包检查

适用环境：CentOS 7、VCS 2025、Python 3.10。两路 DAC 输出为 `real`，采样率
96 MHz，`tx_dfe_en` 指示有效样点。模块在 enable 的一个连续有效区间结束后解调整包。

```text
DAC I/Q -> ble_tx_monitor -> DPI-C -> CPython -> BLE Studio RX
                                                  |
scoreboard <- sync / CRC / 完整 PDU match <----------+
```

通过条件是 `sync_found && crc_valid && pdu_match`。`pdu_match` 比较 Header +
Payload 的完整字节，预期数据由 testcase 提供，不从接收到的数据推导。
当前不包含 ΔF1/ΔF2 的自动合规判定。

更新：2026-10-12，支持 LE1M/LE2M/LE Coded S2/S8。DPI 参数和结果 JSON 不变，
Coded 经两段 pattern demapping/软判决 Viterbi 后再去白化、校验 CRC 和完整 PDU。

## 1. 安装和服务器 smoke

先在服务器 checkout 根目录，使用已有 Python 3.10 创建环境并安装本项目：

```bash
python3.10 -m venv .venv
./.venv/bin/python -m pip install -e .
```

指定解释器及其对应的开发配置工具，执行 smoke：

```bash
export PYTHON="$PWD/.venv/bin/python"
export PYTHON_CONFIG="$(command -v python3.10-config)"
bash sim/vcs/run_smoke.sh
```

脚本要求 PATH 中能找到 `vcs`。也可以通过 `VCS=/实际路径/bin/vcs` 指定。
`VCS_INCLUDE` 可指定含 VCS `svdpi.h` 的目录；默认检查 `VCS_HOME/include`，
没有 `VCS_HOME` 时检查实际 `vcs` 安装路径下的 include，并验证文件存在。

`PYTHON_CONFIG` 必须来自 venv 对应的 base Python 3.10，而不是系统 Python 2.7
或另一个 Python 安装。服务器需具备该 Python 的 headers 和可用于 embedding 的
libpython；脚本检查版本与安装 prefix，使用 `--cflags`、`--ldflags --embed`。
如果缺少这些开发文件，需要由服务器管理员补齐，脚本不会修改系统安装。

所有可再生产物写入：

```text
artifacts/vcs_tx_checker/<时间戳_PID>/
    compile.log
    build/                  # simv / csrc
    fixtures/               # real IQ、预期 PDU、CRC 错误波形
    good/simulation.log
    good/reports/           # 每包 pretty JSON
    two_packets/...
```

smoke 共 19 个场景，保留原 11 项：正确包、连续不同 PHY 的两包、PDU 不符、错误 CRC、复位中断、enable X、
Python 配置错误、缺包、包未结束、enable 卡高、bridge 初始化错误。正常负例需要确认
对应错误确实被检测；要求拒绝结束的负例还必须非零退出。日志不是只有 PASS 字样就通过。
新增 S2/S8 正常包、各自 PDU/CRC 负例、PHY/CI 不符、S2→S8→1M→2M 连续调用。
Coded CRC 负例先破坏信息 CRC 再做 FEC，不能用可纠正的 air symbol 作为必败负例。

## 2. 接入现有 testbench

将以下文件加入现有 VCS filelist，保持 package 在 module 前：

```text
sim/vcs/ble_python_dpi_pkg.sv
sim/vcs/ble_tx_monitor.sv
```

同时把 `sim/vcs/ble_python_dpi.cpp` 加入 VCS 的 C++ 编译输入，保留相邻的
`ble_python_dpi.h`。沿用 smoke 的 `-CFLAGS` / `-LDFLAGS` 设置，连接对应 Python
开发库，运行时能找到 libpython。编译器需要支持 C++11。

下面是端口绑定示意，信号名应替换为你的平台信号；不存在预设的 DUT 层级：

```systemverilog
ble_tx_monitor #(
    .SAMPLE_RATE_HZ(96.0e6),
    .FAIL_FATAL(1'b1),
    .REPORT_DIR("ble_tx_reports")
) tx_checker (
    .dac_clk(dac_sample_clk),
    .dac_rstn(dac_rstn),
    .tx_dfe_en(tx_dfe_en),
    .dac_i(dac_i_real),
    .dac_q(dac_q_real),
    .phy_mode(ble_python_dpi_pkg::BLE_LE_1M),
    .access_address(32'h71764129),
    .channel(32),
    .whitening(1'b0),
    .crc_init(32'h00555555),
    .expected_pdu_hex(case_expected_pdu_hex),
    .packet_checked(tx_checked),
    .packet_passed(tx_passed),
    .sync_found(tx_sync),
    .crc_valid(tx_crc),
    .pdu_match(tx_pdu_match),
    .bridge_error(tx_bridge_error),
    .packet_count(tx_packet_count),
    .failure_count(tx_failure_count),
    .sample_count(tx_sample_count),
    .check_message(tx_check_message)
);
```

`case_expected_pdu_hex` 是完整 PDU 的 hex 字符串，不包含 preamble、AA 或 CRC；
例如 PRBS9/37-byte DTM 包先是 `0025`，后接全部 37 bytes payload，共 39 bytes。
Python 字节序以逐字节 hex 表达，按接收后 LSB-first 组回的字节比较。
每包开始锁存配置和 expected PDU，之后修改只影响下一包。

PHY 常量：`BLE_LE_1M=1`、`BLE_LE_2M=2`、`BLE_LE_CODED_S8=3`、
`BLE_LE_CODED_S2=4`。S2/S8 均为 1 Msym/s，96 MHz 均为 96 SPS。
CI 必须与 case 配置一致，不自动切换 PHY；不符返回 `PHY_CI_MISMATCH`。

运行 simv 时传入绝对路径：

```bash
./simv \
  +BLE_PYTHON="$PWD/.venv/bin/python" \
  +BLE_MODULE_ROOT="$PWD" \
  +BLE_SITE_PACKAGES="$(./.venv/bin/python -c 'import sysconfig; print(sysconfig.get_path("platlib"))')"
```

上述 `$PWD` 必须是 BLEStudio checkout 根目录；若 simv 从其它目录启动，请事先保存
checkout 和 venv 的绝对路径。`BLE_MODULE_ROOT` 必须包含 `ble_studio/tx_checker.py`。
实际解释器嵌入在 simv 进程内，不是每包启动一次命令行 Python。

checker 初始化一次。不同 monitor 可复用同一 bridge，但不能使用互相冲突的 Python
路径。bridge 使用 GIL 并串行处理调用；它不会关闭其它验证组件使用的解释器。
同步检查期间消耗实际运行时间，DPI function 不执行仿真延时。

## 3. 有效边界和 testcase 结束

必须确认 `tx_dfe_en` 的一个高电平区间恰好包含一包全部 DAC 有效样点。如果它仅是
DFE 总开关、跨越多包，或包内会拉低，需要改接真正的 packet-valid 信号。
当前接口也要求 I/Q 是与 DAC 时钟同步的离散样点，而不是无采样时钟的连续模拟节点。

默认 `SAMPLE_SKEW=0ps`，clocking input `#0` 在 Observed region 采样 NBA 后
更新的信号。非零 skew 表示边沿前采样，不能理解成边沿后 delay。若 DAC 的更新边沿
不同，需按平台时序调整采样时钟/skew，并检查首尾样点；smoke 使用 posedge NBA
驱动数据来验证默认配置。

`packet_checked` 在检查结束后保持到下一次采样；其它结果保持最后一次值。scoreboard
可在相应 negedge 读取，避免与 monitor 的采样 region 竞争。默认 `FAIL_FATAL=1`
时，数据错误立即 `$fatal`；设为 0 可由 scoreboard 统一处理失败。

testcase 必须等待最后一个 idle 采样完成后调用：

```systemverilog
@(negedge dac_sample_clk);
tx_checker.check_complete(expected_packet_count);
```

该 task 拒绝零期望包数、缺包、包数不符、未结束的包和之前的任何失败。
验证平台还应保留自己的全局 timeout。`MAX_SAMPLES` 默认 2097152，单包超限时立即
失败；这是防止 enable 卡高无限占用 buffer，不代表包的协议长度。
复位打断的包会记录失败，后续复位不会清空失败历史。
37-byte S2/S8 分别需要 101184/296448 samples；255-byte S8 需要 1635840 samples。
正常长包需足够的 case timeout（255-byte S8 时长 17.04 ms）；用户覆盖较小 buffer
上限会如实报错。smoke 只用 37-byte Coded，TB buffer=327680、watchdog=10ms。

real I/Q 不做补码转换、量化、独立幅度归一化、I/Q 交换或极性修正；NaN/Infinity
被拒绝。全零、过短、同步失败、CRC 错误和 PDU 不符都有具体 failure reason。
Python 运行异常返回 bridge error 并保留 traceback，不能转成 PASS。

## 4. 单独调用 Python

无需 VCS 也可使用相同 checker：

```python
from ble_studio.demodulator import DemodulatorConfig
from ble_studio.tx_checker import check_tx_packet

result = check_tx_packet(
    i_samples, q_samples,
    config=DemodulatorConfig(
        sample_rate=96e6, access_address=0x71764129,
        channel=32, whitening=False,
    ),
    expected_pdu=case_expected_pdu,
    report_path="packet_0001.json",
)
assert result.passed, result.failure_reason
```

这里的 `i_samples`、`q_samples` 和 `case_expected_pdu` 由调用方提供。
结果 JSON 包含实际采样数、PHY、采样率、AA、channel、CRCInit、whitening、完整
expected/received PDU 和各项判定。

## 5. 验证边界

- 支持 LE1M/LE2M/S2/S8 和 integer SPS；96 MHz 分别为 96/48/96/96 SPS。
- uncoded AA 为容错相关、结果 AA 来自配置；Coded 核对 FEC 后 AA，但都不是
  原始 AA air symbols 的逐位无误 signoff。
- Coded 非法 CI、PHY/CI 不符、截断和 header 复核失败均有诊断；CRC/PDU gate 不放宽。
- 不支持 CTE/连接状态机；Coded 性能曲线、RF ΔF1/ΔF2/频谱合规仍未实现。
- 当前是整包数据检查，不是 streaming RX，不是完整 RF signoff。
- RFMeasure 的 payload 边界、PHY 门限、ΔF2 统计和双 pattern 配对尚需校正，
  本模块不会把现有 RF 仪表盘 PASS 作为 TX 数据 PASS 条件。
- 本机 Python/原生 bridge smoke 和 SV 静态展开不等于 VCS 集成通过。
  发布验收仍需在实际 CentOS 7/VCS 2025/Python 3.10 上执行上述 smoke。

`tests/native/tx_checker_bridge_smoke.cpp` 使用测试专用的 DPI open-array adapter，
可验证真实 CPython 初始化、数组传递、异常和重复调用；不验证 VCS ABI、四态信号
或 SV sampling region。它不加入正式 VCS 编译。

已有匹配的 Python 开发环境及 VCS headers 时，可单独执行该原生检查：

```bash
native_dir="$PWD/artifacts/vcs_tx_checker/native"
mkdir -p "$native_dir"
"$PYTHON" sim/vcs/generate_fixture.py "$native_dir/fixtures"
g++ -std=c++11 -Wall -Wextra -Werror \
  -I"$VCS_INCLUDE" $("$PYTHON_CONFIG" --cflags) \
  sim/vcs/ble_python_dpi.cpp tests/native/tx_checker_bridge_smoke.cpp \
  $("$PYTHON_CONFIG" --ldflags --embed) \
  -Wl,-rpath,"$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')" \
  -o "$native_dir/bridge_smoke"
"$native_dir/bridge_smoke" "$PYTHON" "$PWD" \
  "$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("platlib"))')" \
  "$native_dir/fixtures"
```

这里需显式设置 `VCS_INCLUDE`，不能依赖 smoke 脚本进程内的局部变量。故意传入
非法 hex 的负例会打印 Python traceback；最终应看到 `NATIVE_BRIDGE_SMOKE_PASS`。
