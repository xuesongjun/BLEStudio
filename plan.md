# LE Test Packet Interval 零填充计划

状态：待实现（截至 2026-09-28）

当前 Python 主流程尚未实现 `packet_interval` 配置；已提交内容仅包含 MATLAB
interval golden vector，以及 metadata 对实际 `padding_samples` 的记录。本计划保留为
后续 TDD 实现依据。

确认口令：`GO`

日期：2026-07-21

## 1. 目标

新增可配置的 LE Test Packet interval 功能，使 RF Test/DTM IQ waveform 和
Verilog MEM 可以按 Core 6.2 `I(L)` 周期循环播放。

配置形式：

```yaml
tx:
  packet_interval:
    enabled: true
```

默认关闭，现有配置和单 Packet 输出不变。

## 2. 实现方案

### 2.1 Interval 计算与补零

修改 `ble_studio/modulator.py`：

- 定义 625 us interval quantum 和 249 us guard 常量，禁止散落幻数。
- 新增纯函数计算 `I(L)` 和目标 sample 数。
- 新增纯函数在 IQ 尾部追加 `complex zero`。
- 返回 packet samples、padding samples、interval samples 和 interval duration metadata。
- 校验输入为一维 complex waveform、采样率为正数，目标长度必须是整数 sample。

计算规则：

```text
I(L) = ceil((L + 249 us) / 625 us) * 625 us
```

### 2.2 Demo 配置

修改 `examples/demo.py`：

- `SimConfig` 末尾新增 `packet_interval_enabled: bool = False`，保持旧位置参数顺序。
- 从 `tx.packet_interval.enabled` 读取开关。
- 仅在 `rf_test/dtm` 下允许开启；Advertising 明确报错。
- 在 TX 调制后、Channel 前补零。
- console 输出 Packet duration、interval、padding sample 数。
- RFMeasure 继续只消费未补零的 Packet 区间。
- RX 和 IQ exporter 消费完整 interval waveform。

### 2.3 96 MHz 配置

修改 `examples/config_rftest_1m_prbs9_96m.yaml`：

```yaml
tx:
  packet_interval:
    enabled: true
```

重新生成后：

- `iq_tx.mem`：60,000 行。
- 前 36,096 行：LE 1M PRBS9 Packet。
- 后 23,904 行：`000000`。
- 周期：625 us。

### 2.4 文档

修改 `README.md`，说明：

- 单 Packet 与 Direct Test Mode interval waveform 的区别。
- 配置开关、`I(L)` 公式和 96 MHz 示例。
- MEM 循环播放方式及 I/Q packed layout。

## 3. TDD 测试

先新增 `tests/core/test_packet_interval.py`：

1. 96 MHz、376 us 输入得到 60,000 samples。
2. padding 为 23,904 个 `0+0j`。
3. 原 Packet prefix 完全不变。
4. 关闭开关时不改变输出。
5. 625 us 边界前后使用正确 ceiling 行为。
6. Advertising mode 拒绝 interval 配置。
7. Demo 理想 RX 保持 sync、CRC、payload match。
8. 生成 MEM 为 60,000 行且最后一行为 `000000`。

随后运行：

```powershell
python -m pytest tests/core/test_packet_interval.py -q
python -m pytest tests/core -q
python -m pytest tests/logic_analyzer -q
python -m pytest -q
python examples/demo.py examples/config_rftest_1m_prbs9_96m.yaml
```

## 4. 影响评估

- 默认关闭，不改变现有 API 和 waveform 长度。
- 新增字段位于 `SimConfig` 末尾，不破坏旧位置参数。
- 开启后 `iq_tx/iq_rx` 和 HTML 的 sample 数增加到完整 interval。
- Bypass 时 TX/RX padding 均为零；AWGN 下 RX padding 区可包含噪声。
- RF metrics 排除 padding，避免平均功率和频偏被零区污染。
- 不引入新依赖，不修改 Packet bits、GFSK 调制或 Demodulator 算法。

## 5. 预计文件

修改：

- `ble_studio/modulator.py`
- `examples/demo.py`
- `examples/config_rftest_1m_prbs9_96m.yaml`
- `README.md`
- `plan.md`

新增：

- `tests/core/test_packet_interval.py`

## 6. 确认

- 回复 `GO`：按本计划进入 Red -> Green -> full regression。
- 提出修改意见：修订计划后重新等待确认。
- 否决：停止，等待新指令。

---

# 已完成：BLE Studio Core Correctness 修复计划

状态：已按 `GO` 执行完成（2026-07-21）

确认口令：`GO`

日期：2026-07-21

## 1. 本阶段目标

本阶段先修复 BLE Studio 中可由 Core 6.2 向量和理想闭环确定验证的问题，建立后续 RX、信道和 RF 指标优化的可信基线：

1. 修复 LE 1M/2M 前导码、whitening、CRCInit 和 Data Channel PDU 生成。
2. 修复 `CONNECT_IND` payload 丢失。
3. 让 README 已公开的 BER/PER API 恢复可运行。
4. 修复 Demo 中 `access_address`、DTM whitening 和非法 mode 的参数传递。
5. 对整数 SPS 和尚未实现的 LE Coded PHY 做明确校验，禁止静默生成错误波形。
6. 修复 Channel type 与实际 impairment chain 的确定性不一致。
7. 新增 Core/PHY 自动测试，继续保证逻辑分析仪 32 个测试不回归。

## 2. 本阶段明确不做

- 不修改逻辑分析仪的 extraction 算法和已建立的输出契约。
- 不为了让真实 DDR capture 立即同步而调整 Demodulator 判决阈值或相关策略。
- 不在本阶段实现 LE Coded FEC、pattern mapper、CI、TERM1/TERM2。
- 不重新设计 Rician/Rayleigh 的统计模型，不校准 RFMeasure 合规门限。
- 不重构 Visualizer、ReportGenerator 或 IQ IO。
- 不删除历史文件或用户当前未提交改动。

