"""
BLE 信道模型模块
实现各种无线信道模型用于仿真
"""

import numpy as np
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from scipy import signal as scipy_signal


class ChannelType(Enum):
    """信道类型"""
    AWGN = "awgn"                    # 加性高斯白噪声
    FLAT_FADING = "flat_fading"     # 平坦衰落
    RAYLEIGH = "rayleigh"           # 瑞利衰落
    RICIAN = "rician"               # 莱斯衰落
    MULTIPATH = "multipath"         # 多径衰落
    BLE_INDOOR = "ble_indoor"       # BLE 室内信道模型


@dataclass
class ChannelConfig:
    """信道配置"""
    channel_type: ChannelType = ChannelType.AWGN
    sample_rate: float = 8e6
    symbol_rate: float = 1e6       # 符号率 (Hz), 用于 Eb/N0 计算

    # AWGN 参数 - 使用 Eb/N0 (每比特能量/噪声功率谱密度)
    snr_db: float = 20.0           # Eb/N0 (dB), 保留字段名兼容配置文件

    # 频偏参数
    frequency_offset: float = 0.0   # 载波频偏 (Hz)
    frequency_drift: float = 0.0    # 频率漂移率 (Hz/s)

    # 定时参数
    timing_offset: float = 0.0      # 定时偏移 (采样点)
    clock_ppm: float = 0.0          # 时钟偏差 (ppm)

    # 衰落参数
    doppler_freq: float = 1.0       # 多普勒频率 (Hz)
    k_factor: float = 4.0           # 莱斯 K 因子 (线性)
    path_delays: List[float] = None # 多径延迟 (秒)
    path_gains: List[float] = None  # 多径增益 (dB)

    # IQ 失衡参数
    iq_amplitude_imbalance: float = 0.0  # 幅度失衡 (dB)
    iq_phase_imbalance: float = 0.0      # 相位失衡 (度)

    # DC 偏移
    dc_offset_i: float = 0.0        # I 路 DC 偏移
    dc_offset_q: float = 0.0        # Q 路 DC 偏移

    # 相位噪声
    phase_noise_level: float = -100  # 相位噪声电平 (dBc/Hz @ 1MHz offset)

    def __post_init__(self):
        if self.path_delays is None:
            self.path_delays = [0.0]
        if self.path_gains is None:
            self.path_gains = [0.0]


class AWGNChannel:
    """AWGN 信道 (基于 Eb/N0)

    使用 Eb/N0 (每比特能量/噪声功率谱密度) 作为信噪比指标:
    - Eb/N0 是物理层性能的标准度量
    - 噪声功率根据 symbol_rate/sample_rate 自动调整
    - LE 2M 在相同 Eb/N0 下会比 LE 1M 有更高的带内 SNR (因为带宽更大)

    换算关系:
    - SNR(带内) = Eb/N0 × (symbol_rate / sample_rate)
    - LE 1M @ 8Msps: SNR = Eb/N0 - 9 dB
    - LE 2M @ 8Msps: SNR = Eb/N0 - 6 dB
    """

    def __init__(self, ebn0_db: float, sample_rate: float = 8e6,
                 symbol_rate: float = 1e6):
        self.ebn0_db = ebn0_db
        self.sample_rate = sample_rate
        self.symbol_rate = symbol_rate

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用 AWGN 噪声

        Eb/N0 = (信号功率 / 符号率) / (噪声功率谱密度)
        噪声功率 = N0 × 采样率 (噪声带宽 = 采样率)

        对于 GFSK:
        - Eb/N0 ≈ SNR × (采样率 / 符号率)
        - SNR = Eb/N0 × (符号率 / 采样率)

        示例:
        - LE 1M @ 8Msps: samples_per_symbol = 8, SNR = Eb/N0 / 8
        - LE 2M @ 8Msps: samples_per_symbol = 4, SNR = Eb/N0 / 4
        - 相同 Eb/N0 时, LE 2M 的带内 SNR 高 3 dB
        """
        signal_power = np.mean(np.abs(signal) ** 2)

        # Eb/N0 → 带内 SNR
        samples_per_symbol = self.sample_rate / self.symbol_rate
        ebn0_linear = 10 ** (self.ebn0_db / 10)
        snr_linear = ebn0_linear / samples_per_symbol

        noise_power = signal_power / snr_linear

        noise = np.sqrt(noise_power / 2) * (
            np.random.randn(len(signal)) + 1j * np.random.randn(len(signal))
        )

        return signal + noise


class FlatFadingChannel:
    """平坦衰落信道"""

    def __init__(self, doppler_freq: float, sample_rate: float):
        self.doppler_freq = doppler_freq
        self.sample_rate = sample_rate

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用平坦衰落"""
        # 生成瑞利衰落系数
        num_samples = len(signal)
        t = np.arange(num_samples) / self.sample_rate

        # Jakes 模型
        num_sinusoids = 8
        fading = np.zeros(num_samples, dtype=complex)

        for n in range(num_sinusoids):
            alpha = 2 * np.pi * n / num_sinusoids
            beta = np.random.uniform(0, 2 * np.pi)
            freq = self.doppler_freq * np.cos(alpha)
            fading += np.exp(1j * (2 * np.pi * freq * t + beta))

        fading /= np.sqrt(num_sinusoids)

        return signal * fading


