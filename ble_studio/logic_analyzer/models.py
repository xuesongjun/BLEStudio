"""逻辑分析仪 pipeline 使用的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class BleRxConfig:
    """可选的 BLE RX 验证配置。"""

    enabled: bool = False
    phy_mode: str = "LE_1M"
    access_address: int = 0x71764129
    channel: int = 0
    whitening: bool = False
    target_samples_per_symbol: int = 16


@dataclass
class LogicAnalyzerConfig:
    """一次逻辑分析仪转换任务的完整配置。"""

    input_file: Path
    output_dir: Path
    output_stem: str
    config_path: Optional[Path] = None

    profile: str = "iq_ddr"
    sample_rate: float = 500e6
    data_rate: float = 32e6
    mode: str = "ddr"
    data_bits: Tuple[int, ...] = tuple(range(10))
    clk_channel: Optional[int] = 10
    bit_width: int = 10
    rising_edge_data: str = "I"
    falling_edge_data: str = "Q"

    eye_align: bool = True
    search_range: int = 15
    glitch_filter: bool = False
    glitch_threshold: float = 0.3
    adaptive_filter: bool = True
    output_spike_filter: bool = True

    extra_signals: Dict[str, int] = field(default_factory=dict)
    save_formats: Tuple[str, ...] = ("mat", "html")
    max_plot_samples: int = 50_000
    show_plot: bool = False
    include_debug_data: bool = False

    ble_rx: BleRxConfig = field(default_factory=BleRxConfig)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_iq(self) -> bool:
        return self.mode == "ddr"

    @property
    def output_base(self) -> Path:
        return self.output_dir / self.output_stem


@dataclass
class RawCapture:
    """Kingst BIN 解码后的数字通道。"""

    channels: Dict[int, np.ndarray]
    clock: Optional[np.ndarray]
    extra_signals: Dict[str, np.ndarray]
    sample_count: int
    sample_rate: float


@dataclass
class CaptureResult:
    """统一处理结果，所有 exporter 和 RX 验证都消费该对象。"""

    config: LogicAnalyzerConfig
    raw_capture: RawCapture
    cleaned_channels: Dict[int, np.ndarray]
    data1: np.ndarray
    data2: Optional[np.ndarray]
    signed_data1: np.ndarray
    signed_data2: Optional[np.ndarray]
    sample_rate_nominal: float
    sample_rate_measured: Optional[float]
    sample_info: Dict[str, Any] = field(default_factory=dict)
    extra_signals: Dict[str, np.ndarray] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    rx_result: Optional[Dict[str, Any]] = None

    @property
    def is_iq(self) -> bool:
        return self.data2 is not None

    @property
    def sample_rate(self) -> float:
        """下游使用 nominal rate，measured rate 仅作为诊断信息。"""
        return self.sample_rate_nominal

    @property
    def iq(self) -> Optional[np.ndarray]:
        if self.signed_data2 is None:
            return None
        full_scale = float(1 << (self.config.bit_width - 1))
        return (self.signed_data1.astype(np.float64) +
                1j * self.signed_data2.astype(np.float64)) / full_scale

    @property
    def sample_count(self) -> int:
        return int(len(self.data1))