真实 capture RX、信道模型精度和 LE Coded 将在本阶段测试基线通过后分别规划。

## 3. 改动方案

### 3.1 Packet 规范处理

修改 `ble_studio/packet.py`：

- 增加内部 preamble helper，根据 Access Address LSB 和 LE 1M/2M 选择传输序列。
- `BLEPacket` 和 `RFTestPacket` 共享同一选择规则。
- 按 Core 6.2 的 LFSR 方向修正 whitening，并让 TX/RX 共享同一个内部实现。
- `generate()` 使用 `config.crc_init` 调用现有 CRC 算法。
- `create_data_packet()` 生成时保留调用方传入的完整 Data PDU，不再重建错误 header。
- `create_connect_ind()` 返回 `InitA + AdvA + LLData` 的 34-byte payload。
- 增加 channel、payload length、address length、CRCInit 范围等必要输入校验。

不改变现有便捷函数名称和位置参数顺序。

### 3.2 Demodulator 契约

修改 `ble_studio/demodulator.py`：

- 在 `DemodulatorConfig` 添加 `crc_init: int = 0x555555`，属于向后兼容的可选字段。
- CRC 检查使用配置值，不再硬编码 Advertising init。
- 去白化调用与 Packet 相同的内部序列实现。
- 校验 sample rate 必须产生正整数 SPS。
- 对 `LE_CODED_S2/S8` 明确抛出 `NotImplementedError`，避免伪装成 LE 1M 成功。
- 保留当前 LE 1M/2M 解调算法、同步阈值和 frequency/timing recovery 行为。

### 3.3 Modulator 参数校验

修改 `ble_studio/modulator.py`：

- 校验 sample rate、symbol rate、BT、modulation index 和 pulse length 的基本范围。
- sample rate 不能通过 `int()` 静默截断为错误 SPS。
- 对 LE Coded 明确报未实现。
- 不改变当前 LE 1M/2M GFSK phase pulse 算法，先由 characterization tests 固定。

### 3.4 Performance 恢复

修改 `ble_studio/performance.py`：

- 删除对不存在的 `BLEModulator.add_noise/add_frequency_offset/add_timing_offset` 的调用。
- 使用现有 `BLEChannel(ChannelConfig(...))` 统一施加 AWGN、频偏和定时偏移。
- 根据 PHY 传递正确 `symbol_rate`。
- 保留 `quick_ber_test()`、`quick_snr_sweep()` 和现有返回 dataclass。
- 修正 BER 长度差的统计，避免截断后漏算错误。
- 使用现有 seed 语义建立可重复测试，不在本阶段改公共随机数 API。

### 3.5 Demo 参数一致性

修改 `examples/demo.py`：

- 把自定义 DTM `access_address` 真正传入 `create_test_packet()`。
- `rf_test` 和 `dtm` 使用同一 whitening 规则。
- Advertising 固定使用规范 AA；冲突配置给出可操作错误。
- 只接受当前实现的 `rf_test`、`dtm`、`advertising` mode。
- 将 `crc_init` 传入 RX 配置；配置未提供时保持现有默认值。

### 3.6 Channel 确定性修复

修改 `ble_studio/channel.py`：

- 将 `ChannelType.FLAT_FADING` 正确映射到 `FlatFadingChannel`。
- 默认不隐式启用 PhaseNoise；只有用户显式配置时才加入。
- 在 `ChannelConfig` 增加向后兼容的 indoor environment 字段，并让 factory 参数实际生效。
- 校验 path delay/gain 长度、sample/symbol rate、K factor 等基本参数。
- 不改变现有 fading 数学实现，本阶段只修复构建链和参数契约。

## 4. 测试计划

新增 `tests/core/`：

### 4.1 规范向量

- Core 6.2 channel 0/1 whitening 前 64 bits。
- Core 6.2 Data Channel PDU 的 `CRCInit=0xC4C181` CRC bits。
- Core 6.2 PRBS9 起始序列 `11111111100000111101...`。
- DTM PDU header 和 payload pattern。

### 4.2 Packet 测试

- AA LSB 0/1 下 LE 1M 和 LE 2M preamble。
- Advertising、DTM、Data PDU 的 exact bitstream 字段。
- Data Channel custom CRCInit。
- CONNECT_IND payload 字段和长度。
- 非法 channel、payload/address length、CRCInit。

### 4.3 TX/RX 集成测试

- DTM LE 1M/2M 理想 loopback。
- Advertising LE 1M 理想 loopback，覆盖 AA LSB=0。
- Data Channel custom CRCInit + whitening loopback。
- `data/iq/BLE_1M.bwv` MATLAB reference 解调回归。
- Coded PHY 明确报未实现。
- 非整数和过低 sample rate 明确报错。

### 4.4 Performance/Channel

- `quick_ber_test()` 在高 Eb/N0 下可完成且结果结构正确。
- 固定 seed 可重复。
- FrequencyOffset/TimingOffset 实际进入 chain。
- FLAT_FADING 映射正确。
- 默认 Channel 不含未请求的 PhaseNoise。
- indoor environment 参数生效。

## 5. 文档更新

修改 `README.md` 和必要示例注释：

- 删除不存在的 `modulator.add_*` 调用，改为 `BLEChannel`。
- 明确当前正式支持 LE 1M/2M；LE Coded 为未实现能力。
- 修正 Data Channel、BER/PER 和 channel scan 的描述。
- 标明 `snr_db` 当前字段语义实际为 Eb/N0，保留兼容名称。

## 6. 公共接口和兼容性影响

