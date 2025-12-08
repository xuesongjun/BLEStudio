"""
BLE 性能测试模块
实现 BER (误比特率) 和 PER (误包率) 测试
"""

import numpy as np
from typing import Optional, List, Dict, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import time

from .packet import BLEPacket, BLEPacketConfig, BLEPhyMode, create_advertising_packet
from .modulator import BLEModulator, ModulatorConfig
from .demodulator import BLEDemodulator, DemodulatorConfig


class TestMode(Enum):
    """测试模式"""
    BER = "ber"      # 误比特率测试
    PER = "per"      # 误包率测试


@dataclass
class TestConfig:
    """测试配置"""
    phy_mode: BLEPhyMode = BLEPhyMode.LE_1M
    sample_rate: float = 8e6
    channel: int = 37

    # SNR 范围
    snr_start: float = 0.0       # 起始 SNR (dB)
    snr_stop: float = 20.0       # 结束 SNR (dB)
    snr_step: float = 2.0        # SNR 步进 (dB)

    # 测试参数
    num_packets: int = 100       # 每个 SNR 点的包数量
    payload_length: int = 37     # 负载长度 (字节)

    # 信道损伤
    frequency_offset: float = 0.0     # 频偏 (Hz)
    timing_offset: float = 0.0        # 定时偏移 (采样点)

    # 随机种子
    seed: Optional[int] = None


@dataclass
class TestResult:
    """单个 SNR 点的测试结果"""
    snr_db: float
    ber: float                    # 误比特率
    per: float                    # 误包率
    total_bits: int               # 总比特数
    error_bits: int               # 错误比特数
    total_packets: int            # 总包数
    error_packets: int            # 错误包数
    avg_rssi: float               # 平均 RSSI
    avg_freq_offset: float        # 平均频偏估计


@dataclass
class TestReport:
    """完整测试报告"""
    test_mode: TestMode
    config: TestConfig
    results: List[TestResult]
    start_time: float
    end_time: float
    duration: float


