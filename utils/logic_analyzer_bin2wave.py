"""
Kingst 逻辑分析仪 BIN 数据转波形工具

将 Kingst (金思特) 逻辑分析仪采样得到的并行数据恢复成波形数据。

支持功能:
- SDR/DDR 模式
- 自动眼图对齐
- IQ 数据提取
- YAML 配置文件

用法:
    python utils/logic_analyzer_bin2wave.py config.yaml
    python utils/logic_analyzer_bin2wave.py input.bin  # 使用默认配置

配置文件示例见: logic_analyzer_config_example.yaml
"""

import argparse
import numpy as np
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class Config:
    """配置类"""
    # 输入输出
    input_file: str = ""
    output_file: Optional[str] = None

    # 采样参数
    sample_rate: float = 500e6      # 逻辑分析仪采样率 (Hz)
    data_rate: float = 16e6         # 数据速率 (Hz)

    # 数据格式
    mode: str = "ddr"               # sdr 或 ddr
    data_bits: list = field(default_factory=lambda: list(range(10)))  # 数据位通道
    clk_channel: int = 10           # 时钟/数据指示通道
    bit_width: int = 10             # 数据位宽

    # DDR 模式配置
    rising_edge_data: str = "I"     # 上升沿采样的数据 (I 或 Q)
    falling_edge_data: str = "Q"    # 下降沿采样的数据 (I 或 Q)

    # 处理选项
    eye_align: bool = True          # 是否进行眼图对齐
    search_range: int = 15          # 眼图搜索范围

    # 数据清洗选项
    glitch_filter: bool = False     # 是否启用去毛刺
    glitch_threshold: float = 0.3   # 毛刺阈值: <1.0 为百分比(相对数据周期), >=1 为采样点数
    adaptive_filter: bool = True    # 眼图分析后自适应过滤不稳定位

    # 输出选项
    plot: bool = True               # 是否显示图表
    plot_eye: bool = False          # 是否显示眼图分析
    save_formats: list = field(default_factory=lambda: ["txt", "npy", "mat", "html", "mem"])


def load_config(config_path: str) -> Config:
    """从 YAML 文件加载配置"""
    try:
        import yaml
    except ImportError:
        print("[ERROR] 需要安装 pyyaml: pip install pyyaml")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    config = Config()

    # 映射 YAML 字段到 Config
    if 'input_file' in data:
        config.input_file = data['input_file']
    if 'output_file' in data:
        config.output_file = data['output_file']

    # 采样参数
    if 'sample_rate' in data:
        config.sample_rate = float(data['sample_rate'])
    if 'data_rate' in data:
        config.data_rate = float(data['data_rate'])

    # 数据格式
    if 'mode' in data:
        config.mode = data['mode'].lower()
    if 'data_bits' in data:
        config.data_bits = data['data_bits']
    if 'clk_channel' in data:
        config.clk_channel = data['clk_channel']
    if 'data_indicator' in data:  # 别名
        config.clk_channel = data['data_indicator']
    if 'bit_width' in data:
        config.bit_width = data['bit_width']

    # DDR 配置
    if 'rising_edge_data' in data:
        config.rising_edge_data = data['rising_edge_data'].upper()
    if 'falling_edge_data' in data:
        config.falling_edge_data = data['falling_edge_data'].upper()

    # 处理选项
    if 'eye_align' in data:
        config.eye_align = data['eye_align']
    if 'search_range' in data:
        config.search_range = data['search_range']

    # 数据清洗选项
    if 'glitch_filter' in data:
        config.glitch_filter = data['glitch_filter']
    if 'glitch_threshold' in data:
        config.glitch_threshold = data['glitch_threshold']
    if 'adaptive_filter' in data:
        config.adaptive_filter = data['adaptive_filter']

    # 输出选项
    if 'plot' in data:
        config.plot = data['plot']
    if 'plot_eye' in data:
        config.plot_eye = data['plot_eye']
    if 'save_formats' in data:
        config.save_formats = data['save_formats']

    return config


def create_default_config(bin_path: str) -> Config:
    """为 BIN 文件创建默认配置"""
    config = Config()
    config.input_file = bin_path
    return config


def load_binary_data(file_path: str, config: Config) -> tuple:
    """
    加载逻辑分析仪二进制数据

    BIN文件格式 (16通道):
    - 每2字节存储一次采样的16个通道
    - 第1字节: 通道0-7 (低位=通道0)
    - 第2字节: 通道8-15 (低位=通道8)

    Returns:
        (data_dict, clk_array, n_samples)
    """
    with open(file_path, 'rb') as f:
        raw_data = f.read()

    n_samples = len(raw_data) // 2
    print(f"[INFO] 读取 {n_samples} 个采样点")
    print(f"[INFO] 逻辑分析仪采样率: {config.sample_rate/1e6:.1f} MHz")
    print(f"[INFO] 数据速率: {config.data_rate/1e6:.1f} MHz")

    # 解析二进制数据
    data = np.frombuffer(raw_data, dtype=np.uint8).reshape(-1, 2)
    low_byte = data[:, 0]   # ch0-7
    high_byte = data[:, 1]  # ch8-15

    # 提取数据通道
    data_dict = {}
    for ch in config.data_bits:
        if ch < 8:
            data_dict[ch] = (low_byte >> ch) & 1
        else:
            data_dict[ch] = (high_byte >> (ch - 8)) & 1

    # 提取时钟/数据指示通道
    clk_ch = config.clk_channel
    if clk_ch < 8:
        clk_array = (low_byte >> clk_ch) & 1
    else:
        clk_array = (high_byte >> (clk_ch - 8)) & 1

    print(f"[INFO] 数据通道: {config.data_bits}")
    print(f"[INFO] 时钟/指示通道: ch{clk_ch}")
    print(f"[INFO] 模式: {config.mode.upper()}")

    # 计算时间信息
    duration = n_samples / config.sample_rate
    print(f"[INFO] 采样时长: {duration*1e6:.1f} us")

    return data_dict, clk_array, n_samples


