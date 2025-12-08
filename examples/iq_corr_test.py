from ble_studio import export_iq_txt, import_iq_txt
import numpy as np

# 创建测试信号
t = np.arange(100)
signal = np.exp(1j * 2 * np.pi * 0.1 * t) * 0.8

# 导出
export_iq_txt(signal, 'results/test_iq.txt', bit_width=12)

# 导入
imported = import_iq_txt('results/test_iq.txt', bit_width=12, skip_lines=7)

# 验证
print(f'原始信号[0]: {signal[0]:.4f}')
print(f'导入信号[0]: {imported[0]:.4f}')
print(f'原始 RMS: {np.sqrt(np.mean(np.abs(signal)**2)):.4f}')
print(f'导入 RMS: {np.sqrt(np.mean(np.abs(imported)**2)):.4f}')

# 相关性
corr = np.abs(np.corrcoef(signal.real, imported.real)[0,1])
print(f'I 相关性: {corr:.6f}')
corr_q = np.abs(np.corrcoef(signal.imag, imported.imag)[0,1])
print(f'Q 相关性: {corr_q:.6f}')
print('测试通过!' if corr > 0.99 else '测试失败')