# 数据提取规则与测试场景

本文档定义当前逻辑分析仪 pipeline 实际执行的采样算法，并把早期记录的九种边沿
场景整理为 characterization test 的输入依据。

## 符号

- `0`、`1`：某个数据 channel 在一个 logic-analyzer sample 上的电平；
- `*`：clock/data-indicator 的跳变沿；
- `=`：右侧和左侧区间宽度相等，仅用于辅助阅读，不占采样点；
- `<`：右侧区间比左侧区间长，仅用于辅助阅读；
- `>`：左侧区间比右侧区间长，仅用于辅助阅读。

每个测试场景关注相邻两个 `*` 之间应该恢复的一个 bit。并行 word 的组装规则是：
`data_bits[0]` 组成输出 bit 0，`data_bits[1]` 组成输出 bit 1，依此类推。

## 当前实际算法

### 1. Input Glitch Filter

启用 `glitch_filter` 后，pipeline 根据：

```text
min_pulse_width = int(sample_rate / data_rate * glitch_threshold)
```

识别短脉冲。DDR 有 clock 时，位于任一 clock edge 后前半周期内的短脉冲会被保护，
因为它可能是亚稳态下最先出现的有效电平。其他短脉冲最多迭代处理 100 轮。

该步骤发生在 eye analysis 之前，不应与最终 word 的 `output_spike_filter` 混为一谈。

### 2. Eye Analysis

DDR 直接从 clock 找 rising/falling edges；SDR 根据 `sample_rate / data_rate` 生成
virtual edges。对每个候选 offset，算法统计 `sample-1/sample/sample+1` 是否一致：

1. 先计算所有 data bit 的 stability；
2. 以所有 bit stability 的最小值作为 combined score；
3. 取距离最高分不超过 0.05 的 offset；
4. 若存在多个不连续稳定区，选择第一个稳定区；
5. 使用该稳定区中心作为 base offset；
6. 每个 bit 再在 base offset 前后约 3 个 sample 内选择自己的最佳 delay。

DDR 为 rising 和 falling edge 分别生成 delay map。SDR 只生成一组 delay map。

### 3. Extraction

当前 baseline 的最终判决非常明确：

```text
sample_position[channel] = edge_position + eye_delay[channel]
bit_value[channel] = channel_data[sample_position[channel]]
```

代码虽然会观察 edge 前电平、edge 后起始电平和周期内 transitions，但这些上下文值
当前不参与判决。历史文档中“比较前后占比后动态选择周期前半或后半”的策略尚未实现。

因此，当前实现的优先级是：

1. 信任 eye analysis 选出的 per-bit delay；
2. 每个 bit 固定在 `edge + delay` 采样；
3. 用 `data_bits` 顺序组装 word；
4. DDR 按 `rising_edge_data/falling_edge_data` 映射 I/Q；
5. I/Q 边沿数量不同时按较短一路截断；
6. 在 `sample_info` 中保留 edge 和每个 bit 的实际 sample position。

任何引入上下文判决、majority vote 或动态 delay 的改动都属于算法行为变化，必须先
增加新测试并明确更新 characterization baseline，不能只修改本文档。

## 九种历史场景

下表保留早期硬件调试时记录的期望 bit。它们用于构造合成波形和回归测试，不表示
当前代码已经实现了表中所有启发式判断。

| ID | 单 channel 波形 | 历史期望 | 场景含义 | 当前测试依据 |
|---|---|---:|---|---|
| 1 | `0000000000000*1111111111111111*0000` | 1 | 理想稳定数据 | eye delay 应落在中间的稳定 `1` 区域 |
| 2 | `0000000000000*000<11111111111>00*0000` | 1 | 有效电平来得晚、走得早 | 选择到 `1` plateau 的 delay 时结果为 1 |
| 3 | `0000000000000*11111>00000000000*0000` | 1 | 来得准时、结束较早 | characterization 记录 eye delay 是否仍落在前段 `1` |
| 4 | `0000000000000*1111<00000>1111>000*0000` | 1 | 周期内存在异常翻转 | input filter 与 eye delay 分开测试，不能靠隐式上下文修正 |
| 5 | `0000000000000*000000000>1111111*0000` | 1 | 有效电平来得晚 | delay 必须覆盖后段稳定 `1`，否则当前算法会得到 0 |
| 6 | `0000000000111*1111<000000000000*0000` | 1 | 有效电平提前到达 | edge 后选中的稳定位置应保持 1 |
| 7 | `0000000000000*00111111111111111*1111` | 1 | edge 后轻微延迟 | eye delay 应避开最初的 `00` |
| 8 | `0000000000000*0000000000>111111*1111` | 0 | edge 前后同值，历史规则按占比选择 0 | 当前算法只取 eye delay；测试需同时记录历史期望和实际选点值 |
| 9 | `0000000000111*111111111>0000000*1111` | 1 | edge 前后同值，历史规则按占比选择 1 | 当前算法只取 eye delay；测试需防止误宣称已实现占比规则 |

场景 8 和 9 是区分“历史设计意图”与“当前实现”的关键用例。当前结果由 delay 落点
决定，不会因为某个电平在 edge 前后的占比更大而自动改变 sample position。

## 自动测试组织

九种场景应使用参数化测试表达，并分别检查：

- 输入 channel waveform 和 edge positions；
- 配置给定或 eye analysis 得到的 delay；
- `sample_info` 中记录的实际 sample position；
- 当前 baseline 取到的 bit value；
- 历史期望值，作为未来算法评审的显式 metadata；
- filter 开启和关闭时的差异。

建议将测试分为三组，避免一个用例同时验证过多行为：

1. `test_processing.py`：短脉冲、前半周期保护和 adaptive filter；
2. `test_extraction.py`：固定 delay、I/Q edge mapping、word bit order 和 sample positions；
3. characterization tests：九种完整场景在当前工作树上的实际结果。

真实 capture 只用于小型回归 fixture。常规 CI 不依赖完整 capture，也不通过人工查看
HTML 判断 PASS/FAIL。

## Output Spike Filter

提取完成后，`output_spike_filter` 可以修复 I/Q 或单路 word 中的孤立尖刺。判断条件
是当前点同时远离前后邻居，而两个邻居彼此接近；替换值为邻居均值。

该过滤器操作的是已经组装的有符号数值，不改变 `sample_info` 中的原始选点记录。
诊断采样错误时应同时查看：

- 未过滤的 raw/cleaned digital channels；
- `sample_info` 中的 edge 和 per-bit positions；
- 最终 filtered output word。