def filter_glitches(data_dict: dict, config: Config, clk_array: np.ndarray = None) -> dict:
    """
    过滤数据通道中的毛刺

    检测数据中的短脉冲，将其视为毛刺并剔除。
    新增策略：如果短脉冲位于指示信号（clk）周期的前半段，则保留（可能是双稳态的第一个区间）

    Args:
        data_dict: 各通道的数据字典
        config: 配置对象
        clk_array: 时钟/指示信号数组（可选，用于前半段保护）

    Returns:
        过滤后的数据字典
    """
    if not config.glitch_filter:
        return data_dict

    # data_rate 是时钟翻转速率
    # DDR 模式: 真实数据速率 = data_rate (因为每个时钟边沿都采样)
    # SDR 模式: 真实数据速率 = data_rate
    # 数据通道的翻转周期至少应该是一个数据周期
    data_period_samples = config.sample_rate / config.data_rate

    # 毛刺阈值: 小于数据周期 * threshold 的脉冲视为毛刺
    min_pulse_width = int(data_period_samples * config.glitch_threshold)

    if min_pulse_width < 1:
        min_pulse_width = 1

    print(f"\n[数据清洗] 数据翻转周期: {data_period_samples:.1f} 采样点")
    print(f"[数据清洗] 毛刺阈值: < {min_pulse_width} 采样点 (< {config.glitch_threshold*100:.0f}% 数据周期)")

    # 预计算时钟边沿位置（用于前半段保护）
    clk_rising_edges = None
    clk_falling_edges = None
    half_period = int(data_period_samples / 2)

    if clk_array is not None:
        clk_diff = np.diff(clk_array.astype(np.int8))
        clk_rising_edges = np.where(clk_diff == 1)[0] + 1
        clk_falling_edges = np.where(clk_diff == -1)[0] + 1
        print(f"[数据清洗] 启用前半段保护: 时钟边沿后 {half_period} 采样点内的短脉冲不过滤")

    def is_in_first_half(pulse_start: int, pulse_end: int) -> bool:
        """检查脉冲是否在某个时钟周期的前半段"""
        if clk_rising_edges is None or clk_falling_edges is None:
            return False

        pulse_mid = (pulse_start + pulse_end) // 2

        # 检查是否在上升沿后的前半段
        for edge in clk_rising_edges:
            if edge <= pulse_mid < edge + half_period:
                return True

        # 检查是否在下降沿后的前半段
        for edge in clk_falling_edges:
            if edge <= pulse_mid < edge + half_period:
                return True

        return False

    filtered_dict = {}
    total_glitches = 0
    protected_count = 0

    for ch, data in data_dict.items():
        # 复制数据以免修改原始数据
        filtered_data = data.copy()
        glitch_count = 0
        ch_protected = 0

        # 迭代去毛刺，直到没有毛刺为止
        max_iterations = 100
        for iteration in range(max_iterations):
            # 找到所有翻转点
            diff = np.diff(filtered_data.astype(np.int8))
            edges = np.where(diff != 0)[0]

            if len(edges) < 2:
                break

            # 计算相邻翻转之间的间隔
            intervals = np.diff(edges)

            # 找出所有短脉冲 (间隔小于阈值)
            glitch_mask = intervals < min_pulse_width

            if not np.any(glitch_mask):
                break  # 没有毛刺了

            # 批量处理：标记需要恢复的区域
            # 为了避免重叠问题，只处理不相邻的毛刺
            to_fix = []
            i = 0
            while i < len(glitch_mask):
                if glitch_mask[i]:
                    start_idx = edges[i]
                    end_idx = edges[i + 1] if i + 1 < len(edges) else len(filtered_data) - 1

                    # 新增：检查是否在时钟周期的前半段，如果是则跳过（保护）
                    if is_in_first_half(start_idx, end_idx):
                        ch_protected += 1
                        i += 2  # 跳过这个脉冲
                        continue

                    original_value = filtered_data[start_idx]
                    to_fix.append((start_idx, end_idx, original_value))
                    i += 2  # 跳过下一个间隔，避免重叠
                else:
                    i += 1

            if not to_fix:
                break

            # 应用修复
            for start_idx, end_idx, original_value in to_fix:
                filtered_data[start_idx + 1:end_idx + 1] = original_value
                glitch_count += 1

        filtered_dict[ch] = filtered_data
        total_glitches += glitch_count
        protected_count += ch_protected

        if glitch_count > 0 or ch_protected > 0:
            msg = f"[数据清洗] ch{ch}: 修复 {glitch_count} 个毛刺"
            if ch_protected > 0:
                msg += f", 保护 {ch_protected} 个前半段脉冲"
            print(msg)

    print(f"[数据清洗] 总计修复 {total_glitches} 个毛刺, 保护 {protected_count} 个前半段脉冲")

    return filtered_dict