class RayleighChannel:
    """瑞利衰落信道"""

    def __init__(self, doppler_freq: float, sample_rate: float):
        self.doppler_freq = doppler_freq
        self.sample_rate = sample_rate
        self.flat_fading = FlatFadingChannel(doppler_freq, sample_rate)

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用瑞利衰落"""
        return self.flat_fading.apply(signal)


class RicianChannel:
    """莱斯衰落信道"""

    def __init__(self, k_factor: float, doppler_freq: float, sample_rate: float):
        """
        Args:
            k_factor: K 因子 (直射/散射功率比, 线性)
            doppler_freq: 多普勒频率 (Hz)
            sample_rate: 采样率 (Hz)
        """
        self.k_factor = k_factor
        self.doppler_freq = doppler_freq
        self.sample_rate = sample_rate

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用莱斯衰落"""
        num_samples = len(signal)
        t = np.arange(num_samples) / self.sample_rate

        # 直射分量 (LOS)
        los_amplitude = np.sqrt(self.k_factor / (self.k_factor + 1))
        los_phase = np.random.uniform(0, 2 * np.pi)
        los = los_amplitude * np.exp(1j * (2 * np.pi * self.doppler_freq * t + los_phase))

        # 散射分量 (NLOS) - 瑞利
        nlos_amplitude = np.sqrt(1 / (self.k_factor + 1))
        nlos = nlos_amplitude * (
            np.random.randn(num_samples) + 1j * np.random.randn(num_samples)
        ) / np.sqrt(2)

        # 组合
        fading = los + nlos

        return signal * fading


class MultipathChannel:
    """多径衰落信道"""

    def __init__(self, path_delays: List[float], path_gains: List[float],
                 sample_rate: float, doppler_freq: float = 0.0):
        """
        Args:
            path_delays: 各路径延迟 (秒)
            path_gains: 各路径增益 (dB)
            sample_rate: 采样率 (Hz)
            doppler_freq: 多普勒频率 (Hz)
        """
        self.path_delays = np.array(path_delays)
        self.path_gains = 10 ** (np.array(path_gains) / 20)  # dB -> 线性
        self.sample_rate = sample_rate
        self.doppler_freq = doppler_freq

        # 转换延迟为采样点
        self.delay_samples = (self.path_delays * sample_rate).astype(int)

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用多径衰落"""
        max_delay = max(self.delay_samples)
        output = np.zeros(len(signal) + max_delay, dtype=complex)

        for delay, gain in zip(self.delay_samples, self.path_gains):
            # 可选: 添加每路径的衰落
            if self.doppler_freq > 0:
                fading = RayleighChannel(self.doppler_freq, self.sample_rate)
                path_signal = fading.apply(signal) * gain
            else:
                path_signal = signal * gain

            output[delay:delay + len(signal)] += path_signal

        return output[:len(signal)]


class BLEIndoorChannel:
    """BLE 室内信道模型"""

    # 典型室内多径参数 (基于测量)
    INDOOR_OFFICE = {
        'path_delays': [0, 50e-9, 110e-9, 170e-9, 290e-9],
        'path_gains': [0, -3.0, -5.0, -7.0, -10.0],
        'doppler_freq': 1.0,  # 低速移动
    }

    INDOOR_RESIDENTIAL = {
        'path_delays': [0, 20e-9, 40e-9, 60e-9],
        'path_gains': [0, -2.0, -4.0, -6.0],
        'doppler_freq': 0.5,
    }

    INDOOR_INDUSTRIAL = {
        'path_delays': [0, 100e-9, 200e-9, 300e-9, 500e-9, 700e-9],
        'path_gains': [0, -1.5, -3.0, -5.0, -8.0, -12.0],
        'doppler_freq': 2.0,
    }

    def __init__(self, environment: str = 'office', sample_rate: float = 8e6):
        """
        Args:
            environment: 环境类型 ('office', 'residential', 'industrial')
            sample_rate: 采样率 (Hz)
        """
        if environment == 'office':
            params = self.INDOOR_OFFICE
        elif environment == 'residential':
            params = self.INDOOR_RESIDENTIAL
        elif environment == 'industrial':
            params = self.INDOOR_INDUSTRIAL
        else:
            params = self.INDOOR_OFFICE

        self.multipath = MultipathChannel(
            path_delays=params['path_delays'],
            path_gains=params['path_gains'],
            sample_rate=sample_rate,
            doppler_freq=params['doppler_freq']
        )

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用室内信道"""
        return self.multipath.apply(signal)


