# BLEStudio 全仓库整理与 LogicAnalyzer 静态归档调研（2026-10-12）

本节是当前任务；后文为既有调研，保留当时事实和原始路径，不将历史状态误作当前实现。

## 1. 当前状态与用户决定

- Git baseline 为已 push 的 `94801e4`；开始盘点时 tracked 工作树干净，只有未跟踪 `xclip.rpm`。
- 用户已做备份，授权对当前仓库删除、移动和整理，并要求 README 写明目录与用途。
- 用户追加：逻辑分析仪相关内容集中到根 `LogicAnalyzer/`，以后移出 BLEStudio。
- 已询问并获得选择：仅归档保存，保留源码、数据和测试，不再随 BLEStudio 安装或默认运行。
  因而本轮不是拆分新的可安装应用，也不应为维持旧 API 引入 import path hack 或兼容壳。
- 没有额外仓库级 AGENTS.md/CLAUDE.md；遵循当前用户提供的开发规则。

## 2. 目录凌乱的实际来源

| 位置 | 已确认情况 | 处理方向 |
|---|---|---|
| `ble_studio/` | BLE 核心包与 LA 子系统同属安装范围，但核心未导入 LA | 核心保留原架构，LA 静态归档 |
| `examples/` | 2 个 Python 入口与 17 个 YAML 混放 | 1 个 LA 导入配置归档，16 个配置集中 configs/waveforms |
| `utils/` | 4 个已废弃 LA wrapper、6 个分析/实验脚本、1 个顶层 IQ 测试 | LA wrapper 原样归档，分析移 scripts，IQ 检查转正式 test |
| `doc/` | 算法、notebook、两份 PDF、LA 与 VCS 文档混放 | docs 分类，PDF 转 reference，LA 文档归档 |
| 根 plan/research | 约 70 KB/45 KB，累积多个时期计划与研究 | 归入 docs/development，保留历史和未完成事项 |
| `reference/` | MATLAB 脚本、9 个 golden 数据文件、2 张截图 | 脚本/向量分层，截图删除，数据不重新生成 |
| `artifacts/` | 273 个非环境文件，约 45.36 MiB，含多个交接包及解包工作区 | 当前均为可再生产物，归档 LA 占位文件后清理 |
| `data/` | BWV 输入、LA fixtures/profiles、ignored captures/quarantine | BWV 保留，全部 LA 数据随归档移动 |

上述大小为开始盘点时统计，不包含 `.git/` 或 `venv/`，会随运行变化。
`.claude/settings.local.json` 是用户本地工具配置，保留；不因为出现历史路径而删除它。

## 3. LA 依赖与归档边界

已读取核心 `__init__.py`、LA 入口、validation、exporters、配置、测试与旧 wrappers：

- `ble_studio/__init__.py` 不导入 LA。TX/RX、IQ IO、performance、report、checker 和
  `sim/vcs/` 没有 LA 实现依赖，能够移出 LA 而不复制任何核心算法。
- 唯一安装耦合是根 pyproject 的 `ble-la = ble_studio.logic_analyzer.cli:main`。
  静态归档后必须移除该 entry point，不能保留不可 import 的 CLI。
- 反向依赖存在于 LA：`validation.py` 相对导入 BLE demodulator/packet；
  LA exporter/RX tests 使用核心 IQ IO 与 Packet/TX。故单纯移目录后不是独立可运行工具。
- 归档采用原相对路径加 `LogicAnalyzer/` 前缀，保存旧包名、schema 字符串和文档语义。
  不将历史 imports 全局替换成新的独立包名。
- 归档覆盖 package、configs、全部 data、tests/fixture、文档、4 个 wrappers、
  `examples/config_import_hex.yaml` 和 LA artifacts 占位文件。
- `config_import_hex.yaml` 实际导入的是 `data/logic_analyzer/fixtures/adc_ddr_iq.mat`，
  不是 HEX，随相关子系统归档，不继续挂在主项目的通用 IQ 示例下。
- ignored 原始数据现有 `test.bin`、`rssi.bin`、`bk.kvdat`、`raw_data.kvdat`、
  `quarantine/test3.bin`。bk/raw_data SHA-256 均为
  `66ec8092fefa2eb3346c8c0a9b43f1d31cdfc3af5b623a61375d0eb62878cf19`；
  用户选择保留归档数据，本轮不去重删除它们，也不因换路径把 captures 纳入 Git。
