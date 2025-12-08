# BLE Studio

BLE 基带算法平台 - 支持 BLE 数据包生成和解调仿真。

## 功能特性

- **数据包生成**: 支持 BLE 4.x/5.x 广播和数据信道包格式
- **GFSK 调制**: 符合 BLE 规范的高斯频移键控调制
- **GFSK 解调**: 完整的接收机算法链路
- **信道模型**: AWGN、瑞利/莱斯衰落、多径、室内信道等
- **性能测试**: BER/PER 测试、SNR 扫描、灵敏度测试
- **交互式可视化**: 基于 Plotly 的美观图表，支持缩放、悬停等交互

## 安装

```bash
# 克隆项目
git clone <repository-url>
cd BLEStudio

# 安装 (开发模式)
pip install -e .

# 安装开发依赖 (包含绘图支持)
pip install -e ".[dev]"
```

## 快速开始

### 生成 BLE 广播数据包

```python
from ble_studio import BLEPacket
from ble_studio.packet import BLEPacketConfig, BLEPhyMode, create_advertising_packet

# 方式1: 使用便捷函数创建广播包
adv_address = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
adv_data = bytes([0x02, 0x01, 0x06])  # Flags

packet = create_advertising_packet(
    adv_address=adv_address,
    adv_data=adv_data,
    channel=37
)

# 生成比特流
bits = packet.generate()
print(f"数据包长度: {len(bits)} bits")

# 方式2: 自定义配置
config = BLEPacketConfig(
    phy_mode=BLEPhyMode.LE_1M,
    channel=37,
    access_address=0x8E89BED6,
    pdu_type=0x00,
    payload=adv_address + adv_data
)
packet = BLEPacket(config)
bits = packet.generate()
```

### GFSK 调制

```python
from ble_studio import BLEModulator
from ble_studio.modulator import ModulatorConfig

# 配置调制器
config = ModulatorConfig(
    phy_mode=BLEPhyMode.LE_1M,
    sample_rate=8e6,         # 8 MHz 采样率
    modulation_index=0.5,    # 调制指数
    bt=0.5                   # 高斯滤波器 BT 积
)

modulator = BLEModulator(config)

# 调制
iq_signal = modulator.modulate(bits)

# 添加信道损伤
noisy_signal = modulator.add_noise(iq_signal, snr_db=15)
signal_with_cfo = modulator.add_frequency_offset(noisy_signal, freq_offset=50e3)
```

### GFSK 解调

```python
from ble_studio import BLEDemodulator
from ble_studio.demodulator import DemodulatorConfig

# 配置解调器
config = DemodulatorConfig(
    phy_mode=BLEPhyMode.LE_1M,
    sample_rate=8e6,
    access_address=0x8E89BED6,
    channel=37
)

demodulator = BLEDemodulator(config)

# 解调
result = demodulator.demodulate(iq_signal)

if result.success:
    print(f"解调成功!")
    print(f"CRC 校验: {'通过' if result.crc_valid else '失败'}")
    print(f"RSSI: {result.rssi:.2f} dB")
    print(f"频偏: {result.freq_offset/1e3:.2f} kHz")
    print(f"PDU: {result.pdu.hex()}")
```

### 可视化 (Plotly)

```python
from ble_studio import BLEVisualizer, plot_ble_signal

# 创建可视化器
viz = BLEVisualizer()

# IQ 时域波形 (分离 I/Q)
fig = viz.plot_iq_time(iq_signal, sample_rate=8e6, title='IQ 时域波形')
fig.show()  # 在浏览器中显示
fig.write_html('iq_time.html')  # 保存为 HTML

# IQ 时域波形 (叠加)
fig = viz.plot_iq_combined(iq_signal, sample_rate=8e6)
fig.show()

# 频谱图
fig = viz.plot_spectrum(iq_signal, sample_rate=8e6, fft_size=4096)
fig.show()

# 时频谱图 (瀑布图)
fig = viz.plot_spectrogram(iq_signal, sample_rate=8e6)
fig.show()

# 星座图
fig = viz.plot_constellation(iq_signal, downsample=8)
fig.show()

# 比特流
fig = viz.plot_bits(bits, max_bits=200)
fig.show()

# 瞬时频率偏移
fig = viz.plot_frequency_deviation(iq_signal, sample_rate=8e6)
fig.show()

# 眼图
fig = viz.plot_eye_diagram(demod_signal, samples_per_symbol=8)
fig.show()

# 综合仪表板 (一次显示多个图表)
fig = viz.create_dashboard(iq_signal, sample_rate=8e6, bits=bits)
fig.show()

# 快捷函数
fig = plot_ble_signal(iq_signal, sample_rate=8e6, bits=bits)
fig.show()
```

