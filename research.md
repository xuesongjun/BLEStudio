# 逻辑分析仪子系统专项调研

日期：2026-07-20

## 1. 调研目标

本次调研只覆盖以下链路：

```text
Kingst 逻辑分析仪 BIN
  -> 数字通道解析
  -> 毛刺过滤与通道 deskew
  -> DDR IQ 或 SDR 并行数据恢复
  -> TXT/NPY/MAT/MEM/HTML/VCD
  -> BLE Studio IQ 输入
  -> BLEDemodulator 验证
```

BLE Studio 的 Packet、Modulator、Channel、Demodulator 和 RF Measure 算法优化不在本次整理范围内。本次只建立稳定的数据采集、恢复、导出和 RX 验证边界。

## 2. 当前实现地图

### 2.1 主处理链

`utils/logic_analyzer_bin2wave.py` 是当前能力最完整的实现，约 1500 行，内部同时承担：

- YAML 配置解析
- Kingst 16-channel BIN 解码
- 基础与自适应毛刺过滤
- 眼图和每 bit 最佳延迟分析
- DDR I/Q 提取
- SDR 虚拟边沿和单路并行数据提取
- 输出数据 spike filter
- TXT、NPY、MAT、MEM 导出
- Plotly HTML 可视化
- CLI 编排

当前工作树还在该文件中新增 SDR/RSSI、虚拟采样边沿、单通道 spike filter 和 `extra_signals` 配置。这些未提交改动必须作为迁移基线保留，不能用 `HEAD` 版本覆盖。

### 2.2 重复和分叉实现

| 文件 | 当前作用 | 判断 |
|---|---|---|
| `utils/logic_analyzer_bin2wave.py` | 通用 DDR/SDR 主入口 | 作为迁移源保留 |
| `utils/logic_analyzer_to_iq.py` | 初代 10-bit DDR IQ 转换 | 与主入口重复，采样率定义也不同 |
| `utils/bin_to_vcd.py` | 复跑主处理链并生成 DDR VCD | 应合并为统一 exporter |
| `utils/rssi_parser.py` | RSSI 8-bit 和控制信号专用解析 | 应成为 SDR profile，不保留第二套 pipeline |
| `utils/analyze_sampling_issues.py` | I 路不稳定点诊断 | 应转为正式 diagnose 子命令或测试 |
| `utils/search_best_sample.py` | 硬编码路径的延迟搜索实验 | 迁移为测试或 legacy |
| `utils/my_test.py` | 硬编码路径、延迟和 HTML 的实验脚本 | 迁移为 legacy |
| `utils/logic_analyzer_bin2wave_prompt.md` | 早期四行需求说明 | 合并进正式文档 |
| `提取规则.md` | 九类采样情景 | 转为参数化测试和正式算法文档 |

`utils/analyze_signal.py`、`compare_iq.py`、`get_bwv_info.py`、`read_mat.py` 属于通用 IQ/MAT 分析工具，不属于逻辑分析仪核心 pipeline，本阶段不重构其内部逻辑。

## 3. 配置现状

当前存在三种含义不同但命名接近的配置：

| 配置 | 数据语义 | 输出前缀 |
|---|---|---|
| `utils/logic_analyzer_config.yaml` | 10-bit DDR I/Q | `template_data/test_iq` |
| `utils/logic_analyzer_config_rssi.yaml` | 9-bit SDR 重采样数据 | `template_data/rssi_wave` |
| `utils/rssi_config.yaml` | 8-bit 原始 RSSI 加 `agc_init/rampup/fire_timer` | `template_data/rssi_wave` |

两个 RSSI 配置共用同一个输出前缀，已经导致不同工具的产物互相混写。例如：

- `rssi_wave.npy/txt/html/vcd` 来自 RSSI 专用解析器，包含 10,363,525 个 100 MHz 原始采样。
- `rssi_wave.mat/mem` 来自通用 SDR 恢复路径，只包含 93,498 个重采样数据。

同名前缀不再代表同一次 pipeline 结果，无法可靠复现。

配置路径也依赖当前工作目录。配置文件内的相对路径没有按 YAML 所在目录解析，从仓库根目录以外运行会找不到输入文件。

## 4. 数据和产物现状

`template_data/` 同时混放了四类内容：

### 4.1 原始采集

