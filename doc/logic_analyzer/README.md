# 逻辑分析仪数据恢复工具

本子系统把 Kingst 逻辑分析仪导出的 16-channel BIN 转换为 DDR IQ 或 SDR
并行数据，并从同一个 `CaptureResult` 生成 MAT、TXT、MEM、NPZ、HTML 和 VCD。
它解决的是采集数据恢复、硬件时序诊断和 BLE RX 桥接，不修改 BLE
Demodulator 本身的算法。

## 输入格式

Kingst BIN 的每个原始采样固定占 2 bytes，按 little-endian 解释：

- byte 0 对应 channel 0-7，最低位是 channel 0；
- byte 1 对应 channel 8-15，最低位是 channel 8；
- `data_bits` 的列表顺序决定输出 word 的 bit significance；
- DDR profile 还需要一个 clock/data-indicator channel；
- SDR profile 可以声明 `extra_signals`，例如 AGC 或 ramp-up 控制信号。

空文件、奇数字节、非法 channel、`data_bits` 与 `bit_width` 不一致等情况会作为
配置或输入错误终止处理。

## 快速开始

统一入口支持 module 和 console script 两种调用方式：

```powershell
python -m ble_studio.logic_analyzer --help
ble-la --help
```

使用已有配置转换 capture：

```powershell
python -m ble_studio.logic_analyzer convert configs/logic_analyzer/adc_ddr.yaml
ble-la convert configs/logic_analyzer/adc_ddr.yaml
```

`convert` 支持临时覆盖输出设置：

```powershell
ble-la convert capture.yaml --formats mat npz vcd
ble-la convert capture.yaml --output-dir artifacts/logic_analyzer/run_01 --stem adc
ble-la convert capture.yaml --no-plot
```

`--no-plot` 只是不自动打开交互窗口；如果最终 formats 仍包含 `html`，HTML 文件仍会
写出。要完全不生成 HTML，应使用 `--formats` 覆盖格式列表并省略 `html`。

只输出诊断信息：

```powershell
ble-la diagnose configs/logic_analyzer/adc_ddr.yaml
```

配置启用了 BLE RX 但本次只想检查 capture 时，可以增加 `--skip-rx`。

生成 profile 配置。输出路径既可以是位置参数，也可以通过 `-o/--output`
指定：

```powershell
ble-la config --profile adc-ddr configs/logic_analyzer/my_adc.yaml
ble-la config --profile rssi-raw-sdr -o configs/logic_analyzer/my_rssi.yaml
ble-la config --profile rssi-resampled-sdr configs/logic_analyzer/my_resampled.yaml
```

生成配置后，至少需要确认 `input.file`、采样率、channel mapping、I/Q edge
mapping 和输出目录。完整 capture 默认不随 Git 分发，因此示例配置中的输入文件
可能需要先由用户放入本地 `data/logic_analyzer/captures/`。

### CLI 子命令

| 子命令 | 作用 |
|---|---|
| `convert` | 运行一次完整 pipeline，执行可选 BLE RX 验证并导出配置请求的格式 |
| `diagnose` | 输出边沿、eye stability、per-bit delay、sample rate 和 warning 等诊断信息 |
| `config` | 从内置 profile 生成一份可编辑 YAML |

配置、输入或 pipeline 错误会返回非零退出码。BLE 解调失败属于分析结果，通常会在
console 和 summary JSON 中记录 `success=false`，不会被伪装成 capture 转换错误。

## 三种 Profile

CLI profile 名使用连字符，YAML 中的 `capture.profile` 使用下划线名称。

| CLI profile | YAML profile | 模式 | 数据语义 | BLE RX |
|---|---|---|---|---|
| `adc-ddr` | `iq_ddr` | DDR | ch0-9 组成 10-bit word，clock channel 的两个边沿分别恢复 I/Q | 支持 |
| `rssi-raw-sdr` | `rssi_raw_sdr` | SDR | 每个 logic-analyzer sample 直接恢复一个 8-bit RSSI，并保留额外控制信号 | 不支持 |
| `rssi-resampled-sdr` | `rssi_resampled_sdr` | SDR | 按目标 `data_rate` 生成虚拟边沿，恢复重采样后的 9-bit 并行 word | 不支持 |

