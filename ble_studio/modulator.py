"""
BLE GFSK 调制器
实现 BLE 基带信号调制
"""

import numpy as np
from typing import Optional
from dataclasses import dataclass
from .packet import BLEPhyMode


@dataclass
class ModulatorConfig:
    """调制器配置"""
    phy_mode: BLEPhyMode = BLEPhyMode.LE_1M
    sample_rate: float = 8e6          # 采样率 (Hz)
    modulation_index: float = 0.5     # 调制指数
    bt: float = 0.5                   # 高斯滤波器带宽时间积
    center_freq: float = 0.0          # 中心频率偏移 (Hz)


class BLEModulator:
    """BLE GFSK 调制器"""

    def __init__(self, config: Optional[ModulatorConfig] = None):
        self.config = config or ModulatorConfig()
        self._update_parameters()

    def _update_parameters(self):
        """更新内部参数"""
        config = self.config

        # 符号率
        if config.phy_mode == BLEPhyMode.LE_2M:
            self.symbol_rate = 2e6
        else:
            self.symbol_rate = 1e6

        # 每符号采样数
        self.samples_per_symbol = int(config.sample_rate / self.symbol_rate)

        # 频偏
        self.freq_deviation = config.modulation_index * self.symbol_rate / 2

        # 生成高斯滤波器
        self._generate_gaussian_filter()

    def _generate_gaussian_filter(self):
        """生成高斯滤波器"""
        config = self.config

        # 滤波器长度 (符号数)
        filter_span = 4
        filter_len = filter_span * self.samples_per_symbol + 1

        # 时间轴
        t = np.linspace(
            -filter_span / 2,
            filter_span / 2,
            filter_len
        )

        # 高斯滤波器脉冲响应
        # h(t) = sqrt(2*pi/ln(2)) * BT * exp(-2*(pi*BT*t)^2 / ln(2))
        alpha = np.sqrt(2 * np.pi / np.log(2)) * config.bt
        self.gaussian_filter = alpha * np.exp(
            -2 * (np.pi * config.bt * t) ** 2 / np.log(2)
        )
        # 归一化
        self.gaussian_filter /= np.sum(self.gaussian_filter)

    def modulate(self, bits: np.ndarray) -> np.ndarray:
        """
        GFSK 调制

        Args:
            bits: 输入比特流 (0/1)

        Returns:
            IQ 复基带信号
        """
        config = self.config

        # 1. NRZ 编码 (0 -> -1, 1 -> +1)
        nrz = 2 * bits.astype(np.float64) - 1

        # 2. 上采样 (使用阶梯信号而非脉冲)
        # 每个符号重复 samples_per_symbol 次
        upsampled = np.repeat(nrz, self.samples_per_symbol)

        # 3. 高斯滤波 (平滑频率过渡)
        filtered = np.convolve(upsampled, self.gaussian_filter, mode='same')

        # 4. 频率调制 (CPM - 连续相位调制)
        # 瞬时频率 = freq_deviation * filtered
        # 相位 = 2*pi * integral(freq) / sample_rate
        freq_signal = self.freq_deviation * filtered
        phase = 2 * np.pi * np.cumsum(freq_signal) / config.sample_rate

        # 5. 添加中心频率偏移
        if config.center_freq != 0:
            t = np.arange(len(phase)) / config.sample_rate
            phase += 2 * np.pi * config.center_freq * t

        # 6. 生成 IQ 信号 (恒包络)
        iq_signal = np.exp(1j * phase)

        return iq_signal

    def modulate_packet(self, packet_bits: np.ndarray) -> np.ndarray:
        """
        调制完整数据包

        Args:
            packet_bits: BLE 数据包比特流

        Returns:
            IQ 复基带信号
        """
        return self.modulate(packet_bits)

    def add_noise(self, signal: np.ndarray, snr_db: float) -> np.ndarray:
        """
        添加 AWGN 噪声

        Args:
            signal: 输入信号
            snr_db: 信噪比 (dB)

        Returns:
            加噪信号
        """
        # 信号功率
        signal_power = np.mean(np.abs(signal) ** 2)

        # 噪声功率
        noise_power = signal_power / (10 ** (snr_db / 10))

        # 生成复高斯噪声
        noise = np.sqrt(noise_power / 2) * (
            np.random.randn(len(signal)) + 1j * np.random.randn(len(signal))
        )

        return signal + noise

    def add_frequency_offset(self, signal: np.ndarray, freq_offset: float) -> np.ndarray:
        """
        添加载波频偏

        Args:
            signal: 输入信号
            freq_offset: 频率偏移 (Hz)

        Returns:
            带频偏的信号
        """
        t = np.arange(len(signal)) / self.config.sample_rate
        return signal * np.exp(1j * 2 * np.pi * freq_offset * t)

    def add_timing_offset(self, signal: np.ndarray, timing_offset: float) -> np.ndarray:
        """
        添加定时偏移 (通过插值实现)

        Args:
            signal: 输入信号
            timing_offset: 定时偏移 (采样点数, 可以是小数)

        Returns:
            带定时偏移的信号
        """
        from scipy import interpolate

        x_orig = np.arange(len(signal))
        x_new = x_orig - timing_offset

        # 使用三次样条插值
        interp_real = interpolate.interp1d(
            x_orig, signal.real, kind='cubic', fill_value='extrapolate'
        )
        interp_imag = interpolate.interp1d(
            x_orig, signal.imag, kind='cubic', fill_value='extrapolate'
        )

        return interp_real(x_new) + 1j * interp_imag(x_new)