- `test.bin`：当前 DDR IQ 输入，工作树中约 950 KiB。
- `rssi.bin`：当前 RSSI 输入，工作树中约 20.7 MiB。
- `test3.bin`：未跟踪，当前没有代码或配置引用。
- 已删除但 Git 仍记录删除状态的旧 BIN 文件不得在本次整理中恢复或覆盖。

### 4.2 Kingst 工程和 Profile

- `adc_data.kvset`
- `rssi.kvset`
- `diag_0x3.kvset`
- `rfpll.kvset`
- `bk.kvdat`
- `raw_data.kvdat`

`bk.kvdat` 与 `raw_data.kvdat` 的 SHA256 完全相同，是重复数据。第一阶段不直接删除，只做隔离和标记。

### 4.3 可再生输出

- `test_iq.{txt,npy,mat,mem,html}`
- `test_debug.{vcd,html}`
- `rssi_wave.{txt,npy,mat,mem,html,vcd}`
- `rssi_waveform.png`

这些文件均应由 pipeline 生成，不应与输入样本放在同一目录。

### 4.4 参考或旧基线

- `test_iq_old.{txt,npy,mat}`：旧转换器输出，目前仍被示例配置引用。
- `BLE_1M.bwv`：MATLAB/iTest IQ 参考波形，不是逻辑分析仪数据。

当前 `template_data/` 约 852 MiB，其中：

- HTML 约 637 MiB
- TXT 约 139 MiB
- VCD 约 39 MiB
- BIN 约 26 MiB

最大文件 `rssi_wave.html` 约 647 MB。原因是 Plotly 将全部采样点嵌入 HTML，没有绘图点数限制或抽样策略。

当前 `.gitignore` 中 `.html`、`.npy`、`.mat` 的写法只会匹配名为该字符串的文件，不能忽略普通扩展名文件。

## 5. 数据契约问题

### 5.1 BIN 输入

Kingst BIN 被假定为每个采样固定 2 bytes：

- byte 0：channel 0-7
- byte 1：channel 8-15

当前没有文件头、长度和通道范围校验。奇数字节输入会在 `reshape(-1, 2)` 处抛出低层异常。

`data_bits` 的列表顺序决定输出 word 的 bit significance，而 `bit_width` 又独立决定符号位。两者不一致时会产生错误的补码解释。

### 5.2 DDR 和采样率

DDR 使用上升沿和下降沿分别恢复 I/Q，最后按较短一路截断。原始时间戳、burst 间隔和丢失边沿信息只存在于临时 `sample_info`，不会进入 MAT/TXT/MEM。

当前采集的正常时钟周期主要在 31 和 32 个 500 MHz 采样之间交替：

```text
median period = 31       -> 16.129032 MHz
mean period   = 31.24964 -> 16.000184 MHz
nominal                    16.000000 MHz
```

新工具使用 interval median 覆盖 nominal rate，会形成量化偏差。BLE RX 又使用 `int(sample_rate / symbol_rate)`，因此错误 Fs 会影响长包定时。

### 5.3 SDR 和额外控制信号

SDR 使用 `sample_rate / data_rate` 生成虚拟边沿，输出单路整数数据，不是 complex IQ，不能直接送入 BLE Demodulator。

`Config.extra_signals` 已能从 YAML 读取，但主 pipeline 没有消费。真正的 RSSI 控制信号提取仍只存在于独立 `rssi_parser.py`。

### 5.4 输出过滤

最终 `filter_iq_spikes()` 或 `filter_data_spikes()` 当前无条件执行，即使配置关闭了 `glitch_filter`，最终输出仍会被修改。输入毛刺过滤和输出 spike filter 必须拆成两个独立开关。

## 6. 输出与 BLE RX 兼容性

| 格式 | 当前内容 | RX 兼容性 |
|---|---|---|
| TXT | `#` header，四列：I hex、Q hex、I signed、Q signed | 默认不兼容 `IQImporter` |
| MAT | `I/Q` unsigned、`I_signed/Q_signed`、`fs/bit_width` | 显式选择 signed 变量后可用 |
| MEM | 高位 I、低位 Q 的 packed hex | 布局兼容 importer，但 demo 不支持 MEM |
| NPY | IQ 为 Nx2 unsigned，缺少 Fs 和 bit width | 没有统一 importer |
| HTML | 全量 Plotly 图 | 仅用于查看，当前体积失控 |
| VCD | raw/clean/sample/IQ debug signal | 仅用于硬件时序调试 |