- `data/logic_analyzer/legacy_manifest.json` 是早期迁移溯源，随 LA 一起归档，
  不作为当前文件位置清单。新 archive_manifest 另行记录本次完整性。

## 4. 需要同步修正的路径和真实问题

- Demo 默认配置写死 `examples/config.yaml`；`load_config()` 对不存在路径返回 `{}`。
  整理后遗漏任意旧路径可能静默运行默认信号，必须添加缺失配置 regression，明确抛错。
- `SimConfig.output_dir`、from_dict fallback、默认 YAML 和多数示例仍输出 `results/`。
  `ReportGenerator` 的默认输出也为 results；统一进入 artifacts，并保持显式用户路径有效。
- `utils/compare_iq.py` 只查 `results/iq_tx.*` / `iq_rx.*`；当前生成文件名已含 PHY/采样率等，
  所以需要最小 CLI 路径适配，明确指定两份文件，而非猜目录里哪个文件应被比较。
- `utils/iq_corr_test.py` 顶层执行、写固定 results 路径并只打印结果，不是自动断言测试。
  先把 roundtrip/相关性意图迁入 pytest/tmp_path，再删除旧脚本。
- 两个 RF 实验脚本含手工构造 bit、直接频偏统计和历史 PASS 判断，不能视为 RF 合规测试。
  此次只分类和标明用途，不借清理任务重写算法或新增 RF 能力声明。
- `requirements.txt` 与 pyproject 运行依赖重复，另含未被当前代码使用的 pdoc。
  当前 README 安装入口全为 pyproject，可统一并移除重复依赖文件，不新增依赖。
- MATLAB 的 gen_ble_data/validate_ble_vectors 通过相对 `BLE_PKT` 寻址；迁移 vectors 必须
  同步这两处默认路径和注释，保持量化基础库与 golden 文件内容不变。
- 三份 golden JSON 没有需要替换的输出路径字段；九个 MAT/TXT/JSON 均可按原字节迁移。
- `tests/core/test_waveform_metadata.py` 硬编码 golden 目录及两份 Coded config 路径。
  `tests/core/test_loopback.py` 使用 data/iq/BLE_1M.bwv；后者保留，前者同步移动。
- VCS manifest 目前包含完整 LA package、根 plan/research、examples YAML 和 doc 路径。
  迁移后需要同步清单及接入文档，并实际做独立解包测试，不凭主工作树测试宣称交付可用。
- 主 README 的教程、链接和结构说明都需要同步，LA 教程应从主入口移除并指向静态归档说明。

## 5. 当前测试事实与验证策略

2026-10-12 实际 collect：总共 300 tests，其中 tests/core 为 264、tests/logic_analyzer 为 36。
前一提交前全量实际执行为 300 passed in 39.30s。此次仅做了只读 collect，未将其冒充新一轮运行。

整理完成后主项目保留全部 264 项 core tests，加新增工程/路径/CLI 测试；
36 项 LA tests 连同 fixture 原样归档，不再默认收集。测试数量变化必须明确说明原因。
归档以源/目标逐文件 SHA-256 完整性验证，主安装/import/回归要在不依赖归档的条件下通过。
真实 VCS 环境不在本机，继续保留服务器待验收状态。

执行清单、目录映射、删除候选和兼容影响见 plan.md 当前任务。
用户于 2026-10-13 回复 GO，已进入执行；本次实际验证结果记录在 plan.md 当前任务，
下文中的旧路径与历史状态保留，不作为现行使用入口。

执行补充：52 个归档文件和 33 个不可变核心/参考文件最终 hash 均一致；
四份 KVSET 使用原始 CRLF，已通过归档内 .gitattributes 防止 Git 自动换行转换。
主项目最终 301 项回归、独立交接 196 项回归通过，editable/wheel 构建成功。
完整执行结果与清理范围见同目录 plan.md 第 8 节；真实服务器 VCS 仍未运行。

---

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

---

# BLEStudio 仓库目录清理调研

日期：2026-09-27

## 1. 调研范围

本轮只读检查覆盖：

