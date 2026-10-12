# IC Server AI 交接文档

交接更新日期：2026-10-12（加入 Coded S2/S8）。目标：把 BLEStudio 整包 TX checker 接入现有 VCS 验证环境，
用真实 DUT 的 DAC I/Q 判断 BLE TX 数据是否正确。先读本文，再读
[集成与工作说明](ic_server_integration.md)和[完整接口说明](vcs_tx_checker.md)。

## 1. 已确认条件与本轮范围

| 项目 | 已确认信息 |
|---|---|
| 服务器 | CentOS 7 |
| 仿真器 | VCS 2025，具体安装路径/patch 待现场检查 |
| Python | 3.10，headers、libpython、依赖是否完整待检查 |
| DAC | 两路有符号 `real` I/Q，96 MHz |
| 有效指示 | `tx_dfe_en`，包边界语义待核实 |
| 第一阶段 | 收完一包再解调，不要求逐样点 streaming RX |
| 判定 | 同步成功、CRC 正确、完整 Header + Payload 与 case 期望一致 |

当前支持 LE1M/LE2M/S2/S8，96 MHz 对应 96/48/96/96 SPS。枚举与 SV 常量为
1/2/4/3（S2=4、S8=3），必须传 case 实际模式，CI 不符不会自动切换或 PASS。
当前没有经过校正的 ΔF1/ΔF2 自动判定；数据检查 PASS 不代表 RF 合规 PASS。
不要把当前 `RFMeasure` 或仪表盘的 PASS 直接并入本轮验收，也不要擅自扩大到 RF
算法重写。RF 合规检查是后续独立任务。

## 2. 这批文件是什么状态

上传包是按 [上传清单](ic_server_upload_files.txt) 打包的工作区快照，保留相对目录结构。
若从 GitHub checkout 部署，必须选择包含 `coded_phy.py`、`tx_checker.py` 和
`sim/vcs/` 的版本；旧版本不包含完整 Coded checker，不能代替本次交接。

本地已完成：

- Python codec/Core golden、Coded loopback、checker 与 smoke fixture 共 196 项针对性
  测试；全项目 300 项测试通过。
- 原生 C++ smoke 真正嵌入 CPython，正常包、CRC/PDU 错误、异常恢复和连续不同
  配置调用通过，包含 S2/S8/PHY-CI mismatch；GCC 15.2.0 的 C++11/Werror 编译通过。
- Bash syntax、Python compile、diff whitespace 检查通过。
- Verilator 5.040 静态展开及 DPI prototype 一致性检查通过；仍有 34 条 BLKSEQ、
  10 条 clocking input UNDRIVEN 警告，不是 clean lint 或 SV 功能仿真通过。

上述 Python/原生 smoke 在 Windows、本机 Python 3.13.7 完成。
**CentOS 7 + VCS 2025 + Python 3.10 尚未实际编译运行。** 这是你需要补齐的验收，
不得把本地结果写成服务器已通过。

原 20261009 快照不包含 Coded，不能用于此版本的部署。当前交接更新为 20261012，
独立解包验证与 hash 记录见 plan.md。此前离线 wheel 构建因本机缺少
`setuptools`/`wheel` 未完成，未安装额外工具；
服务器需同时核实项目声明的构建依赖与运行依赖。

## 3. 开始集成前必须调查

先读取 IC 项目的规则和现有脚本，检查工作区已有修改。不要覆盖用户代码或猜测层级。
把以下事实写入你的集成记录：

1. DAC sample clock、低有效 reset、I/Q、`tx_dfe_en` 的真实路径、类型与驱动边沿。
2. I/Q 是否确实每个 DAC 时钟提供一对新样点，幅值单位、符号和 I/Q 顺序是什么。
3. `tx_dfe_en` 的一个连续有效区间是否恰好是一整包，包含首尾全部有效样点。
4. 若该信号跨多包或包内间断，寻找真实 packet-valid；不要把多个包强行交给单包 RX。
5. testcase 的 PHY、AA、channel、whitening、CRCInit、完整 PDU 与预期包数来源。
6. testbench top、filelist、C++ 编译/链接选项、simv 启动脚本、scoreboard 和结束机制。
7. 同进程是否已有 CPython/DPI 组件，是否与本 checker 的 Python 路径和版本冲突。
8. 实际 Python 3.10、匹配的 `python3.10-config`、VCS headers、C++ 编译器及动态库路径。

若缺少真实信号或 case 期望值，先完成独立 smoke，再向用户列明缺项。
不要猜一个名字、配置或默认 PDU 来宣称完成 DUT 集成。

## 4. 实施顺序

### A. 隔离部署与基线验证

将包解压到单独目录，按 [集成说明](ic_server_integration.md)安装到 Python 3.10
venv。不要上传或复用 Windows venv、DLL、`.pyc`、simv。
先检查 `import ble_studio.tx_checker`，有 pytest 时运行：

