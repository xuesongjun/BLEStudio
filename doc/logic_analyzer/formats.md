# Canonical 输出格式

所有格式必须由同一个 `CaptureResult` 导出，不允许 exporter 重新运行 BIN decode、
filter、eye analysis 或 extraction。默认输出基名为：

```text
<output.directory>/<output.stem>
```

无论 `output.formats` 是否显式包含 `json`，转换都会生成
`<stem>.summary.json`。其他格式只在配置请求时生成，生成 VCD 不会隐式生成 HTML，
反之亦然。

## 通用数值契约

- `data_bits_lsb_first` 记录输出 bit 0 到高位的 source channel 顺序；
- `I_unsigned/Q_unsigned` 或 `data_unsigned` 保存原始 two's-complement bit pattern；
- `I_signed/Q_signed` 或 `data_signed` 保存解释后的有符号整数；
- DDR normalized complex IQ 定义为：

```python
iq = (I_signed + 1j * Q_signed) / 2**(bit_width - 1)
```

- `fs` 等于 nominal output sample rate；
- `fs_nominal` 明确记录配置契约；
- `fs_measured` 是边沿测量诊断值，无法测量时为 NaN 或空值；
- 下游处理不应使用 `fs_measured` 静默覆盖 `fs`。

`I_raw/Q_raw` 是 `I_unsigned/Q_unsigned` 的兼容 alias，`data_raw` 是
`data_unsigned` 的兼容 alias。canonical 字段名仍以 `*_unsigned` 为准。读取旧
artifact 时应结合 `summary.json` 的 schema 和字段列表判断。

## Summary JSON

文件名：`<stem>.summary.json`

schema 当前为：

```text
ble_studio.logic_analyzer.capture.v1
```

它包含 profile、mode、sample count、raw/nominal/measured sample rate、bit width、
channel mapping、I/Q edge mapping、处理开关、请求的输出格式、warning、BLE RX 结果和
压缩后的 `sample_info` 摘要。大数组只记录 shape、dtype、min/max 和少量首元素，不会
把完整 capture 嵌入 JSON。

`summary.json` 是解释 MAT、MEM 和 VCD 的 metadata 来源，不是波形数据文件。

## MAT

文件名：`<stem>.mat`

MAT 是 BLE RX 和 MATLAB/NumPy 之间的首选 canonical bridge。DDR IQ 至少包含：

| 变量 | 含义 |
|---|---|
| `iq` | `complex128` normalized complex IQ |
| `I_unsigned`, `Q_unsigned` | 原始无符号 bit pattern |
| `I_raw`, `Q_raw` | `I_unsigned/Q_unsigned` 的兼容 alias |
| `I_signed`, `Q_signed` | two's-complement 有符号整数 |
| `fs` | 下游使用的 nominal sample rate |
| `fs_nominal` | 配置定义的 nominal sample rate |
| `fs_measured` | 从采集边沿估算的诊断 sample rate |
| `bit_width` | 每路 I/Q 的位宽 |
| `data_bits_lsb_first` | 输出 bit 到 source channel 的映射 |
| `I_sample_positions`, `Q_sample_positions` | 每个输出 sample、每个 data bit 的 raw sample index；缺失值为 -1 |
| `sample_positions` | 将 I/Q position matrix 沿首维组合后的数组 |
| `I_edges`, `Q_edges` | 对应输出 sample 的 source edge index |
| `metadata` | UTF-8 JSON 字符串形式的 summary |

SDR MAT 使用 `data_unsigned`、`data_signed`、`sample_positions` 和 `edges`，不包含
complex `iq`，因此不能直接送入 BLE Demodulator。

配置中的 extra signal 会以 `extra_<name>` 数组写入 MAT。signal name 中非字母、数字
或下划线的字符会替换为下划线。

MAT 通过 SciPy `savemat(..., do_compression=True)` 写出。一维数组在 MATLAB reader 中
可能表现为 row vector，调用方应按需要 flatten，不应依赖行列方向表达时间轴。

### 在 BLE Studio Demo 中导入 MAT

推荐使用 `iq`，它能精确保留 canonical 归一化和 MAT 中的 `fs`：

```yaml
io:
  input:
    enabled: true
    file: "artifacts/logic_analyzer/adc_ddr/waveform.mat"
    file_type: "mat"
    mat_complex_var: "iq"
```

不要默认读取 `I_unsigned/Q_unsigned`，否则负数的 two's-complement pattern 会被当作大
正数。也无需手动指定 sample rate，现有 `IQImporter.import_mat()` 会优先读取 `fs`。

## TXT

文件名：`<stem>.txt`

TXT 使用 ASCII 和 LF 换行。DDR IQ header 与数据形态如下：

```text
// BLE Studio RX-compatible samples
// Mode: ddr
// Sample Rate: 16000000 Hz
// Bit Width: 10
// Samples: 11841
// Format: I_signed Q_signed
-5 6
-5 3
```

SDR 使用单列 signed decimal，并写出 `// Format: data_signed`。TXT 不包含 unsigned
hex、sample positions 或 extra signal；这些诊断信息使用 debug CSV、NPZ 或 VCD。

现有 `IQImporter.import_txt()` 会自动忽略 `//` header，因此可以使用：