- Git tracked、untracked 和 ignored 文件；
- 顶层目录、文件数量与磁盘占用；
- Python import、CLI、配置、测试、README 和文档引用；
- 可再生 artifact、原始 capture、golden reference、历史实现和兼容 wrapper。

调研期间未删除文件。开始调研时 `master` 与 `origin/master` 同步，工作区无未提交改动。

## 2. 高置信度可清理的本地产物

以下内容均被 Git 忽略且可由现有代码、配置或测试重新生成：

| 路径 | 约占用 | 依据 |
|---|---:|---|
| `artifacts/logic_analyzer/legacy/` | 826.40 MiB | 旧 HTML/TXT/VCD/NPY 等生成物 |
| `artifacts/logic_analyzer/rssi_raw/` | 9.06 MiB | 由 RSSI capture 和正式 YAML 生成 |
| `artifacts/logic_analyzer/adc_ddr/` | 1.92 MiB | 由 ADC DDR capture 和正式 YAML 生成 |
| `artifacts/logic_analyzer/generated_adc.yaml` | 很小 | 临时生成配置 |
| `artifacts/waveforms/ble_1m_prbs9_96m/` | 35.18 MiB | 旧命名波形，MEM 与正式目录 hash 相同 |
| `.pytest_cache/`、各 `__pycache__/` | 0.80 MiB | Python/pytest cache |
| `artifacts/pytest_tmp_commit_20260928/` | 空 | 测试临时目录 |
| `template_data/` | 空 | 已完成迁移的旧目录残留 |

上述范围约可释放 `873.37 MiB`。初始审计建议保留当前正式波形；执行阶段用户进一步
明确要求删除所有可再生输出，因此 `artifacts/waveforms/` 和 `results/` 也纳入清理。
继续保留：

- `artifacts/logic_analyzer/.gitkeep`；
- `data/logic_analyzer/captures/` 与 `quarantine/` 中的原始数据；
- 生成波形所需的 source、配置、MATLAB golden reference 和 testcase。

## 3. 高置信度 tracked 删除候选

| 路径 | 结论与证据 |
|---|---|
| `results_logic_analyzer/` | 6.52 MiB 的旧报告和 IQ 导出；无代码、测试或文档引用，已被 `artifacts/logic_analyzer/` 取代 |
| `save_log.md` | 旧 Claude conversation log；不参与运行、构建或测试，且不应作为产品文档保存 |
| `ble_studio/modulator_v0.py` | 无 import/call site，是当前 `modulator.py` 的旧实现，Git history 已保留历史 |
| `utils/get_bwv_info.py` | 无引用、无参数入口，并硬编码已过时的本机绝对路径 |
| `utils/read_mat.py` | 无引用、无参数入口，并硬编码已过时的本机绝对路径 |
| `utils/test.py` | 顶层立即执行的一次性 RF 调试脚本，不属于 pytest test suite |
| `utils/test_rf_metrics.py` | 与 README 记录的 `utils/rf_metrics_test.py` 职责重叠；后者覆盖模式和脉冲长度分析 |
| `legacy/logic_analyzer/` | production package、CLI 和 tests 均不依赖；目录自身声明不是受支持入口 |

删除 `legacy/logic_analyzer/` 后，需要更新 `README.md` 目录树以及
`doc/logic_analyzer_data_processing.md` 的历史目录说明。旧实现仍可通过 Git history 查看。

## 4. 明确保留内容

- `ble_studio/` 当前实现、`tests/`、`configs/`、`examples/` 和正式文档。
- `reference/` 全部 MATLAB golden vectors、脚本、眼图和星座图。
- `data/iq/BLE_1M.bwv`：loopback test 和两个 import 示例直接读取。
- `data/logic_analyzer/fixtures/`、`profiles/` 和 `legacy_manifest.json`。
- `data/logic_analyzer/captures/test.bin`、`rssi.bin`：正式配置直接读取。
- `data/logic_analyzer/quarantine/test3.bin`：来源未确认，继续隔离而不是删除。
- `doc/Core_v6.2.pdf`、`doc/RFPHY.TS_5.2.pdf`：虽占约 28 MiB，但属于规范依据。
- `utils/logic_analyzer_bin2wave.py`、`bin_to_vcd.py`、`rssi_parser.py`、
  `analyze_sampling_issues.py`：旧命令兼容 wrapper，删除会产生 Breaking Change。