- `DemodulatorConfig` 新增可选 `crc_init`，现有调用无需修改。
- `ChannelConfig` 新增可选 indoor environment/phase-noise 显式配置，现有常规调用保持可构造。
- 正确 whitening 会改变普通 Advertising/Data Packet 的 on-air bits；这是规范修复，旧错误结果不兼容。
- AA LSB=0 的前导码会从错误的 `1010...` 改为规范要求的 `0101...`。
- 非整数 SPS 和 LE Coded 从“静默生成错误结果”改为明确异常。
- Data Channel 与 CONNECT_IND 输出会从错误内容改为规范内容。

不修改现有函数名称，不移除现有导出符号，不引入新依赖。

## 7. 预计改动文件

修改：

- `ble_studio/packet.py`
- `ble_studio/modulator.py`
- `ble_studio/demodulator.py`
- `ble_studio/channel.py`
- `ble_studio/performance.py`
- `examples/demo.py`
- `README.md`

新增：

- `tests/core/__init__.py`
- `tests/core/test_packet_vectors.py`
- `tests/core/test_packet_builders.py`
- `tests/core/test_loopback.py`
- `tests/core/test_channel.py`
- `tests/core/test_performance.py`

不修改用户已有的 `examples/config_rftest_prbs9.yaml` 工作树改动，除非执行时确认某个计划内测试必须调整该文件；如发生则停止请示。

## 8. 验证命令

```powershell
python -m pytest tests/core -q
python -m pytest tests/logic_analyzer -q
python -m pytest -q
python examples/benchmark.py --quick --phy 1M
python examples/benchmark.py --quick --phy 2M
python examples/demo.py examples/config_ideal.yaml
python examples/demo.py examples/config_rftest_prbs9.yaml
```

示例产生的报告仅写入已忽略的 `results/`，不覆盖迁移后的 capture 或 fixture。

## 9. 后续阶段

本计划完成后再分别编写计划：

1. 真实逻分 IQ 的 RX robustness 与 burst/sync 诊断。
2. Channel/RFMeasure 的统计模型和 RFPHY 合规校准。
3. LE Coded S=2/S=8 完整实现。

## 10. 确认

- 回复 `GO`：按本计划开始编码和测试。
- 提出修改意见：修订本计划后重新等待确认。
- 否决：停止，等待新指令。

执行结果：

- Core/PHY、Channel、Performance 与 Demo 新增 41 个测试。
- 逻辑分析仪原有 32 个测试保持通过。
- 全仓 `pytest`：73 passed。
- Advertising 与 DTM 示例均达到 sync、CRC 和 payload match 成功。
- LE 1M/2M quick benchmark 均完成。

---

# 已完成：逻辑分析仪子系统整理计划

状态：已按 `GO` 执行完成（2026-07-20）

确认口令：`GO`

## 1. 目标

本次改动完成以下目标：

1. 将逻辑分析仪能力从零散 `utils` 脚本迁入可安装、可测试的正式 Python package。
2. 统一 DDR IQ、SDR 并行数据和 RSSI/control signal 的处理 pipeline。
3. 让所有输出格式消费同一次处理结果，消除 HTML、VCD、MAT、TXT 之间的数据漂移。
4. 建立明确的 Logic Analyzer -> normalized complex IQ -> BLE Studio RX 契约。
5. 把配置、硬件 Profile、输入 capture、回归 fixture 和生成 artifact 分目录管理。
6. 保留当前命令的兼容 wrapper，避免破坏现有工作流。
7. 为现有算法建立 characterization tests，后续可以安全优化采样算法。

## 2. 明确不做的内容

本阶段不修改以下模块的算法行为：

- `ble_studio/packet.py`
- `ble_studio/modulator.py`
- `ble_studio/channel.py`
- `ble_studio/demodulator.py`
- `ble_studio/measure.py`
- `ble_studio/performance.py`

本阶段不会为了让某个 capture 解调成功而修改 RX，也不处理 Advertising、Data Channel、RFPHY 合规或 Coded PHY 问题。

本阶段不删除原始 capture，不执行 Git history rewrite，不引入 Git LFS。重复和旧文件先迁移到隔离目录，后续再单独确认删除。

## 3. 目标目录

```text
ble_studio/
  logic_analyzer/
    __init__.py
    __main__.py
    config.py
    models.py
    capture.py
    processing.py
    extraction.py
    pipeline.py
    exporters.py
    vcd.py
    visualization.py
    validation.py
    cli.py

configs/
  logic_analyzer/
    adc_ddr.yaml
    rssi_raw_sdr.yaml
    rssi_resampled_sdr.yaml

doc/
  logic_analyzer/
    README.md
    extraction_rules.md
    formats.md

data/
  logic_analyzer/
    README.md
    fixtures/
    captures/          # 本地完整 capture，Git ignore
    profiles/          # Kingst kvset，可版本化
    quarantine/        # 含义未确认的数据，Git ignore
  iq/
    BLE_1M.bwv

artifacts/
  logic_analyzer/      # 所有可再生输出，Git ignore

legacy/
  logic_analyzer/      # 旧实现和一次性实验，只保留参考

tests/
  logic_analyzer/
    test_config.py
    test_capture.py
    test_processing.py
    test_extraction.py
    test_exporters.py
    test_pipeline.py
    test_validation.py
    test_cli.py
    fixtures/
```

## 4. 稳定 API 和 CLI

### 4.1 Python API

建立不依赖 CLI、绘图和文件输出的核心入口：

```python
result = process_capture(config)
```

`CaptureResult` 至少包含：

- capture 类型：`iq_ddr` 或 `parallel_sdr`
- raw channel 数据或其必要 metadata
- unsigned/signed 提取数据
- normalized complex IQ，可为空
- nominal 和 measured sample rate
- bit width、bit order、I/Q edge mapping
- raw/cleaned/sample positions
- extra control signals
- segment/burst 信息
- 实际生效配置
- warning 列表

Exporter、可视化和 RX 验证只读取 `CaptureResult`，不得重新执行采样算法。

### 4.2 CLI

新增统一入口：

