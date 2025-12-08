"""
BLE 数据包生成模块
支持 BLE 4.x/5.x 数据包格式
"""

import numpy as np
from typing import List, Optional, Union
from dataclasses import dataclass, field
from enum import IntEnum


class BLEPhyMode(IntEnum):
    """BLE 物理层模式"""
    LE_1M = 1           # BLE 1M PHY (GFSK)
    LE_2M = 2           # BLE 2M PHY (GFSK)
    LE_CODED_S8 = 3     # BLE Coded PHY S=8
    LE_CODED_S2 = 4     # BLE Coded PHY S=2


class BLEChannelType(IntEnum):
    """BLE 信道类型"""
    ADVERTISING = 0     # 广播信道 (37, 38, 39)
    DATA = 1            # 数据信道 (0-36)


class AdvertisingPDUType(IntEnum):
    """广播信道 PDU 类型"""
    ADV_IND = 0x00           # 可连接可扫描非定向广播
    ADV_DIRECT_IND = 0x01    # 可连接定向广播
    ADV_NONCONN_IND = 0x02   # 不可连接非定向广播
    SCAN_REQ = 0x03          # 扫描请求
    SCAN_RSP = 0x04          # 扫描响应
    CONNECT_IND = 0x05       # 连接请求
    ADV_SCAN_IND = 0x06      # 可扫描非定向广播
    ADV_EXT_IND = 0x07       # 扩展广播 (BLE 5.0)


class DataPDUType(IntEnum):
    """数据信道 PDU LLID 类型"""
    RESERVED = 0x00          # 保留
    LL_DATA_CONT = 0x01      # LL Data PDU 后续片段
    LL_DATA_START = 0x02     # LL Data PDU 起始或完整
    LL_CONTROL = 0x03        # LL Control PDU


class LLControlOpcode(IntEnum):
    """链路层控制 PDU 操作码"""
    LL_CONNECTION_UPDATE_IND = 0x00
    LL_CHANNEL_MAP_IND = 0x01
    LL_TERMINATE_IND = 0x02
    LL_ENC_REQ = 0x03
    LL_ENC_RSP = 0x04
    LL_START_ENC_REQ = 0x05
    LL_START_ENC_RSP = 0x06
    LL_UNKNOWN_RSP = 0x07
    LL_FEATURE_REQ = 0x08
    LL_FEATURE_RSP = 0x09
    LL_PAUSE_ENC_REQ = 0x0A
    LL_PAUSE_ENC_RSP = 0x0B
    LL_VERSION_IND = 0x0C
    LL_REJECT_IND = 0x0D
    LL_PERIPHERAL_FEATURE_REQ = 0x0E
    LL_CONNECTION_PARAM_REQ = 0x0F
    LL_CONNECTION_PARAM_RSP = 0x10
    LL_REJECT_EXT_IND = 0x11
    LL_PING_REQ = 0x12
    LL_PING_RSP = 0x13
    LL_LENGTH_REQ = 0x14
    LL_LENGTH_RSP = 0x15
    LL_PHY_REQ = 0x16
    LL_PHY_RSP = 0x17
    LL_PHY_UPDATE_IND = 0x18


@dataclass
class BLEPacketConfig:
    """BLE 数据包配置"""
    phy_mode: BLEPhyMode = BLEPhyMode.LE_1M
    channel: int = 37                    # 信道号 (0-39)
    channel_type: BLEChannelType = BLEChannelType.ADVERTISING
    access_address: int = 0x8E89BED6     # 接入地址 (广播默认)
    pdu_type: int = 0                    # PDU 类型
    payload: bytes = b''                 # 负载数据
    crc_init: int = 0x555555             # CRC 初始值


@dataclass
class DataChannelConfig:
    """数据信道配置"""
    access_address: int = 0x12345678     # 连接态接入地址 (随机生成)
    crc_init: int = 0x000000             # CRC 初始值 (从 CONNECT_IND 获取)
    channel_map: int = 0x1FFFFFFFFF      # 信道映射 (37 bits)
    hop_increment: int = 5               # 跳频增量 (5-16)
    unmapped_channel: int = 0            # 未映射信道号
    connection_event_counter: int = 0    # 连接事件计数器


