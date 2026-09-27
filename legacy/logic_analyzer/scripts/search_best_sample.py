import numpy as np

file_path = 'C:/workspace/BLEStudio/template_data/test.bin'

with open(file_path, 'rb') as f:
    data = f.read()

raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 2)
low_byte = raw[:, 0]
high_byte = raw[:, 1]

# 提取各通道
channels = {}
for ch in range(10):
    if ch < 8:
        channels[ch] = (low_byte >> ch) & 1
    else:
        channels[ch] = (high_byte >> (ch - 8)) & 1

clk = (high_byte >> 2) & 1  # ch10

# 找边沿
clk_diff = np.diff(clk.astype(np.int8))
rising_edges = np.where(clk_diff == 1)[0] + 1
falling_edges = np.where(clk_diff == -1)[0] + 1

print(f'上升沿 (I): {len(rising_edges)} 个')
print(f'下降沿 (Q): {len(falling_edges)} 个')

# 分别对上升沿和下降沿分析每个 bit 的最佳延迟
search_range = 14

print(f'\\n=== 上升沿 (I) 的最佳采样延迟 ===')
i_delays = {}
for bit in range(10):
    data_ch = channels[bit]
    best_offset = 0
    best_stability = 0
    
    for offset in range(search_range):
        stable = 0
        total = 0
        for edge in rising_edges:
            idx = edge + offset
            if idx < 1 or idx >= len(data_ch) - 1:
                continue
            if data_ch[idx-1] == data_ch[idx] == data_ch[idx+1]:
                stable += 1
            total += 1
        
        if total > 0:
            stability = stable / total
            if stability > best_stability:
                best_stability = stability
                best_offset = offset
    
    i_delays[bit] = best_offset
    print(f'  data{bit}: delay +{best_offset:2d}, stability {best_stability*100:.1f}%')

print(f'\\n=== 下降沿 (Q) 的最佳采样延迟 ===')
q_delays = {}
for bit in range(10):
    data_ch = channels[bit]
    best_offset = 0
    best_stability = 0
    
    for offset in range(search_range):
        stable = 0
        total = 0
        for edge in falling_edges:
            idx = edge + offset
            if idx < 1 or idx >= len(data_ch) - 1:
                continue
            if data_ch[idx-1] == data_ch[idx] == data_ch[idx+1]:
                stable += 1
            total += 1
        
        if total > 0:
            stability = stable / total
            if stability > best_stability:
                best_stability = stability
                best_offset = offset
    
    q_delays[bit] = best_offset
    print(f'  data{bit}: delay +{best_offset:2d}, stability {best_stability*100:.1f}%')

print(f'\\n上升沿延迟: {i_delays}')
print(f'下降沿延迟: {q_delays}')