```text
python -m ble_studio.logic_analyzer convert <config.yaml>
python -m ble_studio.logic_analyzer diagnose <config.yaml>
python -m ble_studio.logic_analyzer config --profile adc-ddr <output.yaml>
```

同时在 `pyproject.toml` 增加 console script，建议命名：

```text
ble-la
```

计划支持的子命令：

- `convert`：运行一次 pipeline，并按配置导出。
- `diagnose`：输出边沿、稳定度、delay、burst 和 sample rate 诊断。
- `config`：生成内置 profile 配置。

旧命令暂时保留 thin wrapper，并输出迁移提示：

- `utils/logic_analyzer_bin2wave.py`
- `utils/bin_to_vcd.py`
- `utils/rssi_parser.py`
- `utils/analyze_sampling_issues.py`

## 5. 配置设计

使用类型化 dataclass，并对以下内容做显式校验：

- 输入存在且字节长度符合 Kingst 16-channel 格式。
- `mode/profile` 合法。
- channel 范围为 0-15。
- `data_bits` 不重复，长度与 `bit_width` 一致。
- DDR 必须提供 clock/data indicator channel 和 I/Q edge mapping。
- sample rate、data rate、输出格式均为有效值。
- `extra_signals` 不与 data/clock channel 非预期冲突。

配置相对路径默认相对于 YAML 所在目录解析。为了兼容旧配置，如果新规则找不到文件，再尝试旧的 CWD 规则并输出 deprecation warning。

保留旧字段的 adapter：

- `sample_rate`
- `data_rate`
- `mode`
- `data_bits`
- `clk_channel` / `data_indicator`
- `rising_edge_data`
- `falling_edge_data`
- `save_formats`

三个正式 profile：

1. `adc_ddr.yaml`：10-bit DDR I/Q。
2. `rssi_raw_sdr.yaml`：8-bit RSSI 加 `agc_init/rampup/fire_timer`，每个 LA sample 一个 word。
3. `rssi_resampled_sdr.yaml`：按目标 word rate 生成虚拟边沿并恢复并行数据。

每个 profile 使用独立 artifact 目录，禁止再次共用 `rssi_wave` 前缀。

## 6. Pipeline 行为

### 6.1 BIN decode

- 只保留一份 Kingst 16-channel decoder。
- 使用明确的 little-endian channel mapping。
- 对空文件、奇数字节、非法 channel 和截断输入给出可操作错误。
- `data_bits` 顺序继续定义输出 bit significance，但配置和 summary 中必须明确记录。

### 6.2 Filtering 和 extraction

- 先用 characterization tests 固定当前工作树行为。
- 将 input glitch filter、adaptive filter 和 output spike filter 拆为三个独立开关。
- DDR、SDR 共享 decoder 和 result model，但使用独立 extraction strategy。
- 保留每个 sample 的 source edge、各 bit sample position 和 segment 信息。
- `提取规则.md` 的九种场景全部转为参数化测试。
- 文档只描述实际实现；不再保留与代码不一致的“上下文智能采样”说明。

### 6.3 Sample rate

- DDR 默认使用配置定义的 nominal IQ rate，例如 `data_rate / 2`。
- measured rate 作为独立 metadata，不再使用量化后的 interval median 静默覆盖 nominal rate。
- measured rate 使用排除 gap 后的 mean 或线性拟合，并记录估算方法。
- RX 验证阶段可选重采样到整数 samples-per-symbol，原始提取数据不被覆盖。

## 7. 统一输出契约

### 7.1 MAT 作为 RX canonical format

DDR IQ MAT 至少包含：

```text
iq
I_unsigned
Q_unsigned
I_signed
Q_signed
fs
fs_nominal
fs_measured
bit_width
sample_positions
metadata
```

其中：

```python
iq = (I_signed + 1j * Q_signed) / 2**(bit_width - 1)
```

BLE Studio 可以直接通过 `mat_complex_var: iq` 导入，不再要求用户手动选择 signed 变量。

### 7.2 TXT

- 默认 RX-compatible TXT 使用 `//` header 和两列 signed decimal：`I Q`。
- 如需 hex 和采样位置，另行生成 debug CSV/TXT，不复用 canonical 文件名。
- metadata 写入同目录的 `summary.json`，不依赖解析 header 恢复 Fs。

### 7.3 NPY/MEM

- NPY 明确文件语义和 dtype，不再用同一后缀表达多个结构。
- MEM 保留高位 I、低位 Q 布局，并在 summary 中记录 bit width 和 Fs。
- 所有跨格式内容必须来自同一个 `CaptureResult`。

### 7.4 HTML/VCD

- HTML 默认最多绘制固定数量的采样点，完整数据仍保存在 MAT/NPY。
- 抽样策略和原始长度写入 summary。
- VCD 成为正式 exporter，不再单独复跑 pipeline。
- VCD 支持 DDR、SDR 和 `extra_signals`，时间戳必须单调。
- VCD 和 HTML 均为显式可选格式，禁止生成一个格式时隐式生成另一个。

## 8. BLE RX 验证

配置增加可选 `ble_rx` 部分：

```yaml
ble_rx:
  enabled: true
  phy_mode: LE_1M
  access_address: 0x71764129
  channel: 0
  whitening: false
  target_samples_per_symbol: 16
```

处理规则：

1. 只接受 `CaptureResult.iq` 非空的 DDR IQ 结果。
2. 使用 normalized complex IQ。
3. 必要时通过现有 SciPy 重采样到整数 SPS。
4. 调用现有 `BLEDemodulator`，不修改其内部算法。
5. 将 `success/sync_found/crc_valid/access_address/freq_offset/timing_offset` 写入 console 和 `summary.json`。
6. 解调失败仍是一次成功完成的分析任务，CLI 返回结构化结果；只有输入、配置或 pipeline 错误才返回非零退出码。

## 9. 文件迁移

### 9.1 代码