```yaml
io:
  input:
    enabled: true
    file: "artifacts/logic_analyzer/adc_ddr/waveform.txt"
    file_type: "txt"
    bit_width: 10
    iq_format: "two_column"
    number_format: "signed"
    skip_lines: 0
    sample_rate: 16.0e6
```

当前 demo 没有把 `frac_bits` 传给 TXT importer；当 `frac_bits=0` 时 importer 会按数据
峰值估计缩放。因而 TXT 保证 I/Q 相位和解调语义一致，但绝对幅度不保证与 MAT 的
`2**(bit_width-1)` 归一化完全相同。需要精确幅度时使用 MAT `iq`。

## MEM

文件名：`<stem>.mem`

MEM 是无 header 的 Verilog `$readmemh` uppercase hex，每行一个 word，使用 LF 换行。

DDR 布局：

```text
packed = (I_unsigned << bit_width) | Q_unsigned
```

即 I 位于高位，Q 位于低位；总宽度为 `2 * bit_width`，hex digits 为向上取整后的
`total_width / 4`。SDR 每行只保存一个 `bit_width` 宽的 two's-complement word。

Python API 可以读取 DDR MEM：

```python
from ble_studio import IQImportConfig, IQImporter

importer = IQImporter(IQImportConfig(bit_width=10))
iq = importer.import_verilog_mem("waveform.mem")
```

MEM 不携带 bit width、sample rate、I/Q polarity 或 channel mapping，必须与同一次
转换的 `summary.json` 一起使用。`examples/demo.py` 当前不支持直接选择 MEM 作为
`io.input`。

## NPZ

文件名：`<stem>.npz`

NPZ 使用 `numpy.savez_compressed`，包含与 MAT 相同的 canonical 数组，并增加：

```text
metadata_json
```

`metadata_json` 是 compact JSON 字符串。典型读取方式：

```python
import json
import numpy as np

archive = np.load("waveform.npz")
iq = archive["iq"]
fs = float(archive["fs"])
metadata = json.loads(str(archive["metadata_json"]))
```

DDR NPZ 包含 `iq` 和 I/Q raw/signed 数组；SDR NPZ 包含 `data_unsigned`、
`data_raw` 和 `data_signed`。extra signal 同样使用 `extra_<name>` key。NPZ 适合
Python 回归测试和完整数值交换，但现有 BLE Studio demo 没有 NPZ importer。

## HTML

文件名：`<stem>.html`

HTML 是查看工具，不是 canonical 数据存储。所有 trace 都使用单调、均匀的有界抽样：

- 若 `sample_count <= max_plot_samples`，绘制全部输出 sample；
- 否则从第一个到最后一个 sample 均匀选择最多 `max_plot_samples` 个 index；
- DDR 显示 signed I/Q 时域和 constellation；
- SDR 显示 signed parallel data；
- 存在 extra signals 时增加控制信号视图。

HTML 只嵌入抽样数据，完整数组仍以 MAT/NPZ 保存。Plotly runtime 使用 CDN，因此完全
离线环境打开 HTML 时可能无法加载交互脚本。`show_plot` 只控制是否自动显示，不改变
是否写出 HTML。

## VCD

文件名：`<stem>.vcd`

VCD 直接消费 `CaptureResult`，不会重新运行处理链。契约如下：

- `$timescale 1ps`；
- timestamp 由 raw sample index 和 raw capture sample rate 换算，保持单调；
- `capture` scope 包含 clock，以及 `I_unsigned/Q_unsigned` 或 `data_unsigned` bus；
- `extra` scope 包含配置声明的控制信号；
- `include_debug_data=true` 时，`debug` scope 还包含 raw 和 cleaned digital channels；
- bus 的事件位置优先使用 `sample_info` 中的 per-bit sample positions，其次使用 edge，
  最后才按 raw/output sample-rate ratio 估算。

同一 raw tick 上的 deskew word 只保留最终组装值。VCD bus 表示 unsigned bit pattern；
signed 解释应结合 `bit_width` 和 summary，而不是依赖波形查看器自动推断。

VCD 用于 GTKWave 等工具中的硬件时序调试，不是 BLE RX 输入格式。

## BLE RX 接入选择

推荐顺序：

1. 在逻辑分析仪 YAML 中启用 `ble_rx`，直接验证内存中的 `CaptureResult.iq`；
2. 需要跨工具或保存基线时，导出 MAT 并使用 `mat_complex_var: iq`；
3. 需要人工检查或简单文本交换时使用 signed TXT，接受幅度可能重新归一化；
4. RTL 联合验证使用 MEM，并从 summary 获取 bit width 和 Fs；
5. NPZ 用于 Python 分析，HTML/VCD 只用于查看和诊断。

直接 BLE RX 验证仅接受 DDR complex IQ。必要时会按
`target_samples_per_symbol` 使用 SciPy `resample_poly` 重采样，然后调用现有
`BLEDemodulator`。结果写入 summary 的 `rx_result`，包括 sample rate、重采样比例、
`success`、`sync_found`、`crc_valid`、access address、frequency offset 和 timing
offset。解调失败不会删除或覆盖已经生成的 capture 结果。