class IQImbalance:
    """IQ 失衡模型"""

    def __init__(self, amplitude_imbalance_db: float = 0.0, phase_imbalance_deg: float = 0.0):
        """
        Args:
            amplitude_imbalance_db: 幅度失衡 (dB)
            phase_imbalance_deg: 相位失衡 (度)
        """
        self.amplitude_imbalance = 10 ** (amplitude_imbalance_db / 20)
        self.phase_imbalance = np.deg2rad(phase_imbalance_deg)

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用 IQ 失衡"""
        i = signal.real
        q = signal.imag

        # 应用失衡
        i_out = i
        q_out = self.amplitude_imbalance * (
            np.sin(self.phase_imbalance) * i + np.cos(self.phase_imbalance) * q
        )

        return i_out + 1j * q_out


class PhaseNoise:
    """相位噪声模型"""

    def __init__(self, level_dbc_hz: float, offset_freq: float = 1e6,
                 sample_rate: float = 8e6):
        """
        Args:
            level_dbc_hz: 相位噪声电平 (dBc/Hz @ offset_freq)
            offset_freq: 偏移频率 (Hz)
            sample_rate: 采样率 (Hz)
        """
        self.level_dbc_hz = level_dbc_hz
        self.offset_freq = offset_freq
        self.sample_rate = sample_rate

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用相位噪声"""
        num_samples = len(signal)

        # 简化模型: 生成 1/f 相位噪声
        # PSD = L(f) = level / f^2
        freqs = np.fft.fftfreq(num_samples, 1 / self.sample_rate)
        freqs[0] = 1  # 避免除零

        # 相位噪声功率谱
        pn_psd = 10 ** (self.level_dbc_hz / 10) * (self.offset_freq / np.abs(freqs)) ** 2

        # 生成随机相位噪声
        pn_fft = np.sqrt(pn_psd) * np.exp(1j * 2 * np.pi * np.random.rand(num_samples))
        phase_noise = np.real(np.fft.ifft(pn_fft))

        return signal * np.exp(1j * phase_noise)


class FrequencyOffset:
    """频率偏移模型"""

    def __init__(self, offset_hz: float, drift_hz_per_s: float = 0.0,
                 sample_rate: float = 8e6):
        """
        Args:
            offset_hz: 初始频偏 (Hz)
            drift_hz_per_s: 频率漂移率 (Hz/s)
            sample_rate: 采样率 (Hz)
        """
        self.offset_hz = offset_hz
        self.drift_hz_per_s = drift_hz_per_s
        self.sample_rate = sample_rate

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用频率偏移"""
        t = np.arange(len(signal)) / self.sample_rate

        # 瞬时频率 = offset + drift * t
        instant_freq = self.offset_hz + self.drift_hz_per_s * t

        # 相位 = 积分(2*pi*freq)
        phase = 2 * np.pi * np.cumsum(instant_freq) / self.sample_rate

        return signal * np.exp(1j * phase)


class TimingOffset:
    """定时偏移模型"""

    def __init__(self, offset_samples: float, clock_ppm: float = 0.0,
                 sample_rate: float = 8e6):
        """
        Args:
            offset_samples: 初始定时偏移 (采样点, 可小数)
            clock_ppm: 时钟偏差 (ppm)
            sample_rate: 采样率 (Hz)
        """
        self.offset_samples = offset_samples
        self.clock_ppm = clock_ppm
        self.sample_rate = sample_rate

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用定时偏移"""
        num_samples = len(signal)

        # 计算重采样因子
        resample_factor = 1 + self.clock_ppm * 1e-6

        # 新的采样时刻
        t_orig = np.arange(num_samples)
        t_new = t_orig * resample_factor + self.offset_samples

        # 三次样条插值
        from scipy.interpolate import interp1d

        interp_real = interp1d(t_orig, signal.real, kind='cubic',
                               bounds_error=False, fill_value=0)
        interp_imag = interp1d(t_orig, signal.imag, kind='cubic',
                               bounds_error=False, fill_value=0)

        return interp_real(t_new) + 1j * interp_imag(t_new)


