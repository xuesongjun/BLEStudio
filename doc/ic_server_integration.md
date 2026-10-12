# IC Server 集成与工作说明

这批交付用于在 VCS 中检查真实 DAC 的 BLE TX 数据，不依赖 MATLAB。
上传包包含 Python 源码、SV monitor、DPI-C/C++ bridge、独立 smoke 和交接文档；
不包含服务器 Python 解释器、第三方依赖、VCS 软件或编译产物。

## 1. 上传哪些文件

完整清单见 [ic_server_upload_files.txt](ic_server_upload_files.txt)，每行一个相对路径，
无通配符、无注释，可直接供 `tar -T` 使用。必须保持目录结构，不要把文件平铺。

| 文件组 | 用途 |
|---|---|
| `ble_studio/` 下清单列出的全部 `.py` | 完整 Python package，包含 RX 及其导入依赖 |
| `pyproject.toml`、`README.md` | 项目安装配置及其引用的 readme |
| `sim/vcs/ble_python_dpi_pkg.sv`、`ble_tx_monitor.sv` | 正式平台的 SV 编译输入 |
| `sim/vcs/ble_python_dpi.cpp`、`.h` | 正式平台的 CPython embedding bridge |
| `sim/vcs/tb_ble_tx_monitor.sv`、`generate_fixture.py`、`run_smoke.sh` | 独立验证，不把 smoke TB 接入正式 top |
| 清单中的 `tests/core/`（含 Core JSON fixture） | Coded codec/loopback/checker/smoke fixture 的 196 项针对性测试 |
| `examples/demo.py`、两份 Coded YAML | 可选 96 MHz IQ/MEM/JSON 生成示例，不加入正式 VCS top |
| `tests/native/tx_checker_bridge_smoke.cpp` | 可选的原生 bridge 诊断，不加入 VCS top |
| 清单列出的 `doc/` 文档、`plan.md`、`research.md` | 交接、接口、实施记录与已知限制 |

即使只 import `ble_studio.tx_checker`，Python 也会先执行 package 的 `__init__.py`，
它会导入可视化等模块。因此不要仅复制 `tx_checker.py` 和 `demodulator.py`。
同时保留 `logic_analyzer/`，避免破坏现有安装入口；本轮 TX 检查不调用该功能。

不需要上传：`venv/`、`.venv/`、`__pycache__/`、`.git/`、`.egg-info/`、Windows
编译产物、旧 `artifacts/`、MATLAB/reference 数据、逻辑分析仪捕获和 `xclip.rpm`。
smoke 波形由脚本在服务器重新生成。此包不包含全仓库测试及 MATLAB/capture 数据，仅运行清单中的
针对性测试；若要全量回归，需要另行同步完整测试及其数据。

本地打包命令，在 `C:\workspace\BLEStudio` 的 PowerShell 中执行：

```powershell
New-Item -ItemType Directory -Force artifacts/ic_server_handoff | Out-Null
tar -czf artifacts/ic_server_handoff/BLEStudio_IC_Server_20261012.tar.gz -T doc/ic_server_upload_files.txt
Get-FileHash artifacts/ic_server_handoff/BLEStudio_IC_Server_20261012.tar.gz -Algorithm SHA256
```

上传这个 `.tar.gz` 即包含清单中的全部文件；若改用 GitHub checkout，必须选择包含
Coded codec、checker 和 VCS 接入文件的版本，不能使用旧版本代替本交接包。
第三方依赖需使用服务器自己的 Linux/Python
3.10 环境，离线服务器应由既有制品源/管理员提供，不能拷贝 Windows site-packages。
清单现为 50 个文件。20261009 是仅含 uncoded checker 的历史快照，保留但不要
用它部署 Coded 功能，也不要用新内容覆盖旧日期压缩包。

## 2. 在服务器先跑独立验证

解压到一个新的空目录，避免覆盖现有 IC 项目。以下约定压缩包已上传到当前目录：

```bash
sha256sum BLEStudio_IC_Server_20261012.tar.gz
mkdir BLEStudio_tx_checker_20261012
tar -xzf BLEStudio_IC_Server_20261012.tar.gz -C BLEStudio_tx_checker_20261012
cd BLEStudio_tx_checker_20261012
python3.10 -m venv .venv
./.venv/bin/python -m pip install -e .
export BLE_STUDIO_ROOT="$PWD"
export PYTHON="$BLE_STUDIO_ROOT/.venv/bin/python"
export PYTHON_CONFIG="$(command -v python3.10-config)"
"$PYTHON" -c 'import sys; import ble_studio.tx_checker; print(sys.version); print(sys.executable)'
bash sim/vcs/run_smoke.sh
```