### 数据信道 PDU

```python
from ble_studio import DataChannelPDU, DataPDUType, create_data_packet

# 创建空 PDU (保持连接)
empty_pdu = DataChannelPDU.create_empty_pdu(nesn=0, sn=0)

# 创建数据 PDU
data_pdu = DataChannelPDU.create_data_pdu(
    payload=b'\x01\x02\x03\x04',
    nesn=0, sn=0, md=0, is_start=True
)

# 创建控制 PDU
version_pdu = DataChannelPDU.create_ll_version_ind()
terminate_pdu = DataChannelPDU.create_ll_terminate_ind(error_code=0x13)
feature_pdu = DataChannelPDU.create_ll_feature_req()
length_pdu = DataChannelPDU.create_ll_length_req()
phy_pdu = DataChannelPDU.create_ll_phy_req(tx_phys=0x01, rx_phys=0x01)

# 创建完整数据信道数据包
packet = create_data_packet(
    pdu=data_pdu,
    access_address=0x12345678,
    crc_init=0x123456,
    channel=0
)
```

### 信道模型

```python
from ble_studio import (
    BLEChannel, ChannelConfig, ChannelType,
    create_awgn_channel, create_fading_channel, create_ble_indoor_channel
)

# 简单 AWGN 信道
channel = create_awgn_channel(snr_db=15)
rx_signal = channel.apply(tx_signal)

# 瑞利衰落信道
channel = create_fading_channel(snr_db=15, doppler_freq=10, channel_type='rayleigh')
rx_signal = channel.apply(tx_signal)

# 莱斯衰落信道
channel = create_fading_channel(snr_db=15, doppler_freq=10, channel_type='rician')
rx_signal = channel.apply(tx_signal)

# BLE 室内信道 (含多径)
channel = create_ble_indoor_channel(snr_db=15, environment='office')
rx_signal = channel.apply(tx_signal)

# 自定义信道 (多种损伤组合)
config = ChannelConfig(
    channel_type=ChannelType.MULTIPATH,
    snr_db=15,
    frequency_offset=50e3,           # 50 kHz 频偏
    timing_offset=0.5,               # 定时偏移
    iq_amplitude_imbalance=1.0,      # 1dB IQ 幅度失衡
    iq_phase_imbalance=5.0,          # 5度 IQ 相位失衡
    dc_offset_i=0.01,                # I 路 DC 偏移
    dc_offset_q=0.01,                # Q 路 DC 偏移
    path_delays=[0, 50e-9, 100e-9],  # 多径延迟
    path_gains=[0, -3, -6],          # 多径增益 (dB)
)
channel = BLEChannel(config)
rx_signal = channel.apply(tx_signal)
```

### BER/PER 性能测试

```python
from ble_studio import (
    quick_ber_test, quick_snr_sweep, plot_ber_curve,
    BLEPerformanceTester, TestConfig, BLEPhyMode
)

# 快速 BER 测试
result = quick_ber_test(snr_db=10, num_packets=100)
print(f"BER: {result.ber:.2e}, PER: {result.per:.2%}")

# SNR 扫描测试
report = quick_snr_sweep(
    snr_start=0,
    snr_stop=20,
    snr_step=2,
    num_packets=100
)

# 绘制 BER/PER 曲线
fig = plot_ber_curve(report, show_theoretical=True)
fig.show()

# 自定义测试配置
config = TestConfig(
    phy_mode=BLEPhyMode.LE_1M,
    snr_start=-5,
    snr_stop=25,
    snr_step=1,
    num_packets=500,
    payload_length=37,
    frequency_offset=10e3,  # 带频偏测试
)
tester = BLEPerformanceTester(config)
report = tester.run_snr_sweep()

# 灵敏度测试 (找到 30.8% PER 对应的 SNR)
sensitivity = tester.run_sensitivity_test(target_per=0.308)
print(f"灵敏度: {sensitivity:.2f} dB")
```