class BLEPerformanceTester:
    """BLE 性能测试器"""

    def __init__(self, config: Optional[TestConfig] = None):
        self.config = config or TestConfig()
        self._setup()

    def _setup(self):
        """初始化测试环境"""
        config = self.config

        if config.seed is not None:
            np.random.seed(config.seed)

        # 配置调制器
        self.mod_config = ModulatorConfig(
            phy_mode=config.phy_mode,
            sample_rate=config.sample_rate,
            modulation_index=0.5,
            bt=0.5
        )
        self.modulator = BLEModulator(self.mod_config)

        # 配置解调器
        self.demod_config = DemodulatorConfig(
            phy_mode=config.phy_mode,
            sample_rate=config.sample_rate,
            access_address=0x8E89BED6,
            channel=config.channel
        )
        self.demodulator = BLEDemodulator(self.demod_config)

    def _generate_random_payload(self, length: int) -> bytes:
        """生成随机负载"""
        return bytes(np.random.randint(0, 256, length, dtype=np.uint8))

    def _generate_test_packet(self) -> Tuple[BLEPacket, np.ndarray]:
        """生成测试数据包"""
        config = self.config

        # 随机广播地址
        adv_address = bytes(np.random.randint(0, 256, 6, dtype=np.uint8))

        # 随机负载
        payload_data = self._generate_random_payload(config.payload_length)

        # 创建数据包
        packet = create_advertising_packet(
            adv_address=adv_address,
            adv_data=payload_data,
            channel=config.channel
        )

        # 生成比特流
        bits = packet.generate()

        return packet, bits

    def _apply_channel(self, signal: np.ndarray, snr_db: float) -> np.ndarray:
        """应用信道效应"""
        config = self.config

        # 添加 AWGN 噪声
        output = self.modulator.add_noise(signal, snr_db)

        # 添加频偏
        if config.frequency_offset != 0:
            output = self.modulator.add_frequency_offset(output, config.frequency_offset)

        # 添加定时偏移
        if config.timing_offset != 0:
            output = self.modulator.add_timing_offset(output, config.timing_offset)

        return output

    def _count_bit_errors(self, tx_bits: np.ndarray, rx_bits: np.ndarray) -> int:
        """计算比特错误数"""
        min_len = min(len(tx_bits), len(rx_bits))
        return int(np.sum(tx_bits[:min_len] != rx_bits[:min_len]))

    def run_ber_test(self, snr_db: float, num_packets: int = None,
                     progress_callback: Callable = None) -> TestResult:
        """
        运行 BER 测试

        Args:
            snr_db: 信噪比 (dB)
            num_packets: 包数量
            progress_callback: 进度回调函数

        Returns:
            TestResult 对象
        """
        if num_packets is None:
            num_packets = self.config.num_packets

        total_bits = 0
        error_bits = 0
        total_packets = 0
        error_packets = 0
        rssi_sum = 0.0
        freq_offset_sum = 0.0

        for i in range(num_packets):
            # 生成测试包
            packet, tx_bits = self._generate_test_packet()

            # 调制
            tx_signal = self.modulator.modulate(tx_bits)

            # 信道
            rx_signal = self._apply_channel(tx_signal, snr_db)

            # 解调
            result = self.demodulator.demodulate(rx_signal)

            # 统计
            total_packets += 1
            total_bits += len(tx_bits)

            rssi_sum += result.rssi
            freq_offset_sum += abs(result.freq_offset)

            if result.success and result.crc_valid:
                # 比较比特
                rx_bits = result.bits
                bit_errors = self._count_bit_errors(tx_bits, rx_bits)
                error_bits += bit_errors
                if bit_errors > 0:
                    error_packets += 1
            else:
                # 解调失败, 假设所有比特错误
                error_bits += len(tx_bits)
                error_packets += 1

            if progress_callback:
                progress_callback(i + 1, num_packets, snr_db)

        # 计算结果
        ber = error_bits / total_bits if total_bits > 0 else 1.0
        per = error_packets / total_packets if total_packets > 0 else 1.0
        avg_rssi = rssi_sum / total_packets if total_packets > 0 else 0.0
        avg_freq_offset = freq_offset_sum / total_packets if total_packets > 0 else 0.0

        return TestResult(
            snr_db=snr_db,
            ber=ber,
            per=per,
            total_bits=total_bits,
            error_bits=error_bits,
            total_packets=total_packets,
            error_packets=error_packets,
            avg_rssi=avg_rssi,
            avg_freq_offset=avg_freq_offset
        )

    def run_per_test(self, snr_db: float, num_packets: int = None,
                     progress_callback: Callable = None) -> TestResult:
        """
        运行 PER 测试

        Args:
            snr_db: 信噪比 (dB)
            num_packets: 包数量
            progress_callback: 进度回调函数

        Returns:
            TestResult 对象
        """
        # PER 测试与 BER 测试类似, 但主要关注 CRC 校验结果
        return self.run_ber_test(snr_db, num_packets, progress_callback)

    def run_snr_sweep(self, test_mode: TestMode = TestMode.BER,
                      progress_callback: Callable = None) -> TestReport:
        """
        运行 SNR 扫描测试

        Args:
            test_mode: 测试模式 (BER/PER)
            progress_callback: 进度回调函数

        Returns:
            TestReport 对象
        """
        config = self.config
        start_time = time.time()

        # 生成 SNR 点
        snr_points = np.arange(config.snr_start, config.snr_stop + config.snr_step, config.snr_step)

        results = []
        total_points = len(snr_points)

        for idx, snr_db in enumerate(snr_points):
            print(f"测试 SNR = {snr_db:.1f} dB ({idx + 1}/{total_points})...")

            if test_mode == TestMode.BER:
                result = self.run_ber_test(snr_db, progress_callback=progress_callback)
            else:
                result = self.run_per_test(snr_db, progress_callback=progress_callback)

            results.append(result)

            print(f"  BER = {result.ber:.2e}, PER = {result.per:.2%}")

        end_time = time.time()

        return TestReport(
            test_mode=test_mode,
            config=config,
            results=results,
            start_time=start_time,
            end_time=end_time,
            duration=end_time - start_time
        )

    def run_sensitivity_test(self, target_per: float = 0.308,
                             snr_range: Tuple[float, float] = (-10, 30),
                             precision: float = 0.1) -> float:
        """
        运行灵敏度测试 (二分搜索)

        Args:
            target_per: 目标 PER (BLE 规范默认 30.8%)
            snr_range: SNR 搜索范围
            precision: 精度 (dB)

        Returns:
            灵敏度 SNR (dB)
        """
        low, high = snr_range

        while high - low > precision:
            mid = (low + high) / 2
            result = self.run_per_test(mid)

            if result.per > target_per:
                low = mid
            else:
                high = mid

            print(f"SNR = {mid:.2f} dB, PER = {result.per:.2%}")

        return (low + high) / 2