- 从当前 `utils/logic_analyzer_bin2wave.py` 提取正式 package。
- `utils/bin_to_vcd.py` 的 VCD 逻辑迁入 `exporters/vcd`。
- `utils/rssi_parser.py` 的 extra signal 提取迁入 SDR pipeline。
- `utils/analyze_sampling_issues.py` 的有效诊断迁入 `diagnose`。
- `utils/logic_analyzer_to_iq.py`、`search_best_sample.py`、`my_test.py` 移入 `legacy/logic_analyzer/`，不再作为文档入口。
- 原入口改为 thin wrapper，兼容期内不删除。

### 9.2 配置和文档

- 现有逻分 YAML 迁入 `configs/logic_analyzer/`。
- `doc/logic_analyzer_data_processing.md`、`提取规则.md` 和 prompt 内容合并到 `doc/logic_analyzer/`。
- README 更新新的目录、CLI、数据流和旧命令兼容说明。
- `examples/config_import_hex.yaml` 更新为 canonical MAT `iq` 示例，不再引用旧 unsigned/signed 特例。

### 9.3 数据

迁移前生成 manifest，记录 path、size、SHA256 和 tracked 状态。

- `test.bin`、`rssi.bin` -> `data/logic_analyzer/captures/`，完整文件本地保留并 Git ignore。
- 从当前 capture 截取 2-32 KiB 的真实 DDR/SDR fixture，提交到 `tests/logic_analyzer/fixtures/`。
- `test3.bin` -> `data/logic_analyzer/quarantine/`，不删除。
- `*.kvset` -> `data/logic_analyzer/profiles/`。
- `*.kvdat` -> `data/logic_analyzer/captures/`；重复项只标记，本阶段不删除。
- `test_iq*`、`test_debug*`、`rssi_wave*` -> `artifacts/logic_analyzer/legacy/`，本地保留并 Git ignore。
- `BLE_1M.bwv` -> `data/iq/`。

不恢复当前已经被用户删除的文件，也不清理 Git 历史中的旧大对象。

## 10. 测试计划

### 10.1 Characterization tests

- 当前 DDR fixture 的 I/Q 长度、前若干 sample、delay 和 sample positions。
- 当前 SDR fixture 的 word 和 extra signals。
- 当前 working tree 的 spike filter 行为。
- 九种采样规则的参数化结果。

### 10.2 Unit tests

- 16-channel BIN mapping：ch0、ch7、ch8、ch15。
- 空文件、奇数字节、非法 channel 和 bit width。
- legacy/new config path resolution。
- DDR I/Q edge mapping、I/Q swap、边沿数量不等。
- SDR 整数和非整数 samples-per-word。
- two's-complement 边界。
- 三种 filter 开关互不影响。
- sample rate nominal/measured 计算。

### 10.3 Export tests

- MAT `iq` 能被 `import_iq_mat()` 直接读回。
- TXT 能被 `import_iq_txt()` 直接读回。
- MAT/TXT/MEM/NPY 的 I/Q 数值一致。
- VCD 时间戳单调且包含配置声明的信号。
- HTML 抽样点数不超过限制。
- 输出只包含配置请求的格式。

### 10.4 Integration tests

- 从仓库外 CWD 调用 CLI。
- `python -m ble_studio.logic_analyzer --help`。
- 旧 wrapper 命令仍可运行。
- DDR capture -> canonical MAT -> IQImporter。
- ideal IQ -> RX validation 的接口测试。
- 真实 capture 的 RX 结果作为诊断输出记录，不强制要求 CRC 成功。

### 10.5 验证命令

计划执行：

```powershell
python -m pytest tests/logic_analyzer -q
python -m ble_studio.logic_analyzer --help
python -m ble_studio.logic_analyzer convert configs/logic_analyzer/adc_ddr.yaml --no-plot
python -m ble_studio.logic_analyzer convert configs/logic_analyzer/rssi_raw_sdr.yaml --no-plot
```

完整 20 MiB RSSI capture 和大 HTML/VCD 仅做本地 slow verification，不进入常规测试。

## 11. 依赖和公共接口影响

### 11.1 新依赖声明

`PyYAML` 已是现有代码的实际必需依赖，但项目没有声明。执行阶段计划将其变为显式依赖。根据项目规范，这是新增外部依赖声明，需要用户在 `GO` 中一并批准；安装时会使用核对过 Python 3.8 支持范围的确定版本。

不计划引入其他第三方依赖。重采样继续使用现有 SciPy。

### 11.2 公共接口

- 新增 `ble_studio.logic_analyzer` API 和 `ble-la` CLI。
- 不修改现有 BLE core 公共函数签名。
- 旧 `utils` 命令暂时保留 wrapper。
- canonical TXT/MAT 是新输出契约；legacy exporter 仅在明确配置时保留旧格式。

## 12. 风险和停止条件

执行时遇到以下情况将立即停止并请示，不继续猜测：

- 当前未提交 SDR/RSSI 行为无法通过 characterization tests 固定。
- 某个待迁移文件的来源或用途无法通过代码、配置、hash 和 metadata 确认。
- 数据移动目标可能覆盖同名文件。
- 真实 fixture 可能包含不适合提交仓库的数据。
- 修正 sample rate 后会改变用户认可的既有解调结果。
- RX 验证需要修改 Demodulator 才能继续。

## 13. 预计改动文件

新增：

- `ble_studio/logic_analyzer/**`
- `configs/logic_analyzer/**`
- `doc/logic_analyzer/**`
- `data/logic_analyzer/README.md`
- `tests/logic_analyzer/**`
- `artifacts/logic_analyzer/.gitkeep`
- `legacy/logic_analyzer/README.md`
- 首次提交时的 `process.txt`

修改：

- `pyproject.toml`
- `.gitignore`
- `README.md`
- `examples/config_import_hex.yaml`
- `utils/logic_analyzer_bin2wave.py`
- `utils/bin_to_vcd.py`
- `utils/rssi_parser.py`
- `utils/analyze_sampling_issues.py`

