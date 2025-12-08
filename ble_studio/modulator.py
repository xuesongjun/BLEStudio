"""
BLE GFSK 调制器
实现 BLE 基带信号调制 (兼容 MATLAB Bluetooth Toolbox)
"""

import numpy as np
from typing import Optional
from dataclasses import dataclass
from scipy.special import erf
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
    """BLE GFSK 调制器 (MATLAB 兼容实现)"""

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

        # 生成高斯频率脉冲
        self._generate_gaussian_pulse()

    @staticmethod
    def _qfunc(t: np.ndarray) -> np.ndarray:
        """Q 函数: Q(t) = 0.5 * (1 - erf(t / sqrt(2)))"""
        return 0.5 * (1 - erf(t / np.sqrt(2)))

    def _generate_gaussian_pulse(self):
        """
        生成高斯频率脉冲 (MATLAB bleWaveformGenerator 兼容)

        使用 Q 函数生成精确的高斯频率脉冲，确保相位变化正确
        MATLAB 默认 PulseLength = 1，这样才能满足 BLE RF 测试指标:
        - ΔF1avg (01010101 模式): 225-275 kHz
        - ΔF2max (11110000 模式): >= 185 kHz
        """
        config = self.config
        N = self.samples_per_symbol
        BT = config.bt

        # 脉冲跨度 (符号数) - MATLAB 默认 PulseLength = 1
        # 使用 L=1 才能满足 BLE RF 测试指标 (ΔF1avg 225-275 kHz)
        L = 1

        # 使用高过采样率计算精确脉冲
        min_os_ratio = 64
        R_up = max(1, int(np.ceil(min_os_ratio / N)))

        tSym = 1.0  # 归一化符号周期
        Ts = tSym / (N * R_up)
        Offset = Ts / 2

        # 时间轴
        num_samples = L * N * R_up
        t = np.arange(num_samples) * Ts + Offset
        t = t - tSym * (L / 2)  # 中心对齐

        # 高斯频率脉冲 g(t) 使用 Q 函数
        K = 2 * np.pi * BT / np.sqrt(np.log(2))
        g = (1 / (2 * tSym)) * (self._qfunc(K * (t - tSym / 2)) -
                                 self._qfunc(K * (t + tSym / 2)))

        # 积分得到相位脉冲
        q = Ts * np.cumsum(g)

        # 归一化: 使得单个符号的相位变化 = 0.5 (对于 h=1)
        # 对于 BLE h=0.5, 每符号相位变化 = h * pi = pi/2
        if q[-1] != 0:
            g = g * 0.5 / q[-1]

        # 下采样到目标采样率
        g_reshaped = g[:num_samples // R_up * R_up].reshape(-1, R_up)
        self.freq_pulse = np.mean(g_reshaped, axis=1) * R_up

        # 归一化滤波器
        self.freq_pulse = self.freq_pulse / np.sum(self.freq_pulse)

    def modulate(self, bits: np.ndarray) -> np.ndarray:
        """
        GFSK 调制 (MATLAB 兼容)

        Args:
            bits: 输入比特流 (0/1)

        Returns:
            IQ 复基带信号
        """
        config = self.config
        N = self.samples_per_symbol
        h = config.modulation_index

        # NRZ 编码: 0 -> -1, 1 -> +1
        symbols = 2 * bits.astype(np.float64) - 1

        # 上采样 (零插入)
        upsampled = np.zeros(len(symbols) * N)
        upsampled[::N] = symbols

        # 频率脉冲成形
        # 使用 'same' 模式保持输出长度，自动处理滤波器延迟
        freq_shaped = np.convolve(upsampled, self.freq_pulse, mode='same')

        # 相位积分
        # 每符号相位变化 = h * pi * symbol
        # 相位增量 = h * pi * freq_shaped (因为 freq_pulse 归一化到 1)
        phase_inc = h * np.pi * freq_shaped
        phase = np.cumsum(phase_inc)

        # 添加中心频率偏移
        if config.center_freq != 0:
            t = np.arange(len(phase)) / config.sample_rate
            phase += 2 * np.pi * config.center_freq * t

        # 生成 IQ 信号
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