- `utils/analyze_signal.py`、`compare_iq.py` 及 README 已公开的分析工具：具备独立功能。
- `venv/`：当前可工作的 Python 环境；本轮不以释放空间为由删除。
- `.claude/settings.local.json`：用户本地工具配置；即使内容过时也不擅自删除。

## 5. 暂不纳入自动清理

- `data/logic_analyzer/captures/bk.kvdat` 与 `raw_data.kvdat` 内容完全相同，但它们属于
  原始 capture。本轮不删除任何一份。
- 示例配置存在命名或 payload 注释不一致，但属于后续配置修正任务，不借目录清理改行为。
- 删除工作树文件不会缩小 `.git` 历史；如需减小 clone 体积，必须单独评估 history rewrite。

## 6. 调研结论

建议分两部分执行：

1. 精确清理 ignored 的旧 artifact、cache 和空目录，预计释放约 `873.37 MiB`；
2. 删除无引用的 tracked 旧输出、日志、旧实现和一次性脚本，并更新目录文档。

该范围不删除 public API、正式 CLI、兼容 wrapper、golden vectors、规范 PDF、原始 capture
或 Python 环境。Verilog 波形作为可再生 artifact 删除，后续可由 96 MHz 示例配置重新生成。

---

# README 使用教程审核

日期：2026-09-28

## 1. 当前问题

当前 README 约 769 行、30 KB，同时承担入门教程、API 手册、实验记录和目录说明，首次使用
路径不够清晰。快速开始使用裸 `pip` 和 `python`：

```powershell
pip install -e .
python examples/demo.py
```

这不能保证安装和运行使用同一个 Python。在当前 Windows 环境中，系统 `python` 指向
pyenv shim，未安装 `ble-studio`/`scipy`；项目 `venv` 中的 editable install 则可以正常
导入 `ble_studio`。因此出现：

```text
ModuleNotFoundError: No module named 'ble_studio'
```

## 2. 已确认的正确入口

Windows PowerShell：

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -e .
.\venv\Scripts\python.exe examples\demo.py
```

开发依赖和测试使用同一个解释器：

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
.\venv\Scripts\python.exe -m pytest -q
```

Linux/macOS 使用 `python3 -m venv venv` 和 `./venv/bin/python` 对应路径。

已确认 `venv` 可以导入 `ble_studio`，module CLI `python -m ble_studio.logic_analyzer --help`
和安装后的 `ble-la --help` 入口存在。

## 3. README 中需要修正的事实

- 示例命令必须绑定 `.\venv\Scripts\python.exe`，或明确先激活 venv。
- 默认配置结构是 `common`、`tx`、`channel`、`io`、`output`；现有 README 的
  `mode`/`rf_test` 旧示例必须删除。
- `examples/config.yaml` 当前使用 `ebn0_db: 100`，不是 README 声称的 SNR 15 dB。
- `100 dB` 是近似理想信道；真正 bypass 使用 `ebn0_db: .inf`。
- 输出目录由 `output.dir` 决定，默认是 `results/`；96 MHz 示例写入
  `artifacts/waveforms/LE1M_96Msps_PRBS9_37B/`。
- 只有 `io.output.enabled` 和对应导出开关打开时才会生成 TXT/MAT/MEM/JSON。
- 当前正式支持 `LE 1M`、`LE 2M`；LE Coded S=2/S=8 尚未实现。
- Python 尚未实现 Packet interval/625 us zero padding；不要在 README 中宣称已支持。
- 采样率必须是 symbol rate 的整数倍。
- 逻辑分析仪正式入口是 `ble-la` 或 `python -m ble_studio.logic_analyzer`；真实 capture
  目录是本地输入，clean clone 不应假定存在完整采集数据。

## 4. 建议保留的教程范围

新版 README 只保留：项目定位、主要功能、Windows/Linux 安装、第一次运行、96 MHz
LE1M PRBS9 37-byte 波形生成、当前 YAML 配置结构、输出命名和 JSON 说明、逻辑分析仪
入口、支持范围、测试命令、关键目录和专题文档链接。

删除或移出 README：大段 Packet/Modulator/Demodulator/Channel/Performance API 示例、
完整 Visualizer 图表列表、长篇控制台输出、重复信道介绍、易失效的源码行号说明以及
未经当前代码验证的能力声明。

---