## 运行示例

```bash
python examples/demo.py
```

输出示例:

```
============================================================
BLE 数据包生成演示
============================================================
数据包比特数: 256
数据包字节数: 32

前导码 (8 bits): [1 0 1 0 1 0 1 0]
接入地址 (32 bits): [0 1 1 0 1 0 1 1 ...]

============================================================
BLE GFSK 调制演示
============================================================
采样率: 8.0 MHz
符号率: 1.0 Msps
每符号采样数: 8
IQ 信号长度: 2048 采样点
信号时长: 256.00 us

============================================================
BLE GFSK 解调演示
============================================================
解调成功: True
CRC 校验: 通过
RSSI: -0.12 dB
频偏估计: 48.23 kHz
```

## 项目结构

```
BLEStudio/
├── ble_studio/
│   ├── __init__.py       # 包入口
│   ├── packet.py         # BLE 数据包生成 (广播+数据信道)
│   ├── modulator.py      # GFSK 调制器
│   ├── demodulator.py    # GFSK 解调器
│   ├── channel.py        # 信道模型
│   ├── performance.py    # BER/PER 性能测试
│   └── visualizer.py     # Plotly 可视化
├── examples/
│   └── demo.py           # 演示程序
├── pyproject.toml        # 项目配置
├── requirements.txt      # 依赖列表
└── README.md
```

## 技术规格

### 支持的 PHY 模式

| 模式 | 符号率 | 调制方式 |
|------|--------|----------|
| LE 1M | 1 Msps | GFSK |
| LE 2M | 2 Msps | GFSK |

### 数据包格式

```
┌──────────┬─────────────┬─────────┬───────┐
│ Preamble │ Access Addr │   PDU   │  CRC  │
│  8/16b   │    32b      │ 16-2056b│  24b  │
└──────────┴─────────────┴─────────┴───────┘
```

### 算法参数

- **调制指数**: 0.5 (BLE 规范)
- **高斯滤波器 BT**: 0.5
- **CRC 多项式**: x²⁴ + x¹⁰ + x⁹ + x⁶ + x⁴ + x³ + x + 1
- **白化多项式**: x⁷ + x⁴ + 1

## 依赖

- Python >= 3.8
- NumPy >= 1.20.0
- SciPy >= 1.7.0
- Plotly >= 5.10.0

## 可视化图表类型

| 图表类型 | 方法 | 说明 |
|---------|------|------|
| IQ 时域 | `plot_iq_time()` | I/Q 分量分离显示 |
| IQ 叠加 | `plot_iq_combined()` | I/Q 分量叠加显示 |
| 频谱图 | `plot_spectrum()` | FFT 功率谱密度 |
| 时频谱 | `plot_spectrogram()` | 瀑布图/热力图 |
| 星座图 | `plot_constellation()` | IQ 散点图 |
| 比特流 | `plot_bits()` | 数字信号阶梯图 |
| 瞬时频率 | `plot_frequency_deviation()` | GFSK 频率偏移 |
| 眼图 | `plot_eye_diagram()` | 符号间叠加 |
| 仪表板 | `create_dashboard()` | 综合多图显示 |

## 信道模型

| 信道类型 | 类/函数 | 说明 |
|---------|--------|------|
| AWGN | `AWGNChannel` | 加性高斯白噪声 |
| 瑞利衰落 | `RayleighChannel` | 无直射路径的衰落信道 |
| 莱斯衰落 | `RicianChannel` | 有直射路径的衰落信道 |
| 多径 | `MultipathChannel` | 自定义多径延迟和增益 |
| BLE 室内 | `BLEIndoorChannel` | 预设室内环境 (办公室/住宅/工业) |
| 频偏 | `FrequencyOffset` | 载波频偏和漂移 |
| 定时偏移 | `TimingOffset` | 采样时钟偏差 |
| IQ 失衡 | `IQImbalance` | 幅度和相位失衡 |
| DC 偏移 | `DCOffset` | I/Q 直流偏移 |
| 相位噪声 | `PhaseNoise` | 振荡器相位噪声 |

## 许可证

MIT License
