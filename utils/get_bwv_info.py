import numpy as np
from scipy.io import loadmat

mat = loadmat(r'C:\workspace\BLEStudio\results\BLE_1M.bwv')
wave = mat['wave'].squeeze()

print(f'总采样点数: {len(wave)}')
print(f'采样率: 120 MHz')
print(f'总时长: {len(wave) / 120e6 * 1e6:.1f} us')

# 计算信号功率分布
power = np.abs(wave) ** 2
threshold = np.max(power) * 0.01  # 1% 阈值

# 找到信号开始和结束位置
signal_mask = power > threshold
if np.any(signal_mask):
    start_idx = np.argmax(signal_mask)
    end_idx = len(signal_mask) - np.argmax(signal_mask[::-1]) - 1
    
    start_us = start_idx / 120e6 * 1e6
    end_us = end_idx / 120e6 * 1e6
    duration_us = end_us - start_us
    
    print(f'\\n信号位置:')
    print(f'  开始: {start_us:.1f} us (采样点 {start_idx})')
    print(f'  结束: {end_us:.1f} us (采样点 {end_idx})')
    print(f'  持续: {duration_us:.1f} us')
    
    # BLE 1M PHY: 1 Mbps = 1 bit/us
    # 一个完整的 DTM 包 (37 bytes payload): 前导(8) + AA(32) + Header(16) + Length(8) + Payload(37*8=296) + CRC(24) = 384 bits = 384 us
    print(f'\\n参考: BLE 1M PHY 37字节 payload 的包长约 384 us')
    
    if duration_us < 300:
        print(f'\\n警告: 信号时长 ({duration_us:.0f} us) 不足以包含完整的 BLE 数据包!')