class DataChannelPDU:
    """数据信道 PDU 生成器"""

    def __init__(self, config: Optional[DataChannelConfig] = None):
        self.config = config or DataChannelConfig()

    @staticmethod
    def create_header(llid: DataPDUType, nesn: int, sn: int, md: int, length: int) -> bytes:
        """
        创建数据信道 PDU 头部

        Args:
            llid: LLID (2 bits) - PDU 类型
            nesn: Next Expected Sequence Number (1 bit)
            sn: Sequence Number (1 bit)
            md: More Data (1 bit)
            length: 负载长度 (8 bits)

        Returns:
            2 字节头部
        """
        # 第一字节: LLID(2) + NESN(1) + SN(1) + MD(1) + RFU(3)
        byte0 = (llid & 0x03) | ((nesn & 0x01) << 2) | ((sn & 0x01) << 3) | ((md & 0x01) << 4)
        # 第二字节: Length(8)
        byte1 = length & 0xFF
        return bytes([byte0, byte1])

    @staticmethod
    def create_empty_pdu(nesn: int = 0, sn: int = 0) -> bytes:
        """创建空 PDU (用于保持连接)"""
        return DataChannelPDU.create_header(
            llid=DataPDUType.LL_DATA_CONT,
            nesn=nesn, sn=sn, md=0, length=0
        )

    @staticmethod
    def create_data_pdu(payload: bytes, nesn: int = 0, sn: int = 0,
                        md: int = 0, is_start: bool = True) -> bytes:
        """
        创建数据 PDU

        Args:
            payload: L2CAP 数据
            nesn: Next Expected Sequence Number
            sn: Sequence Number
            md: More Data flag
            is_start: 是否为起始/完整 PDU

        Returns:
            完整 PDU (头部 + 负载)
        """
        llid = DataPDUType.LL_DATA_START if is_start else DataPDUType.LL_DATA_CONT
        header = DataChannelPDU.create_header(llid, nesn, sn, md, len(payload))
        return header + payload

    @staticmethod
    def create_control_pdu(opcode: LLControlOpcode, ctrl_data: bytes = b'',
                           nesn: int = 0, sn: int = 0) -> bytes:
        """
        创建控制 PDU

        Args:
            opcode: 控制操作码
            ctrl_data: 控制数据
            nesn: Next Expected Sequence Number
            sn: Sequence Number

        Returns:
            完整控制 PDU
        """
        payload = bytes([opcode]) + ctrl_data
        header = DataChannelPDU.create_header(
            llid=DataPDUType.LL_CONTROL,
            nesn=nesn, sn=sn, md=0,
            length=len(payload)
        )
        return header + payload

    @staticmethod
    def create_ll_version_ind(vers_nr: int = 0x09, comp_id: int = 0x0000,
                               sub_vers_nr: int = 0x0000) -> bytes:
        """创建 LL_VERSION_IND PDU"""
        ctrl_data = bytes([
            vers_nr,
            comp_id & 0xFF, (comp_id >> 8) & 0xFF,
            sub_vers_nr & 0xFF, (sub_vers_nr >> 8) & 0xFF
        ])
        return DataChannelPDU.create_control_pdu(LLControlOpcode.LL_VERSION_IND, ctrl_data)

    @staticmethod
    def create_ll_feature_req(features: int = 0) -> bytes:
        """创建 LL_FEATURE_REQ PDU"""
        ctrl_data = features.to_bytes(8, 'little')
        return DataChannelPDU.create_control_pdu(LLControlOpcode.LL_FEATURE_REQ, ctrl_data)

    @staticmethod
    def create_ll_terminate_ind(error_code: int = 0x13) -> bytes:
        """创建 LL_TERMINATE_IND PDU"""
        return DataChannelPDU.create_control_pdu(
            LLControlOpcode.LL_TERMINATE_IND, bytes([error_code])
        )

    @staticmethod
    def create_ll_length_req(max_rx_octets: int = 251, max_rx_time: int = 2120,
                              max_tx_octets: int = 251, max_tx_time: int = 2120) -> bytes:
        """创建 LL_LENGTH_REQ PDU (BLE 4.2+)"""
        ctrl_data = bytes([
            max_rx_octets & 0xFF, (max_rx_octets >> 8) & 0xFF,
            max_rx_time & 0xFF, (max_rx_time >> 8) & 0xFF,
            max_tx_octets & 0xFF, (max_tx_octets >> 8) & 0xFF,
            max_tx_time & 0xFF, (max_tx_time >> 8) & 0xFF,
        ])
        return DataChannelPDU.create_control_pdu(LLControlOpcode.LL_LENGTH_REQ, ctrl_data)

    @staticmethod
    def create_ll_phy_req(tx_phys: int = 0x01, rx_phys: int = 0x01) -> bytes:
        """创建 LL_PHY_REQ PDU (BLE 5.0+)"""
        ctrl_data = bytes([tx_phys, rx_phys])
        return DataChannelPDU.create_control_pdu(LLControlOpcode.LL_PHY_REQ, ctrl_data)