class DCOffset:
    """DC 偏移模型"""

    def __init__(self, dc_i: float = 0.0, dc_q: float = 0.0):
        """
        Args:
            dc_i: I 路 DC 偏移
            dc_q: Q 路 DC 偏移
        """
        self.dc_i = dc_i
        self.dc_q = dc_q

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """应用 DC 偏移"""
        return signal + (self.dc_i + 1j * self.dc_q)


class BLEChannel:
    """BLE 综合信道模型"""

    def __init__(self, config: Optional[ChannelConfig] = None):
        self.config = config or ChannelConfig()
        self._build_channel()

    def _build_channel(self):
        """构建信道链"""
        cfg = self.config
        self.impairments = []

        # 1. 多径/衰落
        if cfg.channel_type == ChannelType.RAYLEIGH:
            self.impairments.append(
                RayleighChannel(cfg.doppler_freq, cfg.sample_rate)
            )
        elif cfg.channel_type == ChannelType.RICIAN:
            self.impairments.append(
                RicianChannel(cfg.k_factor, cfg.doppler_freq, cfg.sample_rate)
            )
        elif cfg.channel_type == ChannelType.MULTIPATH:
            self.impairments.append(
                MultipathChannel(cfg.path_delays, cfg.path_gains,
                                 cfg.sample_rate, cfg.doppler_freq)
            )
        elif cfg.channel_type == ChannelType.BLE_INDOOR:
            self.impairments.append(
                BLEIndoorChannel('office', cfg.sample_rate)
            )

        # 2. 频偏
        if cfg.frequency_offset != 0 or cfg.frequency_drift != 0:
            self.impairments.append(
                FrequencyOffset(cfg.frequency_offset, cfg.frequency_drift, cfg.sample_rate)
            )

        # 3. 定时偏移
        if cfg.timing_offset != 0 or cfg.clock_ppm != 0:
            self.impairments.append(
                TimingOffset(cfg.timing_offset, cfg.clock_ppm, cfg.sample_rate)
            )

        # 4. IQ 失衡
        if cfg.iq_amplitude_imbalance != 0 or cfg.iq_phase_imbalance != 0:
            self.impairments.append(
                IQImbalance(cfg.iq_amplitude_imbalance, cfg.iq_phase_imbalance)
            )

        # 5. DC 偏移
        if cfg.dc_offset_i != 0 or cfg.dc_offset_q != 0:
            self.impairments.append(
                DCOffset(cfg.dc_offset_i, cfg.dc_offset_q)
            )

        # 6. 相位噪声
        if cfg.phase_noise_level > -120:
            self.impairments.append(
                PhaseNoise(cfg.phase_noise_level, sample_rate=cfg.sample_rate)
            )

        # 7. AWGN (最后添加)
        self.impairments.append(AWGNChannel(
            cfg.snr_db,
            sample_rate=cfg.sample_rate,
            symbol_rate=cfg.symbol_rate
        ))

    def apply(self, signal: np.ndarray) -> np.ndarray:
        """
        应用所有信道效应

        Args:
            signal: 输入信号

        Returns:
            经过信道的信号
        """
        output = signal.copy()

        for impairment in self.impairments:
            output = impairment.apply(output)

        return output

    def set_snr(self, ebn0_db: float):
        """动态设置 Eb/N0"""
        self.config.snr_db = ebn0_db
        # 更新 AWGN 信道
        cfg = self.config
        for i, imp in enumerate(self.impairments):
            if isinstance(imp, AWGNChannel):
                self.impairments[i] = AWGNChannel(
                    ebn0_db,
                    sample_rate=cfg.sample_rate,
                    symbol_rate=cfg.symbol_rate
                )


def create_awgn_channel(snr_db: float) -> BLEChannel:
    """创建简单 AWGN 信道"""
    config = ChannelConfig(
        channel_type=ChannelType.AWGN,
        snr_db=snr_db
    )
    return BLEChannel(config)


def create_fading_channel(snr_db: float, doppler_freq: float = 1.0,
                          channel_type: str = 'rayleigh') -> BLEChannel:
    """创建衰落信道"""
    if channel_type == 'rayleigh':
        ch_type = ChannelType.RAYLEIGH
        k_factor = 0
    else:
        ch_type = ChannelType.RICIAN
        k_factor = 4.0

    config = ChannelConfig(
        channel_type=ch_type,
        snr_db=snr_db,
        doppler_freq=doppler_freq,
        k_factor=k_factor
    )
    return BLEChannel(config)


def create_ble_indoor_channel(snr_db: float, environment: str = 'office') -> BLEChannel:
    """创建 BLE 室内信道"""
    config = ChannelConfig(
        channel_type=ChannelType.BLE_INDOOR,
        snr_db=snr_db
    )
    return BLEChannel(config)