移动或归档：

- 现有逻辑分析仪 YAML、Markdown、legacy scripts、Kingst Profile、capture 和生成产物。

## 14. 确认

请审阅本计划。

- 回复 `GO`：按本计划进入执行阶段。
- 提出修改意见：修订 `plan.md` 后重新等待确认。
- 否决：停止本任务，等待新指令。

---

# gen_ble_data.m 审核与修正计划

状态：已按 `GO` 执行；MATLAB runtime 回归待用户环境完成

确认口令：`GO`

日期：2026-07-22

## 1. 已确认的产品决策

1. 默认 PRBS9 以 Bluetooth Core DTM transmission-order vector 为准，不保留 MATLAB legacy 兼容模式。
2. `isResample` 只生成模拟 ADC 输出文件；重采样后的非整数 SPS 数据不送入当前 `bleIdealReceiver`。
3. `useAWGN` 开启时生成并导出带噪 IQ 文件，同时保留 clean TX reference。
4. MAT/TXT 固定输出到 `reference/BLE_PKT`，每组文件必须描述同一采样率、长度和配置，并写入 metadata。

## 2. 修正范围

### 2.1 BLE packet source

修改 `reference/Matlab/gen_ble_data.m`：

- 修正 PRBS9/PRBS15 的 MATLAB polynomial 表达和 BLE transmission-order 校验。
- 用 Core DTM golden prefix/full payload 检查 PRBS，不仅检查 polynomial 名称。
- 显式定义 `headerValue`、`payloadLenBytes`、`headerBits`、`lengthBits`，避免变量复用。
- 对 `rate`、`Fs`、channel、header、payload length、AA 和 amplitude 做范围校验；非法值明确报错。
- 所有 DTM pattern 显式标注 byte order 与 on-air LSB-first order。
- 保持 `AccessAddress=0x71764129`、CRC polynomial/init、`WhitenStatus='Off'` 和 `PulseLength=1` 的已确认行为。

### 2.2 Output and metadata

- 使用脚本目录解析 `reference/BLE_PKT`，必要时创建目录，不依赖当前 CWD 或 Windows 分隔符。
- 明确区分 clean TX、resampled ADC 和 AWGN 输出，禁止同名覆盖。
- MAT 保存 `LEWaveform`、`Fs`、实际输出采样率、PHY、channel、AA、CRC init、PDU/bits、padding 和 quantization metadata。
- TXT/MEM 使用实际输出采样率命名，并保证 MAT/TXT 来自同一 waveform。
- 检查 `fopen/save` 错误并保证文件句柄清理。

### 2.3 Packet interval padding

- 保留 Core 6.2 `I(L)=ceil((L+249 us)/625 us)*625 us`。
- 使用整数 sample 目标长度和显式边界检查；`I(L)` 命名为 packet interval，不与 BLE `T_IFS` 混淆。
- padding 在 clean/resampled/AWGN pipeline 中的顺序和输出语义写入注释与 metadata。

### 2.4 Resample / simulated ADC

- 计算并保存 `FsOut = Fs*P/Q`、`P`、`Q` 和 ADC clock 来源。
- resampled 输出只用于 ADC 文件和离线分析，不调用当前要求整数 SPS 的 ideal RX。
- 更新 scope 和文件命名使用 `FsOut`；修正过期的采样率注释。
- 明确 padding 是在 resample 前还是后执行，并用目标 sample 数验证最终 interval。

### 2.5 AWGN

- 将 SNR/EbN0、noise floor、NF、带宽和 signal power 统一到一个可解释配置。
- 修正噪声底单位和显示值，删除未使用变量。
- 固定 RNG seed 以支持回归测试。
- 导出 clean TX 和 noisy IQ，分别写 metadata；不把 idle zero 区误计入 active packet SNR。
- RX 验证传入对应 `NoiseVariance`，并检查 access address、bit length、BER/bit error count。

### 2.6 MATLAB helper

修改 `reference/Matlab/mydec2comphex.m` 和 `quantize_nm.m`：

- 固定 two's-complement hex 宽度并校验 finite/integer/range。
- 明确 I/Q rounding policy；real 和 imaginary component 统一使用 MATLAB `round`。
- 为半 LSB rounding 行为加入注释和 golden test，避免 MATLAB/NumPy 边界差异。

## 3. TDD / golden vectors

新增 MATLAB reference regression 测试或等价可执行检查：

1. Core PRBS9 完整 payload 和前缀。
2. DTM header、length、Access Address、CRC 和 whitening-off bitstream。
3. 8/96 Msps clean waveform 长度、MAT/TXT 一致性。
4. resampled ADC 输出的 `FsOut/P/Q` metadata 和文件长度。
5. packet interval padding 的 target samples 和 zero 区。
6. AWGN 输出与 clean 输出可区分、seed 可重复、active 区域 SNR 可复现。
7. 12-bit fixed-width hex/MEM 逐行比较。

## 4. 预期改动文件

修改：

- `reference/Matlab/gen_ble_data.m`
- `reference/Matlab/quantize_nm.m`
- `reference/Matlab/mydec2comphex.m`
- `plan.md`

新增或更新：

- `reference/BLE_PKT` 下的 clean/resampled/AWGN reference vectors
- MATLAB vector regression testcase（路径待根据 MATLAB CI/本地运行方式确认）

## 5. 暂不执行的事项

- 不修改 BLEStudio Python 默认 PRBS9 实现。
- 不增加 MATLAB legacy PRBS 模式。
- 不把非整数 SPS 的 resampled waveform 强行接入当前 ideal RX。
- 不在没有用户确认 ADC clock 公式来源前重写硬件时钟计算。

## 6. 确认

- 回复 `GO`：按本计划进入 Red -> Green -> full regression。
- 提出修改意见：修订本计划后重新等待确认。
- 否决：停止，等待新指令。

