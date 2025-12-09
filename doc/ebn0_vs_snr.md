# Eb/N0 与 SNR 的区别

## 概述

在数字通信系统中，**Eb/N0** 和 **SNR** 是两个最常用的信噪比度量，但它们有本质区别：

| 指标 | 全称 | 含义 | 单位 |
|------|------|------|------|
| **Eb/N0** | Energy per bit to Noise power spectral density | 每比特能量与噪声功率谱密度之比 | dB |
| **SNR** | Signal-to-Noise Ratio | 信号功率与噪声功率之比 | dB |

## 物理意义

### Eb/N0 (每比特能量/噪声功率谱密度)

```
Eb/N0 = (信号功率 / 比特率) / (噪声功率 / 带宽)
      = (Ps / Rb) / (Pn / B)
      = (Ps / Pn) × (B / Rb)
```

- **Eb**: 每个比特的能量 (Joules/bit)
- **N0**: 噪声功率谱密度 (Watts/Hz)
- **与带宽无关**: 归一化到每比特，是物理层性能的标准度量
- **适用于不同调制方式的公平比较**

### SNR (信号功率/噪声功率)

```
SNR = 信号功率 / 噪声功率
    = Ps / Pn
```

- **带宽相关**: 噪声功率取决于接收机带宽
- **直观但不够通用**: 不同带宽系统无法直接比较

## 换算关系

对于数字调制系统：

```
SNR = Eb/N0 × (Rb / B)
```

其中：
- **Rb**: 比特率 (bits/s)
- **B**: 噪声带宽 (Hz)

在采样系统中（如 BLE Studio 仿真）：

```
SNR = Eb/N0 × (符号率 / 采样率)
    = Eb/N0 × (1 / samples_per_symbol)
```

### BLE 具体计算

| PHY 模式 | 符号率 | 采样率 | samples_per_symbol | SNR vs Eb/N0 |
|----------|--------|--------|-------------------|--------------|
| LE 1M | 1 Msps | 8 Msps | 8 | SNR = Eb/N0 - 9 dB |
| LE 2M | 2 Msps | 8 Msps | 4 | SNR = Eb/N0 - 6 dB |

**示例**：Eb/N0 = 18 dB 时

- LE 1M: SNR = 18 - 9 = 9 dB (带内)
- LE 2M: SNR = 18 - 6 = 12 dB (带内)

这就是为什么 **LE 2M 在相同 Eb/N0 下解调性能更好** —— 它的带内 SNR 更高。

## 为什么使用 Eb/N0？

### 1. 物理现实性

Eb/N0 反映了实际无线信道的物理特性：

- **发射功率固定** → 每比特能量 Eb 固定
- **热噪声由温度决定** → N0 = kT (k: 玻尔兹曼常数, T: 温度)
- **带宽越大，噪声功率越大**

### 2. 公平比较

不同调制方式、不同带宽的系统可以在同一 Eb/N0 下比较：

```
系统 A: 1 Mbps, BW = 1 MHz
系统 B: 2 Mbps, BW = 2 MHz

在相同 Eb/N0 下:
- 系统 A 的 SNR = Eb/N0 × (1M / 1M) = Eb/N0
- 系统 B 的 SNR = Eb/N0 × (2M / 2M) = Eb/N0

但如果系统 B 只用 1 MHz 带宽传 2 Mbps (更高效的调制):
- 系统 B 的 SNR = Eb/N0 × (2M / 1M) = Eb/N0 + 3 dB
```

### 3. BER 曲线标准化

学术论文和规范中，BER (误比特率) 曲线通常以 Eb/N0 为横轴：

```
GFSK (BT=0.5, h=0.5) 理论 BER:
- BER = 10^-3 @ Eb/N0 ≈ 10 dB
- BER = 10^-6 @ Eb/N0 ≈ 14 dB
```

## 转换公式速查

### 基本公式

```
Eb/N0 (dB) = SNR (dB) + 10 × log10(采样率 / 符号率)
SNR (dB)   = Eb/N0 (dB) - 10 × log10(采样率 / 符号率)
```

### BLE 快速转换 (8 MHz 采样率)

| PHY 模式 | 符号率 | 转换公式 |
|----------|--------|----------|
| **LE 1M** | 1 MHz | `Eb/N0 = SNR + 9 dB`<br>`SNR = Eb/N0 - 9 dB` |
| **LE 2M** | 2 MHz | `Eb/N0 = SNR + 6 dB`<br>`SNR = Eb/N0 - 6 dB` |

### 常用值对照表

| Eb/N0 (dB) | LE 1M 带内 SNR | LE 2M 带内 SNR |
|------------|----------------|----------------|
| 10 | 1 dB | 4 dB |
| 12 | 3 dB | 6 dB |
| 14 | 5 dB | 8 dB |
| 16 | 7 dB | 10 dB |
| 18 | 9 dB | 12 dB |
| 20 | 11 dB | 14 dB |

### Python 转换函数

