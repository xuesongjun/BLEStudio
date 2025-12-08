"""
BLE GFSK 解调器
实现 BLE 基带信号解调
"""

import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass
from .packet import BLEPhyMode, BLEPacket


@dataclass
class DemodulatorConfig:
    """解调器配置"""
    phy_mode: BLEPhyMode = BLEPhyMode.LE_1M
    sample_rate: float = 8e6          # 采样率 (Hz)
    access_address: int = 0x8E89BED6  # 接入地址
    channel: int = 37                  # 信道号
    whitening: bool = True             # 是否启用去白化 (默认开启)


@dataclass
class DemodulationResult:
    """解调结果"""
    success: bool                      # 是否成功解调
    bits: np.ndarray                   # 解调后的比特
    pdu: bytes                         # PDU 数据
    crc_valid: bool                    # CRC 校验结果
    rssi: float                        # 信号强度
    freq_offset: float                 # 频偏估计
    timing_offset: float               # 定时偏移估计


class BLEDemodulator:
    """BLE GFSK 解调器"""

    # 广播接入地址
    ADV_ACCESS_ADDRESS = 0x8E89BED6

    def __init__(self, config: Optional[DemodulatorConfig] = None):
        self.config = config or DemodulatorConfig()
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

        # 生成接入地址比特序列用于相关检测
        self._generate_access_address_pattern()

    def _generate_access_address_pattern(self):
        """生成接入地址比特模式"""
        aa = self.config.access_address
        bits = []
        for i in range(32):
            bits.append((aa >> i) & 1)
        self.access_address_bits = np.array(bits, dtype=np.uint8)

        # 生成前导码 + 接入地址的匹配模式
        if self.config.phy_mode == BLEPhyMode.LE_2M:
            preamble = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)
        else:
            preamble = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)

        self.sync_pattern = np.concatenate([preamble, self.access_address_bits])

    def _fm_demodulate(self, signal: np.ndarray) -> np.ndarray:
        """
        FM 解调 (差分相位法)

        Args:
            signal: IQ 复信号

        Returns:
            瞬时频率信号
        """
        # 差分相位
        phase_diff = np.angle(signal[1:] * np.conj(signal[:-1]))
        return np.concatenate([[0], phase_diff])

    def _matched_filter(self, signal: np.ndarray) -> np.ndarray:
        """
        匹配滤波器

        Args:
            signal: 输入信号

        Returns:
            滤波后信号
        """
        # 简单的移动平均滤波器
        h = np.ones(self.samples_per_symbol) / self.samples_per_symbol
        return np.convolve(signal, h, mode='same')

    def _symbol_timing_recovery(self, signal: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        符号定时恢复 (Mueller-Muller 算法简化版)

        Args:
            signal: 输入信号

        Returns:
            (采样点, 定时偏移估计)
        """
        sps = self.samples_per_symbol

        # 简单方法: 使用过采样信号的能量来找最佳采样时刻
        num_symbols = len(signal) // sps

        # 计算每个可能采样相位的能量
        energies = np.zeros(sps)
        for phase in range(sps):
            samples = signal[phase::sps][:num_symbols]
            energies[phase] = np.sum(np.abs(samples) ** 2)

        # 找到最大能量的相位
        best_phase = np.argmax(energies)

        # 采样
        samples = signal[best_phase::sps]

        return samples, best_phase / sps

    def _detect_access_address(self, bits: np.ndarray) -> int:
        """
        检测接入地址位置

        Args:
            bits: 比特流

        Returns:
            接入地址起始位置 (-1 表示未找到)
        """
        pattern = self.sync_pattern
        pattern_nrz = 2 * pattern.astype(np.float64) - 1
        bits_nrz = 2 * bits.astype(np.float64) - 1

        # 相关检测
        correlation = np.correlate(bits_nrz, pattern_nrz, mode='valid')

        # 寻找峰值
        threshold = len(pattern) * 0.8  # 80% 匹配阈值
        peaks = np.where(correlation > threshold)[0]

        if len(peaks) > 0:
            return peaks[0]

        return -1

    def _remove_whitening(self, bits: np.ndarray, channel: int) -> np.ndarray:
        """去白化"""
        # 使用 BLEPacket 中的白化函数
        lfsr = (channel & 0x3F) | 0x40

        result = np.zeros(len(bits), dtype=np.uint8)
        for i in range(len(bits)):
            result[i] = bits[i] ^ (lfsr & 1)
            feedback = ((lfsr >> 6) ^ (lfsr >> 3)) & 1
            lfsr = ((lfsr << 1) | feedback) & 0x7F

        return result

    def _check_crc(self, data: bytes) -> Tuple[bool, int]:
        """
        检查 CRC (兼容 MATLAB bleWaveformGenerator)

        Args:
            data: PDU + CRC 数据

        Returns:
            (CRC 是否正确, 计算的 CRC 值)
        """
        if len(data) < 3:
            return False, 0

        # PDU 数据 (不含 CRC)
        pdu = data[:-3]

        # 接收到的 CRC
        received_crc = data[-3] | (data[-2] << 8) | (data[-1] << 16)

        # 计算 CRC (MATLAB 兼容方法)
        # 1. 将字节转为比特流 (LSB first per byte)
        bits = []
        for byte in pdu:
            for i in range(8):
                bits.append((byte >> i) & 1)

        # 2. MSB-first 直接方法 CRC 计算
        poly = 0x00065B
        crc = 0x555555  # 初始值

        for bit in bits:
            msb = (crc >> 23) & 1
            crc = (crc << 1) & 0xFFFFFF
            if msb ^ bit:
                crc ^= poly

        # 3. Bit reverse CRC 输出
        crc_rev = 0
        for i in range(24):
            if crc & (1 << i):
                crc_rev |= (1 << (23 - i))

        calculated_crc = crc_rev

        return calculated_crc == received_crc, calculated_crc

    def _bits_to_bytes(self, bits: np.ndarray) -> bytes:
        """比特转字节 (LSB first)"""
        result = []
        for i in range(0, len(bits) - 7, 8):
            byte = 0
            for j in range(8):
                byte |= (bits[i + j] << j)
            result.append(byte)
        return bytes(result)

    def _estimate_frequency_offset(self, signal: np.ndarray) -> float:
        """
        估计载波频偏

        Args:
            signal: IQ 信号

        Returns:
            频偏估计 (Hz)
        """
        # 使用自相关法估计频偏
        autocorr = np.sum(signal[1:] * np.conj(signal[:-1]))
        phase_diff = np.angle(autocorr)
        freq_offset = phase_diff * self.config.sample_rate / (2 * np.pi)
        return freq_offset

    def _compensate_frequency_offset(self, signal: np.ndarray, freq_offset: float) -> np.ndarray:
        """补偿频偏"""
        t = np.arange(len(signal)) / self.config.sample_rate
        return signal * np.exp(-1j * 2 * np.pi * freq_offset * t)

    def demodulate(self, signal: np.ndarray) -> DemodulationResult:
        """
        解调 BLE 信号

        Args:
            signal: IQ 复基带信号

        Returns:
            解调结果
        """
        config = self.config

        # 1. 估计 RSSI
        rssi = 10 * np.log10(np.mean(np.abs(signal) ** 2) + 1e-10)

        # 2. 频偏估计和补偿
        freq_offset = self._estimate_frequency_offset(signal)
        signal_compensated = self._compensate_frequency_offset(signal, freq_offset)

        # 3. FM 解调
        freq_signal = self._fm_demodulate(signal_compensated)

        # 4. 匹配滤波
        filtered = self._matched_filter(freq_signal)

        # 5. 符号定时恢复
        samples, timing_offset = self._symbol_timing_recovery(filtered)

        # 6. 判决
        bits = (samples > 0).astype(np.uint8)

        # 7. 检测接入地址
        aa_pos = self._detect_access_address(bits)

        if aa_pos < 0:
            return DemodulationResult(
                success=False,
                bits=bits,
                pdu=b'',
                crc_valid=False,
                rssi=rssi,
                freq_offset=freq_offset,
                timing_offset=timing_offset
            )

        # 8. 提取数据部分 (跳过前导码和接入地址)
        # aa_pos 是 sync_pattern (前导码+接入地址) 的起始位置
        # 需要跳过前导码和接入地址
        preamble_len = 16 if config.phy_mode == BLEPhyMode.LE_2M else 8
        data_start = aa_pos + preamble_len + 32  # 前导码 + 接入地址

        if data_start >= len(bits):
            return DemodulationResult(
                success=False,
                bits=bits,
                pdu=b'',
                crc_valid=False,
                rssi=rssi,
                freq_offset=freq_offset,
                timing_offset=timing_offset
            )

        # 9. 去白化 (根据配置决定)
        data_bits = bits[data_start:]
        if config.whitening:
            dewhitened_bits = self._remove_whitening(data_bits, config.channel)
        else:
            dewhitened_bits = data_bits  # 不去白化

        # 10. 解析 PDU
        data_bytes = self._bits_to_bytes(dewhitened_bits)

        if len(data_bytes) < 2:
            return DemodulationResult(
                success=False,
                bits=bits,
                pdu=b'',
                crc_valid=False,
                rssi=rssi,
                freq_offset=freq_offset,
                timing_offset=timing_offset
            )

        # PDU 长度
        pdu_length = data_bytes[1]
        total_length = 2 + pdu_length + 3  # Header(2) + Payload + CRC(3)

        if len(data_bytes) < total_length:
            return DemodulationResult(
                success=False,
                bits=bits,
                pdu=data_bytes[:2],
                crc_valid=False,
                rssi=rssi,
                freq_offset=freq_offset,
                timing_offset=timing_offset
            )

        # 11. CRC 校验
        pdu_with_crc = data_bytes[:total_length]
        crc_valid, _ = self._check_crc(pdu_with_crc)

        pdu = pdu_with_crc[:-3]  # 不含 CRC

        return DemodulationResult(
            success=crc_valid,
            bits=bits,
            pdu=pdu,
            crc_valid=crc_valid,
            rssi=rssi,
            freq_offset=freq_offset,
            timing_offset=timing_offset
        )

    def find_packets(self, signal: np.ndarray, max_packets: int = 10) -> List[DemodulationResult]:
        """
        在信号中查找多个数据包

        Args:
            signal: IQ 信号
            max_packets: 最大数据包数量

        Returns:
            解调结果列表
        """
        results = []
        offset = 0
        window_size = int(self.config.sample_rate * 0.5e-3)  # 0.5ms 窗口

        while offset < len(signal) - window_size and len(results) < max_packets:
            window = signal[offset:offset + window_size]
            result = self.demodulate(window)

            if result.success:
                results.append(result)
                # 跳过这个数据包
                packet_samples = len(result.bits) * self.samples_per_symbol
                offset += packet_samples
            else:
                # 向前滑动
                offset += self.samples_per_symbol * 8

        return results