## 7. 执行结果

- 已重写 `gen_ble_data.m` 的 DTM payload、CRC、packet interval、ADC resample、AWGN、metadata 和输出路径逻辑。
- 已增加 `validate_ble_vectors.m`，独立校验 PRBS9/PRBS15、DTM header、Access Address、CRC、MAT/TXT 和 metadata。
- 已收紧 `quantize_nm.m`、`mydec2comphex.m` 的输入/范围检查；通用 helper 不使用 BLE 专属 message ID。
- 用户确认删除旧 reference 后，已清空 `reference/BLE_PKT` 中原有的 8/96 Msps MAT/TXT。
- Python 全量 regression 为 `73 passed`，独立 LFSR 计算与 MATLAB 文件中的 PRBS9/PRBS15 golden 常量一致。
- 当前环境未安装 MATLAB/Octave，因此尚未生成新 MAT/TXT，也未执行 MATLAB runtime 和 `validate_ble_vectors`；这一步必须在用户 MATLAB 环境完成。

---

# Python BLE 波形 JSON Sidecar 实施计划

日期：2026-07-22

状态：已完成

## 1. 目标

让 Python BLEStudio 成为正式 BLE 波形生成入口。启用 IQ output 后，每个实际生成的
TX/RX 波形使用包含 PHY、实际采样率、payload 和长度的描述性文件名，并自动附带同名
pretty JSON，用来说明协议内容、调制与信道参数、采样信息、定点量化规则及关联文件
身份；`gen_ble_data.m` 和现有 MATLAB vectors 只作为 golden regression，不再作为
日常生成依赖。

## 2. 固定设计决策

1. generated packet 的 basename 固定为
   `<PHY>_<sample-rate>Msps_<payload>_<length>B_<TX|RX>`。例如：
   `LE1M_96Msps_PRBS9_37B_TX.mem`、`LE1M_96Msps_PRBS9_37B_TX.json` 和
   `LE1M_96Msps_PRBS9_37B_RX.json`。
2. JSON 使用 UTF-8、2-space indent、末尾换行和 strict JSON；禁止 `NaN/Infinity`。
3. schema 标识为 `ble_studio.waveform.v1`，并保留整数 `schema_version: 1`。
4. JSON 在 TXT/MAT/MEM 全部成功写出后最后生成，`files` 只列实际存在的产物。
5. JSON 不嵌入全量 IQ；用 sample count 和关联文件 SHA-256 证明它描述的具体波形。
6. 同一 waveform 的 TXT/MAT/MEM/JSON 共用同一 basename；TX 和 RX 只通过末尾
   `_TX` / `_RX` 区分。
7. sample-rate token 使用实际 waveform sample rate。整数 MHz 写成 `96Msps`；
   非整数值采用去除尾零的十进制 MHz，避免 Python float 尾差进入文件名。
8. canonical PHY token 与 MATLAB 保持一致：`LE1M`、`LE2M`、`LE125K`、`LE500K`。
9. payload token 使用稳定短名：`PRBS9`、`PRBS15`、固定 DTM pattern 或 `ADV`。
10. 外部 IQ 使用 `<sanitized-input-stem>_<sample-rate>Msps_RX`，不在文件名中声称其
    实际 packet 类型；receiver expectation 仅写入 JSON。
11. 不改变现有 `IQExporter.quantize()` 函数签名。

## 3. JSON Schema v1

首版按以下语义分组：

```text
schema / schema_version / generator
output_kind / source_kind / mode
signal
  sample_rate_hz / symbol_rate_hz / samples_per_symbol
  sample_count / duration_us / active_samples / padding_samples
packet
  phy_mode / channel_index / frequency_mhz
  access_address / header_value / payload_type / payload_length_bytes
  payload_hex / pdu_hex / crc_hex / pdu_with_crc_hex
  crc_init / whitening / packet_bit_count
modulation
  modulation_index / bt / pulse_length
channel
  type / bypass / ebn0_db / frequency_offset_hz
  doppler_hz / k_factor / random_seed
quantization
  applies_to / bit_width / scale_to_full / scale_factor
  rounding / signed_min / signed_max / saturation_i / saturation_q
  txt_layout / mem_layout
files
  <format>: name / size_bytes / sha256
```

具体规则：

- clean TX 的 `channel` 为 `null`；RX 才记录实际 channel。
- bypass RX 使用 `ebn0_db: null`，不输出 `Infinity`。
- generated TX/RX 可写入实际 packet；外部 IQ 的 RX 使用 `packet: null`，并单独记录
  `receiver_expectation` 和 `input_file`，避免把 RX 输入来源描述错。
- `random_seed` 首版为 `null`，明确表示 AWGN sample 不能仅靠参数重建；输出 hash 仍能
  唯一核对本次文件。
- 未实施 interval padding 时记录 `padding_samples: 0`，不宣称存在 625 us interval。

## 4. Red：先增加失败测试

### 4.1 IQ exporter 单元测试

1. 正负 half-LSB 的 I/Q 都按 ties-away-from-zero 量化，覆盖 `+0.5/-0.5` 和连续边界。
2. 上下限 clip 与 I/Q saturation count 正确。
3. `scale_to_full` 的实际 scale factor 与 metadata 一致，动态缩放时不写误导性 Q label。
4. 12-bit MEM 每行固定 6 hex digits，并保持 I 位于高 12 bits、Q 位于低 12 bits。
5. pretty JSON 可被标准解析器读取，包含多行、末尾换行，且拒绝 non-finite number。
6. 文件 size/SHA-256 与实际 TXT/MAT/MEM 一致。

### 4.2 生成流程集成测试

1. LE 1M、96 MHz、PRBS9、37 bytes 生成
   `LE1M_96Msps_PRBS9_37B_TX.{txt,mat,mem,json}`，JSON 记录 96 MHz、96 SPS、
   36,096 active samples，以及正确的 AA、payload、PDU、CRC init 和 whitening 状态。