def adaptive_glitch_filter(data_dict: dict, clk_array: np.ndarray,
                           edges: np.ndarray, delays: dict,
                           edge_name: str, config: Config,
                           verbose: bool = False) -> dict:
    """
    基于眼图采样点的自适应毛刺过滤

    原理：在实际采样位置 (edge + delay) 检查数据是否与周围一致，
    如果不一致，则在该时钟周期内进行局部修复。

    Args:
        data_dict: 各通道数据字典
        clk_array: 时钟信号
        edges: 边沿位置数组
        delays: 各通道的采样延迟
        edge_name: 边沿名称 (用于日志)
        config: 配置
        verbose: 是否输出详细信息

    Returns:
        修复后的数据字典
    """
    # 计算时钟半周期
    if len(edges) < 2:
        return data_dict

    edge_intervals = np.diff(edges)
    half_period = int(np.median(edge_intervals))

    print(f"\n[自适应过滤] {edge_name}")
    print(f"[自适应过滤] 时钟半周期: {half_period} 采样点")

    filtered_dict = {}
    total_fixes = 0

    for bit_idx, data in data_dict.items():
        filtered_data = data.copy()
        delay = delays.get(bit_idx, 0)
        fixes = 0
        unstable_samples = []

        # 第一轮：多数表决修复
        for i, edge in enumerate(edges):
            sample_idx = edge + delay

            if sample_idx < 2 or sample_idx >= len(data) - 2:
                continue

            # 使用更宽的窗口检查稳定性 (±2采样点)
            window = filtered_data[sample_idx - 2:sample_idx + 3]
            val = filtered_data[sample_idx]

            # 计算窗口内与采样值相同的比例
            same_count = np.sum(window == val)

            # 如果采样点与周围不一致 (窗口内少于4个相同)
            if same_count < 4:
                unstable_samples.append((i, sample_idx, same_count))

                # 确定时钟周期边界
                start_idx = edge
                end_idx = edges[i + 1] if i + 1 < len(edges) else edge + half_period
                end_idx = min(end_idx, len(filtered_data))

                # 统计这个周期内的值分布
                segment = filtered_data[start_idx:end_idx]
                if len(segment) > 0:
                    ones = np.sum(segment)
                    zeros = len(segment) - ones

                    # 多数表决
                    dominant_val = 1 if ones > zeros else 0
                    ratio = max(ones, zeros) / len(segment)

                    # 如果有明显的主要值 (>60%)
                    if ratio > 0.6:
                        # 修复整个周期内与主要值不同的点
                        for j in range(start_idx, end_idx):
                            if filtered_data[j] != dominant_val:
                                filtered_data[j] = dominant_val
                                fixes += 1

        # 第二轮：时间上下文修复 - 使用相邻周期的值
        for i, edge in enumerate(edges):
            sample_idx = edge + delay

            if sample_idx < 3 or sample_idx >= len(filtered_data) - 3:
                continue

            val = filtered_data[sample_idx]
            # 扩展检查范围到 ±3
            extended_window = filtered_data[sample_idx - 3:sample_idx + 4]
            same_count = np.sum(extended_window == val)

            # 如果在更大窗口内仍然不稳定
            if same_count < 5:
                # 使用相邻的周期来决定这个值
                prev_edge_idx = i - 1 if i > 0 else 0
                next_edge_idx = i + 1 if i + 1 < len(edges) else i

                prev_sample = edges[prev_edge_idx] + delay
                next_sample = edges[next_edge_idx] + delay

                # 获取前后采样点的值
                votes = []
                if 0 <= prev_sample < len(filtered_data) and prev_sample != sample_idx:
                    votes.append(filtered_data[prev_sample])
                if 0 <= next_sample < len(filtered_data) and next_sample != sample_idx:
                    votes.append(filtered_data[next_sample])

                # 如果前后采样点一致，用它们来修复
                if len(votes) >= 2 and votes[0] == votes[1] and votes[0] != val:
                    start_idx = edge
                    end_idx = edges[i + 1] if i + 1 < len(edges) else edge + half_period
                    end_idx = min(end_idx, len(filtered_data))

                    expected_val = votes[0]
                    for j in range(start_idx, end_idx):
                        if filtered_data[j] != expected_val:
                            filtered_data[j] = expected_val
                            fixes += 1

        # 第三轮：锁存点修复 - 确保采样点位置数据稳定
        # 这一轮专门处理那些在采样点位置仍有跳变的情况
        for i, edge in enumerate(edges):
            sample_idx = edge + delay

            if sample_idx < 1 or sample_idx >= len(filtered_data) - 1:
                continue

            # 检查采样点及其邻近是否完全一致
            prev_val = filtered_data[sample_idx - 1]
            curr_val = filtered_data[sample_idx]
            next_val = filtered_data[sample_idx + 1]

            if not (prev_val == curr_val == next_val):
                # 采样点位置不稳定，使用滑动窗口投票
                window_start = max(0, sample_idx - 4)
                window_end = min(len(filtered_data), sample_idx + 5)
                window = filtered_data[window_start:window_end]

                ones = np.sum(window)
                zeros = len(window) - ones
                dominant_val = 1 if ones > zeros else 0

                # 只修复采样点附近的小范围
                fix_start = max(0, sample_idx - 2)
                fix_end = min(len(filtered_data), sample_idx + 3)

                for j in range(fix_start, fix_end):
                    if filtered_data[j] != dominant_val:
                        filtered_data[j] = dominant_val
                        fixes += 1

        filtered_dict[bit_idx] = filtered_data
        total_fixes += fixes

        if fixes > 0:
            print(f"[自适应过滤] data{bit_idx}: 修复 {fixes} 个采样点")

        if verbose and unstable_samples:
            print(f"[自适应过滤] data{bit_idx}: 发现 {len(unstable_samples)} 个不稳定采样位置")

    print(f"[自适应过滤] {edge_name} 总计修复 {total_fixes} 个采样点")

    return filtered_dict