```bash
"$PYTHON" -m pytest -q -p no:cacheprovider tests/core
```

随后运行 `bash sim/vcs/run_smoke.sh`。目标是所有 19 个场景按预期通过验证，保存
compile.log、各场景 simulation.log 和 JSON。负例本身出现 FAIL/fatal 是预期行为，
必须由 runner 同时核对退出状态和标记，不能只搜索 PASS 或把所有非零退出当作失败。

服务器缺少 Python 开发文件、依赖、可用编译器或 license 时，记录原始错误并说明
需要补齐什么。不要擅自升级系统 Python、安装新依赖、修改全局环境或更换仿真器。
可先执行文档中的原生 bridge smoke 定位 embedding 问题；它不能替代 VCS smoke。

### B. 接入真实平台

1. filelist 加入 `ble_python_dpi_pkg.sv`、`ble_tx_monitor.sv`，package 在前。
2. C++ 输入加入 `ble_python_dpi.cpp`，保留相邻 header；复用 smoke 的 Python
   headers/libpython、C++11、pthread 和 runtime library 配置。
3. 仅实例化通用 monitor 并绑定真实 DAC 信号；不要把 smoke TB 加入正式 top。
4. testcase 在包开始前准备完整 expected PDU 和协议配置；monitor 在首个有效样点
   锁存，不能等包开始后再更新。期望值来自 test stimulus/参考模型，不来自 DUT 接收结果。
5. 设置独立且可写的报告目录，传入 3 个绝对路径 plusargs。多个 monitor 使用同一
   Python 环境；不要让初始化路径互相冲突。
6. 核实采样时序和首尾样点。默认 `SAMPLE_SKEW=0ps` 采样 NBA 后的输出；非零
   clocking input skew 是边沿前采样，不是边沿后延时。
7. 选择 `FAIL_FATAL=1` 立即失败，或设为 0 并让 scoreboard 消费全部结果。
8. testcase 结束前，在最后的 idle 采样完成后调用 monitor 的
   `check_complete(expected_packet_count)`，并保留全局 timeout。

完整端口绑定模板、编译选项与调用示例见 [接口说明](vcs_tx_checker.md)。
示例中的 AA/channel/CRCInit 只用于示例，不是所有 testcase 的固定值。

### C. DUT 集成验收

- 至少一个真实 DUT 的 96 MHz LE1M/PRBS9/37-byte TX case：收到一包、样点数和
  边界合理、sync/CRC/PDU 全通过，JSON 与 testcase 逐字节一致。
- 若平台有 LE2M，再验证 LE2M；至少连续两包验证配置锁存、计数与结果不串包。
- 若 DUT 支持 Coded，分别验证 96 MHz S2/S8 PRBS9/37-byte case，样点数分别为
  101184/296448；增加 PHY/CI 不符和连续切换模式的负例/回归。
- 只修改 expected PDU 的一个 payload bit：正确 DUT 波形也必须报 `PDU_MISMATCH`。
- 刻意漏掉一包或在包未结束时调用完成检查：testcase 必须失败，不能零包 PASS。
- reset 中断、enable X、CRC 错误等边界至少保留独立 smoke 的验证记录。
- 确认 checker 的失败进入平台最终 case verdict，不能只是打印错误后回归仍报 PASS。

没有可运行的 DUT testcase 时，只能交付“独立 smoke 通过、DUT 验收待执行”。

## 5. 不允许为了通过测试而做的修改

- 不修改 RX/CRC/PRBS 算法掩盖配置、采样或 DUT 错误。
- 不自动交换 I/Q、取反、独立归一化、补造首尾样点或修改 expected PDU。
- 不用 BLEStudio 理想 TX fixture 代替真实 DAC 数据，宣称 DUT 已通过。
- 不把 CRC 通过、同步通过或成功调用 Python 单独作为整包 PASS。
- 不吞没 Python traceback、关闭失败计数或省略 `check_complete()`。
- 不擅自提交/push、删除现有文件、重构验证平台或改变公共接口。

若 VCS 的实际 ABI/clocking 支持要求修改 checker，先说明具体日志、最小修正方案
和影响范围；不得在无证据的情况下大改实现。

## 6. 最终向用户交付

1. 修改文件列表及 diff，真实层级绑定表、采样边沿和包边界结论。
2. 使用的 VCS patch、Python/编译器版本、headers/libpython 路径、依赖版本记录。
3. 独立 smoke 与 DUT case 的可重复编译/运行命令。
4. 19 个 smoke 场景结果、真实 DUT 正负例结果、日志和每包 JSON 路径。
5. scoreboard gate 与 testcase 完成检查的实际接入位置。
6. 仍未验证的事项和阻塞项；明确“TX 数据检查”与“RF 合规检查”的区别。

如获得提交授权，按 IC 项目规则提交并记录变更；否则保留工作区改动供用户 review。