TXT 与默认 `IQImporter` 的冲突包括：

- Writer 使用 `#` 注释，Importer 只跳过 `//`。
- Writer 前两列为 `0x...`，demo 默认按 signed decimal 解析。
- TXT header 中的 sample rate 不会被读取。

MAT 是当前最可靠的桥接格式，但必须配置 `I_signed/Q_signed`。如果默认读取 `I/Q`，负值补码会被当成大的正数。

当前 `test_iq.mat`、正确配置后的 TXT 和 MEM 得到一致的 IQ phase 数据，但进入当前 Demodulator 都是 `sync_found=False`。这说明后续需要区分：

1. capture/extraction 是否正确；
2. Fs、I/Q polarity、bit order 和 burst 时间是否正确；
3. BLE RX 本身是否能处理该采样率和时钟误差。

本阶段只建立可观测、可重复的桥接和验证结果，不修改 RX 算法来掩盖采集问题。

## 7. VCD 和可视化分叉

- 主配置允许写 `vcd`，但主 `save_data()` 没有 VCD 分支。
- `bin_to_vcd.py` 会重新执行处理链，并且不一定执行与主入口相同的最终 spike filter。
- VCD 实现按 10-bit DDR 和固定 `sample_info` 结构编写，不支持新的 SDR 路径。
- `bin_to_vcd.py` 生成 VCD 后还会强制生成 HTML，进一步放大产物。
- HTML 使用所有采样点，缺少 `max_plot_samples` 和 decimation。

所有 exporter 必须消费同一个不可变的 pipeline result，不能各自重跑算法。

## 8. 工程化问题

- `utils` 没有 `__init__.py`，打包配置只包含 `ble_studio*`，安装后逻辑分析仪工具不可用。
- 不同脚本混用裸导入、`utils.` 导入和 `sys.path.insert()`。
- 没有正式 pytest 测试，算法修改只能依靠人工查看 HTML/VCD。
- `提取规则.md` 描述的上下文智能采样与当前“直接信任眼图最佳点”实现不一致。
- 当前完整 capture 和输出体积不适合常规 CI，也没有 Git LFS 或外部 artifact 规则。
- `PyYAML` 已被多个入口实际依赖，但没有在项目依赖中声明。

## 9. 整理原则

1. 当前工作树是迁移基线，不覆盖用户未提交改动。
2. 先补 characterization tests，再拆分 1500 行脚本。
3. 只保留一条 BIN decode 和 processing pipeline。
4. RSSI 作为通用 SDR profile，不保留第二套完整实现。
5. TXT/MAT/MEM/HTML/VCD 必须来自同一个 pipeline result。
6. MAT 使用 normalized complex `iq` 作为 BLE RX canonical interface，同时保留 raw/signed 数据用于硬件调试。
7. RX 验证是可选步骤，只调用现有 `BLEDemodulator`，不在本阶段修改其算法。
8. 大 capture 和可再生产物不进入常规 Git；Git 只保留小型真实 fixture 和硬件 Profile。
9. 第一阶段不删除原始数据、不重写 Git 历史；迁移前记录文件 path、size 和 hash。
10. 旧命令先保留 thin wrapper，避免一次性破坏现有使用方式。

## 10. 调研结论

逻辑分析仪功能当前并非单纯的目录杂乱，而是存在 pipeline 重复、配置语义冲突、输出契约分裂、采样率元数据偏差和不可控大产物等问题。

建议将其迁入可安装的 `ble_studio.logic_analyzer` 子包，建立类型化配置、单一处理 API、统一 exporter、可选 BLE RX 验证以及独立的数据和 artifact 目录。具体执行方案见 `plan.md`。

---

# BLE Core 与仿真平台专项调研

日期：2026-07-21

## 1. 调研范围和事实来源

本轮只读调研覆盖：

```text
Packet/PDU -> GFSK Modulator -> Channel/Impairments -> Demodulator
           -> BER/PER/RF Measure -> examples/demo.py
```

事实来源：

- 仓库内 `doc/Core_v6.2.pdf`：Vol 6 Part B、Part C、Part F。
- 仓库内 `doc/RFPHY.TS_5.2.pdf`。
- `ble_studio/packet.py`、`modulator.py`、`channel.py`、`demodulator.py`、`performance.py`、`measure.py`。
- 最小无损实验和现有 MATLAB `.bwv` 参考波形。

