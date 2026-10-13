# BLE Studio

## 运行环境

- 最低 Python（项目声明）：`Python >=3.8`。
- 完整回归实测：Python 3.13.7；Python 3.8 的运行兼容性尚未实际验证。

核心依赖如下，执行 `pip install -e .` 时自动安装：

| 依赖与版本约束 | 用途 |
|---|---|
| `numpy>=1.20.0` | 数组与复数 IQ 运算 |
| `scipy>=1.7.0` | 信号处理、重采样、MAT 文件读写 |
| `plotly>=5.10.0` | 交互式波形图与 HTML 报告 |
| `PyYAML==6.0.3` | 读取 YAML 配置 |

pytest、Matplotlib、Jupyter、nbformat 属于可选开发依赖，不是核心运行依赖；
开发与测试时用 `pip install -e ".[dev]"` 安装。

### 快速自检

首次使用先按下方“1. 安装并运行”创建 venv 并安装项目；已有环境在仓库根目录执行：

Windows PowerShell：

```powershell
.\venv\Scripts\python.exe scripts\check_env.py
```

Linux/macOS：

```bash
./venv/bin/python scripts/check_env.py
```

脚本不依赖 pytest，不自动安装依赖，也不导出波形或报告。它检查 Python 版本、
四项核心依赖的导入与实际版本、BLEStudio 是否来自当前仓库，以及 LE 1M、96 MHz、
PRBS9、37 bytes 理想 TX/RX 的同步、CRC、完整 PDU 和 bits。

最终输出 `[PASS] Overall` 且退出码为 `0` 表示上述基础自检通过；
`[FAIL] Overall` 的退出码为 `1`，失败项会显示原因与处理提示；
`[SKIP]` 表示因前置检查失败而未执行，不能视为通过。

失败时先核对输出的 `Python executable`；缺包、安装损坏或导入了别的 checkout，
请在仓库根目录用同一解释器重新执行 `pip install -e .`：
Windows 为 `.\venv\Scripts\python.exe -m pip install -e .`，
Linux 为 `./venv/bin/python -m pip install -e .`。

已安装包的依赖约束可另用 `.\venv\Scripts\python.exe -m pip check` 核对
（Linux：`./venv/bin/python -m pip check`）；自检的核心依赖检查是导入可用性与版本显示，
不替代依赖约束检查、完整 pytest 回归、VCS 仿真或 RF 合规验收。

## 功能简介

BLE 基带仿真与芯片 TX 数据检查工具。支持 LE 1M、LE 2M、LE Coded S2/S8，
提供 Packet/DTM 数据生成、GFSK TX/RX、信道损伤、IQ/MEM/JSON 导出和 VCS 整包 checker。

```text
Packet / 外部 IQ → TX / Channel → RX → 数据检查、波形文件、HTML 报告
```

不是完整 BLE 协议栈。当前 Python 生成单包，不包含 Test Packet 的 `I(L)` 周期补零；
ΔF1/ΔF2 尚无经过校准的自动合规判定，解调/CRC/PDU 检查通过不代表 RF 合规通过。

## 1. 安装并运行

所有命令从仓库根目录执行，配置中的相对路径也以此为基准。
安装与运行必须使用同一个 Python 环境；已有 `venv` 可以直接复用。

Windows PowerShell：

```powershell
cd C:\workspace\BLEStudio
python -m venv venv
.\venv\Scripts\python.exe -m pip install -e .
.\venv\Scripts\python.exe examples\demo.py
```

Linux/macOS（先进入仓库根目录）：

```bash
python3 -m venv venv
./venv/bin/python -m pip install -e .
./venv/bin/python examples/demo.py
```

默认读取 `configs/waveforms/default.yaml`，结果写入 `artifacts/waveforms/default/`。
浏览器打开其中的 `index.html` 查看报告。

- `ModuleNotFoundError: No module named 'ble_studio'`：先用上述 venv Python 执行安装，不要混用系统 pip。
- `FileNotFoundError`：检查当前目录和配置路径；缺失配置会明确报错，不再静默生成默认波形。
- 更新旧工作区后重新执行 `pip install -e .`，刷新安装元数据和已移除的旧 CLI。

## 2. 生成 96 MHz、PRBS9、37 bytes 波形

以 LE 1M 为例：

```powershell
.\venv\Scripts\python.exe examples\demo.py configs\waveforms\rftest_1m_prbs9_96m.yaml
```

