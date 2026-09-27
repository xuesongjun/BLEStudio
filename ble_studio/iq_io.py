"""
BLE Studio IQ 数据导入导出模块
支持 Verilog 硬件仿真平台的 IQ 数据文件格式
"""

import hashlib
import json
import tempfile

import numpy as np
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union, Literal
from dataclasses import dataclass
from enum import Enum


def _json_default(value: Any) -> Any:
    """将常用标量类型转换为 JSON 原生类型。"""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(
        f"Object of type {type(value).__name__} is not JSON serializable"
    )


def write_pretty_json(file_path: Union[str, Path], data: Any) -> Path:
    """写入便于人工阅读的 strict JSON，并保证文件以换行结尾。"""
    # 先完成序列化校验，避免 NaN/Infinity 等非法值留下半写入文件。
    text = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
        default=_json_default,
    )
    output = Path(file_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.write("\n")
        temp_path.replace(output)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return output


def describe_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """返回关联文件的名称、字节数和 SHA-256。"""
    path = Path(file_path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


class IQFormat(Enum):
    """IQ 数据格式"""
    INTERLEAVED = "interleaved"     # I0 Q0 I1 Q1 I2 Q2 ... (交织)
    SEPARATE = "separate"           # I0 I1 I2 ... 然后 Q0 Q1 Q2 ... (分离)
    TWO_COLUMN = "two_column"       # 每行: I Q (两列)
    COMPLEX = "complex"             # 每行: I+jQ 或 I,Q


class NumberFormat(Enum):
    """数值格式"""
    SIGNED_INT = "signed"           # 有符号整数 (补码)
    UNSIGNED_INT = "unsigned"       # 无符号整数
    HEX = "hex"                     # 十六进制
    FLOAT = "float"                 # 浮点数


@dataclass
class IQExportConfig:
    """IQ 导出配置"""
    bit_width: int = 12             # 量化位宽 (8, 10, 12, 14, 16 等)
    frac_bits: int = 0              # 小数位数 (Q格式中的小数部分, 0表示纯整数)
    iq_format: IQFormat = IQFormat.TWO_COLUMN
    number_format: NumberFormat = NumberFormat.SIGNED_INT
    scale_to_full: bool = True      # 是否缩放到满量程
    add_header: bool = False        # 是否添加文件头注释
    separator: str = " "            # 分隔符 (空格, 逗号, 制表符等)


@dataclass
class IQImportConfig:
    """IQ 导入配置"""
    bit_width: int = 12             # 量化位宽
    frac_bits: int = 0              # 小数位数
    iq_format: IQFormat = IQFormat.TWO_COLUMN
    number_format: NumberFormat = NumberFormat.SIGNED_INT
    sample_rate: float = 8e6        # 采样率 (Hz)
    skip_lines: int = 0             # 跳过的行数 (头部注释)


class IQExporter:
    """IQ 数据导出器 - 用于 Verilog 硬件仿真"""

    def __init__(self, config: Optional[IQExportConfig] = None):
        self.config = config or IQExportConfig()

    @staticmethod
    def _round_ties_away_from_zero(values: np.ndarray) -> np.ndarray:
        """按 MATLAB round 语义处理正负 half-LSB。"""
        return np.copysign(np.floor(np.abs(values) + 0.5), values)

    def _quantize_with_details(
        self, signal: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """量化 IQ，并返回与本次结果严格对应的参数和饱和统计。"""
        cfg = self.config
        max_val = 2 ** (cfg.bit_width - 1) - 1
        min_val = -2 ** (cfg.bit_width - 1)
        full_scale = 2 ** (cfg.bit_width - 1)

        samples = np.asarray(signal)
        i_data = samples.real
        q_data = samples.imag

        if cfg.frac_bits > 0:
            scale = float(2 ** cfg.frac_bits)
        elif cfg.scale_to_full and samples.size:
            max_amp = max(
                float(np.max(np.abs(i_data))),
                float(np.max(np.abs(q_data))),
            )
            scale = float(full_scale / max_amp) if max_amp > 0 else float(full_scale)
        else:
            scale = float(full_scale)

        i_rounded = self._round_ties_away_from_zero(i_data * scale)
        q_rounded = self._round_ties_away_from_zero(q_data * scale)
        saturation_i = int(
            np.count_nonzero((i_rounded < min_val) | (i_rounded > max_val))
        )
        saturation_q = int(
            np.count_nonzero((q_rounded < min_val) | (q_rounded > max_val))
        )

        # clip 后再转换为整数，避免超范围浮点值在转换阶段先发生整数溢出。
        i_quant = np.clip(i_rounded, min_val, max_val).astype(np.int32)
        q_quant = np.clip(q_rounded, min_val, max_val).astype(np.int32)
        q_format = (
            f"Q{cfg.bit_width - cfg.frac_bits}.{cfg.frac_bits}"
            if cfg.frac_bits > 0
            else None
        )
        details: Dict[str, Any] = {
            "bit_width": cfg.bit_width,
            "frac_bits": cfg.frac_bits,
            "scale_to_full": cfg.scale_to_full,
            "scale_factor": scale,
            "rounding": "ties_away_from_zero",
            "signed_min": min_val,
            "signed_max": max_val,
            "saturation_i": saturation_i,
            "saturation_q": saturation_q,
            "q_format": q_format,
        }
        return i_quant, q_quant, details

    def quantize(self, signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        将复数 IQ 信号量化为定点数

        Args:
            signal: 复数 IQ 信号 (归一化, 幅度 <= 1)

        Returns:
            (I_quantized, Q_quantized) 量化后的 I/Q 数组
        """
        i_quant, q_quant, _ = self._quantize_with_details(signal)
        return i_quant, q_quant

    def quantization_details(self, signal: np.ndarray) -> Dict[str, Any]:
        """返回当前配置下实际采用的缩放、舍入和饱和信息。"""
        _, _, details = self._quantize_with_details(signal)
        return details

    def to_unsigned(self, data: np.ndarray) -> np.ndarray:
        """有符号转无符号 (补码)"""
        cfg = self.config
        mask = (1 << cfg.bit_width) - 1
        return data & mask

    def to_hex_string(self, value: int) -> str:
        """转换为十六进制字符串"""
        cfg = self.config
        num_hex_digits = (cfg.bit_width + 3) // 4
        if value < 0:
            # 补码表示
            value = value & ((1 << cfg.bit_width) - 1)
        return f"{value:0{num_hex_digits}X}"

    def export_txt(self, signal: np.ndarray, file_path: Union[str, Path],
                   config: Optional[IQExportConfig] = None) -> dict:
        """
        导出 IQ 数据到文本文件

        Args:
            signal: 复数 IQ 信号
            file_path: 输出文件路径
            config: 导出配置 (可选, 覆盖默认配置)

        Returns:
            导出信息字典
        """
        if config:
            self.config = config
        cfg = self.config

        # 量化与 metadata 必须来自同一次计算。
        i_quant, q_quant, quantization = self._quantize_with_details(signal)

        file_path = Path(file_path)
        lines = []

        # 添加头部注释
        if cfg.add_header:
            lines.append(f"// BLE Studio IQ Data Export")
            lines.append(f"// Bit Width: {cfg.bit_width}")
            if quantization["q_format"] is not None:
                lines.append(f"// Q Format: {quantization['q_format']}")
            lines.append(f"// Scale Factor: {quantization['scale_factor']:.12g}")
            lines.append(f"// Rounding: {quantization['rounding']}")
            lines.append(f"// IQ Format: {cfg.iq_format.value}")
            lines.append(f"// Number Format: {cfg.number_format.value}")
            lines.append(f"// Samples: {len(signal)}")
            lines.append(f"//")

        # 格式化数据
        if cfg.iq_format == IQFormat.TWO_COLUMN:
            for i, q in zip(i_quant, q_quant):
                if cfg.number_format == NumberFormat.HEX:
                    lines.append(f"{self.to_hex_string(i)}{cfg.separator}{self.to_hex_string(q)}")
                elif cfg.number_format == NumberFormat.UNSIGNED_INT:
                    i_u = self.to_unsigned(np.array([i]))[0]
                    q_u = self.to_unsigned(np.array([q]))[0]
                    lines.append(f"{i_u}{cfg.separator}{q_u}")
                else:
                    lines.append(f"{i}{cfg.separator}{q}")

        elif cfg.iq_format == IQFormat.INTERLEAVED:
            data = []
            for i, q in zip(i_quant, q_quant):
                if cfg.number_format == NumberFormat.HEX:
                    data.extend([self.to_hex_string(i), self.to_hex_string(q)])
                elif cfg.number_format == NumberFormat.UNSIGNED_INT:
                    i_u = self.to_unsigned(np.array([i]))[0]
                    q_u = self.to_unsigned(np.array([q]))[0]
                    data.extend([str(i_u), str(q_u)])
                else:
                    data.extend([str(i), str(q)])
            lines.extend(data)

        elif cfg.iq_format == IQFormat.SEPARATE:
            # 先输出所有 I, 再输出所有 Q
            for i in i_quant:
                if cfg.number_format == NumberFormat.HEX:
                    lines.append(self.to_hex_string(i))
                elif cfg.number_format == NumberFormat.UNSIGNED_INT:
                    lines.append(str(self.to_unsigned(np.array([i]))[0]))
                else:
                    lines.append(str(i))
            for q in q_quant:
                if cfg.number_format == NumberFormat.HEX:
                    lines.append(self.to_hex_string(q))
                elif cfg.number_format == NumberFormat.UNSIGNED_INT:
                    lines.append(str(self.to_unsigned(np.array([q]))[0]))
                else:
                    lines.append(str(q))

        # 写入文件 (使用 Unix 换行符以匹配 MATLAB 格式)
        with open(file_path, 'w', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')

        return {
            'file': str(file_path),
            'samples': len(signal),
            'bit_width': cfg.bit_width,
            'q_format': quantization["q_format"],
            'iq_format': cfg.iq_format.value,
            'number_format': cfg.number_format.value,
            'quantization': quantization,
        }

    def export_separate_files(self, signal: np.ndarray, i_path: Union[str, Path],
                              q_path: Union[str, Path]) -> dict:
        """
        导出 I 和 Q 到分离的文件

        Args:
            signal: 复数 IQ 信号
            i_path: I 数据文件路径
            q_path: Q 数据文件路径

        Returns:
            导出信息字典
        """
        cfg = self.config
        i_quant, q_quant, quantization = self._quantize_with_details(signal)

        def format_value(v):
            if cfg.number_format == NumberFormat.HEX:
                return self.to_hex_string(v)
            elif cfg.number_format == NumberFormat.UNSIGNED_INT:
                return str(self.to_unsigned(np.array([v]))[0])
            else:
                return str(v)

        # 写 I 文件
        with open(i_path, 'w') as f:
            for i in i_quant:
                f.write(format_value(i) + '\n')

        # 写 Q 文件
        with open(q_path, 'w') as f:
            for q in q_quant:
                f.write(format_value(q) + '\n')

        return {
            'i_file': str(i_path),
            'q_file': str(q_path),
            'samples': len(signal),
            'bit_width': cfg.bit_width,
            'q_format': quantization["q_format"],
            'quantization': quantization,
        }

    def export_verilog_mem(self, signal: np.ndarray, file_path: Union[str, Path]) -> dict:
        """
        导出为 Verilog $readmemh 格式

        Args:
            signal: 复数 IQ 信号
            file_path: 输出文件路径

        Returns:
            导出信息字典
        """
        cfg = self.config
        i_quant, q_quant, quantization = self._quantize_with_details(signal)

        file_path = Path(file_path)
        lines = []

        # I 和 Q 打包成一个宽字
        total_bits = cfg.bit_width * 2
        num_hex = (total_bits + 3) // 4

        for i, q in zip(i_quant, q_quant):
            # 高位: I, 低位: Q
            i_u = i & ((1 << cfg.bit_width) - 1)
            q_u = q & ((1 << cfg.bit_width) - 1)
            packed = (i_u << cfg.bit_width) | q_u
            lines.append(f"{packed:0{num_hex}X}")

        with open(file_path, 'w', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')

        return {
            'file': str(file_path),
            'samples': len(signal),
            'bit_width': cfg.bit_width,
            'packed_width': total_bits,
            'format': 'verilog_memh',
            'quantization': quantization,
        }


class IQImporter:
    """IQ 数据导入器"""

    def __init__(self, config: Optional[IQImportConfig] = None):
        self.config = config or IQImportConfig()

    def from_signed(self, value: int, bit_width: int) -> int:
        """无符号转有符号"""
        if value >= (1 << (bit_width - 1)):
            return value - (1 << bit_width)
        return value

    def import_txt(self, file_path: Union[str, Path],
                   config: Optional[IQImportConfig] = None) -> np.ndarray:
        """
        从文本文件导入 IQ 数据

        Args:
            file_path: 输入文件路径
            config: 导入配置 (可选)

        Returns:
            复数 IQ 信号 (归一化)
        """
        if config:
            self.config = config
        cfg = self.config

        file_path = Path(file_path)

        with open(file_path, 'r') as f:
            lines = f.readlines()

        # 跳过头部
        lines = lines[cfg.skip_lines:]

        # 移除注释和空行
        lines = [line.strip() for line in lines
                 if line.strip() and not line.strip().startswith('//')]

        i_data = []
        q_data = []

        if cfg.iq_format == IQFormat.TWO_COLUMN:
            for line in lines:
                # 支持多种分隔符
                parts = line.replace(',', ' ').replace('\t', ' ').split()
                if len(parts) >= 2:
                    i_val = self._parse_value(parts[0], cfg)
                    q_val = self._parse_value(parts[1], cfg)
                    i_data.append(i_val)
                    q_data.append(q_val)

        elif cfg.iq_format == IQFormat.INTERLEAVED:
            values = []
            for line in lines:
                parts = line.replace(',', ' ').replace('\t', ' ').split()
                for p in parts:
                    values.append(self._parse_value(p, cfg))
            for idx in range(0, len(values) - 1, 2):
                i_data.append(values[idx])
                q_data.append(values[idx + 1])

        elif cfg.iq_format == IQFormat.SEPARATE:
            values = []
            for line in lines:
                parts = line.replace(',', ' ').replace('\t', ' ').split()
                for p in parts:
                    values.append(self._parse_value(p, cfg))
            half = len(values) // 2
            i_data = values[:half]
            q_data = values[half:half * 2]

        # 转换为浮点并归一化
        i_arr = np.array(i_data, dtype=np.float64)
        q_arr = np.array(q_data, dtype=np.float64)

        # Q 格式反量化
        if cfg.frac_bits > 0:
            scale = 2 ** cfg.frac_bits
        else:
            # 找到实际数据的最大值来估算缩放因子
            max_val = max(np.max(np.abs(i_arr)), np.max(np.abs(q_arr)))
            if max_val > 0:
                # 估算使用的缩放因子 (通常是 max_val * 0.95)
                scale = max_val / 0.95
            else:
                scale = 2 ** (cfg.bit_width - 1)

        i_arr = i_arr / scale
        q_arr = q_arr / scale

        return i_arr + 1j * q_arr

    def _parse_value(self, s: str, cfg: IQImportConfig) -> int:
        """解析单个数值"""
        s = s.strip()

        if cfg.number_format == NumberFormat.HEX:
            # 十六进制
            val = int(s, 16)
            return self.from_signed(val, cfg.bit_width)

        elif cfg.number_format == NumberFormat.UNSIGNED_INT:
            val = int(s)
            return self.from_signed(val, cfg.bit_width)

        elif cfg.number_format == NumberFormat.FLOAT:
            return int(float(s))

        else:  # SIGNED_INT
            return int(s)

    def import_separate_files(self, i_path: Union[str, Path], q_path: Union[str, Path],
                              config: Optional[IQImportConfig] = None) -> np.ndarray:
        """
        从分离的 I/Q 文件导入

        Args:
            i_path: I 数据文件路径
            q_path: Q 数据文件路径
            config: 导入配置

        Returns:
            复数 IQ 信号
        """
        if config:
            self.config = config
        cfg = self.config

        def read_values(path):
            values = []
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('//'):
                        values.append(self._parse_value(line, cfg))
            return values

        i_data = read_values(i_path)
        q_data = read_values(q_path)

        # 确保长度一致
        min_len = min(len(i_data), len(q_data))
        i_data = i_data[:min_len]
        q_data = q_data[:min_len]

        # 归一化
        if cfg.frac_bits > 0:
            scale = 2 ** cfg.frac_bits
        else:
            scale = 2 ** (cfg.bit_width - 1)

        i_arr = np.array(i_data, dtype=np.float64) / scale
        q_arr = np.array(q_data, dtype=np.float64) / scale

        return i_arr + 1j * q_arr

    def import_verilog_mem(self, file_path: Union[str, Path],
                           config: Optional[IQImportConfig] = None) -> np.ndarray:
        """
        从 Verilog $readmemh 格式导入

        Args:
            file_path: 输入文件路径
            config: 导入配置

        Returns:
            复数 IQ 信号
        """
        if config:
            self.config = config
        cfg = self.config

        file_path = Path(file_path)

        i_data = []
        q_data = []
        mask = (1 << cfg.bit_width) - 1

        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('//'):
                    packed = int(line, 16)
                    i_val = (packed >> cfg.bit_width) & mask
                    q_val = packed & mask
                    i_data.append(self.from_signed(i_val, cfg.bit_width))
                    q_data.append(self.from_signed(q_val, cfg.bit_width))

        # 归一化
        if cfg.frac_bits > 0:
            scale = 2 ** cfg.frac_bits
        else:
            scale = 2 ** (cfg.bit_width - 1)

        i_arr = np.array(i_data, dtype=np.float64) / scale
        q_arr = np.array(q_data, dtype=np.float64) / scale

        return i_arr + 1j * q_arr

    def import_mat(self, file_path: Union[str, Path],
                   i_var: str = 'I', q_var: str = 'Q',
                   complex_var: Optional[str] = None,
                   sample_rate: Optional[float] = None) -> Tuple[np.ndarray, float]:
        """
        从 MATLAB .mat 文件导入 IQ 数据

        Args:
            file_path: .mat 文件路径
            i_var: I 数据变量名
            q_var: Q 数据变量名
            complex_var: 复数变量名 (如果数据以复数形式存储)
            sample_rate: 采样率 (Hz), 如果为 None 则尝试从文件读取

        Returns:
            (复数 IQ 信号, 采样率)
        """
        try:
            from scipy.io import loadmat
        except ImportError:
            raise ImportError("需要安装 scipy: pip install scipy")

        file_path = Path(file_path)
        mat_data = loadmat(str(file_path))

        # 尝试获取采样率
        fs = sample_rate or self.config.sample_rate

        # 检查顶层变量
        for var_name in ['fs', 'Fs', 'sample_rate', 'sampleRate', 'SampleRate']:
            if var_name in mat_data:
                fs = float(mat_data[var_name].flatten()[0])
                break

        # 检查 info2.fs (iTest .bwv 文件格式)
        if 'info2' in mat_data:
            try:
                info2 = mat_data['info2']
                if info2.dtype.names and 'fs' in info2.dtype.names:
                    fs_val = info2['fs'][0, 0]
                    if fs_val is not None and len(fs_val) > 0:
                        fs = float(fs_val.flatten()[0])
            except (IndexError, TypeError, ValueError):
                pass

        # 获取 IQ 数据
        if complex_var and complex_var in mat_data:
            # 复数形式
            signal = mat_data[complex_var].flatten().astype(np.complex128)
        elif i_var in mat_data and q_var in mat_data:
            # 分离的 I/Q
            i_data = mat_data[i_var].flatten().astype(np.float64)
            q_data = mat_data[q_var].flatten().astype(np.float64)
            signal = i_data + 1j * q_data
        elif 'iq' in mat_data or 'IQ' in mat_data:
            # 常见变量名
            var_name = 'iq' if 'iq' in mat_data else 'IQ'
            data = mat_data[var_name]
            if np.iscomplexobj(data):
                signal = data.flatten().astype(np.complex128)
            else:
                # 可能是 Nx2 矩阵
                if data.shape[1] == 2:
                    signal = data[:, 0] + 1j * data[:, 1]
                else:
                    signal = data[0, :] + 1j * data[1, :]
        elif 'signal' in mat_data or 'Signal' in mat_data:
            var_name = 'signal' if 'signal' in mat_data else 'Signal'
            signal = mat_data[var_name].flatten().astype(np.complex128)
        else:
            # 列出可用变量
            available = [k for k in mat_data.keys() if not k.startswith('__')]
            raise ValueError(f"无法找到 IQ 数据. 可用变量: {available}")

        return signal, fs


# 便捷函数
def export_iq_txt(signal: np.ndarray, file_path: Union[str, Path],
                  bit_width: int = 12, frac_bits: int = 0,
                  iq_format: str = "two_column",
                  number_format: str = "signed",
                  add_header: bool = True) -> dict:
    """
    导出 IQ 数据到文本文件的便捷函数

    Args:
        signal: 复数 IQ 信号
        file_path: 输出文件路径
        bit_width: 量化位宽 (默认 12)
        frac_bits: 小数位数 (Q格式, 默认 0)
        iq_format: IQ 格式 ("two_column", "interleaved", "separate")
        number_format: 数值格式 ("signed", "unsigned", "hex")
        add_header: 是否添加文件头

    Returns:
        导出信息字典
    """
    config = IQExportConfig(
        bit_width=bit_width,
        frac_bits=frac_bits,
        iq_format=IQFormat(iq_format),
        number_format=NumberFormat(number_format),
        add_header=add_header,
    )
    exporter = IQExporter(config)
    return exporter.export_txt(signal, file_path)


def export_iq_verilog(signal: np.ndarray, file_path: Union[str, Path],
                      bit_width: int = 12, frac_bits: int = 0) -> dict:
    """
    导出 IQ 数据为 Verilog $readmemh 格式

    Args:
        signal: 复数 IQ 信号
        file_path: 输出文件路径
        bit_width: 量化位宽

    Returns:
        导出信息字典
    """
    config = IQExportConfig(bit_width=bit_width, frac_bits=frac_bits)
    exporter = IQExporter(config)
    return exporter.export_verilog_mem(signal, file_path)


def import_iq_txt(file_path: Union[str, Path],
                  bit_width: int = 12, frac_bits: int = 0,
                  iq_format: str = "two_column",
                  number_format: str = "signed",
                  skip_lines: int = 0) -> np.ndarray:
    """
    从文本文件导入 IQ 数据的便捷函数

    Args:
        file_path: 输入文件路径
        bit_width: 量化位宽
        frac_bits: 小数位数
        iq_format: IQ 格式
        number_format: 数值格式
        skip_lines: 跳过的行数

    Returns:
        复数 IQ 信号
    """
    config = IQImportConfig(
        bit_width=bit_width,
        frac_bits=frac_bits,
        iq_format=IQFormat(iq_format),
        number_format=NumberFormat(number_format),
        skip_lines=skip_lines,
    )
    importer = IQImporter(config)
    return importer.import_txt(file_path)


def import_iq_mat(file_path: Union[str, Path],
                  i_var: str = 'I', q_var: str = 'Q',
                  complex_var: Optional[str] = None) -> Tuple[np.ndarray, float]:
    """
    从 MATLAB .mat 文件导入 IQ 数据的便捷函数

    Args:
        file_path: .mat 文件路径
        i_var: I 数据变量名
        q_var: Q 数据变量名
        complex_var: 复数变量名

    Returns:
        (复数 IQ 信号, 采样率)
    """
    importer = IQImporter()
    return importer.import_mat(file_path, i_var, q_var, complex_var)


def frequency_shift(signal: np.ndarray, shift_hz: float, sample_rate: float) -> np.ndarray:
    """
    对 IQ 信号进行频率搬移（变频）

    原理：将信号乘以复数指数 exp(j * 2 * pi * f_shift * t)
    - 正频率：上变频（频谱右移）
    - 负频率：下变频（频谱左移）

    Args:
        signal: 复数 IQ 信号
        shift_hz: 频率偏移量 (Hz)
            - 正值：上变频（如 1e6 表示上移 1 MHz）
            - 负值：下变频（如 -1e6 表示下移 1 MHz）
        sample_rate: 采样率 (Hz)

    Returns:
        频率搬移后的复数 IQ 信号

    Example:
        # 下变频 1 MHz（去除 1 MHz 中频）
        baseband = frequency_shift(if_signal, -1e6, 8e6)

        # 上变频 1 MHz（添加 1 MHz 中频）
        if_signal = frequency_shift(baseband, 1e6, 8e6)
    """
    n_samples = len(signal)
    t = np.arange(n_samples) / sample_rate
    mixer = np.exp(1j * 2 * np.pi * shift_hz * t)
    return signal * mixer


def frequency_shift_iq(i_data: np.ndarray, q_data: np.ndarray,
                       shift_hz: float, sample_rate: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    对分离的 I/Q 数据进行频率搬移

    Args:
        i_data: I 路数据（实数数组）
        q_data: Q 路数据（实数数组）
        shift_hz: 频率偏移量 (Hz)
        sample_rate: 采样率 (Hz)

    Returns:
        (I_shifted, Q_shifted) 频率搬移后的 I/Q 数据
    """
    signal = i_data + 1j * q_data
    shifted = frequency_shift(signal, shift_hz, sample_rate)
    return shifted.real, shifted.imag