本轮没有修改 BLE Core 代码，也没有用理想闭环成功来替代规范向量验证。

## 2. 当前可运行基线

| 场景 | 当前结果 | 结论 |
|---|---|---|
| DTM LE 1M，8 Msps，理想 IQ | `success=True, sync=True, crc=True` | 基本调制/解调闭环可运行 |
| DTM LE 2M，8 Msps，理想 IQ | `success=True, sync=True, crc=True` | LE 2M 理想闭环可运行 |
| MATLAB `BLE_1M.bwv`，120 Msps | `success=True, sync=True, crc=True` | RX 能解调现有 MATLAB 参考波形 |
| Advertising LE 1M，理想 IQ | 恢复 bits 与 TX 完全一致，但 `sync=False` | Packet 前导码与 RX 规则不一致 |
| 逻辑分析仪完整 DDR capture | `sync=False, crc=False` | 需在核心确定性问题修复后继续诊断 |

这说明现有 RX 不是整体不可用；优先级应是先修复确定性的 Packet、配置和测试链路，再优化真实 capture 的同步与定时。

## 3. P0：Packet 与链路层确定性错误

### 3.1 前导码没有根据 Access Address LSB 选择

Core 6.2 Vol 6 Part B 2.1.1 要求：前导码第一个传输 bit 必须与 Access Address 的 LSB 相同。

当前 `BLEPacket.generate()` 和 `RFTestPacket.generate()` 固定使用：

```text
LE 1M: 10101010
LE 2M: 1010101010101010
```

默认 Advertising AA `0x8E89BED6` 的 LSB 为 0，正确前导码应为 `01010101`。当前理想 Advertising 波形虽然全部 bits 均能正确判决，但 Demodulator 按规范生成同步模式，因此必然同步失败。

影响：

- 所有 LSB=0 的 Advertising/Data AA。
- 使用自定义偶数 AA 的 DTM/Data 测试。
- 真实 capture 与合成 TX 的同步行为不一致。

### 3.2 Whitening LFSR 与官方 sample vector 不一致

Core 6.2 Vol 6 Part C 4.1 给出 channel 0 的前 64 个 whitening bits：

```text
00000010 01001101 00111101 11000011 11111000 11101100 01010010 11111010
```

当前 `_get_whitening_sequence(0, 64)` 输出：

```text
01000100 11000101 11010110 11000001 10011010 10011100 11110110 10000101
```

TX 和 RX 复用了同一种错误方向，所以内部 loopback 可能通过，但不能证明与 Bluetooth 设备或 MATLAB 兼容。

### 3.3 `crc_init` 配置未进入 TX/RX

当前 CRC 核心算法在显式传入 `init=0xC4C181` 时能匹配 Core 6.2 Data Channel sample vector：

```text
PDU: 0x16 0x05 0x01 0x02 0x03 0x04 0x05
CRC transmission bits: 10100010 00001011 01001011
```

但正式链路存在两个问题：

- `BLEPacket.generate()` 和 `RFTestPacket.generate()` 调用 `_calculate_crc(pdu)`，没有传 `config.crc_init`。
- `BLEDemodulator._check_crc()` 固定使用 `0x555555`。

实测同一 PDU 配置 `0x555555` 和 `0xC4C181` 会生成完全相同的 CRC bits。所有 ACL Data Channel 自定义 CRCInit 当前都不可用。

### 3.4 Data Channel PDU 被重建成错误头部

`create_data_packet()` 把完整 PDU 写到动态属性 `_data_pdu`，但 `BLEPacket.generate_pdu()` 从不读取该属性，而是用 `pdu_type=0` 和 payload 重新生成 Advertising 风格头部。

实测：

```text
requested PDU:  02 03 01 02 03
generated PDU:  00 03 01 02 03
```

README 中公开的 Data Channel 示例因此无法生成所声明的 LLID/NESN/SN/MD。

### 3.5 `create_connect_ind()` 丢弃完整 Payload

函数已经组装 `InitA + AdvA + LLData`，但返回时调用 `create_advertising_packet()` 并传入两个空 payload 参数。

实测输出：

```text
generated PDU: 05 00
payload length: 0
```

应有的 34-byte CONNECT_IND payload 完全丢失。

## 4. P0：公开性能测试接口不可运行

`BLEPerformanceTester._apply_channel()` 调用以下不存在的方法：

