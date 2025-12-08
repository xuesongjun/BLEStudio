import numpy as np
from ble_studio.modulator import BLEModulator, ModulatorConfig
from ble_studio.packet import BLEPhyMode
from ble_studio.visualizer import BLEVisualizer

# 直接生成 0x55 pattern 信号
config = ModulatorConfig(
    phy_mode=BLEPhyMode.LE_1M,
    sample_rate=8e6,
    modulation_index=0.5,
    bt=0.5
)
mod = BLEModulator(config)

# 模拟完整包结构: preamble(8) + AA(32) + header(16) + payload(37*8)
preamble = np.array([1,0,1,0,1,0,1,0])
aa = np.array([0,1,1,0,1,0,1,1,0,1,1,1,1,1,0,1,1,0,0,1,0,0,0,1,0,1,1,1,0,0,0,1])  # 0x8E89BED6
header = np.array([0,0,1,0,0,1,0,1,0,1,0,0,1,0,1,0])  # 随便写的
payload = np.array([0,1] * (37*4))  # 0x55 pattern, 37 bytes = 296 bits

bits = np.concatenate([preamble, aa, header, payload])
iq = mod.modulate(bits)

# 计算 RF 指标
viz = BLEVisualizer()
metrics = viz.calculate_rf_metrics(
    signal=iq,
    sample_rate=8e6,
    samples_per_symbol=8,
    symbol_rate=1e6,
    payload_type='PATTERN_10101010'
)

print('RF 测试指标 (修复后):')
print(f'  ΔF1avg: {metrics["delta_f1_avg"]:.1f} kHz (标准: 225-275 kHz)')
print(f'  ΔF1max: {metrics["delta_f1_max"]:.1f} kHz')
print(f'  ΔF2avg: {metrics["delta_f2_avg"]:.1f} kHz')
print(f'  ΔF2max: {metrics["delta_f2_max"]:.1f} kHz (标准: >= 185 kHz)')
print(f'  ΔF2/ΔF1: {metrics["delta_f2_ratio"]:.3f} (标准: >= 0.8)')
print(f'  ICFT: {metrics["icft"]:.1f} kHz (标准: |ICFT| <= 150 kHz)')
print(f'  Freq Drift: {metrics["freq_drift"]:.1f} kHz')
print()

# 与 rf_metrics_test.py 的结果对比
print('对比 rf_metrics_test.py 的结果:')
print('  应该是 ΔF1avg ≈ 250 kHz')