# VCS DAC TX 整包解调调研（2026-10-09）

- 用户环境：CentOS 7/VCS 2025/Python 3.10；DAC real I/Q，96 MHz，数据有效
  信号 tx_dfe_en。接受包结束后解调整包。
- 仓库没有 VCS/DPI 组件或 streaming RX API。BLEDemodulator.demodulate()
  接收整段 complex IQ，频偏/定时估计使用整段数据，要求 integer SPS。
- 实测 LE1M/96 MHz/PRBS9/37-byte 分离 float64 I/Q，再组合进入 RX：
  36,096 samples（376 us），sync、CRC、完整 PDU 核对均通过。
- DemodulationResult.access_address 是配置值，不是严格的接收 AA 核对结果。
- 现有 write_pretty_json() 可复用为每包诊断结果保存接口。
- real 数据直接作为浮点 IQ，不需要补码转换或整数反量化。
- 推荐逐点采集、每包一次同步 DPI 调用；C++ 嵌入一次 CPython 并缓存 callable，
  open array 用 VCS 实际 svdpi.h 和生成 prototype，避免新增 binding framework。
- 嵌入解释器的路径、libpython、headers 和依赖需要单独验证；shell Python
  导入成功不代表 VCS 进程的嵌入环境正确。
- tx_dfe_en 是否一个连续有效区间精确对应一包、DAC clock/IQ 层级名及更新时序
  尚未提供；monitor 使用通用端口，明确列为接入检查项。
- 本机没有 VCS，未声称完成 CentOS 7/VCS 2025 集成验证。

查阅资料：

- CPython 3.10 embedding：
  https://docs.python.org/3.10/extending/embedding.html
- CPython 初始化配置：
  https://docs.python.org/3.10/c-api/init_config.html
- DPI 数组映射/访问参考（以实施时 VCS headers 为准）：
  https://www.doulos.com/knowhow/systemverilog/systemverilog-tutorials/systemverilog-dpi-tutorial

第一版做数据检查；RFMeasure 合规校正仍保留为后续独立工作。

## GO 后实施记录

独立入口为 `ble_studio.tx_checker.check_tx_packet()`，通过显式
DemodulatorConfig 和 expected PDU 调用已有 RX。DPI 标量适配层
`check_tx_packet_dpi()` 把结果返回为原生 Python dict。

新增 `sim/vcs/`，含 DPI SV package、real IQ monitor、CPython C++ bridge/header、
VCS smoke TB、fixture generator 和启动脚本。脚本使用实际 Python 3.10 的
headers/libpython，检查安装 prefix 和 VCS svdpi.h，逐个检查 11 个正常/负例场景。
不存在对服务器安装 ripgrep 的要求；脚本日志检查仅使用 Bash 内置功能。

原生 smoke 额外使用测试专用 open-array adapter，真实嵌入 CPython 并验证 C API
数组、异常和 callable 缓存；其边界明确是 bridge，不是 simulator ABI 或四态仿真。
共享 C++ header 与 Verilator 从 SV 生成的 DPI prototype 同时编译无冲突。

验证结果：33 项新增 Python 测试、完整 126 项 Python 回归、原生 bridge smoke、
GCC Werror 编译、Python compile、Bash syntax 通过。本机 Python 是 3.13.7，
没有冒充目标 Python 3.10。SV 静态展开使用 Verilator 5.040，存在 34 条 BLKSEQ
和 10 条 clocking input UNDRIVEN 警告，不是 clean lint，也未替代 VCS 联调。
CentOS 7/VCS 2025/Python 3.10 smoke 仍需要在真实服务器执行。

---

# LE Coded S=2/S=8 专项调研（2026-10-12）

## 1. 范围、来源和实际状态

用户要求开发 BLE LE Coded 的 S2/S8。本轮先调研和规划，尚未修改实现。
工作树中已有未提交的 VCS checker/交接材料，必须保留；`xclip.rpm` 与任务无关。
没有发现额外的仓库 AGENTS.md/CLAUDE.md，遵循用户提供的全局开发规范。

协议依据固定为仓库已有的 Bluetooth Core 6.2，不宣称它是最新版本：