- `BLEModulator.add_noise()`
- `BLEModulator.add_frequency_offset()`
- `BLEModulator.add_timing_offset()`

`quick_ber_test()`、`quick_snr_sweep()` 和 README 中的公开示例会直接抛出 `AttributeError`。仓库另一个 `examples/benchmark.py` 使用 `BLEChannel`，因此能运行，但形成了两套不一致的性能测试入口。

## 5. P1：配置和能力声明问题

### 5.1 Demo 参数没有完整传递

- `examples/demo.py` 计算了自定义 `access_address`，但创建 DTM Packet 时没有传给 `create_test_packet()`；RX 却使用自定义值。
- `mode: dtm` 走 DTM TX 分支，但 RX whitening 判断只识别 `mode == 'rf_test'`，因此会错误开启去白化。
- 未知 `mode` 会静默进入 Advertising 分支，没有配置错误。

### 5.2 LE Coded 是枚举占位，不是已实现 PHY

`BLEPhyMode` 暴露 `LE_CODED_S2/S8`，示例配置也列出这两个值，但 Packet、Modulator、Demodulator 没有 FEC、pattern mapping、CI、TERM1/TERM2 或 Coded preamble。

实测 LE 1M、LE Coded S=2、LE Coded S=8 对相同 payload 均产生相同 bit 数和 IQ sample 数。当前行为是静默按 1M uncoded 处理，比显式报未实现更危险。

### 5.3 Sample rate 被静默截断为整数 SPS

Modulator 和 Demodulator 都使用：

```python
int(sample_rate / symbol_rate)
```

例如 7.5 Msps 被当作 7 SPS，生成波形的实际 symbol rate 与 metadata 不一致；0.5 Msps 会令 SPS 为 0 并触发 `ZeroDivisionError`。应显式要求正整数 SPS，或由独立 resampler 处理。

### 5.4 Channel 枚举和实际 impairment chain 不一致

- `ChannelType.FLAT_FADING` 存在，但 `_build_channel()` 没有分支，实际只加入 PhaseNoise 和 AWGN。
- `phase_noise_level=-100` 是默认值，且条件 `> -120`，因此所有 Channel 默认隐式加入 PhaseNoise。
- `create_ble_indoor_channel(environment=...)` 接受环境参数，但 `BLEChannel` 固定构造 `BLEIndoorChannel('office', ...)`。

这与“只添加用户指定损伤”的平台目标不一致。

## 6. 测试与文档缺口

- `tests/` 目前只有逻辑分析仪测试，没有 Packet、Modulator、Channel、Demodulator、Performance、RF Measure 测试。
- README 仍展示不存在的 `modulator.add_noise()` 和相关方法。
- README 宣称 Data Channel、BER/PER 公共接口可用，但实际入口确定失败。
- `examples/config_channel_scan.yaml` 是单信道手动配置，却在项目结构中标注为“全信道扫描”。
- Coded PHY 在配置注释中出现，但 README 技术规格只列出 LE 1M/2M，能力边界不统一。

## 7. 优先级结论

建议按以下顺序继续：

1. **Core correctness baseline**：规范向量测试、前导码、whitening、CRCInit、Data PDU、CONNECT_IND、SPS 验证。
2. **Platform executable path**：修复 Performance 与 Demo 参数传递，统一使用 `BLEChannel`。
3. **RX robustness**：在理想/规范向量稳定后，继续分析完整逻分 capture 的 burst、polarity、timing、CFO 和同步策略。
4. **Channel/RF accuracy**：校准 fading、phase noise、Eb/N0、RFMeasure，并建立统计测试。
5. **LE Coded**：单独实现并以 Core 6.2 FEC/pattern mapping sample data验证；完成前明确报 `NotImplementedError`。

下一阶段具体执行边界见 `plan.md`。

---

# LE Test Packet Interval 零填充调研

日期：2026-07-21

## 1. 当前波形行为

当前 `RFTestPacket` 生成完整 LE Test Packet，`BLEModulator.modulate()` 为每个
packet bit 生成固定 SPS 数量的恒包络 IQ sample。输出长度严格等于：

```text
packet_bits * samples_per_symbol
```

当前 37-byte PRBS9 LE 1M Packet 包含：

```text
Preamble        8 bits
Access Address 32 bits
PDU Header     16 bits
Payload       296 bits
CRC            24 bits
Total         376 bits = 376 us @ LE 1M
```