def analyze_eye_diagram(data_dict: dict, clk_array: np.ndarray,
                        config: Config, iq_swap: bool = False) -> tuple:
    """
    基于眼图分析找到每路数据的最佳采样延迟

    Returns:
        (rising_delays, falling_delays, rising_edges, falling_edges):
        上升沿延迟、下降沿延迟、上升沿位置、下降沿位置
    """
    clk_diff = np.diff(clk_array.astype(np.int8))

    # 找到上升沿和下降沿
    rising_edges = np.where(clk_diff == 1)[0] + 1
    falling_edges = np.where(clk_diff == -1)[0] + 1
    all_edges = np.sort(np.concatenate([rising_edges, falling_edges]))

    if len(all_edges) < 2:
        print("[ERROR] 时钟边沿数量不足")
        return {}, {}

    # 计算时钟半周期
    edge_intervals = np.diff(all_edges)
    half_period_samples = int(np.median(edge_intervals))
    half_period_ns = half_period_samples / config.sample_rate * 1e9

    print(f"\n[眼图分析] 时钟半周期: ~{half_period_ns:.1f} ns ({half_period_samples} samples)")
    print(f"[眼图分析] 检测到 {len(rising_edges)} 个上升沿, {len(falling_edges)} 个下降沿")

    # 限制搜索范围
    actual_search_range = min(config.search_range, half_period_samples - 1)
    print(f"[眼图分析] 搜索范围: 边沿后 0 ~ {actual_search_range} 采样点")

    def analyze_edges(edges, edge_name):
        """对指定边沿进行眼图分析"""
        delays = {}
        all_offset_scores = {}  # 存储所有 bit 的得分

        print(f"\n  === {edge_name} ===")

        # 第一步：收集所有 bit 在各偏移位置的稳定性得分
        for bit_idx in sorted(data_dict.keys()):
            data = data_dict[bit_idx]
            offset_scores = {}

            for offset in range(0, actual_search_range):
                stable = 0
                total = 0

                for edge in edges:
                    sample_idx = edge + offset
                    if sample_idx < 1 or sample_idx >= len(data) - 1:
                        continue

                    # 检查该位置数据与相邻位置是否一致 (稳定)
                    if data[sample_idx - 1] == data[sample_idx] == data[sample_idx + 1]:
                        stable += 1
                    total += 1

                if total > 0:
                    offset_scores[offset] = stable / total

            all_offset_scores[bit_idx] = offset_scores

        # 第二步：计算每个偏移位置的综合得分（所有 bit 的最小稳定性）
        combined_scores = {}
        for offset in range(0, actual_search_range):
            min_score = 1.0
            for bit_idx in data_dict.keys():
                score = all_offset_scores[bit_idx].get(offset, 0)
                min_score = min(min_score, score)
            combined_scores[offset] = min_score

        # 第三步：找到综合最佳的时间窗口（优先选择靠前的区域）
        base_offset = 0
        if combined_scores:
            best_combined_score = max(combined_scores.values())
            # 找出所有综合得分达到最佳的偏移
            good_offsets = sorted([off for off, score in combined_scores.items()
                                  if score >= best_combined_score - 0.05])  # 5% 容差

            if good_offsets:
                # 找所有连续区域
                all_regions = []
                current_region = [good_offsets[0]]
                for i in range(1, len(good_offsets)):
                    if good_offsets[i] == good_offsets[i-1] + 1:
                        current_region.append(good_offsets[i])
                    else:
                        all_regions.append(current_region)
                        current_region = [good_offsets[i]]
                all_regions.append(current_region)

                # 优先选择第一个区域（靠近边沿的区域）
                # 这符合"双稳态时选择第一个稳定区间"的策略
                first_region = all_regions[0]

                # 选择窗口中心作为基准偏移
                base_offset = first_region[len(first_region) // 2]

                if len(all_regions) > 1:
                    print(f"  [最佳窗口] 发现 {len(all_regions)} 个稳定区域，选择第一个: 偏移 {first_region[0]}-{first_region[-1]}, 中心={base_offset}, 综合稳定性={best_combined_score*100:.1f}%")
                else:
                    print(f"  [最佳窗口] 偏移 {first_region[0]}-{first_region[-1]}, 中心={base_offset}, 综合稳定性={best_combined_score*100:.1f}%")

        # 第四步：在最佳窗口附近为每个 bit 选择具体的延迟
        for bit_idx in sorted(data_dict.keys()):
            offset_scores = all_offset_scores[bit_idx]

            if offset_scores:
                best_score = max(offset_scores.values())

                # 在基准偏移附近找最佳的位置 (±3 采样点范围内)
                search_start = max(0, base_offset - 3)
                search_end = min(actual_search_range, base_offset + 4)

                best_offset = base_offset
                best_local_score = offset_scores.get(base_offset, 0)

                for off in range(search_start, search_end):
                    score = offset_scores.get(off, 0)
                    if score > best_local_score:
                        best_local_score = score
                        best_offset = off

                delays[bit_idx] = best_offset

                # ASCII 眼图
                bar = ""
                for off in range(actual_search_range):
                    score = offset_scores.get(off, 0)
                    if score >= 0.95:
                        bar += "#"
                    elif score >= 0.85:
                        bar += "="
                    elif score >= 0.7:
                        bar += "+"
                    elif score >= 0.5:
                        bar += "-"
                    else:
                        bar += " "

                print(f"  data{bit_idx}: delay +{best_offset:2d}, stability {best_local_score*100:.1f}%  |{bar}|")
            else:
                delays[bit_idx] = 0
                print(f"  data{bit_idx}: unable to analyze")

        return delays

    # 根据配置决定边沿分配
    if config.rising_edge_data == "I":
        rising_name = f"上升沿 ({config.rising_edge_data})"
        falling_name = f"下降沿 ({config.falling_edge_data})"
    else:
        rising_name = f"上升沿 ({config.rising_edge_data})"
        falling_name = f"下降沿 ({config.falling_edge_data})"

    rising_delays = analyze_edges(rising_edges, rising_name)
    falling_delays = analyze_edges(falling_edges, falling_name)

    return rising_delays, falling_delays, rising_edges, falling_edges


def extract_data(data_dict: dict, clk_array: np.ndarray,
                 rising_delays: dict, falling_delays: dict,
                 config: Config) -> tuple:
    """
    从二进制数据提取波形数据

    Returns:
        对于 DDR 模式: (i_data, q_data, actual_sample_rate)
        对于 SDR 模式: (data, None, actual_sample_rate)
    """
    clk_diff = np.diff(clk_array.astype(np.int8))

    rising_edges = np.where(clk_diff == 1)[0] + 1
    falling_edges = np.where(clk_diff == -1)[0] + 1

    def extract_value(edge_idx: int, delays: dict, next_edge_idx: int = None,
                       prev_values: dict = None) -> tuple:
        """提取一个采样点的值

        策略（基于上下文判断）：
        clk 高电平=I数据，低电平=Q数据
        边沿前是上一路数据，边沿后是当前路数据

        1. 比较边沿前的值与边沿后开始时的值
        2. 如果相同：说明边沿后开始的值与上一路一致，是真实数据（后面的跳变是下一数据提前来了）
        3. 如果不同：说明边沿后开始的值是旧数据残留，真实数据在后面

        Args:
            edge_idx: 当前边沿位置
            delays: 各 bit 的延迟（作为参考/后备）
            next_edge_idx: 下一个边沿位置（用于确定周期范围）
            prev_values: 上一周期各 bit 的采样值 {bit_idx: value}（未使用，保留接口）

        Returns:
            (value, sample_positions): 采样值和每个 bit 的实际采样位置字典
        """
        value = 0
        sample_positions = {}  # bit_idx -> 实际采样位置

        # 确定当前周期的搜索范围
        if next_edge_idx is None:
            avg_delay = int(np.mean(list(delays.values()))) if delays else 8
            period_end = edge_idx + avg_delay + 5
        else:
            period_end = next_edge_idx

        for bit_idx in config.data_bits:
            if bit_idx not in data_dict:
                continue

            data = data_dict[bit_idx]
            delay = delays.get(bit_idx, 0)
            default_sample_idx = edge_idx + delay

            if default_sample_idx >= len(data):
                continue

            search_end = min(period_end, len(data) - 1)

            # 边沿前的值（边沿位置前一个采样点）- 这是上一路(I/Q)的数据
            before_edge_val = int(data[edge_idx - 1]) if edge_idx > 0 else None
            # 边沿后开始时的值
            start_val = int(data[edge_idx])

            # 找到周期内所有跳变点
            transitions = []
            for i in range(edge_idx, search_end - 1):
                if int(data[i]) != int(data[i + 1]):
                    transitions.append(i + 1)

            # 采样逻辑：
            # 1. 首先在眼图最佳延迟位置采样
            # 2. 检查采样点是否稳定（前后值一致）
            # 3. 如果不稳定，使用周期内占比判断（提取规则8/9）

            sample_val = int(data[default_sample_idx])

            # 直接使用眼图最佳位置的采样值
            # 眼图分析已找到最稳定的采样点，信任该结果
            bit_val = sample_val

            sample_pos = default_sample_idx

            bit_pos = config.data_bits.index(bit_idx)
            value |= (bit_val << bit_pos)
            sample_positions[bit_idx] = sample_pos

        return value, sample_positions

    if config.mode == "ddr":
        # DDR 模式: 上升沿和下降沿各采样一次
        if config.rising_edge_data == "I":
            i_edges, i_delays = rising_edges, rising_delays
            q_edges, q_delays = falling_edges, falling_delays
        else:
            q_edges, q_delays = rising_edges, rising_delays
            i_edges, i_delays = falling_edges, falling_delays

        print(f"[INFO] 检测到 {len(i_edges)} 个 I 采样点, {len(q_edges)} 个 Q 采样点")

        # 合并所有边沿并排序，用于确定每个周期的范围
        all_edges_sorted = np.sort(np.concatenate([rising_edges, falling_edges]))

        def get_next_edge(edge_idx):
            """获取下一个边沿位置"""
            pos = np.searchsorted(all_edges_sorted, edge_idx, side='right')
            if pos < len(all_edges_sorted):
                return all_edges_sorted[pos]
            return None

        # 提取 I 值和采样位置
        i_values = []
        i_sample_positions = []  # 每个采样的位置信息列表
        prev_i_bits = {}  # 上一次各 bit 的采样值
        for idx in i_edges:
            if idx + config.search_range < len(clk_array):
                next_edge = get_next_edge(idx)
                val, positions = extract_value(idx, i_delays, next_edge, prev_i_bits)
                i_values.append(val)
                i_sample_positions.append(positions)
                # 更新上一次的采样值
                for bit_idx in config.data_bits:
                    if bit_idx in positions:
                        prev_i_bits[bit_idx] = int(data_dict[bit_idx][positions[bit_idx]])

        # 提取 Q 值和采样位置
        q_values = []
        q_sample_positions = []
        prev_q_bits = {}  # 上一次各 bit 的采样值
        for idx in q_edges:
            if idx + config.search_range < len(clk_array):
                next_edge = get_next_edge(idx)
                val, positions = extract_value(idx, q_delays, next_edge, prev_q_bits)
                q_values.append(val)
                q_sample_positions.append(positions)
                # 更新上一次的采样值
                for bit_idx in config.data_bits:
                    if bit_idx in positions:
                        prev_q_bits[bit_idx] = int(data_dict[bit_idx][positions[bit_idx]])

        # 对齐长度
        min_len = min(len(i_values), len(q_values))
        i_data = np.array(i_values[:min_len], dtype=np.uint16)
        q_data = np.array(q_values[:min_len], dtype=np.uint16)
        i_sample_positions = i_sample_positions[:min_len]
        q_sample_positions = q_sample_positions[:min_len]

        # DDR 模式: data_rate 是时钟翻转速率，真实 IQ 采样率 = data_rate / 2
        # (每两个翻转产生一对 IQ 样本)
        actual_sample_rate = config.data_rate / 2

        # 验证采样率 (通过测量时钟频率)
        if len(rising_edges) >= 2:
            # 测量的是上升沿频率 = data_rate / 2
            measured_rising_freq = config.sample_rate / np.median(np.diff(rising_edges))
            print(f"[INFO] 测量时钟频率: {measured_rising_freq/1e6:.3f} MHz (上升沿)")
            # IQ 采样率 = 上升沿频率 (每个上升沿一个 I 或 Q)
            actual_sample_rate = measured_rising_freq

        print(f"[INFO] IQ 采样率: {actual_sample_rate/1e6:.3f} MHz")
        print(f"[INFO] 提取 {min_len} 个 IQ 采样点")

        # 返回数据和采样位置信息
        sample_info = {
            'i_edges': i_edges[:min_len],
            'q_edges': q_edges[:min_len],
            'i_sample_positions': i_sample_positions,
            'q_sample_positions': q_sample_positions,
        }

        return i_data, q_data, actual_sample_rate, sample_info

    else:
        # SDR 模式: 仅在一个边沿采样
        edges = rising_edges
        delays = rising_delays

        print(f"[INFO] 检测到 {len(edges)} 个采样点")

        # 合并所有边沿用于确定周期范围
        all_edges_sorted = np.sort(np.concatenate([rising_edges, falling_edges]))

        def get_next_edge(edge_idx):
            pos = np.searchsorted(all_edges_sorted, edge_idx, side='right')
            if pos < len(all_edges_sorted):
                return all_edges_sorted[pos]
            return None

        values = []
        sample_positions = []
        prev_bits = {}  # 上一次各 bit 的采样值
        for idx in edges:
            if idx + config.search_range < len(clk_array):
                next_edge = get_next_edge(idx)
                val, positions = extract_value(idx, delays, next_edge, prev_bits)
                values.append(val)
                sample_positions.append(positions)
                # 更新上一次的采样值
                for bit_idx in config.data_bits:
                    if bit_idx in positions:
                        prev_bits[bit_idx] = int(data_dict[bit_idx][positions[bit_idx]])

        data = np.array(values, dtype=np.uint16)

        actual_sample_rate = config.data_rate

        if len(rising_edges) >= 2:
            measured_clk_freq = config.sample_rate / np.median(np.diff(rising_edges))
            actual_sample_rate = measured_clk_freq

        print(f"[INFO] 采样率: {actual_sample_rate/1e6:.3f} MHz")
        print(f"[INFO] 提取 {len(data)} 个采样点")

        sample_info = {
            'edges': edges[:len(data)],
            'sample_positions': sample_positions,
        }

        return data, None, actual_sample_rate, sample_info


def unsigned_to_signed(data: np.ndarray, bit_width: int) -> np.ndarray:
    """将无符号整数转换为有符号整数 (补码格式)"""
    signed_data = data.astype(np.int32)
    max_val = 1 << (bit_width - 1)
    signed_data[signed_data >= max_val] -= (1 << bit_width)
    return signed_data


def filter_iq_spikes(i_data: np.ndarray, q_data: np.ndarray,
                     config: Config) -> tuple:
    """
    过滤IQ数据中的尖刺毛刺

    使用孤立点检测：如果某个采样点与前后邻居差异都很大，但邻居之间很接近，
    则该点是毛刺，用邻居均值替换。

    Args:
        i_data: I路数据
        q_data: Q路数据
        config: 配置

    Returns:
        (filtered_i, filtered_q)
    """
    # 转换为有符号数进行处理
    i_signed = unsigned_to_signed(i_data.copy(), config.bit_width)
    q_signed = unsigned_to_signed(q_data.copy(), config.bit_width)

    # 毛刺检测阈值: 满量程的 3%
    max_val = 1 << (config.bit_width - 1)
    threshold = int(max_val * 0.03)  # 3% 满量程
    if threshold < 15:
        threshold = 15  # 最小阈值

    print(f"[IQ过滤] 毛刺检测阈值: {threshold}")

    def fix_spikes(arr, name):
        """检测并修复孤立毛刺"""
        arr = arr.copy()
        total_fixed = 0

        # 多轮修复，直到没有毛刺
        for round_num in range(10):
            fixed = 0
            for i in range(2, len(arr) - 2):
                # 当前点与前后邻居的差异
                diff_prev = abs(arr[i] - arr[i-1])
                diff_next = abs(arr[i] - arr[i+1])
                # 邻居之间的差异
                neighbor_diff = abs(arr[i-1] - arr[i+1])

                # 计算邻居均值
                neighbor_avg = (arr[i-1] + arr[i+1]) // 2
                deviation = abs(arr[i] - neighbor_avg)

                # 孤立尖刺检测:
                # 1. 当前点与前后都有较大差异 (>threshold)
                # 2. 邻居之间差异很小 (< threshold/3)
                # 3. 偏离均值超过阈值
                if diff_prev > threshold and diff_next > threshold:
                    if neighbor_diff < threshold // 3 and deviation > threshold:
                        arr[i] = neighbor_avg
                        fixed += 1

            total_fixed += fixed
            if fixed == 0:
                break

        if total_fixed > 0:
            print(f"[IQ过滤] {name}: 修复 {total_fixed} 个毛刺")

        return arr

    i_filtered = fix_spikes(i_signed, "I路")
    q_filtered = fix_spikes(q_signed, "Q路")

    # 转回无符号数
    i_result = i_filtered.copy()
    q_result = q_filtered.copy()
    i_result[i_result < 0] += (1 << config.bit_width)
    q_result[q_result < 0] += (1 << config.bit_width)

    return i_result.astype(np.uint16), q_result.astype(np.uint16)


def save_data(data1: np.ndarray, data2: Optional[np.ndarray],
              output_path: str, sample_rate: float, config: Config):
    """保存数据"""
    is_iq = data2 is not None

    if is_iq:
        i_signed = unsigned_to_signed(data1, config.bit_width)
        q_signed = unsigned_to_signed(data2, config.bit_width)
    else:
        data_signed = unsigned_to_signed(data1, config.bit_width)

    # TXT
    if "txt" in config.save_formats:
        txt_path = f"{output_path}.txt"
        hex_width = (config.bit_width + 3) // 4
        with open(txt_path, 'w') as f:
            f.write(f"# Wave Data - {len(data1)} samples @ {sample_rate/1e6:.3f} MHz\n")
            f.write(f"# Bit width: {config.bit_width}, signed (MSB is sign bit)\n")
            if is_iq:
                f.write(f"# Format: I (hex), Q (hex), I (signed), Q (signed)\n")
                for i_u, q_u, i_s, q_s in zip(data1, data2, i_signed, q_signed):
                    f.write(f"0x{i_u:0{hex_width}X}, 0x{q_u:0{hex_width}X}, {i_s:5d}, {q_s:5d}\n")
            else:
                f.write(f"# Format: data (hex), data (signed)\n")
                for d_u, d_s in zip(data1, data_signed):
                    f.write(f"0x{d_u:0{hex_width}X}, {d_s:5d}\n")
        print(f"[OUTPUT] TXT: {txt_path}")

    # NPY
    if "npy" in config.save_formats:
        npy_path = f"{output_path}.npy"
        if is_iq:
            np.save(npy_path, np.column_stack([data1, data2]))
        else:
            np.save(npy_path, data1)
        print(f"[OUTPUT] NPY: {npy_path}")

    # MAT
    if "mat" in config.save_formats:
        try:
            from scipy.io import savemat
            mat_path = f"{output_path}.mat"
            if is_iq:
                savemat(mat_path, {
                    'I': data1, 'Q': data2,
                    'I_signed': i_signed, 'Q_signed': q_signed,
                    'fs': sample_rate, 'bit_width': config.bit_width,
                })
            else:
                savemat(mat_path, {
                    'data': data1, 'data_signed': data_signed,
                    'fs': sample_rate, 'bit_width': config.bit_width,
                })
            print(f"[OUTPUT] MAT: {mat_path}")
        except ImportError:
            pass

    # MEM (Verilog $readmemh 格式，BLEStudio 兼容)
    if "mem" in config.save_formats:
        mem_path = f"{output_path}.mem"
        if is_iq:
            # IQ 打包: 高位 I，低位 Q
            total_bits = config.bit_width * 2
            num_hex = (total_bits + 3) // 4
            mask = (1 << config.bit_width) - 1
            with open(mem_path, 'w', newline='\n') as f:
                for i_val, q_val in zip(data1, data2):
                    i_u = int(i_val) & mask
                    q_u = int(q_val) & mask
                    packed = (i_u << config.bit_width) | q_u
                    f.write(f"{packed:0{num_hex}X}\n")
        else:
            # 单通道数据
            num_hex = (config.bit_width + 3) // 4
            mask = (1 << config.bit_width) - 1
            with open(mem_path, 'w', newline='\n') as f:
                for val in data1:
                    f.write(f"{int(val) & mask:0{num_hex}X}\n")
        print(f"[OUTPUT] MEM: {mem_path}")


def plot_data(data1: np.ndarray, data2: Optional[np.ndarray],
              sample_rate: float, config: Config, output_path: str):
    """绘制数据图表"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("[WARN] plotly 不可用，跳过绘图")
        return

    is_iq = data2 is not None

    if is_iq:
        i_signed = unsigned_to_signed(data1, config.bit_width)
        q_signed = unsigned_to_signed(data2, config.bit_width)
    else:
        data_signed = unsigned_to_signed(data1, config.bit_width)

    t = np.arange(len(data1)) / sample_rate * 1e6

    if is_iq:
        # IQ 数据: 2x2 布局
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                f'IQ Time Domain ({config.bit_width}-bit signed)',
                'IQ Constellation',
                'Spectrum',
                'Instantaneous Frequency'
            ),
            specs=[
                [{"type": "scatter"}, {"type": "scatter"}],
                [{"type": "scatter"}, {"type": "scatter"}]
            ],
            row_heights=[0.5, 0.5],
            column_widths=[0.6, 0.4],
            horizontal_spacing=0.08,
            vertical_spacing=0.12
        )

        # 时域
        fig.add_trace(go.Scattergl(x=t, y=i_signed, mode='lines', name='I',
                                   line=dict(color='blue', width=1)), row=1, col=1)
        fig.add_trace(go.Scattergl(x=t, y=q_signed, mode='lines', name='Q',
                                   line=dict(color='red', width=1)), row=1, col=1)
        fig.update_xaxes(title_text='Time (us)', row=1, col=1)
        fig.update_yaxes(title_text='Value', row=1, col=1)

        # 星座图
        fig.add_trace(go.Scattergl(x=i_signed, y=q_signed, mode='markers',
                                   marker=dict(size=3, color=np.arange(len(i_signed)),
                                               colorscale='Viridis', opacity=0.7),
                                   showlegend=False), row=1, col=2)
        fig.update_xaxes(title_text='I', row=1, col=2)
        fig.update_yaxes(title_text='Q', scaleanchor="x2", scaleratio=1, row=1, col=2)

        # 频谱
        max_val = 1 << (config.bit_width - 1)
        iq_signal = (i_signed + 1j * q_signed) / max_val
        fft_size = min(4096, len(iq_signal))
        if fft_size > 0:
            spectrum = np.fft.fftshift(np.fft.fft(iq_signal[:fft_size]))
            freq = np.fft.fftshift(np.fft.fftfreq(fft_size, 1/sample_rate)) / 1e6
            psd = 20 * np.log10(np.abs(spectrum) + 1e-10)
            psd = psd - np.max(psd)
            fig.add_trace(go.Scattergl(x=freq, y=psd, mode='lines',
                                       line=dict(color='green', width=1),
                                       showlegend=False), row=2, col=1)
        fig.update_xaxes(title_text='Frequency (MHz)', row=2, col=1)
        fig.update_yaxes(title_text='Power (dB)', range=[-80, 5], row=2, col=1)

        # 瞬时频率
        if len(iq_signal) > 1:
            phase = np.unwrap(np.angle(iq_signal))
            freq_inst = np.diff(phase) * sample_rate / (2 * np.pi) / 1e3
            fig.add_trace(go.Scattergl(x=t[:-1], y=freq_inst, mode='lines',
                                       line=dict(color='magenta', width=1),
                                       showlegend=False), row=2, col=2)
        fig.update_xaxes(title_text='Time (us)', row=2, col=2)
        fig.update_yaxes(title_text='Frequency (kHz)', row=2, col=2)

        title = "IQ Analysis"

    else:
        # 单通道数据
        fig = make_subplots(rows=2, cols=1,
                           subplot_titles=('Time Domain', 'Spectrum'),
                           vertical_spacing=0.12)

        fig.add_trace(go.Scattergl(x=t, y=data_signed, mode='lines',
                                   line=dict(color='blue', width=1)), row=1, col=1)
        fig.update_xaxes(title_text='Time (us)', row=1, col=1)
        fig.update_yaxes(title_text='Value', row=1, col=1)

        # 频谱
        fft_size = min(4096, len(data_signed))
        if fft_size > 0:
            spectrum = np.fft.fft(data_signed[:fft_size])
            freq = np.fft.fftfreq(fft_size, 1/sample_rate) / 1e6
            psd = 20 * np.log10(np.abs(spectrum) + 1e-10)
            psd = psd - np.max(psd)
            fig.add_trace(go.Scattergl(x=freq[:fft_size//2], y=psd[:fft_size//2],
                                       mode='lines', line=dict(color='green', width=1),
                                       showlegend=False), row=2, col=1)
        fig.update_xaxes(title_text='Frequency (MHz)', row=2, col=1)
        fig.update_yaxes(title_text='Power (dB)', range=[-80, 5], row=2, col=1)

        title = "Wave Analysis"

    fig.update_layout(
        height=900,
        title_text=title,
        title_x=0.5,
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.3),
        margin=dict(l=60, r=40, t=80, b=60),
        autosize=True
    )

    # 保存
    if "html" in config.save_formats:
        html_path = f"{output_path}.html"
        fig.write_html(html_path, config={'responsive': True})
        print(f"[OUTPUT] HTML: {html_path}")

    if config.plot:
        fig.show()


def generate_example_config(output_path: str):
    """生成示例配置文件"""
    example = """# Kingst 逻辑分析仪数据转波形配置文件
# ==========================================

# 输入输出文件
input_file: "template_data/test.bin"
output_file: "template_data/test_iq"  # 可选，默认为 input_file + "_wave"

# 采样参数
sample_rate: 500e6    # 逻辑分析仪采样率 (Hz)
data_rate: 16e6       # 数据速率 (Hz)

# 数据格式
mode: ddr             # sdr 或 ddr
data_bits: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]  # 数据位通道列表
clk_channel: 10       # 时钟通道 (SDR) 或数据指示通道 (DDR)
# data_indicator: 10  # clk_channel 的别名
bit_width: 10         # 数据位宽