2. `LE1M_96Msps_PRBS9_37B_TX.json` 的协议字段与
   `reference/BLE_PKT/LE1M_96Msps.json` golden 对齐；
   Python packed MEM 继续与 MATLAB golden TXT 逐行一致。
3. TX JSON 的 sample count 与同 basename 的 TXT data rows、MEM rows、MAT IQ length
   一致。
4. bypass 时 TX/RX 数组相同，但 `output_kind` 和 channel provenance 不同。
5. AWGN RX 有 channel 参数，clean TX 不带 channel 结果，JSON 中不出现 `Infinity`。
6. 外部 IQ 采样率不同于 TX 配置时，TX 仍记录 `cfg.sample_rate`；RX 记录导入文件的
   有效采样率、来源文件和 hash，且不把配置 packet 当成真实 RX source。
7. `export_tx=false` 不生成任何 `_TX.*`；关闭整个 output 时不生成任何 sidecar。
8. 请求的导出格式失败时异常向上传播，且不生成内容不完整却声称成功的 JSON。
9. 文件名 formatter 覆盖 LE1M/LE2M/LE125K/LE500K、整数/非整数 Msps、所有 DTM
   payload token 和非法路径字符清理。
10. 外部 IQ 的 RX basename 使用输入文件 stem 和实际 RX 采样率；当 TX 与 RX 采样率
    不同时，两组文件名分别反映各自采样率。

## 5. Green：实现步骤

1. 在 `ble_studio/iq_io.py` 增加不改变公共量化返回值的内部 quantization detail，统一
   I/Q half-LSB rounding，并提供 strict pretty JSON、file descriptor/SHA-256 helper。
2. 调整 TXT header：保留原格式兼容，补充实际 scale factor；只在定义确实匹配时报告
   Q format。
3. 在 `examples/demo.py` 根据实际 PHY、sample rate、payload/source 和 TX/RX 方向生成
   稳定 basename，并组装 waveform schema；packet/modulator/channel 等语义由仿真
   主流程提供，文件和 quantization 事实由 IQ exporter 提供。
4. 修正 TX/RX sample rate 归属；外部 IQ 路径建立明确的 source provenance。
5. 先写 TXT/MAT/MEM，校验成功后计算 size/hash，最后原子地写同名 JSON sidecar。
6. MAT 请求缺少 `scipy` 时抛出带解决方式的错误，不再静默跳过。
7. 更新 README 的波形导出说明和 96 MHz PRBS9 示例，列出 JSON 的用途与字段边界。

## 6. 预计文件清单

修改：

- `ble_studio/iq_io.py`
- `examples/demo.py`
- `README.md`
- `tests/core/test_iq_io.py`（若现有测试文件不存在则新增）
- `tests/core/test_demo.py` 或新增 `tests/core/test_waveform_metadata.py`
- `research.md`
- `plan.md`

仅当 packet 现有接口无法无重复地提供 CRC/PDU metadata 时，才对
`ble_studio/packet.py` 增加向后兼容的只读 helper，并先检查全部调用方。

## 7. 影响与明确不做

- 不改变 BLE packet、浮点 IQ 或 public quantize 返回类型。
- 按用户要求，输出 basename 从通用 `iq_tx` / `iq_rx` 改为描述性命名。这是有意的
  文件接口变更；现有 Verilog testbench 中写死的 `$readmemh(".../iq_tx.mem")` 需要改为
  新文件名。不会额外保留同内容 legacy alias，避免目录内出现两份含义相同的波形。
- half-LSB 精确落点的定点导出值会从 NumPy ties-to-even 改为已确认的 MATLAB/Core
  golden policy；非 half-LSB 样本不受影响。
- TXT header 可能增加/修正注释行；数据行和 Verilog MEM layout 保持不变。
- 不实现 packet interval padding，不改变 AWGN RNG/seed API，不加入性能 sweep。
- 不增加依赖，不运行 MATLAB；使用已经生成的 MATLAB 文件做离线 golden regression。

## 8. 验证

1. 运行新增的 exporter/metadata testcase，完成 Red -> Green。
2. 运行 `pytest -q` 全量 regression。
3. 用 `examples/config_rftest_1m_prbs9_96m.yaml` 实际生成一组波形，检查 JSON 人工可读、
   所有文件 hash/长度一致。
4. 将 Python `LE1M_96Msps_PRBS9_37B_TX.mem` 与 MATLAB 96 MHz golden TXT 逐行比较。

## 9. 确认

- 回复 `GO`：按本计划开始 TDD 实施。
- 提出修改意见：修订 `plan.md` 后重新等待确认。
- 否决：停止，等待新指令。

## 10. 执行结果

- generated BLE waveform 已改用
  `<PHY>_<sample-rate>Msps_<payload>_<length>B_<TX|RX>` 描述性 basename；外部 IQ
  使用输入文件 stem、实际采样率和 RX 方向命名。
- 每个实际导出的 TX/RX 自动生成同 basename 的 strict pretty JSON，记录 packet、
  modulation、channel、source、实际采样信息、量化规则和关联文件 SHA-256。
- TX sample rate 与 imported RX sample rate 已解耦；外部 IQ metadata 不再冒充配置中的
  PRBS packet，receiver expectation 单独记录。
- Python I/Q 量化已统一为 MATLAB `round` 的 ties-away-from-zero，并记录实际动态
  scale、clip 范围及 I/Q saturation count。
- `LE1M_96Msps_PRBS9_37B_TX.mem` 与 MATLAB 96 MHz golden TXT 逐字节一致；浮点 IQ
  最大复数误差为 `2.854e-14`。
- 新生成的正式示例位于 `artifacts/waveforms/LE1M_96Msps_PRBS9_37B`。
- 定向 metadata/exporter tests 与全量 regression 均通过；最终结果为 `93 passed`。