96 MHz 下生成 36,096 samples，实测所有 sample 幅度约为 1，零 sample 数量为 0。
因此当前文件是单个 Packet，不包含 Direct Test Mode packet interval。

## 2. Core 6.2 规则

Core 6.2 Vol 6 Part F 4.1.6 定义 LE Test Packet interval：

```text
I(L) = ceil((L + 249 us) / 625 us) * 625 us
```

其中 `L` 是 LE Test Packet 的发送时长。

对于当前 `L = 376 us`：

```text
I(L) = 625 us
target samples = 625 us * 96 MHz = 60,000
zero padding = 60,000 - 36,096 = 23,904 samples
```

若 Verilog 按 memory 首尾循环播放，60,000 行文件将形成规范的 625 us Packet
起始间隔。空闲阶段使用复数 `0+0j`，12-bit I/Q packed MEM 表示为 `000000`。

## 3. 配置边界

建议新增：

```yaml
tx:
  packet_interval:
    enabled: true
```

行为规则：

- 默认 `false`，保持现有单 Packet 输出兼容。
- 仅允许 `rf_test` 和 `dtm` mode 使用。
- 在调制后、进入 channel 前追加复数零。
- `iq_tx` 保存 TX 关闭区间的零；非 bypass channel 的 `iq_rx` 可在间隔中包含噪声。
- RF modulation metrics 只分析原始 Packet 区间，不能把补零区计入功率和频偏统计。
- 不重复复制多个 Packet；一个 MEM 周期包含一个 Packet 和一个补零间隔，交给 Verilog 循环地址播放。

## 4. TDD 验证点

1. `376 us @ 96 MHz` 得到 60,000 samples，其中后 23,904 点严格为零。
2. 原始 36,096 samples 前缀逐点不变。
3. `L + 249 us` 跨过 625 us 边界时正确扩展到下一个 625 us 整数倍。
4. 配置关闭时保持 36,096 samples。
5. Advertising mode 开启该配置时明确报错。
6. 生成的 `iq_tx.mem` 为 60,000 行，末尾为 `000000`。
7. RX 仍能完成 sync、CRC 和 payload match。

---

# Python BLE 波形 JSON Sidecar 调研

日期：2026-07-22

## 1. 目标与格式选择

后续 BLE 波形由 Python BLEStudio 生成，`reference/Matlab/gen_ble_data.m` 只作为
golden reference。每个 Python 波形需要携带可长期追溯的描述，解决 TXT/MEM 文件
脱离生成环境后无法确认 PHY、packet、采样率、量化格式和信道条件的问题。

选择与 MATLAB reference 一致的描述性文件名和 JSON sidecar：

- generated packet 统一使用
  `<PHY>_<sample-rate>Msps_<payload>_<length>B_<TX|RX>` basename。例如当前目标为
  `LE1M_96Msps_PRBS9_37B_TX.mem`，其 sidecar 为
  `LE1M_96Msps_PRBS9_37B_TX.json`。
- 同一波形的 TXT/MAT/MEM/JSON 必须共用同一个 basename，不能再使用信息不足的
  `iq_tx.*` / `iq_rx.*`。
- basename 中的采样率取该文件实际 waveform sample rate，而不是未经验证的 YAML
  原始值；整数 MHz 写成 `96Msps`，非整数 MHz 使用去除尾零后的十进制表示。
- 外部 IQ 使用 `<input-stem>_<sample-rate>Msps_RX`，不把 receiver expectation 中的
  PRBS/PHY 配置伪装成输入文件的已知真实内容。
- UTF-8、`indent=2`、文件末尾换行，保证人工可读。
- 使用版本化 schema，便于后续增加 channel/performance 字段。
- 只记录 metadata、关键协议十六进制数据和文件摘要，不嵌入全量 IQ samples。
- 不引入新的第三方依赖。

## 2. 当前 Python 生成与导出链路

当前主流程位于 `examples/demo.py`：

1. `SimConfig.from_dict()` 读取 YAML。
2. `RFTestPacket` 或 advertising packet 生成 packet bits。
3. `BLEModulator` 生成 clean TX IQ。
4. 可选导入外部 IQ 作为 channel input。
5. `BLEChannel` 生成 RX IQ，或在理想条件下 bypass。
6. `export_iq()` 写出 TXT、MAT 和 Verilog MEM。

