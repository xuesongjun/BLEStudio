import numpy as np
from scipy.io import loadmat

mat = loadmat(r"C:\workspace\BLEStudio\results\BLE_1M.bwv")
wave = mat["wave"].squeeze()
fs = 120e6

# 检查信号幅度分布
amplitude = np.abs(wave)
print(f"幅度最大值: {np.max(amplitude):.4f}")
print(f"幅度均值: {np.mean(amplitude):.4f}")

# 使用不同阈值
for thresh_pct in [0.01, 0.05, 0.1]:
    threshold = np.max(amplitude) * thresh_pct
    signal_start = np.argmax(amplitude > threshold)
    print(f"\n阈值 {thresh_pct*100}%: {threshold:.4f}")
    print(f"  信号开始: sample {signal_start} ({signal_start/fs*1e6:.1f} μs)")

# 检查前 2000 个采样点的幅度
print(f"\n前 2000 点幅度:")
for i in range(0, 2000, 200):
    print(f"  [{i:4d}-{i+200:4d}]: max={np.max(amplitude[i:i+200]):.4f}, mean={np.mean(amplitude[i:i+200]):.4f}")