安装命令使用项目已有依赖：NumPy、SciPy、Plotly、PyYAML，版本约束以
`pyproject.toml` 为准，未新增第三方依赖。安装构建还需要配置中声明的
`setuptools>=61.0` 和 `wheel`；离线环境需同时提供这些构建工具，不能只准备运行库。
不要为本任务安装整个 `.[dev]` 工具集合。
已有 pytest 时另跑 `"$PYTHON" -m pytest -q -p no:cacheprovider tests/core`；
上述目录在本交接包中只有 4 个针对性 test 文件（196 项），完整仓库中则是全套 core 测试。
若缺 pytest，记录该项未运行，依照服务器既有依赖管理流程处理。

执行前加载平台原有 VCS/license 环境。脚本默认从 PATH 查找 `vcs`，可通过环境变量
`VCS` 指定可执行文件；`VCS_INCLUDE` 指向含 VCS `svdpi.h` 的目录。不要拿其它
simulator 的 header 替代真实 VCS header。

`PYTHON_CONFIG` 必须对应 venv 的 base Python 3.10，需提供 Python headers 和
embedding 用的 libpython。若配置工具不存在或 `--ldflags --embed` 不可用，先补齐
开发环境，不能用系统 Python 2.7 的工具或其它版本链接。脚本会检查版本/prefix。

成功标志是脚本退出码 0，并输出 `VCS TX checker smoke passed. Artifacts: ...`。
输出位于 `artifacts/vcs_tx_checker/<时间戳_PID>/`，有 compile.log、独立场景日志和
每包 JSON。`bridge_error/missing/unfinished/stuck/init_error` 的 simv 非零退出是
故意设计的负例，由 runner 验证；不要跳过它们。

独立解包测试、smoke fixture 重新生成、manifest/hash 核对的当前结果见 plan.md。
此前额外的离线 wheel 构建未完成：本机
venv 缺少 `setuptools`/`wheel`，报 `Cannot import 'setuptools.build_meta'`。
未为此安装依赖或修改系统；服务器仍需验证实际安装和 VCS 编译运行。

## 3. 接入现有 IC testbench

保持 BLEStudio 源码目录与 IC 工程分离，使用它的绝对路径引用文件即可。
具体 module 实例模板、端口与 C++ 选项见 [vcs_tx_checker.md](vcs_tx_checker.md)。

最少需要做四处接入：

1. **编译**：package、monitor 加入 SV filelist；bridge `.cpp` 加入 C++ 输入，使用
   匹配的 Python headers/libpython 和 C++11 编译选项。
2. **采样**：monitor 接真实 DAC clock/reset/I/Q/packet-valid；确认有效边界与采样 region。
3. **case 数据**：传每包实际配置、完整 expected PDU；在包开始前稳定。
4. **最终判定**：scoreboard 接失败状态，testcase 结束前调用 `check_complete()`，保留 timeout。

保存 `BLE_STUDIO_ROOT` 和 `PYTHON` 绝对路径后，即使 simv 在回归结果目录执行也使用：

```bash
./simv \
  "+BLE_PYTHON=$PYTHON" \
  "+BLE_MODULE_ROOT=$BLE_STUDIO_ROOT" \
  "+BLE_SITE_PACKAGES=$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("platlib"))')"
```

不能将回归目录的 `$PWD` 当成源码根目录。现有启动脚本还应保留 Python libdir 的
runtime library 搜索配置；编译和运行环境复用 `run_smoke.sh` 的设置。

协议配置包括 PHY、Access Address、channel、whitening、CRCInit。
`expected_pdu_hex` 是完整 Header + Payload 的逐字节 hex，不包括 preamble/AA/CRC。
当前 checker 采用两字节 header，第二字节表示 payload 长度。DTM PRBS9/37 bytes
的 PDU 是 `0025` 加 37 bytes payload，共 39 bytes；不能只传 payload 或字符串 `PRBS9`。

上述数据必须来自 testcase 激励/独立参考，不能从解调结果生成期望再自我比较。
smoke 的理想 TX fixture 仅用于验证接入链路，不代替真实 DUT case 的验收。

