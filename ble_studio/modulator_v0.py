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
    pulse_length: int = 1             # 频率脉冲长度 (符号数), MATLAB 默认为 1


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

        # 频偏 (用于兼容性，实际调制使用 modulation_index)
        self.freq_deviation = config.modulation_index * self.symbol_rate / 2

        # 生成 GMSK 频率脉冲 (MATLAB 风格)
        self._generate_frequency_pulse()

    @staticmethod
    def _qfunc(t: np.ndarray) -> np.ndarray:
        """Q 函数: Q(t) = 0.5 * erfc(t / sqrt(2)) = 0.5 * (1 - erf(t / sqrt(2)))"""
        return 0.5 * (1 - erf(t / np.sqrt(2)))

    def _generate_frequency_pulse(self):
        """
        生成 GMSK 频率脉冲 (参考 MATLAB gmskmodparams)

        MATLAB 实现:
        1. 在高过采样率下计算精确的频率脉冲 g(t)
        2. 对 g(t) 积分得到相位脉冲 q(t)
        3. 下采样到目标采样率
        """
        config = self.config
        N = self.samples_per_symbol  # 每符号采样数
        L = config.pulse_length      # 脉冲长度 (符号数)
        BT = config.bt               # 带宽时间积

        # 使用高过采样率计算精确脉冲 (MATLAB 使用 min_os_ratio=64)
        min_os_ratio = 64
        R_up = max(1, int(np.ceil(min_os_ratio / N)))  # 上采样因子

        tSym = 1.0  # 符号周期 (归一化)
        Ts = tSym / (N * R_up)  # 过采样周期
        Offset = Ts / 2  # 梯形积分偏移

        # 精细时间轴
        t = np.arange(Offset, L * tSym - Ts + Offset + Ts/2, Ts)
        t = t[:L * N * R_up]  # 确保长度正确
        t = t - tSym * (L / 2)  # 偏移到脉冲中心

        # 高斯频率脉冲 g(t) (使用 Q 函数)
        # g(t) = (1/2T) * [Q(K*(t-T/2)) - Q(K*(t+T/2))]
        # K = 2*pi*BT / sqrt(ln(2))
        K = 2 * np.pi * BT / np.sqrt(np.log(2))
        g = (1 / (2 * tSym)) * (self._qfunc(K * (t - tSym / 2)) -
                                 self._qfunc(K * (t + tSym / 2)))

        # 积分得到相位脉冲 q(t)
        q = Ts * np.cumsum(g)

        # 归一化使总相位变化为 0.5 (对应 h=0.5 时每符号 pi/2 相位)
        g = g * 0.5 / q[-1] if q[-1] != 0 else g

        # 下采样: 每 R_up 个样本取平均
        g_len = len(g)
        g_wrap = np.mean(g[:g_len // R_up * R_up].reshape(-1, R_up), axis=1)

        # 缩放到采样率
        g = Ts * R_up * g_wrap

        # 最终相位脉冲 q
        self.phase_pulse = np.concatenate([[0], np.cumsum(g[:-1])])
        self.freq_pulse = g

    def modulate(self, bits: np.ndarray) -> np.ndarray:
        """
        GFSK 调制 (MATLAB 兼容实现)

        Args:
            bits: 输入比特流 (0/1)

        Returns:
            IQ 复基带信号
        """
        config = self.config
        N = self.samples_per_symbol
        L = config.pulse_length
        h = config.modulation_index
        nSym = len(bits)

        # NRZ 编码: 0 -> -1, 1 -> +1
        symbols = 2 * bits.astype(np.float64) - 1

        # 上采样 (每符号重复 N 次)
        data = np.repeat(symbols, N)

        # 添加前导历史 (用于滤波器初始化)
        if L > 1:
            symbPreHist = h * np.ones((L - 1) * N)
        else:
            symbPreHist = h * np.ones(N)

        scaledData = np.concatenate([symbPreHist, h * data])

        # 计算预历史相位偏移
        if L > 1:
            q_tail = self.phase_pulse[N:]
            phvec = np.sum(h * q_tail.reshape(N, L - 1, order='F'), axis=1)
            preHistPhase = 2 * np.pi * phvec[0]
        else:
            preHistPhase = 0

        # CPM 调制: 逐符号计算相位
        phi = np.zeros(nSym * N)
        filtWin = np.arange(L * N - 1, -1, -1)  # 滤波窗口索引
        phState = 0.0

        for ind in range(nSym):
            # 提取滤波窗口内的数据
            filtData = scaledData[filtWin + ind * N] * self.phase_pulse

            # 按符号周期求和
            filtPhase = np.sum(filtData.reshape(N, L, order='F'), axis=1)

            # 累加相位
            phi[ind * N:(ind + 1) * N] = phState + filtPhase

            # 更新相位状态 (每符号增加 h/2 * symbol)
            phState = phState + 0.5 * scaledData[ind * N]

        # 最终相位
        cpmPhase = 2 * np.pi * phi - preHistPhase

        # 添加中心频率偏移
        if config.center_freq != 0:
            t = np.arange(len(cpmPhase)) / config.sample_rate
            cpmPhase += 2 * np.pi * config.center_freq * t

        # 生成 IQ 信号
        iq_signal = np.exp(1j * cpmPhase)

        return iq_signal