仓库中的参考配置分别是：

- `configs/logic_analyzer/adc_ddr.yaml`
- `configs/logic_analyzer/rssi_raw_sdr.yaml`
- `configs/logic_analyzer/rssi_resampled_sdr.yaml`

`adc_ddr.yaml` 当前约定上升沿为 Q、下降沿为 I。该映射来自现有硬件采集，换用其他
探针或 RTL 接口时必须根据实际极性确认，不能把它当作所有硬件的固定规则。

## 配置结构

新配置分为五个 section：

```yaml
input:
  file: "../../data/logic_analyzer/captures/test.bin"

capture:
  profile: "iq_ddr"
  mode: "ddr"
  sample_rate: 500.0e6
  data_rate: 32.0e6
  data_bits: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
  bit_width: 10
  clock_channel: 10
  rising_edge_data: "Q"
  falling_edge_data: "I"

processing:
  eye_align: true
  search_range: 15
  glitch_filter: true
  glitch_threshold: 0.2
  adaptive_filter: false
  output_spike_filter: true

output:
  directory: "../../artifacts/logic_analyzer/adc_ddr"
  stem: "waveform"
  formats: [mat, txt, mem, html, json]
  max_plot_samples: 50000
  show_plot: false
  include_debug_data: false

ble_rx:
  enabled: true
  phy_mode: "LE_1M"
  access_address: 0x71764129
  channel: 0
  whitening: false
  target_samples_per_symbol: 16
```

新配置中的相对输入和输出路径按 YAML 所在目录解析。legacy flat YAML 仍可加载；
如果按新规则找不到相对输入，loader 会尝试旧的 current-working-directory 规则并
记录迁移 warning。新配置不应依赖该 fallback。

## 数据目录

```text
configs/logic_analyzer/              可版本化的转换配置
data/logic_analyzer/captures/        本地完整 BIN/KVDAT capture，默认 Git ignore
data/logic_analyzer/fixtures/        小型、可复现的测试输入
data/logic_analyzer/profiles/        Kingst .kvset 硬件通道配置
data/logic_analyzer/quarantine/      来源或语义未确认的数据
artifacts/logic_analyzer/            所有可再生输出，默认 Git ignore
tests/logic_analyzer/fixtures/       自动测试专用的微型 fixture
```

不要把 MAT、TXT、MEM、NPZ、HTML 或 VCD 放回 capture 目录。一个输出 stem 必须只
对应一次 pipeline 结果，避免不同 profile 复用文件名前缀后互相覆盖。

## 处理链

```text
YAML config
  -> Kingst 16-channel decode
  -> input glitch filter
  -> DDR edge detection / SDR virtual edges
  -> eye analysis and per-bit delay
  -> optional adaptive filter
  -> DDR IQ / SDR parallel extraction
  -> optional output spike filter
  -> CaptureResult
       -> optional BLE RX validation
       -> summary/TXT/MAT/MEM/NPZ/HTML/VCD exporters
```

三个 filter 是独立开关：

- `glitch_filter` 处理原始数字通道中的短脉冲；
- `adaptive_filter` 根据 eye 采样位置修复不稳定数字通道；
- `output_spike_filter` 处理已经组装好的 I/Q 或并行 word 中的孤立尖刺。

所有 exporter 只读取同一个 `CaptureResult`，不会为了生成 VCD 或 HTML 重新执行
采样算法。因此同一次转换中的跨格式数据具有相同的 I/Q 顺序、sample count 和
处理配置。

## Sample Rate

结果同时保留 nominal 和 measured sample rate：

- DDR nominal IQ rate 为 `data_rate / 2`；
- SDR nominal output rate 为 `data_rate`；
- measured rate 来自采集边沿，只作为诊断 metadata；
- `CaptureResult.sample_rate` 和 canonical `fs` 使用 nominal rate，避免用边沿间隔
  的量化结果静默覆盖配置契约。

BLE RX 验证可以把 normalized complex IQ 重采样到整数 samples-per-symbol，但不会
覆盖原始提取数组。格式字段和导入方法见 [formats.md](formats.md)，当前采样判决与
九种历史场景见 [extraction_rules.md](extraction_rules.md)。