def calculate_data_channel(unmapped_channel: int, channel_map: int,
                           num_used_channels: int = None) -> int:
    """
    计算数据信道 (根据信道映射)

    Args:
        unmapped_channel: 未映射信道号 (0-36)
        channel_map: 37-bit 信道映射
        num_used_channels: 可用信道数 (可选, 自动计算)

    Returns:
        映射后的数据信道号
    """
    if num_used_channels is None:
        num_used_channels = bin(channel_map).count('1')

    if (channel_map >> unmapped_channel) & 1:
        # 信道可用, 直接使用
        return unmapped_channel
    else:
        # 信道不可用, 重新映射
        remap_index = unmapped_channel % num_used_channels
        count = 0
        for ch in range(37):
            if (channel_map >> ch) & 1:
                if count == remap_index:
                    return ch
                count += 1
    return 0


def next_data_channel(last_unmapped_channel: int, hop_increment: int,
                      channel_map: int) -> tuple:
    """
    计算下一个数据信道

    Args:
        last_unmapped_channel: 上一个未映射信道
        hop_increment: 跳频增量 (5-16)
        channel_map: 信道映射

    Returns:
        (未映射信道, 实际信道)
    """
    unmapped = (last_unmapped_channel + hop_increment) % 37
    actual = calculate_data_channel(unmapped, channel_map)
    return unmapped, actual