- Vol 6 Part B §2.2、§3.2/3.3：Coded 格式、whitening、FEC、pattern mapper。
- Vol 6 Part C §2.1–2.4：FEC、pattern mapper 和完整 S2/S8 发送符号的独立 sample data。
- Vol 6 Part F §4.1/4.1.1：LE Test packet 与 DTM whitening 规则。

核对的是 Bluetooth SIG 官方 HTML，来源地址记录如下：

```text
https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-62/out/en/low-energy-controller/link-layer-specification.html
https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-62/out/en/low-energy-controller/sample-data.html
https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-62/out/en/low-energy-controller/rfphy-test-modes.html
```

现有 reference/BLE_PKT 仅发现 LE1M 向量，没有 S2/S8 MATLAB IQ golden。
不能因此宣称与 MATLAB Coded IQ 逐样点一致；本轮以官方发送符号为独立 oracle，
复用已有 GFSK 调制和现有 LE1M golden 回归，不要求购买或运行 MATLAB。

## 2. 已核实的协议要点

- 两种模式空中符号率均为 1 Msym/s；96 MHz 均为 96 SPS。
- 前导为 80 个符号，`00111100` 重复 10 次，不使用 uncoded 的交替前导。
- 第一 block 为 AA + CI + TERM1，固定 S8；第二 block 为 PDU + CRC + TERM2，
  由 CI 选择 S2/S8。CI 的 `00` 对应 S8、按发送顺序的 `10` 对应 S2，另两个值保留。
- FEC 为约束长度 4、码率 1/2 的卷积码，G0/G1 按规定顺序输出；TERM 各 3 个零。
  S8 把 FEC bit 0/1 映为 `0011`/`1100`，S2 不增加 pattern 映射。
- whitening 仅覆盖 PDU+CRC，在 FEC 之前；不处理 AA、CI、TERM。DTM 关闭 whitening。

## 3. 现有代码与实际调用方

| 位置 | 已确认的当前实现 | Coded 所需处理 |
|---|---|---|
| packet.py `_validate_uncoded_phy` | Packet、RFTestPacket、Modulator、RX 都调用并拒绝 Coded | 同步更新所有入口，不能仅放开枚举 |
| packet.py `generate` 两处 | preamble + AA + whitening(PDU+CRC) | 新增两段编码/映射，复用 CRC/PRBS |
| modulator.py | 2M 以外按 1M；输入 0/1 直接 GFSK | 接收已编码空中符号，不重复编码 |
| demodulator.py | uncoded 同步、去白化、解析 CRC | Coded 同步、分段软度量/Viterbi、CI/TERM/长度 |
| demodulator.py `find_packets` | 固定 0.5 ms，按 result.bits 推算跳过长度 | 按 Coded 实际包边界搜索和推进 |
| tx_checker.py | 最短包长只区分 1M/2M；完整 PDU 比对 | Coded 最短帧长及失败原因 |
| sim/vcs | enum 常量只有 1/2，monitor 默认 buffer 262144 | 增加常量和长包 buffer/测试 |
| examples/demo.py | DTM 已透传 PHY；advertising helper 固定 LE1M | DTM 开通、legacy advertising 明确拒绝 |
| examples/demo.py metadata | 已有 LE125K/LE500K 命名，但 packet_bit_count 等同 len(bits) | 追加明确的空中符号/编码信息 |
| demo.py/report.py | 都会重新调用当前 RFMeasure，report PHY 识别只有 1M/2M | Coded 的 RF 合规显示未评估，不产生假 PASS |
| performance.py | 固定使用 create_advertising_packet，忽略 packet PHY 配置 | 不宣称支持 Coded PER/BER，保留显式拒绝 |
| logic_analyzer/validation.py | PHY 名解析已有 Coded，重采样按空中符号率；旧 warning 说未实现 | 接通实际 RX、更新诊断与测试 |

`DemodulationResult.bits` 的主要消费者是性能模块、uncoded loopback 和 find_packets。
必须保持其原始符号含义，不能改成信息 bits 后让旧 BER 统计和跳包长度失真。
如果增加帧边界/诊断字段，放到 dataclass 尾部提供默认值，检查所有构造和 JSON 调用。

## 4. 独立参考与长度核算

官方 sample data 提供固定 AA、PDU、CRC、FEC 两段输出和 S2/S8 发送符号，适合
固定 fixture，不应从新编码器动态生成 expected。各层分别验证，避免同错闭环。
现有 CRC 对官方参考 PDU `0003424c45`、init `555555` 计算得到 `290ace`，与参考
一致，说明可以复用既有 CRC，无需顺带重写 CRC/bit order。