当前 TXT/MEM 由 `ble_studio/iq_io.py::IQExporter` 写出；MAT 只包含 `iq/I/Q/fs`。
整个波形导出链路没有 JSON metadata。逻辑分析仪模块已有独立的 pretty JSON summary，
可以复用它的 UTF-8、缩进和末尾换行规则，但 capture schema 与 generated waveform
语义不同，不能直接混用。

## 3. Sidecar 必须记录的事实

### 3.1 生成器与来源

- schema 名称和版本、BLEStudio 版本、UTC 生成时间。
- `output_kind`：`clean_tx` 或 `channel_output`。
- `source_kind`：`generated_packet`、`generated_tx` 或 `imported_iq`。
- 外部 IQ 输入时记录输入文件名、SHA-256、有效采样率和频移；不能把当前 YAML 中
  配置的 PRBS packet 误写成外部 IQ 的真实内容。

### 3.2 BLE packet 与 modulation

- mode、PHY、channel、frequency、Access Address、CRC init、whitening。
- payload type/length/hex、PDU hex、CRC 和完整 packet 长度。
- sample rate、symbol rate、samples per symbol、sample count、duration。
- modulation index、BT、active samples、padding samples。

字段名称应与 MATLAB golden JSON 中的 `phy_mode`、`payload_hex`、`pdu_hex`、
`pdu_with_crc_hex` 等核心字段可直接对应；Python schema 可以按 `signal/packet/channel`
分组，避免继续扩展扁平的一层结构。

### 3.3 Channel 与量化

- TX metadata 不伪造 channel 结果；RX 记录 channel type、bypass、Eb/N0、frequency
  offset、Doppler 和 Rician K-factor。
- `Eb/N0=.inf` 不能序列化成非标准 JSON `Infinity`；用 `bypass=true`、
  `ebn0_db=null` 表示。
- TXT/MEM 记录 bit width、实际 scale factor、rounding policy、clip 范围、I/Q
  saturation count，以及 MEM 的 `I high / Q low` packed layout。
- 记录实际成功生成的 TXT/MAT/MEM 文件名、byte size 和 SHA-256；JSON 不记录自身
  hash，避免递归依赖。

## 4. 调研发现的现有可信度问题

这些问题会直接导致 sidecar 描述错误或与 MATLAB golden 不一致，因此应在同一改动中
以回归测试修正：

1. `examples/demo.py` 当前给 `iq_tx` 传入 channel input 的局部 `sample_rate`。导入
   外部 IQ 且采样率不同后，clean TX 的 MAT/metadata 会错误记录外部采样率；TX 必须
   始终使用 `cfg.sample_rate`，RX 使用 channel 的有效采样率。
2. `IQExporter.quantize()` 使用 `np.round`。NumPy 在恰好半 LSB 时采用 ties-to-even，
   MATLAB `round` 采用 ties-away-from-zero；当前注释“与 MATLAB 一致”不成立。Python
   导出需要显式实现正负一致的 ties-away-from-zero，同时保持 `quantize()` 的公共
   返回签名不变。
3. `scale_to_full=true` 时 scale factor 由实际波形峰值动态决定，但 TXT header 固定写
   `Q{bit_width-frac_bits}.{frac_bits}`。当 `frac_bits=0` 时该标签不能准确描述实际
   归一化映射；metadata 和 header 应报告实际 scale factor，而不是给出误导性 Q 格式。
4. MAT 导出缺少 `scipy` 时当前代码静默跳过。sidecar 只能列出实际成功写出的文件，
   请求的格式无法生成时应给出可操作错误，不能生成一份声称文件存在的 metadata。
5. 当前 channel 使用全局随机源且没有 seed。sidecar 可用输出文件 hash 标识本次带噪
   波形，并将 `random_seed` 记为 `null`；可复现 RNG 改造不属于本任务。

## 5. 范围边界

- JSON 在 `io.output.enabled=true` 时随每个实际导出的 TX/RX 波形自动生成，不增加一个
  容易被忘记开启的 metadata 开关。
- `export_tx=false` 时不生成任何 `_TX.*`；RX 仍生成对应的 `_RX.*` 和 JSON。
- 当前 Python 主流程尚未实现 `packet_interval` 配置。metadata 只根据实际数组记录
  active/padding 状态，本任务不借 JSON 功能顺带实现 interval padding。
- 不修改 MATLAB generator；MATLAB 文件只用于 golden regression。
- 不修改 channel 随机数接口，不在本任务接入 performance sweep。
