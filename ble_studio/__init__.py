"""
BLE Studio - BLE 基带算法平台
支持 BLE 数据包生成和解调
"""

__version__ = "0.1.0"

from .packet import (
    BLEPacket,
    BLEPacketConfig,
    BLEPhyMode,
    BLEChannelType,
    AdvertisingPDUType,
    DataPDUType,
    DataChannelPDU,
    DataChannelConfig,
    create_advertising_packet,
    create_data_packet,
    generate_random_access_address,
    # RF Test (DTM)
    RFTestPayloadType,
    RFTestPayloadGenerator,
    RFTestConfig,
    RFTestPacket,
    create_test_packet,
)
from .modulator import BLEModulator, ModulatorConfig
from .demodulator import BLEDemodulator, DemodulatorConfig
from .visualizer import BLEVisualizer, plot_ble_signal
from .report import ReportGenerator
from .channel import (
    BLEChannel,
    ChannelConfig,
    ChannelType,
    AWGNChannel,
    RayleighChannel,
    RicianChannel,
    MultipathChannel,
    BLEIndoorChannel,
    create_awgn_channel,
    create_fading_channel,
    create_ble_indoor_channel,
)
from .performance import (
    BLEPerformanceTester,
    TestConfig,
    TestResult,
    TestReport,
    TestMode,
    quick_ber_test,
    quick_snr_sweep,
    plot_ber_curve,
)
from .iq_io import (
    IQExporter,
    IQImporter,
    IQExportConfig,
    IQImportConfig,
    IQFormat,
    NumberFormat,
    export_iq_txt,
    export_iq_verilog,
    import_iq_txt,
    import_iq_mat,
)