## 4. 模块如何工作

```text
DAC 每个有效时钟的一对 real I/Q
    -> SV queue 收集整包、锁存本包配置
    -> enable 结束，转 dynamic real array
    -> 同步 DPI-C/C++ 调用已初始化的 CPython
    -> check_tx_packet_dpi -> check_tx_packet -> BLEDemodulator
    -> 返回同步/CRC/完整 PDU 比对结果，保存 pretty JSON
    -> monitor / scoreboard 判定，case 结束核对包数与失败历史
```

Python 解释器每进程初始化一次，每包调用一次。它嵌入 simv，不是每包启动 Python
子进程。DPI 调用会消耗实际执行时间，但不推进仿真时间；当前不是异步或 streaming RX。

Python 先检查输入维度、长度、finite 和配置，将两路组合为 `I + jQ`。RX 进行频偏
估计/补偿、FM 解调、匹配滤波、符号定时与 bit 判决，相关检测同步、按配置去白化，
读取 PDU 并校验 CRC。checker 再与 case 的完整 expected PDU 逐字节比较。
Coded 先同步专用前导/编码 AA，从本包前导估计 CFO，解码固定 S8 的 Block 1
并核对 AA/CI，再按 S2/S8 解码 Block 2。header prefix 不强制 TERM 终态；按长度
严格提取 PDU+CRC+TERM 后去白化和 CRC 检查。原始 RX `bits` 是 air decisions。
不自动交换 I/Q、不改变极性、不独立归一化、不对 real 做补码转换或量化。

每包通过条件：`sync_found && crc_valid && pdu_match`，且没有 capture/bridge 错误。
整条 case 还要求收到准确的预期包数、所有包通过、最后没有未闭合包或中断状态。
`packet_count` 也计入 capture 失败事件，不是“成功包数”；最后一包通过不能覆盖之前失败。

## 5. 结果、异常与限制

| 结果/原因 | 含义与处理 |
|---|---|
| `packet_passed` | 最近一包的数据检查通过；在 `packet_checked` 有效时消费 |
| `CRC_FAILED` | 同步后 CRC 错误，即使 PDU match 也必须失败 |
| `PDU_MISMATCH` | CRC 正确但内容与 testcase 不符 |
| `NO_SIGNAL` / `INSUFFICIENT_SAMPLES` / `SYNC_NOT_FOUND` | 全零、样点不足或未同步 |
| `INVALID_CI` / `PHY_CI_MISMATCH` | 保留 CI 或配置与实际 Coded 模式不符 |
| `TRUNCATED_PACKET` / `FEC_BLOCK_ONE_INVALID` / `HEADER_DECODE_MISMATCH` | Coded 分段/边界/字段校验失败 |
| `RESET_DURING_PACKET` / `UNKNOWN_TX_DFE_EN` / `UNKNOWN_PACKET_CONFIG` | 采样/控制失败 |
| `MAX_SAMPLES_EXCEEDED` | 超出 monitor buffer 上限，检查 enable 和边界 |
| `bridge_error` | Python 导入/参数/执行等错误，查看 C++ 日志中的 traceback |

DPI 的 return 0 只表示跨语言调用成功，不代表数据 PASS，必须读取独立结果。
`FAIL_FATAL=1` 默认立即终止错误 case；为 0 时由 scoreboard 统一管理，仍要调用完成检查。
`packet_checked` 保持到下一次采样，建议在 negedge 消费，避免 region 竞争。

启用非空 `REPORT_DIR` 后，正常调用 checker 的包生成 `<monitor层级>_packet_XXXXXX.json`，
包含配置、样点数、expected/received PDU、判定与原因。capture 失败或 bridge 异常
不保证生成 JSON，必须同时保留仿真日志/traceback，不能把缺 JSON 当成无错误。

uncoded AA 是容错同步相关，报告 AA 来自配置；Coded 核对 FEC 后 AA，但不代表
发送的每个原始 air symbol 都无误（可纠正损伤仍可恢复正确 PDU）。
ΔF1/ΔF2 尚未纳入判定，频偏诊断值也不能当成它们。第一阶段报告只能说明 TX 数据
检查是否通过，不能称 RF signoff。真实 VCS 验收和 DUT 正负例的清单见
[AI 交接文档](ic_server_ai_handoff.md)。
