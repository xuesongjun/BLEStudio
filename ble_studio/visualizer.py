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
        'background': '#FAFAFA',
        'grid': '#E5E5E5',
        'text': '#2D3436',
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
            theme: 主题名称 ('default', 'dark')
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

    def _apply_layout(self, fig: go.Figure, title: str = '',
                      xaxis_title: str = '', yaxis_title: str = '') -> go.Figure:
        """应用默认布局"""
        fig.update_layout(
            **self.DEFAULT_LAYOUT,
            title=dict(text=title, font=dict(size=16, color=self.COLORS['text'])),
            xaxis=dict(
                title=xaxis_title,
                gridcolor=self.COLORS['grid'],
                zerolinecolor=self.COLORS['grid'],
            ),
            yaxis=dict(
                title=yaxis_title,
                gridcolor=self.COLORS['grid'],
                zerolinecolor=self.COLORS['grid'],
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

        fig.add_trace(go.Scatter(
            x=t, y=signal.real,
            mode='lines',
            name='I (同相)',
            line=dict(color=self.COLORS['primary'], width=1.5),
            hovertemplate='时间: %{x:.2f} μs<br>I: %{y:.4f}<extra></extra>'
        ))

        fig.add_trace(go.Scatter(
            x=t, y=signal.imag,
            mode='lines',
            name='Q (正交)',
            line=dict(color=self.COLORS['secondary'], width=1.5),
            hovertemplate='时间: %{x:.2f} μs<br>Q: %{y:.4f}<extra></extra>'
        ))

        self._apply_layout(fig, title, '时间 (μs)', '幅度')
        fig.update_layout(
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
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

        fig.add_trace(go.Scatter(
            x=freq_mhz,
            y=psd,
            mode='lines',
            name='功率谱密度',
            line=dict(color=self.COLORS['primary'], width=1.5),
            fill='tozeroy',
            fillcolor=f'rgba(99, 110, 250, 0.2)',
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

        fig.add_trace(go.Scattergl(
            x=signal.real,
            y=signal.imag,
            mode='markers',
            marker=dict(
                size=3,
                color=self.COLORS['primary'],
                opacity=0.5,
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
        fig.add_trace(go.Scatter(
            x=np.cos(theta),
            y=np.sin(theta),
            mode='lines',
            line=dict(color=self.COLORS['grid'], width=1, dash='dash'),
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

        fig.add_trace(go.Scatter(
            x=t,
            y=freq_inst / 1e3,  # 转换为 kHz
            mode='lines',
            line=dict(color=self.COLORS['tertiary'], width=1),
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