class BLEPacket:
    """BLE 基带数据包生成器"""

    # BLE 前导码
    PREAMBLE_1M = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)  # 1M PHY
    PREAMBLE_2M = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)  # 2M PHY

    # CRC 多项式 (x^24 + x^10 + x^9 + x^6 + x^4 + x^3 + x + 1)
    CRC_POLY = 0x100065B
    CRC_INIT_ADV = 0x555555  # 广播信道 CRC 初始值

    # 白化多项式 (x^7 + x^4 + 1)
    WHITENING_POLY = 0x11

    def __init__(self, config: Optional[BLEPacketConfig] = None):
        self.config = config or BLEPacketConfig()

    def _bytes_to_bits(self, data: bytes) -> np.ndarray:
        """字节转比特 (LSB first)"""
        bits = []
        for byte in data:
            for i in range(8):
                bits.append((byte >> i) & 1)
        return np.array(bits, dtype=np.uint8)

    def _int_to_bits(self, value: int, num_bits: int) -> np.ndarray:
        """整数转比特 (LSB first)"""
        bits = []
        for i in range(num_bits):
            bits.append((value >> i) & 1)
        return np.array(bits, dtype=np.uint8)

    def _calculate_crc(self, data: bytes, init: int = None) -> int:
        """计算 BLE CRC24"""
        if init is None:
            init = self.CRC_INIT_ADV

        crc = init
        for byte in data:
            for i in range(8):
                bit = (byte >> i) & 1
                if (crc & 1) ^ bit:
                    crc = (crc >> 1) ^ 0x65B
                else:
                    crc = crc >> 1
        return crc & 0xFFFFFF

    def _get_whitening_sequence(self, channel: int, length: int) -> np.ndarray:
        """生成白化序列"""
        # 初始化 LFSR (channel 号 + 1 作为种子)
        lfsr = (channel & 0x3F) | 0x40

        sequence = np.zeros(length, dtype=np.uint8)
        for i in range(length):
            sequence[i] = lfsr & 1
            # x^7 + x^4 + 1
            feedback = ((lfsr >> 6) ^ (lfsr >> 3)) & 1
            lfsr = ((lfsr << 1) | feedback) & 0x7F

        return sequence

    def _apply_whitening(self, bits: np.ndarray, channel: int) -> np.ndarray:
        """应用白化"""
        whitening_seq = self._get_whitening_sequence(channel, len(bits))
        return bits ^ whitening_seq

    def generate_pdu(self) -> bytes:
        """生成 PDU (Protocol Data Unit)"""
        config = self.config

        # 广播 PDU 头部 (2字节)
        # [PDU Type (4bit)] [RFU (1bit)] [ChSel (1bit)] [TxAdd (1bit)] [RxAdd (1bit)]
        # [Length (8bit)]
        pdu_header = bytes([
            config.pdu_type & 0x0F,
            len(config.payload) & 0xFF
        ])

        return pdu_header + config.payload

    def generate(self) -> np.ndarray:
        """生成完整的 BLE 基带数据包 (比特流)"""
        config = self.config

        # 1. 前导码
        if config.phy_mode == BLEPhyMode.LE_2M:
            preamble = self.PREAMBLE_2M.copy()
        else:
            preamble = self.PREAMBLE_1M.copy()

        # 2. 接入地址 (32 bits, LSB first)
        access_addr_bits = self._int_to_bits(config.access_address, 32)

        # 3. PDU
        pdu = self.generate_pdu()
        pdu_bits = self._bytes_to_bits(pdu)

        # 4. CRC (24 bits)
        crc = self._calculate_crc(pdu)
        crc_bits = self._int_to_bits(crc, 24)

        # 5. 组合 PDU + CRC 并白化
        data_bits = np.concatenate([pdu_bits, crc_bits])
        whitened_bits = self._apply_whitening(data_bits, config.channel)

        # 6. 组合完整数据包
        packet_bits = np.concatenate([
            preamble,
            access_addr_bits,
            whitened_bits
        ])

        return packet_bits

    def generate_bytes(self) -> bytes:
        """生成数据包字节"""
        bits = self.generate()
        # 补齐到字节边界
        pad_len = (8 - len(bits) % 8) % 8
        if pad_len > 0:
            bits = np.concatenate([bits, np.zeros(pad_len, dtype=np.uint8)])

        # 比特转字节
        result = []
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                byte |= (bits[i + j] << j)
            result.append(byte)

        return bytes(result)


def create_advertising_packet(
    adv_address: bytes,
    adv_data: bytes = b'',
    channel: int = 37,
    pdu_type: int = 0x00  # ADV_IND
) -> BLEPacket:
    """创建广播数据包的便捷函数"""

    # 广播地址 (6 bytes) + 广播数据
    payload = adv_address + adv_data

    config = BLEPacketConfig(
        phy_mode=BLEPhyMode.LE_1M,
        channel=channel,
        channel_type=BLEChannelType.ADVERTISING,
        access_address=0x8E89BED6,  # 广播接入地址
        pdu_type=pdu_type,
        payload=payload,
        crc_init=0x555555
    )

    return BLEPacket(config)


def create_data_packet(
    pdu: bytes,
    access_address: int,
    crc_init: int,
    channel: int,
    phy_mode: BLEPhyMode = BLEPhyMode.LE_1M
) -> BLEPacket:
    """
    创建数据信道数据包的便捷函数

    Args:
        pdu: 数据信道 PDU (由 DataChannelPDU 生成)
        access_address: 连接接入地址
        crc_init: CRC 初始值
        channel: 数据信道号 (0-36)
        phy_mode: PHY 模式

    Returns:
        BLEPacket 对象
    """
    config = BLEPacketConfig(
        phy_mode=phy_mode,
        channel=channel,
        channel_type=BLEChannelType.DATA,
        access_address=access_address,
        pdu_type=0,  # 数据信道不使用此字段
        payload=pdu[2:] if len(pdu) > 2 else b'',  # 跳过头部
        crc_init=crc_init
    )

    # 直接设置 PDU (包含头部)
    packet = BLEPacket(config)
    packet._data_pdu = pdu  # 存储完整 PDU
    return packet


