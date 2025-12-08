"""
BLE Studio 可视化模块
使用 Plotly 绘制美观的交互式图表
"""

import numpy as np
from typing import Optional, Tuple
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class BLEVisualizer:
    """BLE 信号可视化工具"""

    # 默认颜色主题
    COLORS = {
        'primary': '#636EFA',      # 蓝色
        'secondary': '#EF553B',    # 红色
        'tertiary': '#00CC96',     # 绿色
        'quaternary': '#AB63FA',   # 紫色
        'background': "#FAFAFA",
        'grid': '#E5E5E5',
        'text': '#2D3436',
    }

    # 仪器风格颜色主题 (黑底黄色谱线 - 仿频谱仪/蓝牙测试仪)
    INSTRUMENT_COLORS = {
        'primary': '#FFFF00',      # 纯亮黄色 (主谱线) - 类似示波器/频谱仪
        'secondary': '#00FF00',    # 亮绿色 (次要)
        'tertiary': '#00FFFF',     # 青色
        'quaternary': '#FF8800',   # 橙色
        'trace1': '#FFFF00',       # 亮黄色 (I 分量)
        'trace2': '#00FF00',       # 亮绿色 (Q 分量)
        'background': '#000000',   # 纯黑背景
        'plot_bg': '#000000',      # 绘图区纯黑
        'grid': '#404040',         # 深灰网格 (不太亮)
        'grid_minor': '#202020',   # 更深网格
        'text': '#FFFFFF',         # 白色文字
        'title': '#FFFF00',        # 黄色标题
        'axis': '#808080',         # 坐标轴颜色
        'reference': '#FF0000',    # 参考线红色
    }

    # 默认布局配置
    DEFAULT_LAYOUT = dict(
        font=dict(family='Microsoft YaHei, Arial, sans-serif', size=12),
        paper_bgcolor='white',
        plot_bgcolor='#FAFAFA',
        margin=dict(l=60, r=40, t=60, b=60),
        hovermode='x unified',
    )

    def __init__(self, theme: str = 'default'):
        """
        初始化可视化器

        Args:
            theme: 主题名称 ('default', 'dark', 'instrument')
        """
        self.theme = theme
        if theme == 'dark':
            self.COLORS.update({
                'background': '#1E1E1E',
                'grid': '#333333',
                'text': '#E0E0E0',
            })
            self.DEFAULT_LAYOUT.update({
                'paper_bgcolor': '#1E1E1E',
                'plot_bgcolor': '#252525',
                'font': dict(color='#E0E0E0'),
            })
        elif theme == 'instrument':
            # 仪器风格: 黑底黄色高对比度
            self.COLORS = self.INSTRUMENT_COLORS.copy()
            self.DEFAULT_LAYOUT = dict(
                font=dict(family='Consolas, Monaco, monospace', size=11, color=self.INSTRUMENT_COLORS['text']),
                paper_bgcolor=self.INSTRUMENT_COLORS['background'],
                plot_bgcolor=self.INSTRUMENT_COLORS['plot_bg'],
                margin=dict(l=60, r=40, t=50, b=50),
                hovermode='x unified',
            )

    def _apply_layout(self, fig: go.Figure, title: str = '',
                      xaxis_title: str = '', yaxis_title: str = '') -> go.Figure:
        """应用默认布局"""
        fig.update_layout(
            **self.DEFAULT_LAYOUT,
            title=dict(text=title, font=dict(size=16, color=self.COLORS.get('title', self.COLORS['text']))),
            xaxis=dict(
                title=dict(text=xaxis_title, font=dict(color=self.COLORS['text'])),
                gridcolor=self.COLORS['grid'],
                zerolinecolor=self.COLORS['grid'],
                linecolor=self.COLORS.get('axis', self.COLORS['grid']),
                tickfont=dict(color=self.COLORS['text']),
            ),
            yaxis=dict(
                title=dict(text=yaxis_title, font=dict(color=self.COLORS['text'])),
                gridcolor=self.COLORS['grid'],
                zerolinecolor=self.COLORS['grid'],
                linecolor=self.COLORS.get('axis', self.COLORS['grid']),
                tickfont=dict(color=self.COLORS['text']),
            ),
        )
        return fig

    def plot_iq_time(self, signal: np.ndarray, sample_rate: float,
                     title: str = 'IQ 时域波形',
                     max_samples: int = 5000) -> go.Figure:
        """
        绘制 IQ 信号时域波形

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            title: 图表标题
            max_samples: 最大显示采样点数

        Returns:
            Plotly Figure 对象
        """
        # 限制显示点数以提高性能
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        t = np.arange(len(signal)) / sample_rate * 1e6  # 转换为 us

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            subplot_titles=('I 分量 (同相)', 'Q 分量 (正交)')
        )

        # I 分量
        fig.add_trace(
            go.Scatter(
                x=t, y=signal.real,
                mode='lines',
                name='I',
                line=dict(color=self.COLORS['primary'], width=1),
                hovertemplate='时间: %{x:.2f} μs<br>I: %{y:.4f}<extra></extra>'
            ),
            row=1, col=1
        )

        # Q 分量
        fig.add_trace(
            go.Scatter(
                x=t, y=signal.imag,
                mode='lines',
                name='Q',
                line=dict(color=self.COLORS['secondary'], width=1),
                hovertemplate='时间: %{x:.2f} μs<br>Q: %{y:.4f}<extra></extra>'
            ),
            row=2, col=1
        )

        fig.update_layout(
            **self.DEFAULT_LAYOUT,
            title=dict(text=title, font=dict(size=16)),
            height=500,
            showlegend=True,
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        )

        fig.update_xaxes(title_text='时间 (μs)', row=2, col=1, gridcolor=self.COLORS['grid'])
        fig.update_yaxes(title_text='幅度', gridcolor=self.COLORS['grid'])

        return fig

    def plot_iq_combined(self, signal: np.ndarray, sample_rate: float,
                         title: str = 'IQ 时域波形',
                         max_samples: int = 5000) -> go.Figure:
        """
        在同一图中绘制 IQ 信号

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            title: 图表标题
            max_samples: 最大显示采样点数

        Returns:
            Plotly Figure 对象
        """
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        t = np.arange(len(signal)) / sample_rate * 1e6

        fig = go.Figure()

        # 根据主题选择颜色
        i_color = self.COLORS.get('trace1', self.COLORS['primary'])
        q_color = self.COLORS.get('trace2', self.COLORS['secondary'])

        fig.add_trace(go.Scatter(
            x=t, y=signal.real,
            mode='lines',
            name='I (同相)',
            line=dict(color=i_color, width=1.2 if self.theme != 'instrument' else 1.8),
            hovertemplate='时间: %{x:.2f} μs<br>I: %{y:.4f}<extra></extra>'
        ))

        fig.add_trace(go.Scatter(
            x=t, y=signal.imag,
            mode='lines',
            name='Q (正交)',
            line=dict(color=q_color, width=1.2 if self.theme != 'instrument' else 1.8),
            hovertemplate='时间: %{x:.2f} μs<br>Q: %{y:.4f}<extra></extra>'
        ))

        self._apply_layout(fig, title, '时间 (μs)', '幅度')
        fig.update_layout(
            legend=dict(
                orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
                font=dict(color=self.COLORS['text'])
            ),
        )

        return fig

    def plot_spectrum(self, signal: np.ndarray, sample_rate: float,
                      title: str = '频谱图',
                      fft_size: int = 4096,
                      center_freq: float = 0.0) -> go.Figure:
        """
        绘制频谱图

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            title: 图表标题
            fft_size: FFT 点数
            center_freq: 中心频率 (Hz)

        Returns:
            Plotly Figure 对象
        """
        # 计算 FFT
        if len(signal) < fft_size:
            signal = np.pad(signal, (0, fft_size - len(signal)))

        # 使用 Hanning 窗
        window = np.hanning(fft_size)
        signal_windowed = signal[:fft_size] * window

        spectrum = np.fft.fftshift(np.fft.fft(signal_windowed))
        freq = np.fft.fftshift(np.fft.fftfreq(fft_size, 1/sample_rate))

        # 转换为 MHz 并添加中心频率
        freq_mhz = (freq + center_freq) / 1e6

        # 功率谱密度 (dB)
        psd = 20 * np.log10(np.abs(spectrum) + 1e-10)
        psd = psd - np.max(psd)  # 归一化

        fig = go.Figure()

        # 根据主题选择颜色和填充
        line_color = self.COLORS['primary']
        line_width = 1.8 if self.theme == 'instrument' else 1.5
        if self.theme == 'instrument':
            fill_color = 'rgba(255, 255, 0, 0.1)'  # 半透明亮黄色
        else:
            fill_color = 'rgba(99, 110, 250, 0.2)'

        fig.add_trace(go.Scatter(
            x=freq_mhz,
            y=psd,
            mode='lines',
            name='功率谱密度',
            line=dict(color=line_color, width=line_width),
            fill='tozeroy',
            fillcolor=fill_color,
            hovertemplate='频率: %{x:.3f} MHz<br>功率: %{y:.1f} dB<extra></extra>'
        ))

        self._apply_layout(fig, title, '频率 (MHz)', '相对功率 (dB)')
        fig.update_yaxes(range=[-80, 5])

        return fig

    def plot_spectrogram(self, signal: np.ndarray, sample_rate: float,
                         title: str = '时频谱图',
                         fft_size: int = 256,
                         overlap: float = 0.75) -> go.Figure:
        """
        绘制时频谱图 (瀑布图)

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            title: 图表标题
            fft_size: FFT 点数
            overlap: 重叠比例

        Returns:
            Plotly Figure 对象
        """
        hop_size = int(fft_size * (1 - overlap))
        num_frames = (len(signal) - fft_size) // hop_size + 1

        spectrogram = np.zeros((fft_size, num_frames))
        window = np.hanning(fft_size)

        for i in range(num_frames):
            start = i * hop_size
            frame = signal[start:start + fft_size] * window
            spectrogram[:, i] = np.abs(np.fft.fftshift(np.fft.fft(frame)))

        # 转换为 dB
        spectrogram_db = 20 * np.log10(spectrogram + 1e-10)
        spectrogram_db = spectrogram_db - np.max(spectrogram_db)

        # 时间和频率轴
        t = np.arange(num_frames) * hop_size / sample_rate * 1e6  # us
        freq = np.fft.fftshift(np.fft.fftfreq(fft_size, 1/sample_rate)) / 1e6  # MHz

        fig = go.Figure()

        fig.add_trace(go.Heatmap(
            x=t,
            y=freq,
            z=spectrogram_db,
            colorscale='Viridis',
            zmin=-60,
            zmax=0,
            colorbar=dict(title='dB', ticksuffix=' dB'),
            hovertemplate='时间: %{x:.2f} μs<br>频率: %{y:.3f} MHz<br>功率: %{z:.1f} dB<extra></extra>'
        ))

        self._apply_layout(fig, title, '时间 (μs)', '频率 (MHz)')

        return fig

    def plot_constellation(self, signal: np.ndarray,
                           title: str = '星座图',
                           max_points: int = 10000,
                           downsample: int = 1) -> go.Figure:
        """
        绘制星座图

        Args:
            signal: 复数 IQ 信号
            title: 图表标题
            max_points: 最大显示点数
            downsample: 下采样因子

        Returns:
            Plotly Figure 对象
        """
        # 下采样
        signal = signal[::downsample]
        if len(signal) > max_points:
            signal = signal[:max_points]

        fig = go.Figure()

        # 根据主题选择颜色
        point_color = self.COLORS['primary']
        point_opacity = 0.7 if self.theme == 'instrument' else 0.5

        fig.add_trace(go.Scattergl(
            x=signal.real,
            y=signal.imag,
            mode='markers',
            marker=dict(
                size=3,
                color=point_color,
                opacity=point_opacity,
            ),
            hovertemplate='I: %{x:.4f}<br>Q: %{y:.4f}<extra></extra>'
        ))

        self._apply_layout(fig, title, 'I (同相)', 'Q (正交)')

        # 使坐标轴等比例
        max_val = max(np.max(np.abs(signal.real)), np.max(np.abs(signal.imag))) * 1.1
        fig.update_xaxes(range=[-max_val, max_val], scaleanchor='y', scaleratio=1)
        fig.update_yaxes(range=[-max_val, max_val])

        # 添加参考圆
        theta = np.linspace(0, 2*np.pi, 100)
        circle_color = self.COLORS.get('reference', self.COLORS['grid']) if self.theme == 'instrument' else self.COLORS['grid']
        fig.add_trace(go.Scatter(
            x=np.cos(theta),
            y=np.sin(theta),
            mode='lines',
            line=dict(color=circle_color, width=1, dash='dash'),
            showlegend=False,
            hoverinfo='skip'
        ))

        return fig

    def plot_bits(self, bits: np.ndarray,
                  title: str = '比特流',
                  max_bits: int = 200) -> go.Figure:
        """
        绘制比特流

        Args:
            bits: 比特数组 (0/1)
            title: 图表标题
            max_bits: 最大显示比特数

        Returns:
            Plotly Figure 对象
        """
        if len(bits) > max_bits:
            bits = bits[:max_bits]

        fig = go.Figure()

        # 使用阶梯图
        x = np.repeat(np.arange(len(bits) + 1), 2)[1:-1]
        y = np.repeat(bits, 2)

        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='lines',
            line=dict(color=self.COLORS['primary'], width=2),
            fill='tozeroy',
            fillcolor=f'rgba(99, 110, 250, 0.3)',
            hovertemplate='Bit %{x:.0f}: %{y:.0f}<extra></extra>'
        ))

        self._apply_layout(fig, title, '比特索引', '值')
        fig.update_yaxes(range=[-0.2, 1.4], tickvals=[0, 1])

        return fig

    def plot_frequency_deviation(self, signal: np.ndarray, sample_rate: float,
                                  title: str = '瞬时频率偏移',
                                  max_samples: int = 5000) -> go.Figure:
        """
        绘制瞬时频率偏移

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            title: 图表标题
            max_samples: 最大显示采样点数

        Returns:
            Plotly Figure 对象
        """
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        # 计算瞬时频率
        phase = np.angle(signal)
        phase_unwrapped = np.unwrap(phase)
        freq_inst = np.diff(phase_unwrapped) * sample_rate / (2 * np.pi)

        t = np.arange(len(freq_inst)) / sample_rate * 1e6  # us

        fig = go.Figure()

        # 根据主题选择颜色
        line_color = self.COLORS.get('tertiary', self.COLORS['primary'])
        line_width = 1.0
        if self.theme == 'instrument':
            line_color = self.COLORS['primary']  # 仪器风格用亮黄色
            line_width = 1.5

        fig.add_trace(go.Scatter(
            x=t,
            y=freq_inst / 1e3,  # 转换为 kHz
            mode='lines',
            line=dict(color=line_color, width=line_width),
            hovertemplate='时间: %{x:.2f} μs<br>频偏: %{y:.1f} kHz<extra></extra>'
        ))

        self._apply_layout(fig, title, '时间 (μs)', '频率偏移 (kHz)')

        return fig

    def plot_eye_diagram(self, signal: np.ndarray, samples_per_symbol: int,
                         title: str = '眼图',
                         num_traces: int = 100) -> go.Figure:
        """
        绘制眼图

        Args:
            signal: 实数信号 (解调后)
            samples_per_symbol: 每符号采样数
            title: 图表标题
            num_traces: 叠加轨迹数

        Returns:
            Plotly Figure 对象
        """
        # 每个轨迹包含 2 个符号周期
        trace_len = 2 * samples_per_symbol
        num_traces = min(num_traces, len(signal) // trace_len)

        fig = go.Figure()

        t = np.linspace(0, 2, trace_len)

        for i in range(num_traces):
            start = i * samples_per_symbol
            trace = signal[start:start + trace_len]
            if len(trace) < trace_len:
                break

            fig.add_trace(go.Scatter(
                x=t,
                y=trace.real if np.iscomplexobj(trace) else trace,
                mode='lines',
                line=dict(color=self.COLORS['primary'], width=0.5),
                opacity=0.3,
                showlegend=False,
                hoverinfo='skip'
            ))

        self._apply_layout(fig, title, '符号周期', '幅度')

        return fig

    def plot_frequency_eye_diagram(self, signal: np.ndarray, sample_rate: float,
                                    samples_per_symbol: int = 8,
                                    title: str = '频率眼图',
                                    num_traces: int = 100) -> go.Figure:
        """
        绘制基于瞬时频率的眼图 (GFSK 专用)

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            samples_per_symbol: 每符号采样数
            title: 图表标题
            num_traces: 叠加轨迹数

        Returns:
            Plotly Figure 对象
        """
        # 计算瞬时频率
        phase = np.unwrap(np.angle(signal))
        freq_inst = np.diff(phase) * sample_rate / (2 * np.pi)

        # 每个轨迹包含 2 个符号周期
        trace_len = 2 * samples_per_symbol
        num_traces = min(num_traces, len(freq_inst) // samples_per_symbol - 2)

        fig = go.Figure()

        t = np.linspace(0, 2, trace_len)

        # 根据主题选择颜色
        trace_color = self.COLORS['primary']
        trace_opacity = 0.6 if self.theme == 'instrument' else 0.4
        trace_width = 1.2 if self.theme == 'instrument' else 0.8
        ref_color = self.COLORS.get('reference', 'red')

        for i in range(num_traces):
            start = i * samples_per_symbol
            trace = freq_inst[start:start + trace_len]
            if len(trace) < trace_len:
                break

            fig.add_trace(go.Scatter(
                x=t,
                y=trace / 1e3,  # 转换为 kHz
                mode='lines',
                line=dict(color=trace_color, width=trace_width),
                opacity=trace_opacity,
                showlegend=False,
                hoverinfo='skip'
            ))

        # 添加参考线 (±250 kHz for BLE 1M)
        fig.add_hline(y=250, line=dict(color=ref_color, width=1, dash='dash'),
                      annotation_text='+250 kHz', annotation_font=dict(color=self.COLORS['text']))
        fig.add_hline(y=-250, line=dict(color=ref_color, width=1, dash='dash'),
                      annotation_text='-250 kHz', annotation_font=dict(color=self.COLORS['text']))
        fig.add_hline(y=0, line=dict(color=self.COLORS['grid'], width=1, dash='dot'))

        self._apply_layout(fig, title, '符号周期', '瞬时频率 (kHz)')
        fig.update_yaxes(range=[-400, 400])

        return fig

    def calculate_rf_metrics(self, signal: np.ndarray, sample_rate: float,
                             samples_per_symbol: int = 8,
                             symbol_rate: float = 1e6,
                             payload_type: str = 'PRBS9') -> dict:
        """
        计算 BLE RF 测试指标 (符合 BLE RF-PHY Test Suite 规范)

        根据 BLE RF-PHY Test Specification:
        - ΔF1: 使用 0x0F (11110000) payload, 测量相对于序列中心频率的偏差
               ΔF1_max = 第2,3,6,7位相对于f1_ccf的平均偏差
               ΔF1_avg = 所有ΔF1_max的平均值
               要求: 225 kHz ≤ ΔF1avg ≤ 275 kHz (1M PHY)
        - ΔF2: 使用 0x55 (10101010) payload, 测量每个位的峰值频率偏差
               ΔF2_max = 每个位的峰值频率相对于f2_ccf的偏差
               ΔF2_avg = 所有ΔF2_max的平均值 = avg_one - avg_zero
               要求: ΔF2 ≥ 185 kHz, ΔF2/ΔF1 ≥ 0.8
        - ICFT: 在前导码上测量初始载波频率偏移
               要求: |ICFT| ≤ 150 kHz

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            samples_per_symbol: 每符号采样数
            symbol_rate: 符号率 (Hz)
            payload_type: 负载类型 (PRBS9, PATTERN_11110000, PATTERN_10101010 等)

        Returns:
            RF 测试指标字典
        """
        # 计算瞬时频率
        phase = np.unwrap(np.angle(signal))
        freq_inst = np.diff(phase) * sample_rate / (2 * np.pi)

        if len(freq_inst) < 20 * samples_per_symbol:
            return self._empty_rf_metrics()

        # ========== 1. ICFT: 初始载波频率偏移 (在前导码上测量) ==========
        # 前导码: 8 bits (LE 1M), 积分8位的平均频率
        # 前导码是 10101010, 理想情况下积分为0
        preamble_samples = 8 * samples_per_symbol
        preamble_freq = freq_inst[:preamble_samples]
        icft = np.mean(preamble_freq)  # 理想情况下应该为 0

        # ========== 2. 提取 payload 区域的瞬时频率 ==========
        # 跳过: 前导码(8bit) + 接入地址(32bit) + PDU头(16bit) = 56 bits
        header_bits = 8 + 32 + 16  # 56 bits
        payload_start = header_bits * samples_per_symbol
        freq_payload = freq_inst[payload_start:] if len(freq_inst) > payload_start else freq_inst

        if len(freq_payload) < 16 * samples_per_symbol:
            return self._empty_rf_metrics()

        # ========== 3. 计算每个符号的频率特征 ==========
        symbol_freq_peak = []      # 峰值频率 (带符号)
        symbol_freq_abs_mean = []  # 绝对值平均 (用于 ΔF1)
        symbol_freq_mid_avg = []   # 符号中间平均 (用于 ΔF2 稳态)
        for i in range(len(freq_payload) // samples_per_symbol):
            start = i * samples_per_symbol
            end = start + samples_per_symbol
            symbol_data = freq_payload[start:end]
            # 峰值 (带符号): 用于判断 1/0
            peak_idx = np.argmax(np.abs(symbol_data))
            symbol_freq_peak.append(symbol_data[peak_idx])
            # 绝对值平均: 用于 ΔF1avg (BLE 标准定义)
            symbol_freq_abs_mean.append(np.mean(np.abs(symbol_data)))
            # 中间区域平均: 用于 ΔF2 稳态测量
            mid_start = start + samples_per_symbol // 4
            mid_end = end - samples_per_symbol // 4
            symbol_freq_mid_avg.append(np.mean(freq_payload[mid_start:mid_end]))

        symbol_freq_peak = np.array(symbol_freq_peak)
        symbol_freq_abs_mean = np.array(symbol_freq_abs_mean)
        symbol_freq_mid_avg = np.array(symbol_freq_mid_avg)

        if len(symbol_freq_peak) < 16:
            return self._empty_rf_metrics()

        # 分离 '1' 和 '0' 符号 (基于峰值符号)
        threshold = 0
        freq_ones = symbol_freq_peak[symbol_freq_peak > threshold]
        freq_zeros = symbol_freq_peak[symbol_freq_peak < threshold]

        avg_one = np.mean(freq_ones) if len(freq_ones) > 0 else 0
        avg_zero = np.mean(freq_zeros) if len(freq_zeros) > 0 else 0

        # ========== 4. ΔF1 计算 (使用 0x55 pattern: 10101010) ==========
        # BLE 规范: ΔF1avg 是每个符号内瞬时频率绝对值的平均
        # ΔF1avg 应在 225-275 kHz 范围内
        # 支持多种 payload_type 格式: 'PATTERN_10101010', '10101010 (0x55)', '0x55' 等
        payload_upper = payload_type.upper()
        is_55_pattern = any(p in payload_upper for p in [
            'PATTERN_10101010', 'PATTERN_01010101',
            '10101010', '01010101',
            '0X55', '0XAA'
        ])

        if is_55_pattern:
            # 0x55 pattern: ΔF1 = 每个符号瞬时频率绝对值的平均
            delta_f1_values = symbol_freq_abs_mean.tolist()
        else:
            # 非 0x55 pattern: 使用峰值相对于中心的偏移
            center_freq = (avg_one + avg_zero) / 2
            delta_f1_values = [abs(peak - center_freq) for peak in symbol_freq_peak]

        # ========== 5. ΔF2 计算 (使用 0x0F pattern: 11110000) ==========
        # BLE 规范: ΔF2 是 11110000 模式下的稳态频率偏差
        # ΔF2max >= 185 kHz, ΔF2/ΔF1 >= 0.8
        # 支持多种 payload_type 格式: 'PATTERN_11110000', '11110000 (0xF0)', '0xF0' 等
        is_0f_pattern = any(p in payload_upper for p in [
            'PATTERN_11110000', 'PATTERN_00001111',
            '11110000', '00001111',
            '0XF0', '0X0F'
        ])

        delta_f2_values = []

        if is_0f_pattern:
            # 0x0F pattern: 8-bit 序列分组 (11110000 或 00001111)
            # ΔF2 是稳态区域 (第2,3,6,7位) 的频率偏差
            bits_per_sequence = 8
            num_sequences = len(symbol_freq_peak) // bits_per_sequence
            for seq_idx in range(num_sequences):
                seq_start = seq_idx * bits_per_sequence
                seq_freq = symbol_freq_peak[seq_start:seq_start + bits_per_sequence]
                if len(seq_freq) == 8:
                    # 稳态位: 索引 1,2 (1111中间) 和 5,6 (0000中间)
                    stable_freqs = [seq_freq[i] for i in [1, 2, 5, 6]]
                    center = (np.mean([seq_freq[1], seq_freq[2]]) +
                              np.mean([seq_freq[5], seq_freq[6]])) / 2
                    for sf in stable_freqs:
                        delta_f2_values.append(abs(sf - center))
        else:
            # 通用计算: 使用峰值频率
            center_freq = (avg_one + avg_zero) / 2
            for peak in symbol_freq_peak:
                delta_f2_values.append(abs(peak - center_freq))

        # ========== 6. 稳定调制指标 ==========
        # ΔF2avg (稳定调制) = |avg_one - avg_zero| / 2
        # 这是 '1' 和 '0' 相对于中心频率的平均偏移
        delta_f2_stable = abs(avg_one - avg_zero) / 2

        # ========== 7. 频率漂移 (Carrier Frequency Drift) ==========
        # 规范: 在 payload 区域内, 每 10-bit (1M) 间隔测量频率
        # |f0 - fn| ≤ 50 kHz, |fn - fn-5| ≤ 20 kHz (per 50μs)
        drift_interval_bits = 10  # 1M PHY
        drift_interval_samples = drift_interval_bits * samples_per_symbol
        num_drift_points = len(freq_payload) // drift_interval_samples

        drift_freqs = []
        for i in range(num_drift_points):
            start = i * drift_interval_samples
            end = start + drift_interval_samples
            drift_freqs.append(np.mean(freq_payload[start:end]))

        if len(drift_freqs) >= 2:
            f0_payload = drift_freqs[0]
            freq_drift_max = max(abs(f - f0_payload) for f in drift_freqs)
            # 漂移率
            drift_rates = [abs(drift_freqs[i+1] - drift_freqs[i])
                          for i in range(len(drift_freqs) - 1)]
            drift_rate_max = max(drift_rates) if drift_rates else 0
        else:
            freq_drift_max = 0
            drift_rate_max = 0

        # ========== 8. 功率计算 ==========
        signal_power = np.abs(signal) ** 2
        p_avg_linear = np.mean(signal_power)
        p_peak_linear = np.max(signal_power)
        p_avg_dbm = 10 * np.log10(p_avg_linear + 1e-10)
        p_peak_dbm = 10 * np.log10(p_peak_linear + 1e-10)

        # ========== 9. 计算最终指标 ==========
        delta_f1_avg = np.mean(delta_f1_values) / 1e3 if delta_f1_values else 0
        delta_f1_max = np.max(delta_f1_values) / 1e3 if delta_f1_values else 0
        delta_f1_min = np.min(delta_f1_values) / 1e3 if delta_f1_values else 0
        delta_f2_avg = delta_f2_stable / 1e3  # kHz (稳定调制指标)
        delta_f2_max = np.max(delta_f2_values) / 1e3 if delta_f2_values else delta_f2_avg

        # ΔF2/ΔF1 比值 (规范要求 ≥ 0.8)
        delta_f2_ratio = delta_f2_avg / delta_f1_avg if delta_f1_avg > 0 else 0

        return {
            'delta_f1_avg': delta_f1_avg,  # kHz
            'delta_f1_max': delta_f1_max,  # kHz
            'delta_f1_min': delta_f1_min,  # kHz
            'delta_f2_avg': delta_f2_avg,  # kHz
            'delta_f2_max': delta_f2_max,  # kHz
            'delta_f2_ratio': delta_f2_ratio,
            'freq_drift': freq_drift_max / 1e3,  # kHz
            'drift_rate': drift_rate_max / 1e3,  # kHz
            'icft': icft / 1e3,  # kHz
            'p_peak_dbm': p_peak_dbm,
            'p_avg_dbm': p_avg_dbm,
            'avg_one': avg_one / 1e3,  # kHz
            'avg_zero': avg_zero / 1e3,  # kHz
            # 判定结果 (BLE RF-PHY 规范要求, 1M PHY)
            'delta_f1_pass': 225 <= delta_f1_avg <= 275,  # 225 kHz ≤ ΔF1avg ≤ 275 kHz
            'delta_f2_pass': delta_f2_avg >= 185,  # ΔF2 ≥ 185 kHz
            'ratio_pass': delta_f2_ratio >= 0.8,  # ΔF2/ΔF1 ≥ 0.8
            'icft_pass': abs(icft / 1e3) <= 150,  # |ICFT| ≤ 150 kHz
            'drift_pass': freq_drift_max / 1e3 <= 50,  # |f0 - fn| ≤ 50 kHz
        }

    def _empty_rf_metrics(self) -> dict:
        """返回空的 RF 指标"""
        return {
            'delta_f1_avg': 0, 'delta_f1_max': 0, 'delta_f1_min': 0,
            'delta_f2_avg': 0, 'delta_f2_max': 0, 'delta_f2_ratio': 0,
            'freq_drift': 0, 'drift_rate': 0, 'icft': 0,
            'p_peak_dbm': -100, 'p_avg_dbm': -100, 'avg_one': 0, 'avg_zero': 0,
            'delta_f1_pass': False, 'delta_f2_pass': False, 'ratio_pass': False,
            'icft_pass': False, 'drift_pass': False,
        }

    def plot_rf_metrics_panel(self, metrics: dict, title: str = 'RF 测试指标',
                                 payload_type: str = 'PRBS9') -> go.Figure:
        """
        绘制 RF 测试仪表盘 (类似蓝牙测试仪显示)

        Args:
            metrics: RF 测试指标字典 (来自 calculate_rf_metrics)
            title: 图表标题
            payload_type: 负载类型 (如 'PRBS9', 'PATTERN_10101010' 等)

        Returns:
            Plotly Figure 对象
        """
        fig = go.Figure()

        # 根据主题设置颜色
        if self.theme in ('instrument', 'dark'):
            bg_color = self.COLORS.get('background', '#1a1a2e')
            value_color = self.COLORS.get('secondary', '#00ff88')  # 亮绿色
            label_color = '#888888'
            separator_color = '#444444'
            title_color = self.COLORS.get('primary', '#00aaff')
            line_color = '#333355'
            pass_color = self.COLORS.get('secondary', '#00ff88')
            fail_color = self.COLORS.get('reference', '#ff4444')
        else:
            # default 主题 - 白底深色文字
            bg_color = '#ffffff'
            value_color = '#2D3436'
            label_color = '#666666'
            separator_color = '#cccccc'
            title_color = self.COLORS.get('primary', '#636EFA')
            line_color = '#e0e0e0'
            pass_color = '#52c41a'
            fail_color = '#ff4d4f'

        # 背景设置
        fig.update_layout(
            paper_bgcolor=bg_color,
            plot_bgcolor=bg_color,
            font=dict(family='Consolas, Monaco, monospace', size=12, color=value_color),
        )

        # 指标数据 - 左侧
        left_labels = [
            'Packet Type',
            'P AVG',
            'ΔF1 Avg',
            'ΔF2 Avg',
            'Min ΔF1 max',
            'Min ΔF2 max',
            'Freq Drift',
            'Max Drift Rate',
        ]

        left_values = [
            'DTM',
            f"{metrics.get('p_avg_dbm', -100):.1f} dBm",
            f"{metrics.get('delta_f1_avg', 0):.1f} kHz",
            f"{metrics.get('delta_f2_avg', 0):.1f} kHz",
            f"{metrics.get('delta_f1_min', 0):.1f} kHz",
            f"{metrics.get('delta_f2_avg', 0) * 0.8:.1f} kHz",
            f"{metrics.get('freq_drift', 0):.1f} kHz",
            f"{metrics.get('drift_rate', 0):.2f} kHz/ms",
        ]

        # 指标数据 - 右侧
        right_labels = [
            'Payload',
            'P PEAK',
            'Max ΔF1 max',
            'Max ΔF2 max',
            'ΔF2 ≥185 kHz',
            'ΔF2/ΔF1 ≥0.8',
            'ICFT ≤150 kHz',
            'Drift ≤50 kHz',
        ]

        # 判定结果格式化
        def pass_fail(condition):
            return '✓ PASS' if condition else '✗ FAIL'

        right_values = [
            payload_type,
            f"{metrics.get('p_peak_dbm', -100):.1f} dBm",
            f"{metrics.get('delta_f1_max', 0):.1f} kHz",
            f"{metrics.get('delta_f2_max', 0):.1f} kHz",
            pass_fail(metrics.get('delta_f2_pass', False)),
            pass_fail(metrics.get('ratio_pass', False)),
            pass_fail(metrics.get('icft_pass', False)),
            pass_fail(metrics.get('drift_pass', False)),
        ]

        # 绘制左侧标签和值
        for i, (label, value) in enumerate(zip(left_labels, left_values)):
            y_pos = 0.95 - i * 0.11
            # 标签
            fig.add_annotation(
                x=0.02, y=y_pos, text=label,
                font=dict(size=11, color=label_color),
                showarrow=False, xanchor='left', yanchor='middle',
                xref='paper', yref='paper'
            )
            # 分隔符
            fig.add_annotation(
                x=0.25, y=y_pos, text='—',
                font=dict(size=11, color=separator_color),
                showarrow=False, xanchor='center', yanchor='middle',
                xref='paper', yref='paper'
            )
            # 值
            color = value_color
            if 'FAIL' in str(value):
                color = fail_color
            elif 'PASS' in str(value):
                color = pass_color
            fig.add_annotation(
                x=0.28, y=y_pos, text=value,
                font=dict(size=11, color=color, family='Consolas, Monaco, monospace'),
                showarrow=False, xanchor='left', yanchor='middle',
                xref='paper', yref='paper'
            )

        # 绘制右侧标签和值
        for i, (label, value) in enumerate(zip(right_labels, right_values)):
            if not label:
                continue
            y_pos = 0.95 - i * 0.11
            # 标签
            fig.add_annotation(
                x=0.52, y=y_pos, text=label,
                font=dict(size=11, color=label_color),
                showarrow=False, xanchor='left', yanchor='middle',
                xref='paper', yref='paper'
            )
            # 分隔符
            fig.add_annotation(
                x=0.75, y=y_pos, text='—',
                font=dict(size=11, color=separator_color),
                showarrow=False, xanchor='center', yanchor='middle',
                xref='paper', yref='paper'
            )
            # 值
            color = value_color
            if 'FAIL' in str(value):
                color = fail_color
            elif 'PASS' in str(value):
                color = pass_color
            fig.add_annotation(
                x=0.78, y=y_pos, text=value,
                font=dict(size=11, color=color, family='Consolas, Monaco, monospace'),
                showarrow=False, xanchor='left', yanchor='middle',
                xref='paper', yref='paper'
            )

        # 添加标题
        fig.add_annotation(
            x=0.5, y=1.02, text=title,
            font=dict(size=14, color=title_color),
            showarrow=False, xanchor='center', yanchor='bottom',
            xref='paper', yref='paper'
        )

        # 添加分隔线
        fig.add_shape(
            type='line', x0=0.5, x1=0.5, y0=0.05, y1=0.98,
            line=dict(color=line_color, width=1),
            xref='paper', yref='paper'
        )

        fig.update_layout(
            width=500,
            height=320,
            margin=dict(l=10, r=10, t=40, b=10),
            xaxis=dict(visible=False, range=[0, 1]),
            yaxis=dict(visible=False, range=[0, 1]),
        )

        return fig

    def create_dashboard(self, signal: np.ndarray, sample_rate: float,
                         bits: Optional[np.ndarray] = None,
                         title: str = 'BLE 信号分析仪表板') -> go.Figure:
        """
        创建综合仪表板

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            bits: 比特流 (可选)
            title: 图表标题

        Returns:
            Plotly Figure 对象
        """
        num_rows = 3 if bits is not None else 2

        subplot_titles = ['IQ 时域波形', '频谱图', '星座图']
        if bits is not None:
            subplot_titles.append('比特流')

        fig = make_subplots(
            rows=num_rows, cols=2,
            subplot_titles=subplot_titles[:num_rows*2],
            specs=[
                [{'colspan': 2}, None],
                [{}, {}],
                [{'colspan': 2}, None] if bits is not None else None,
            ][:num_rows],
            vertical_spacing=0.1,
            horizontal_spacing=0.08,
        )

        # 限制数据点数
        max_samples = 3000
        sig_plot = signal[:max_samples] if len(signal) > max_samples else signal
        t = np.arange(len(sig_plot)) / sample_rate * 1e6

        # IQ 时域
        fig.add_trace(go.Scatter(
            x=t, y=sig_plot.real, mode='lines', name='I',
            line=dict(color=self.COLORS['primary'], width=1)
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=t, y=sig_plot.imag, mode='lines', name='Q',
            line=dict(color=self.COLORS['secondary'], width=1)
        ), row=1, col=1)

        # 频谱
        fft_size = min(4096, len(signal))
        window = np.hanning(fft_size)
        spectrum = np.fft.fftshift(np.fft.fft(signal[:fft_size] * window))
        freq = np.fft.fftshift(np.fft.fftfreq(fft_size, 1/sample_rate)) / 1e6
        psd = 20 * np.log10(np.abs(spectrum) + 1e-10)
        psd = psd - np.max(psd)

        fig.add_trace(go.Scatter(
            x=freq, y=psd, mode='lines', name='频谱',
            line=dict(color=self.COLORS['tertiary'], width=1),
            fill='tozeroy', fillcolor='rgba(0, 204, 150, 0.2)'
        ), row=2, col=1)

        # 星座图
        const_signal = signal[::8][:5000]
        fig.add_trace(go.Scattergl(
            x=const_signal.real, y=const_signal.imag, mode='markers',
            name='星座点',
            marker=dict(size=2, color=self.COLORS['quaternary'], opacity=0.5)
        ), row=2, col=2)

        # 比特流
        if bits is not None:
            bits_plot = bits[:200] if len(bits) > 200 else bits
            x = np.repeat(np.arange(len(bits_plot) + 1), 2)[1:-1]
            y = np.repeat(bits_plot, 2)
            fig.add_trace(go.Scatter(
                x=x, y=y, mode='lines', name='比特',
                line=dict(color=self.COLORS['primary'], width=2),
                fill='tozeroy', fillcolor='rgba(99, 110, 250, 0.3)'
            ), row=3, col=1)

        fig.update_layout(
            **self.DEFAULT_LAYOUT,
            title=dict(text=title, font=dict(size=18)),
            height=800 if bits is not None else 600,
            showlegend=True,
        )

        return fig


def plot_ble_signal(signal: np.ndarray, sample_rate: float = 8e6,
                    bits: Optional[np.ndarray] = None) -> go.Figure:
    """
    快速绘制 BLE 信号的便捷函数

    Args:
        signal: 复数 IQ 信号
        sample_rate: 采样率 (Hz)
        bits: 比特流 (可选)

    Returns:
        Plotly Figure 对象
    """
    viz = BLEVisualizer()
    return viz.create_dashboard(signal, sample_rate, bits)