输出到 `artifacts/waveforms/LE1M_96Msps_PRBS9_37B/`：

| 文件 | 内容 |
|---|---|
| `LE1M_96Msps_PRBS9_37B_TX.mem` | 理想 TX，供 Verilog `$readmemh` 使用 |
| `LE1M_96Msps_PRBS9_37B_RX.mem` | Channel 输出 |
| 同名 `.txt` | 有符号 I/Q 两列整数 |
| 同名 `.mat` | 浮点复数 IQ |
| 同名 `.json` | PHY、采样率、包内容、量化规则、样点数及文件 SHA-256 |
| `index.html`、`charts.html`、`report.html` | HTML 报告 |

此配置 MEM 每行 24 bits，I 占高 12 bits、Q 占低 12 bits，两路均为有符号补码。
默认文件名含 PHY、采样率、Payload 类型、长度及 TX/RX 标记；请保留同名 JSON，便于追溯。

LE Coded 使用相同采样率和 Payload：

```powershell
.\venv\Scripts\python.exe examples\demo.py configs\waveforms\rftest_s2_prbs9_96m.yaml
.\venv\Scripts\python.exe examples\demo.py configs\waveforms\rftest_s8_prbs9_96m.yaml
```

输出目录分别为 `artifacts/waveforms/LE500K_96Msps_PRBS9_37B/`（S2）和
`artifacts/waveforms/LE125K_96Msps_PRBS9_37B/`（S8）。三份配置均为理想信道，无尾部补零。

## 3. 修改配置

配置统一放在 `configs/waveforms/`，不要再放进 `examples/` 或 `scripts/`。

| 配置文件 | 用途 |
|---|---|
| `default.yaml` | 默认 RF Test 示例 |
| `rftest_1m_prbs9_96m.yaml`、`rftest_s2_prbs9_96m.yaml`、`rftest_s8_prbs9_96m.yaml` | 96 MHz 理想 IQ/MEM/JSON |
| `rftest_2m_prbs15.yaml`、`rftest_prbs9.yaml` | 其他 PHY/Payload 示例 |
| `rftest_df1.yaml`、`rftest_df2.yaml`、`rftest_pattern.yaml` | 调制特性激励，不等同于合规 testcase |
| `advertising.yaml`、`ideal.yaml` | Advertising 示例 |
| `low_snr.yaml`、`rayleigh.yaml`、`channel_scan.yaml` | 信道与损伤实验 |
| `import_bwv.yaml`、`import_mat.yaml` | 外部 IQ 导入示例 |

复制最接近需求的 YAML 再修改，主要字段：

```yaml
common:
  mode: "rf_test"          # rf_test / dtm / advertising
  channel: 0

tx:
  phy_mode: "LE_1M"        # LE_1M / LE_2M / LE_CODED_S2 / LE_CODED_S8
  sample_rate: 96.0e6
  payload_type: "PRBS9"
  payload_length: 37
  whitening: false

channel:
  type: "awgn"
  ebn0_db: .inf            # .inf 为理想信道，有限值加入 AWGN
  freq_offset: 0

output:
  dir: "artifacts/waveforms/my_case"
  html_report: true
```

其余字段参照现有配置。需要 TXT/MAT/MEM/JSON 时，还需开启 `io.output.enabled`
及相应 `export_txt`、`export_mat`、`export_verilog`、`export_tx` 开关。
采样率需为空中 symbol rate 的整数倍：LE 1M/Coded 为 1 MHz，LE 2M 为 2 MHz。

运行指定配置：

```powershell
.\venv\Scripts\python.exe examples\demo.py configs\waveforms\advertising.yaml
```

## 4. VCS 与辅助分析

VCS 整包 checker 从 DAC I/Q 收集一包后检查同步、CRC 和完整 PDU：

- [集成与工作说明](docs/integration/vcs/ic_server_integration.md)
- [交给 IC Server AI 的说明](docs/integration/vcs/ic_server_ai_handoff.md)
- [接口及 smoke 说明](docs/integration/vcs/vcs_tx_checker.md)
- [上传文件清单](docs/integration/vcs/ic_server_upload_files.txt)

真实 CentOS 7 / VCS 2025 / Python 3.10 环境仍需服务器验收，本地 Python 测试不能替代 VCS 仿真。

比较明确指定的两份波形（两者同为 TXT 或 MAT）：