对当前两字节 header、L-byte payload、无 CTE 的单包，按上述字段推导：

```text
S2 air symbols = 376 + 2 * (16 + 8*L + 24 + 3)
S8 air symbols = 376 + 8 * (16 + 8*L + 24 + 3)
```

L=37、96 MHz：S2 为 1054 us / 101184 samples；S8 为 3088 us / 296448 samples。
L=255 的 S8 为 17040 us / 1635840 samples。现有 monitor 默认上限无法容纳
37-byte S8，因此仅完成 Python codec 不等于 VCS 可用。
smoke TB 自设 MAX_SAMPLES=40000、watchdog=5ms，也必须配套调整并保留卡高负例。

## 5. 实施决策与验收边界

- 用一个无循环依赖的内部 coded_phy.py 容纳协议 codec，复用现有公共类和错误模式。
- 首版采用软度量 Viterbi，分段解码且校验 CI/配置一致；不通过自动切换 PHY 或修改
  DUT I/Q 掩盖问题。uncoded 主路径保持数值兼容。
- 同步采用 Coded 模板；Coded 帧长由解码出的 header 和协议字段决定。
- 当前 CFO 使用整包相邻样点相位相关；Coded 固定码型可能改变全包统计，因此
  Coded 分支计划从已同步的平衡 preamble 估计 CFO，不改 uncoded 数值链路。
- header 长度必须在部分 FEC 解码并按配置去白化后读取；部分 trellis 不能错误
  强制为 TERM 终态。CRC 负例应在 FEC 前注入，避免被正常纠错后误判测试失败。
- VCS bridge 不改 ABI；结果和 JSON 仍以 sync/CRC/PDU 为数据判定，RF 另行验收。
- 不顺带引入 RF/性能算法优化、连接流程、Packet interval 或部署依赖解耦。
- 涉及 VCS package/monitor/smoke 时使用已完整读取的 hdl-toolkit:coding-style，
  新逻辑只在验证模块中，不新增 CDC 或 DUT RTL。

2026-10-12 基线验证：`venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`，
本机 Python 3.13.7，126 passed in 9.64s。S2/S8 当前仍明确拒绝；尚未新增实现测试。
CentOS 7/VCS 2025/Python 3.10 不在本机，真实服务器验收保持待执行。

## 6. GO 后实现与验证记录（2026-10-12）

以上实现地图描述修改前基线，不能再把旧的 `_validate_uncoded_phy`/拒绝 Coded
当作当前行为。当前四种 PHY 统一校验，Coded Packet 完成两段编码，RX 完成软
Viterbi、CI/AA/TERM/长度、去白化和 CRC，checker 保留原来的完整 PDU gate。

固定 `tests/core/fixtures/le_coded_core_6_2.json` 作为独立 oracle，encoder、mapper、
decoder 与完整发送序列分别验证，且 RX 直接解调官方发送符号，不调用 Packet
现场生成 expected。无 MATLAB Coded IQ golden，不声称 IQ 与 MATLAB 逐样点一致。

边界调研发现：整段能量定时会受后包的长度与 sample phase 影响；短包后接长包
或两包 phase 相差半符号时会产生边界偏移/漏包。因此 Coded 粗同步改为 sample 域
归一化相关，之后在本包前导局部恢复 clock/CFO。相关窗口方差接近零时屏蔽纯载波
的数值假峰。相关回归和 64-case sample-phase sweep 均通过，不改 uncoded 路径。

1/2 SPS 时，差分/匹配滤波中心可能越过末 symbol；仅在完整样点长度已核实后，
把缺失的末个软观测作为 erasure(0) 交给终态约束，不补造 IQ，不修改原始 air
decisions。低/中 SPS 附加测试通过；主交付仍是 8/96 MHz 的整数 SPS。

最终全量为 300 passed，native embedding 通过；SV 静态无错误但保留 BLKSEQ/
UNDRIVEN 警告。交付文件、命令、未验收的 VCS/服务器事项详见 plan.md 与交接文档。
本轮没有实现 Coded RF 合规、PER 曲线、CTE、extended advertising 或 Packet interval。
