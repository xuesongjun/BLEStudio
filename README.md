# BLE Studio

BLE Studio 是一个用于 BLE 基带仿真的 Python 工具，提供：

- BLE Packet 和 RF Test/DTM 测试数据生成；
- LE 1M/LE 2M GFSK TX、Channel、RX 理想闭环；
- AWGN、频偏、衰落和其他信道损伤测试；
- TXT、MAT、Verilog MEM 和 JSON 波形导出；
- Kingst 逻辑分析仪 BIN 数据恢复和 BLE RX 验证。

基本数据流：

```text
BLE TX 或外部 IQ → Channel → BLE RX → 报告/波形文件
```

当前项目不是完整 BLE 协议栈。LE Coded S=2/S=8、连接状态机和 Packet interval
（625 us zero padding）尚未实现。

## 快速开始

### Windows PowerShell

请保证创建环境、安装依赖和运行程序使用同一个 Python。推荐使用项目自己的 `venv`：

```powershell
cd C:\workspace\BLEStudio

python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -e .

# 使用默认配置运行
.\venv\Scripts\python.exe examples\demo.py
```

如果系统没有 `python` 命令，可以将第一行替换为：

```powershell
py -m venv venv
```

### Linux/macOS

```bash
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -e .
./venv/bin/python examples/demo.py
```

不要混用系统 `python`/`pip` 和 `venv` 中的解释器。若看到：

```text
ModuleNotFoundError: No module named 'ble_studio'
```

请改用上面明确的 `venv` Python，或者先激活环境：

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -e .
python examples\demo.py
```

默认示例读取 `examples/config.yaml`。报告输出目录由配置中的 `output.dir` 决定，默认
为 `results/`。

## 生成 96 MHz BLE 1M 波形

生成 LE 1M、96 MHz、PRBS9、37-byte RF Test 波形：

```powershell
.\venv\Scripts\python.exe examples\demo.py examples\config_rftest_1m_prbs9_96m.yaml
```

输出目录：

```text
artifacts/waveforms/LE1M_96Msps_PRBS9_37B/
```

常见输出文件：

| 文件 | 用途 |
|---|---|
| `*_TX.mem` | Verilog `$readmemh` 的理想 TX IQ |
| `*_RX.mem` | 经过 Channel 后的 RX IQ |
| `*.txt` | 量化后的 I/Q 文本 |
| `*.mat` | MATLAB/科学计算工具使用 |
| `*.json` | PHY、采样率、Packet、量化规则、文件大小和 SHA-256 |
| `index.html`、`charts.html` | 可选 HTML 报告 |

文件名格式为：

```text
<PHY>_<sample-rate>Msps_<payload>_<length>B_<TX|RX>.<extension>
```

当前 Python 生成的是单个 Packet。LE Test Packet 的 `I(L)` 周期和尾部 zero padding
仍未实现；interval golden vector 保存在 `reference/BLE_PKT/`，用于后续 TDD 开发。

## 配置文件

Demo 配置使用以下顶层结构：

```yaml
common:
  mode: "rf_test"       # rf_test / dtm / advertising
  channel: 0

tx:
  phy_mode: "LE_1M"     # LE_1M / LE_2M
  sample_rate: 96.0e6
  modulation_index: 0.5
  bt: 0.5
  payload_type: "PRBS9"
  payload_length: 37
  whitening: false
  access_address: 0x71764129
  crc_init: 0x555555

channel:
  type: "awgn"
  ebn0_db: .inf          # .inf 表示 bypass；有限值表示加入 AWGN
  freq_offset: 0

io:
  output:
    enabled: true
    bit_width: 12
    frac_bits: 0
    scale_to_full: true
    export_txt: true
    export_mat: true
    export_verilog: true
    export_tx: true

output:
  dir: "artifacts/waveforms/example"
  html_report: true