# DDR 模式配置 (仅 mode: ddr 时有效)
rising_edge_data: I   # 上升沿采样的数据: I 或 Q
falling_edge_data: Q  # 下降沿采样的数据: I 或 Q

# 处理选项
eye_align: true       # 是否进行眼图对齐
search_range: 15      # 眼图搜索范围 (采样点数)

# 数据清洗选项
glitch_filter: false  # 是否启用去毛刺
glitch_threshold: 0.3 # 毛刺阈值: <1.0 为百分比(如 0.3 = 30% 数据周期), >=1 为采样点数

# 输出选项
plot: true            # 是否显示图表
plot_eye: false       # 是否显示眼图分析图
save_formats:         # 保存格式列表
  - txt
  - npy
  - mat
  - html
  - mem               # Verilog $readmemh 格式, BLEStudio 兼容
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(example)
    print(f"[OUTPUT] 示例配置文件: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Kingst 逻辑分析仪 BIN 数据转波形',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 使用配置文件
    python utils/logic_analyzer_bin2wave.py config.yaml

    # 直接处理 BIN 文件 (使用默认配置)
    python utils/logic_analyzer_bin2wave.py test.bin

    # 生成示例配置文件
    python utils/logic_analyzer_bin2wave.py --generate-config config.yaml
        """
    )

    parser.add_argument('input', nargs='?', help='配置文件 (.yaml) 或数据文件 (.bin)')
    parser.add_argument('--generate-config', '-g', metavar='PATH',
                        help='生成示例配置文件')
    parser.add_argument('--no-plot', action='store_true', help='不显示图表')

    args = parser.parse_args()

    # 生成示例配置
    if args.generate_config:
        generate_example_config(args.generate_config)
        return

    if not args.input:
        parser.print_help()
        return

    input_path = Path(args.input)

    # 判断输入类型
    if input_path.suffix.lower() == '.yaml' or input_path.suffix.lower() == '.yml':
        config = load_config(args.input)
    elif input_path.suffix.lower() == '.bin':
        config = create_default_config(args.input)
    else:
        print(f"[ERROR] 不支持的文件类型: {input_path.suffix}")
        print("        支持 .yaml/.yml (配置文件) 或 .bin (数据文件)")
        sys.exit(1)

    # 覆盖命令行参数
    if args.no_plot:
        config.plot = False

    # 确定输出路径
    if config.output_file is None:
        input_p = Path(config.input_file)
        config.output_file = str(input_p.parent / f"{input_p.stem}_wave")

    # 开始处理
    print("=" * 60)
    print("Kingst Logic Analyzer BIN to Wave Converter")
    print("=" * 60)

    # 加载数据
    data_dict, clk_array, n_samples = load_binary_data(config.input_file, config)

    # 数据清洗 (去毛刺)
    if config.glitch_filter:
        print("\n" + "=" * 60)
        print("Glitch Filter")
        print("=" * 60)
        data_dict = filter_glitches(data_dict, config, clk_array)

    # 眼图分析
    if config.eye_align:
        print("\n" + "=" * 60)
        print("Eye Diagram Analysis")
        print("=" * 60)
        rising_delays, falling_delays, rising_edges, falling_edges = analyze_eye_diagram(
            data_dict, clk_array, config
        )
        print(f"\n[INFO] 上升沿延迟: {rising_delays}")
        print(f"[INFO] 下降沿延迟: {falling_delays}")

        # 自适应过滤：基于眼图分析结果进行二次过滤
        if config.adaptive_filter:
            print("\n" + "=" * 60)
            print("Adaptive Glitch Filter")
            print("=" * 60)

            # 根据配置决定哪个边沿对应哪个数据
            if config.rising_edge_data == "I":
                rising_name = "I路 (上升沿)"
                falling_name = "Q路 (下降沿)"
            else:
                rising_name = "Q路 (上升沿)"
                falling_name = "I路 (下降沿)"

            # 多轮自适应过滤，直到没有改进为止
            max_rounds = 5
            for round_num in range(max_rounds):
                prev_data_dict = {k: v.copy() for k, v in data_dict.items()}

                # 对两个边沿分别进行自适应过滤
                data_dict = adaptive_glitch_filter(
                    data_dict, clk_array, rising_edges, rising_delays,
                    rising_name, config
                )
                data_dict = adaptive_glitch_filter(
                    data_dict, clk_array, falling_edges, falling_delays,
                    falling_name, config
                )

                # 检查是否有改进
                changed = False
                for k in data_dict:
                    if not np.array_equal(data_dict[k], prev_data_dict[k]):
                        changed = True
                        break

                if not changed:
                    print(f"\n[自适应过滤] 第 {round_num + 1} 轮无改进，停止迭代")
                    break
                else:
                    print(f"\n[自适应过滤] 完成第 {round_num + 1} 轮，继续下一轮...")

            # 重新进行眼图分析以验证效果
            print("\n[验证] 重新进行眼图分析...")
            rising_delays, falling_delays, _, _ = analyze_eye_diagram(
                data_dict, clk_array, config
            )
            print(f"\n[INFO] 上升沿延迟: {rising_delays}")
            print(f"[INFO] 下降沿延迟: {falling_delays}")
    else:
        # 使用默认延迟
        rising_delays = {bit: 0 for bit in config.data_bits}
        falling_delays = {bit: 0 for bit in config.data_bits}

    # 提取数据
    print("\n" + "=" * 60)
    print("Data Extraction")
    print("=" * 60)
    data1, data2, actual_sample_rate, sample_info = extract_data(
        data_dict, clk_array, rising_delays, falling_delays, config
    )

    # 保存数据
    print("\n" + "=" * 60)
    print("Save Output")
    print("=" * 60)
    save_data(data1, data2, config.output_file, actual_sample_rate, config)

    # 绘图
    if config.plot or "html" in config.save_formats:
        plot_data(data1, data2, actual_sample_rate, config, config.output_file)

    print(f"\n[DONE] 转换完成")


if __name__ == '__main__':
    main()