def theoretical_ber_gfsk(snr_db: float, h: float = 0.5) -> float:
    """
    计算 GFSK 理论 BER (非相干检测)

    Args:
        snr_db: Eb/N0 (dB)
        h: 调制指数

    Returns:
        理论 BER
    """
    from scipy.special import erfc

    snr_linear = 10 ** (snr_db / 10)

    # 非相干 FSK 近似
    ber = 0.5 * np.exp(-snr_linear / 2)

    return ber


def plot_ber_curve(report: TestReport, show_theoretical: bool = True):
    """
    绘制 BER/PER 曲线

    Args:
        report: 测试报告
        show_theoretical: 是否显示理论曲线
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    snr_values = [r.snr_db for r in report.results]
    ber_values = [r.ber for r in report.results]
    per_values = [r.per for r in report.results]

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=('BER vs SNR', 'PER vs SNR'))

    # BER 曲线
    fig.add_trace(
        go.Scatter(x=snr_values, y=ber_values, mode='lines+markers',
                   name='仿真 BER', line=dict(color='blue', width=2)),
        row=1, col=1
    )

    # 理论 BER
    if show_theoretical:
        snr_theory = np.linspace(min(snr_values), max(snr_values), 100)
        ber_theory = [theoretical_ber_gfsk(s) for s in snr_theory]
        fig.add_trace(
            go.Scatter(x=snr_theory, y=ber_theory, mode='lines',
                       name='理论 BER', line=dict(color='red', width=1, dash='dash')),
            row=1, col=1
        )

    # PER 曲线
    fig.add_trace(
        go.Scatter(x=snr_values, y=per_values, mode='lines+markers',
                   name='仿真 PER', line=dict(color='green', width=2)),
        row=1, col=2
    )

    # 30.8% PER 参考线
    fig.add_hline(y=0.308, line_dash="dash", line_color="gray",
                  annotation_text="30.8% (BLE 规范)", row=1, col=2)

    fig.update_yaxes(type="log", title="BER", row=1, col=1)
    fig.update_yaxes(type="log", title="PER", row=1, col=2)
    fig.update_xaxes(title="SNR (dB)")

    fig.update_layout(
        title=f"BLE {report.config.phy_mode.name} 性能测试结果",
        height=500,
        showlegend=True
    )

    return fig


def quick_ber_test(snr_db: float, num_packets: int = 100,
                   phy_mode: BLEPhyMode = BLEPhyMode.LE_1M) -> TestResult:
    """
    快速 BER 测试

    Args:
        snr_db: 信噪比 (dB)
        num_packets: 包数量
        phy_mode: PHY 模式

    Returns:
        TestResult 对象
    """
    config = TestConfig(
        phy_mode=phy_mode,
        num_packets=num_packets
    )
    tester = BLEPerformanceTester(config)
    return tester.run_ber_test(snr_db)


def quick_snr_sweep(snr_start: float = 0, snr_stop: float = 20, snr_step: float = 2,
                    num_packets: int = 100, phy_mode: BLEPhyMode = BLEPhyMode.LE_1M) -> TestReport:
    """
    快速 SNR 扫描测试

    Args:
        snr_start: 起始 SNR
        snr_stop: 结束 SNR
        snr_step: SNR 步进
        num_packets: 每点包数量
        phy_mode: PHY 模式

    Returns:
        TestReport 对象
    """
    config = TestConfig(
        phy_mode=phy_mode,
        snr_start=snr_start,
        snr_stop=snr_stop,
        snr_step=snr_step,
        num_packets=num_packets
    )
    tester = BLEPerformanceTester(config)
    return tester.run_snr_sweep()