```

采样率必须是当前 PHY symbol rate 的整数倍：LE 1M 使用 1 MHz，LE 2M 使用 2 MHz。

常用配置：

| 配置 | 用途 |
|---|---|
| `examples/config.yaml` | 默认 RF Test 示例 |
| `examples/config_rftest_1m_prbs9_96m.yaml` | 96 MHz、LE 1M、PRBS9、37 bytes |
| `examples/config_rftest_2m_prbs15.yaml` | LE 2M、PRBS15 |
| `examples/config_rftest_pattern.yaml` | RF Test 调制测试模板 |
| `examples/config_advertising.yaml` | Advertising packet |
| `examples/config_low_snr.yaml` | 低 Eb/N0 和频偏测试 |
| `examples/config_ideal.yaml` | Advertising 理想信道示例 |

运行指定配置：

```powershell
.\venv\Scripts\python.exe examples\demo.py examples\config_advertising.yaml
```

只有 `io.output.enabled: true` 且相应 `export_*` 开关打开时，才会写出 TXT、MAT、MEM
和 JSON。`output.dir` 可以设置为任意本地输出目录；生成目录属于可再生产物，不建议提交
到 Git。

## 逻辑分析仪数据恢复

正式入口：

```powershell
.\venv\Scripts\python.exe -m ble_studio.logic_analyzer --help
```

将 Kingst 16-channel BIN 恢复为 IQ/SDR 数据：

```powershell
# 10-bit DDR ADC/IQ
.\venv\Scripts\python.exe -m ble_studio.logic_analyzer convert configs/logic_analyzer/adc_ddr.yaml

# RSSI 原始 SDR
.\venv\Scripts\python.exe -m ble_studio.logic_analyzer convert configs/logic_analyzer/rssi_raw_sdr.yaml

# 只诊断采样和 RX，不导出波形
.\venv\Scripts\python.exe -m ble_studio.logic_analyzer diagnose configs/logic_analyzer/adc_ddr.yaml

# 生成可编辑的 profile 配置
.\venv\Scripts\python.exe -m ble_studio.logic_analyzer config --profile adc-ddr my_adc.yaml
```

配置默认读取：

```text
data/logic_analyzer/captures/test.bin
data/logic_analyzer/captures/rssi.bin
```

完整 capture 不属于 Git tracked 文件。使用自己的数据时，请先把 BIN 文件放入该目录，
然后修改 `configs/logic_analyzer/*.yaml` 中的 `input.file`。输出默认写入
`artifacts/logic_analyzer/`。

详细说明：

- [逻辑分析仪使用与配置](doc/logic_analyzer/README.md)
- [采样和提取规则](doc/logic_analyzer/extraction_rules.md)
- [输出格式](doc/logic_analyzer/formats.md)

也可以使用安装后的命令：

```powershell
.\venv\Scripts\ble-la.exe --help
```

## 当前支持范围

| 能力 | 状态 |
|---|---|
| LE 1M GFSK TX/RX | 支持 |
| LE 2M GFSK TX/RX | 支持 |
| RF Test PRBS9/PRBS15/固定 pattern | 支持 |
| Advertising 基础 Packet | 支持 |
| CRC、whitening、理想 TX/RX loopback | 支持 |
| AWGN、频偏、衰落和部分 RF 指标 | 支持 |
| LE Coded S=2/S=8 | 未实现，入口会抛出 `NotImplementedError` |
| Packet interval `I(L)` zero padding | 未实现 |
| 完整 BLE 链路层/连接状态机 | 不在本项目范围 |

## 测试

安装开发依赖并运行全量回归：

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
.\venv\Scripts\python.exe -m pytest -q
```

当前回归覆盖 Packet/Core vectors、TX/RX loopback、Channel、IQ metadata/exporter 和
逻辑分析仪 pipeline。

## 项目目录

```text
ble_studio/                 # 核心 BLE 算法和 logic analyzer package
configs/                    # 正式 logic analyzer 配置
data/                       # golden IQ、fixture、profile 和本地 capture 目录
doc/                        # 协议、算法和 logic analyzer 文档
examples/                   # Demo 与 YAML 示例
reference/                  # MATLAB golden 脚本和参考向量
tests/                      # Core 与 logic analyzer 回归
artifacts/                  # 可再生输出目录，默认不提交
```

## 参考资料

- [Eb/N0 与 SNR](doc/ebn0_vs_snr.md)
- [GFSK phase pulse](doc/gfsk_phase_pulse.md)
- [BLE Core 6.2 PDF](doc/Core_v6.2.pdf)
- [RFPHY Test Specification PDF](doc/RFPHY.TS_5.2.pdf)
- [MATLAB golden reference](reference/Matlab/)

## 常见问题

### `ModuleNotFoundError: No module named 'ble_studio'`

通常是安装和运行使用了不同的 Python。执行：

```powershell
.\venv\Scripts\python.exe -m pip install -e .
.\venv\Scripts\python.exe examples\demo.py
```

### `No module named scipy`

使用项目解释器安装依赖，不要只运行系统 `pip install`：

```powershell
.\venv\Scripts\python.exe -m pip install -e .
```

### 逻辑分析仪提示输入文件不存在

完整 capture 默认不随 Git 提交。请将 BIN 文件放到
`data/logic_analyzer/captures/`，并检查 YAML 中的 `input.file` 路径。
