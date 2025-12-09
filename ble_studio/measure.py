"""
BLE RF 测量模块

负责 BLE RF-PHY 规范中定义的各项射频指标测量:
- ΔF1: 调制特性测试 (0x0F pattern)
- ΔF2: 调制特性测试 (0x55 pattern)
- ICFT: 初始载波频率容差
- 频率漂移
- 功率测量
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class RFMetrics:
    """RF 测量结果"""
    # ΔF1 指标 (使用 0x0F pattern 测量)
    delta_f1_avg: float = 0.0  # kHz
    delta_f1_max: float = 0.0  # kHz
    delta_f1_min: float = 0.0  # kHz

    # ΔF2 指标 (使用 0x55 pattern 测量)
    delta_f2_avg: float = 0.0  # kHz
    delta_f2_max: float = 0.0  # kHz
    delta_f2_ratio: float = 0.0  # ΔF2/ΔF1

    # 频率指标
    freq_drift: float = 0.0   # kHz, 频率漂移
    drift_rate: float = 0.0   # kHz, 漂移率
    icft: float = 0.0         # kHz, 初始载波频率偏差
    avg_one: float = 0.0      # kHz, '1' 符号平均频率
    avg_zero: float = 0.0     # kHz, '0' 符号平均频率

    # 功率指标
    p_avg_dbm: float = -100.0  # dBm
    p_peak_dbm: float = -100.0  # dBm

    # 判定结果 (BLE RF-PHY 规范, 1M PHY)
    delta_f1_pass: bool = False  # 225 kHz ≤ ΔF1avg ≤ 275 kHz
    delta_f2_pass: bool = False  # ΔF2 ≥ 185 kHz
    ratio_pass: bool = False     # ΔF2/ΔF1 ≥ 0.8
    icft_pass: bool = False      # |ICFT| ≤ 150 kHz
    drift_pass: bool = False     # |f0 - fn| ≤ 50 kHz

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'delta_f1_avg': self.delta_f1_avg,
            'delta_f1_max': self.delta_f1_max,
            'delta_f1_min': self.delta_f1_min,
            'delta_f2_avg': self.delta_f2_avg,
            'delta_f2_max': self.delta_f2_max,
            'delta_f2_ratio': self.delta_f2_ratio,
            'freq_drift': self.freq_drift,
            'drift_rate': self.drift_rate,
            'icft': self.icft,
            'avg_one': self.avg_one,
            'avg_zero': self.avg_zero,
            'p_avg_dbm': self.p_avg_dbm,
            'p_peak_dbm': self.p_peak_dbm,
            'delta_f1_pass': self.delta_f1_pass,
            'delta_f2_pass': self.delta_f2_pass,
            'ratio_pass': self.ratio_pass,
            'icft_pass': self.icft_pass,
            'drift_pass': self.drift_pass,
        }


class RFMeasure:
    """
    BLE RF 测量器

    符合 BLE RF-PHY Test Specification 的射频指标测量
    """

    def __init__(self, sample_rate: float = 8e6, samples_per_symbol: int = 8):
        """
        初始化测量器

        Args:
            sample_rate: 采样率 (Hz)
            samples_per_symbol: 每符号采样数
        """
        self.sample_rate = sample_rate
        self.samples_per_symbol = samples_per_symbol

    def measure(self, signal: np.ndarray, payload_type: str = 'PRBS9') -> RFMetrics:
        """
        测量 RF 指标

        Args:
            signal: 复数 IQ 信号
            payload_type: 负载类型 (PRBS9, PATTERN_11110000, PATTERN_10101010 等)

        Returns:
            RFMetrics 测量结果
        """
        # 预处理: 去除前导/尾部空白
        signal = self._trim_signal(signal)
        if signal is None or len(signal) < 20 * self.samples_per_symbol:
            return RFMetrics()

        # 计算瞬时频率
        freq_inst = self._compute_instantaneous_frequency(signal)
        if len(freq_inst) < 20 * self.samples_per_symbol:
            return RFMetrics()

        # 提取各区域频率
        preamble_freq, payload_freq = self._extract_regions(freq_inst)

        # 计算基本频率统计
        symbol_stats = self._compute_symbol_statistics(payload_freq)

        # 计算各项指标
        icft = self._measure_icft(preamble_freq)
        delta_f1 = self._measure_delta_f1(payload_freq, payload_type)
        delta_f2 = self._measure_delta_f2(payload_freq, payload_type, symbol_stats)
        drift = self._measure_frequency_drift(payload_freq)
        power = self._measure_power(signal)

        # 计算比值
        delta_f2_ratio = delta_f2['avg'] / delta_f1['avg'] if delta_f1['avg'] > 0 else 0

        return RFMetrics(
            delta_f1_avg=delta_f1['avg'],
            delta_f1_max=delta_f1['max'],
            delta_f1_min=delta_f1['min'],
            delta_f2_avg=delta_f2['avg'],
            delta_f2_max=delta_f2['max'],
            delta_f2_ratio=delta_f2_ratio,
            freq_drift=drift['max'],
            drift_rate=drift['rate'],
            icft=icft,
            avg_one=symbol_stats['avg_one'],
            avg_zero=symbol_stats['avg_zero'],
            p_avg_dbm=power['avg'],
            p_peak_dbm=power['peak'],
            # 判定结果
            delta_f1_pass=225 <= delta_f1['avg'] <= 275,
            delta_f2_pass=delta_f2['avg'] >= 185,
            ratio_pass=delta_f2_ratio >= 0.8,
            icft_pass=abs(icft) <= 150,
            drift_pass=drift['max'] <= 50,
        )

    def _trim_signal(self, signal: np.ndarray) -> Optional[np.ndarray]:
        """去除信号前导/尾部空白区域"""
        amplitude = np.abs(signal)
        if np.max(amplitude) == 0:
            return None

        threshold = np.max(amplitude) * 0.01
        valid_mask = amplitude > threshold
        valid_indices = np.where(valid_mask)[0]

        if len(valid_indices) == 0:
            return None

        return signal[valid_indices[0]:valid_indices[-1] + 1]

    def _compute_instantaneous_frequency(self, signal: np.ndarray) -> np.ndarray:
        """计算瞬时频率"""
        phase = np.unwrap(np.angle(signal))
        return np.diff(phase) * self.sample_rate / (2 * np.pi)

    def _extract_regions(self, freq_inst: np.ndarray) -> tuple:
        """提取前导码和 payload 区域"""
        sps = self.samples_per_symbol

        # 前导码: 8 bits
        preamble_samples = 8 * sps
        preamble_freq = freq_inst[:preamble_samples]

        # Payload: 跳过前导码(8) + 接入地址(32) + PDU头(16) = 56 bits
        header_bits = 56
        payload_start = header_bits * sps
        payload_freq = freq_inst[payload_start:] if len(freq_inst) > payload_start else freq_inst

        return preamble_freq, payload_freq

    def _compute_symbol_statistics(self, freq_payload: np.ndarray) -> dict:
        """计算符号频率统计"""
        sps = self.samples_per_symbol
        num_symbols = len(freq_payload) // sps

        symbol_peaks = []
        for i in range(num_symbols):
            start = i * sps
            symbol_data = freq_payload[start:start + sps]
            peak_idx = np.argmax(np.abs(symbol_data))
            symbol_peaks.append(symbol_data[peak_idx])

        symbol_peaks = np.array(symbol_peaks)
        freq_ones = symbol_peaks[symbol_peaks > 0]
        freq_zeros = symbol_peaks[symbol_peaks < 0]

        return {
            'peaks': symbol_peaks,
            'avg_one': np.mean(freq_ones) / 1e3 if len(freq_ones) > 0 else 0,
            'avg_zero': np.mean(freq_zeros) / 1e3 if len(freq_zeros) > 0 else 0,
        }

    def _measure_icft(self, preamble_freq: np.ndarray) -> float:
        """测量 ICFT (初始载波频率偏差)"""
        # 前导码是 10101010，理想情况下积分为 0
        return np.mean(preamble_freq) / 1e3  # kHz

    def _measure_delta_f1(self, freq_payload: np.ndarray, payload_type: str) -> dict:
        """
        测量 ΔF1 (使用 0x0F / 11110000 pattern)

        BLE RF-PHY 规范:
        - f1_ccf: 每个 00001111 序列的中心频率
        - ΔF1_max: 第 2,3,6,7 bit 相对于 f1_ccf 的偏移平均值
        - 测量从 payload 第 5 bit 开始，最后 4 bits 丢弃
        """
        sps = self.samples_per_symbol
        payload_upper = payload_type.upper()

        is_0f_pattern = any(p in payload_upper for p in [
            'PATTERN_11110000', 'PATTERN_00001111',
            '11110000', '00001111', '0XF0', '0X0F'
        ])

        delta_f1_values = []

        if is_0f_pattern:
            # 按规范测量
            measure_start_bit = 4
            measure_end_bit = len(freq_payload) // sps - 4
            measurable_bits = measure_end_bit - measure_start_bit
            num_sequences = measurable_bits // 8

            for seq_idx in range(num_sequences):
                seq_start = (measure_start_bit + seq_idx * 8) * sps
                seq_freq = freq_payload[seq_start:seq_start + 8 * sps]

                if len(seq_freq) < 8 * sps:
                    continue

                f1_ccf = np.mean(seq_freq)

                # ΔF1_max: 第 2,3,6,7 bit 偏移的平均值
                bit_deltas = []
                for bit_idx in [1, 2, 5, 6]:
                    bit_freq = seq_freq[bit_idx * sps:(bit_idx + 1) * sps]
                    bit_deltas.append(abs(np.mean(bit_freq) - f1_ccf))

                delta_f1_values.append(np.mean(bit_deltas))
        else:
            # 通用计算: 使用峰值相对于中心的偏移
            num_symbols = len(freq_payload) // sps
            for i in range(num_symbols):
                symbol_data = freq_payload[i * sps:(i + 1) * sps]
                peak = symbol_data[np.argmax(np.abs(symbol_data))]
                delta_f1_values.append(abs(peak))

        if not delta_f1_values:
            return {'avg': 0, 'max': 0, 'min': 0}

        return {
            'avg': np.mean(delta_f1_values) / 1e3,
            'max': np.max(delta_f1_values) / 1e3,
            'min': np.min(delta_f1_values) / 1e3,
        }

    def _measure_delta_f2(self, freq_payload: np.ndarray, payload_type: str,
                          symbol_stats: dict) -> dict:
        """
        测量 ΔF2 (使用 0x55 / 10101010 pattern)

        BLE RF-PHY 规范:
        - f2_ccf: 每个 10101010 序列的中心频率
        - ΔF2_max: 每个 bit 的最大采样值相对于 f2_ccf 的偏移
        - 测量从 payload 第 5 bit 开始，最后 4 bits 丢弃
        """
        sps = self.samples_per_symbol
        payload_upper = payload_type.upper()

        is_55_pattern = any(p in payload_upper for p in [
            'PATTERN_10101010', 'PATTERN_01010101',
            '10101010', '01010101', '0X55', '0XAA'
        ])

        delta_f2_values = []

        if is_55_pattern:
            # 按规范测量
            measure_start_bit = 4
            measure_end_bit = len(freq_payload) // sps - 4
            measurable_bits = measure_end_bit - measure_start_bit
            num_sequences = measurable_bits // 8

            for seq_idx in range(num_sequences):
                seq_start = (measure_start_bit + seq_idx * 8) * sps
                seq_freq = freq_payload[seq_start:seq_start + 8 * sps]

                if len(seq_freq) < 8 * sps:
                    continue

                f2_ccf = np.mean(seq_freq)

                # ΔF2_max: 每个 bit 的最大采样值偏移
                for bit_idx in range(8):
                    bit_freq = seq_freq[bit_idx * sps:(bit_idx + 1) * sps]
                    max_sample = bit_freq[np.argmax(np.abs(bit_freq))]
                    delta_f2_values.append(abs(max_sample - f2_ccf))
        else:
            # 通用计算: 使用稳定调制指标
            avg_one = symbol_stats['avg_one'] * 1e3  # 转回 Hz
            avg_zero = symbol_stats['avg_zero'] * 1e3
            delta_f2_stable = abs(avg_one - avg_zero) / 2
            delta_f2_values = [delta_f2_stable]

        if not delta_f2_values:
            return {'avg': 0, 'max': 0}

        return {
            'avg': np.mean(delta_f2_values) / 1e3,
            'max': np.max(delta_f2_values) / 1e3,
        }

    def _measure_frequency_drift(self, freq_payload: np.ndarray) -> dict:
        """测量频率漂移"""
        sps = self.samples_per_symbol
        drift_interval = 10 * sps  # 每 10 bits 测量一次
        num_points = len(freq_payload) // drift_interval

        if num_points < 2:
            return {'max': 0, 'rate': 0}

        drift_freqs = []
        for i in range(num_points):
            start = i * drift_interval
            drift_freqs.append(np.mean(freq_payload[start:start + drift_interval]))

        f0 = drift_freqs[0]
        freq_drift_max = max(abs(f - f0) for f in drift_freqs)

        drift_rates = [abs(drift_freqs[i + 1] - drift_freqs[i])
                       for i in range(len(drift_freqs) - 1)]
        drift_rate_max = max(drift_rates) if drift_rates else 0

        return {
            'max': freq_drift_max / 1e3,
            'rate': drift_rate_max / 1e3,
        }

    def _measure_power(self, signal: np.ndarray) -> dict:
        """测量功率"""
        power = np.abs(signal) ** 2
        p_avg = np.mean(power)
        p_peak = np.max(power)

        return {
            'avg': 10 * np.log10(p_avg + 1e-10),
            'peak': 10 * np.log10(p_peak + 1e-10),
        }


def calculate_rf_metrics(signal: np.ndarray, sample_rate: float,
                         samples_per_symbol: int = 8,
                         payload_type: str = 'PRBS9') -> dict:
    """
    便捷函数: 计算 RF 测量指标

    Args:
        signal: 复数 IQ 信号
        sample_rate: 采样率 (Hz)
        samples_per_symbol: 每符号采样数
        payload_type: 负载类型

    Returns:
        RF 指标字典
    """
    measurer = RFMeasure(sample_rate, samples_per_symbol)
    return measurer.measure(signal, payload_type).to_dict()