```python
import numpy as np

def ebn0_to_snr(ebn0_db, sample_rate=8e6, symbol_rate=1e6):
    """Eb/N0 (dB) 转 带内 SNR (dB)"""
    return ebn0_db - 10 * np.log10(sample_rate / symbol_rate)

def snr_to_ebn0(snr_db, sample_rate=8e6, symbol_rate=1e6):
    """带内 SNR (dB) 转 Eb/N0 (dB)"""
    return snr_db + 10 * np.log10(sample_rate / symbol_rate)

# 示例
print(f"LE 1M: Eb/N0=18dB -> SNR={ebn0_to_snr(18, 8e6, 1e6):.1f}dB")  # 9 dB
print(f"LE 2M: Eb/N0=18dB -> SNR={ebn0_to_snr(18, 8e6, 2e6):.1f}dB")  # 12 dB
print(f"LE 1M: SNR=10dB -> Eb/N0={snr_to_ebn0(10, 8e6, 1e6):.1f}dB")  # 19 dB
```

### 与 CEVA 指标对比

CEVA BLE IP 规格书中的 9.5 dB SNR (30.8% PER) 转换：

```
CEVA LE 1M:
  SNR (带内 1MHz) = 9.5 dB
  Eb/N0 (8MHz 采样) = 9.5 + 10*log10(8/1) = 9.5 + 9 = 18.5 dB

CEVA LE 2M:
  SNR (带内 2MHz) = 9.5 dB
  Eb/N0 (8MHz 采样) = 9.5 + 10*log10(8/2) = 9.5 + 6 = 15.5 dB
```

## BLE Studio 中的实现

### 配置文件

支持两种字段名（向后兼容）：

```yaml
# 方式 1: 推荐 (语义明确)
channel:
  ebn0_db: 18

# 方式 2: 向后兼容 (旧配置文件仍可使用)
channel:
  snr_db: 18
```

**注意**: 无论使用哪个字段名，值都按 **Eb/N0** 计算噪声。如果同时存在两个字段，优先使用 `ebn0_db`。

### 信道模型 (channel.py)

```python
class AWGNChannel:
    def apply(self, signal):
        # Eb/N0 → 带内 SNR
        samples_per_symbol = self.sample_rate / self.symbol_rate
        ebn0_linear = 10 ** (self.ebn0_db / 10)
        snr_linear = ebn0_linear / samples_per_symbol

        # 计算噪声功率
        signal_power = np.mean(np.abs(signal) ** 2)
        noise_power = signal_power / snr_linear

        # 添加 AWGN
        noise = np.sqrt(noise_power / 2) * (randn + 1j * randn)
        return signal + noise
```

### 实测门限 (BLE Studio v1.0)

使用 `examples/benchmark.py` 测试的解调门限：

| PHY 模式 | 30% PER 所需 Eb/N0 | 对应带内 SNR | vs CEVA |
|----------|-------------------|--------------|---------|
| LE 1M | ~15.5 dB | ~6.5 dB | 领先 3 dB |
| LE 2M | ~13.5 dB | ~7.5 dB | 领先 2 dB |

运行测试：
```bash
python examples/benchmark.py          # 完整测试
python examples/benchmark.py --quick  # 快速测试
```

## 常见误解

### 误解 1: "SNR 就是 Eb/N0"

**错误**。只有当 符号率 = 采样率 (即 1 sample/symbol) 时，两者才相等。

### 误解 2: "LE 2M 需要更高的 SNR"

**部分正确**。LE 2M 确实需要更高的**带内 SNR**，但需要更低的 **Eb/N0**。

原因：LE 2M 的符号率是 LE 1M 的 2 倍，在相同 Eb/N0 下带内 SNR 高 3 dB。

### 误解 3: "传统 SNR 更真实"

**错误**。传统 SNR 依赖于接收机带宽的选择，不同带宽会得到不同的 SNR 值。

Eb/N0 是带宽无关的物理量，更能反映实际信道条件。

## 参考资料

1. **Bluetooth Core Specification v5.x**, Volume 6, Part A - RF 测试规范
2. **Proakis, J.G.** - *Digital Communications*, Chapter 4: SNR 和 Eb/N0 的关系
3. **Sklar, B.** - *Digital Communications*, Chapter 3: 信道容量与 Eb/N0

## 总结

| 场景 | 推荐使用 |
|------|---------|
| 论文/规范中的 BER 曲线 | Eb/N0 |
| 比较不同调制方式性能 | Eb/N0 |
| 接收机灵敏度测试 | Eb/N0 |
| 简单仿真/调试 | SNR (明确带宽) |
| BLE Studio 信道仿真 | **Eb/N0** (snr_db 字段) |

在 BLE Studio 中，`snr_db` 配置项实际按 **Eb/N0** 计算噪声，这样可以：
- 正确反映 LE 1M 和 LE 2M 的性能差异
- 与蓝牙测试规范保持一致
- 实现物理上准确的信道仿真