def create_connect_ind(
    init_address: bytes,
    adv_address: bytes,
    access_address: int,
    crc_init: int,
    win_size: int = 2,
    win_offset: int = 0,
    interval: int = 24,  # 30ms (24 * 1.25ms)
    latency: int = 0,
    timeout: int = 72,   # 720ms
    channel_map: int = 0x1FFFFFFFFF,
    hop: int = 5,
    sca: int = 0
) -> BLEPacket:
    """
    创建 CONNECT_IND PDU

    Args:
        init_address: 发起者地址 (6 bytes)
        adv_address: 广播者地址 (6 bytes)
        access_address: 连接接入地址 (4 bytes)
        crc_init: CRC 初始值 (3 bytes)
        win_size: 发送窗口大小
        win_offset: 发送窗口偏移
        interval: 连接间隔 (单位: 1.25ms)
        latency: 从设备延迟
        timeout: 监督超时 (单位: 10ms)
        channel_map: 信道映射 (37 bits)
        hop: 跳频增量 (5-16)
        sca: 睡眠时钟精度

    Returns:
        BLEPacket 对象
    """
    # LLData 部分 (22 bytes)
    ll_data = bytes([
        # Access Address (4 bytes)
        access_address & 0xFF,
        (access_address >> 8) & 0xFF,
        (access_address >> 16) & 0xFF,
        (access_address >> 24) & 0xFF,
        # CRC Init (3 bytes)
        crc_init & 0xFF,
        (crc_init >> 8) & 0xFF,
        (crc_init >> 16) & 0xFF,
        # WinSize (1 byte)
        win_size,
        # WinOffset (2 bytes)
        win_offset & 0xFF,
        (win_offset >> 8) & 0xFF,
        # Interval (2 bytes)
        interval & 0xFF,
        (interval >> 8) & 0xFF,
        # Latency (2 bytes)
        latency & 0xFF,
        (latency >> 8) & 0xFF,
        # Timeout (2 bytes)
        timeout & 0xFF,
        (timeout >> 8) & 0xFF,
        # Channel Map (5 bytes, 37 bits)
        channel_map & 0xFF,
        (channel_map >> 8) & 0xFF,
        (channel_map >> 16) & 0xFF,
        (channel_map >> 24) & 0xFF,
        (channel_map >> 32) & 0x1F,
        # Hop + SCA (1 byte)
        (hop & 0x1F) | ((sca & 0x07) << 5)
    ])

    payload = init_address + adv_address + ll_data

    return create_advertising_packet(
        adv_address=b'',  # 不使用
        adv_data=b'',
        channel=37,
        pdu_type=AdvertisingPDUType.CONNECT_IND
    )


def generate_random_access_address() -> int:
    """
    生成随机接入地址 (符合 BLE 规范)

    规则:
    - 不能是广播接入地址 (0x8E89BED6)
    - 不能全 0 或全 1
    - 不能超过 6 个连续的 0 或 1
    - 至少有 2 个 bit 翻转
    """
    while True:
        aa = np.random.randint(0, 0xFFFFFFFF)

        # 检查不是广播地址
        if aa == 0x8E89BED6:
            continue

        # 检查不是全 0 或全 1
        if aa == 0 or aa == 0xFFFFFFFF:
            continue

        # 检查连续 0/1 不超过 6 个
        binary = format(aa, '032b')
        max_consecutive = max(
            len(s) for s in binary.replace('0', ' ').split() + binary.replace('1', ' ').split()
            if s
        )
        if max_consecutive > 6:
            continue

        # 检查至少 2 个翻转
        transitions = sum(1 for i in range(31) if binary[i] != binary[i+1])
        if transitions < 2:
            continue

        return aa