```powershell
.\venv\Scripts\python.exe scripts\compare_iq.py --help
.\venv\Scripts\python.exe scripts\compare_iq.py artifacts\waveforms\LE1M_96Msps_PRBS9_37B\LE1M_96Msps_PRBS9_37B_TX.txt artifacts\waveforms\LE1M_96Msps_PRBS9_37B\LE1M_96Msps_PRBS9_37B_RX.txt
```

TXT 比较针对 I/Q 两列整数，不接受 packed MEM。MAT 使用 `iq` 或 `IQ` 变量。
无文件、空数据、非有限 MAT 数据、格式不符或长度不等返回错误；正常比较有差异时输出报告，
不自动当作 testcase 失败。其他 `scripts/` 脚本保留为分析/实验工具，其历史 RF PASS 显示不可用于 signoff。

## 5. 目录结构与作用

```text
BLEStudio/
├── ble_studio/                活动 Python 核心
│   ├── packet.py              Packet、PRBS、CRC、白化
│   ├── coded_phy.py           LE Coded FEC、映射与解码
│   ├── modulator.py           GFSK TX
│   ├── channel.py             信道与损伤
│   ├── demodulator.py         同步与 RX
│   ├── tx_checker.py          整包数据检查
│   ├── iq_io.py               IQ 导入、量化与导出
│   ├── measure.py             测量算法
│   ├── performance.py         性能实验
│   ├── visualizer.py          图表
│   └── report.py              HTML 报告
├── configs/waveforms/         16 份运行配置
├── examples/                 demo.py、benchmark.py 使用入口
├── scripts/                  环境自检、IQ、调制、RF 辅助分析脚本
├── sim/vcs/                  SV monitor、DPI bridge、smoke
├── tests/
│   ├── core/                 算法、loopback、导出回归及规范 fixture
│   ├── tooling/              布局、路径、隔离、CLI 回归
│   └── native/               C++ embedding smoke
├── docs/
│   ├── algorithms/           算法说明与 notebook
│   ├── integration/vcs/      接入、交接、上传清单
│   └── development/          plan.md、research.md，含历史与待开发项
├── reference/
│   ├── matlab/               MATLAB golden 生成/校验脚本、通用基础库
│   ├── vectors/              固定 MAT/TXT/JSON/BWV 参考数据
│   └── specifications/       BLE Core、RFPHY PDF
├── artifacts/                运行时按需创建，所有可再生产物，Git ignore
├── README.md                 本教程
├── pyproject.toml            安装、依赖、包发现与默认测试配置
├── process.txt               按 commit 追加的变更日志
└── .gitignore                本地环境、缓存与输出忽略规则
```

存放规则：

- 源码、配置、测试、文档分别进入上表目录，不混放临时脚本或结果。
- 波形/报告放 `artifacts/waveforms/`，独立报告默认 `artifacts/reports/`，VCS 产物放 `artifacts/vcs_tx_checker/`，交接包放 `artifacts/ic_server_handoff/`。
- `reference/vectors/` 保存 MATLAB golden 与固定外部波形 `BLE_1M.bwv`，不是运行输出，不要随意重生成或删除。MATLAB 仅作参考，日常生成无需 MATLAB License。
- `venv/`、`.git/`、`.claude/` 是本地环境/管理目录，保持原位；缓存和 artifacts 可清理。

本次不保留旧目录兼容入口：配置不再在 `examples/`，文档由 `doc/` 改为 `docs/`，
MATLAB/向量改放 `reference/matlab/`、`reference/vectors/`，辅助脚本改放 `scripts/`。
默认输出不再使用 `results/`，依赖统一以 `pyproject.toml` 为准。

## 6. 开发与参考

已有开发环境直接运行：

```powershell
.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

新环境需要开发工具时使用 `python -m pip install -e ".[dev]"`。
默认测试只收集 `tests/` 中的 BLEStudio 测试。

- [开发计划与执行记录](docs/development/plan.md)、[调研记录](docs/development/research.md)
- [相关性](docs/algorithms/correlation_explanation.md)、[Eb/N0 与 SNR](docs/algorithms/ebn0_vs_snr.md)、[GFSK](docs/algorithms/gfsk_phase_pulse.md)
- [MATLAB golden 脚本](reference/matlab/)、[Golden 向量](reference/vectors/)
- [BLE Core 6.2](reference/specifications/Core_v6.2.pdf)、[RFPHY Test Specification](reference/specifications/RFPHY.TS_5.2.pdf)
