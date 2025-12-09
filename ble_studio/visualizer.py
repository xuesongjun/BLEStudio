"""
BLE Studio 可视化模块
使用 Plotly 绘制美观的交互式图表

注意: RF 测量功能已移至 measure 模块
"""

import numpy as np
from typing import Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .measure import calculate_rf_metrics


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
                      center_freq: float = 0.0,
                      show_mask: bool = False,
                      phy_mode: str = 'LE_1M') -> go.Figure:
        """
        绘制频谱图

        Args:
            signal: 复数 IQ 信号
            sample_rate: 采样率 (Hz)
            title: 图表标题
            fft_size: FFT 点数
            center_freq: 中心频率 (Hz)
            show_mask: 是否显示 BLE 频谱模版
            phy_mode: PHY 模式 ('LE_1M', 'LE_2M', 'LE_Coded')

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
        psd = psd - np.max(psd)  # 归一化到峰值 0 dB

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

        # 添加 BLE 频谱模版
        if show_mask:
            mask_result = self._add_spectrum_mask(fig, freq_mhz, psd, phy_mode)
            # 更新标题显示 PASS/FAIL
            if mask_result['pass']:
                title = f"{title} ✓ PASS"
            else:
                title = f"{title} ✗ FAIL (违规: {mask_result['violation_count']})"

        self._apply_layout(fig, title, '频率 (MHz)', '相对功率 (dB)')
        fig.update_yaxes(range=[-80, 5])

        return fig

    def _get_ble_spectrum_mask(self, phy_mode: str = 'LE_1M') -> list:
        """
        获取 BLE 频谱模版定义 (台阶状)

        根据 Bluetooth Core Spec v5.x, Volume 6, Part A, Section 3:
        - LE 1M PHY: ±500kHz 带内, -20dBc@±1.5MHz, -30dBc@±2.5MHz, -40dBc@≥3MHz
        - LE 2M PHY: ±1MHz 带内, -20dBc@±2MHz, -30dBc@±3MHz, -40dBc@≥4MHz

        Returns:
            频谱模版点列表 [(freq_offset_mhz, level_dbc), ...] - 台阶状
        """
        if phy_mode == 'LE_2M':
            # LE 2M PHY 频谱模版 (台阶状)
            return [
                (-5.0, -40),
                (-4.0, -40), (-4.0, -30),
                (-3.0, -30), (-3.0, -20),
                (-2.0, -20), (-2.0, 0),
                (-1.0, 0),
                (1.0, 0),
                (2.0, 0), (2.0, -20),
                (3.0, -20), (3.0, -30),
                (4.0, -30), (4.0, -40),
                (5.0, -40)
            ]
        else:
            # LE 1M PHY 频谱模版 (台阶状)
            # BLE RF-PHY Test Specification 定义的限制
            return [
                (-4.0, -40),
                (-3.0, -40), (-3.0, -30),
                (-2.5, -30), (-2.5, -20),
                (-1.5, -20), (-1.5, 0),
                (-0.5, 0),
                (0.5, 0),
                (1.5, 0), (1.5, -20),
                (2.5, -20), (2.5, -30),
                (3.0, -30), (3.0, -40),
                (4.0, -40)
            ]

    def _add_spectrum_mask(self, fig: go.Figure, freq_mhz: np.ndarray,
                           psd: np.ndarray, phy_mode: str = 'LE_1M') -> dict:
        """
        在频谱图上添加 BLE 频谱模版并检测违规

        Args:
            fig: Plotly Figure 对象
            freq_mhz: 频率数组 (MHz)
            psd: 功率谱密度数组 (dB, 已归一化)
            phy_mode: PHY 模式

        Returns:
            检测结果字典 {'pass': bool, 'violation_count': int, 'violations': list}
        """
        mask_points = self._get_ble_spectrum_mask(phy_mode)

        # 提取模版的 x, y 坐标
        mask_freq = [p[0] for p in mask_points]
        mask_level = [p[1] for p in mask_points]

        # 根据主题选择模版颜色
        if self.theme == 'instrument':
            mask_color = 'rgba(255, 0, 0, 0.8)'  # 亮红色
            mask_fill = 'rgba(255, 0, 0, 0.1)'
            violation_color = 'rgba(255, 0, 0, 1.0)'
        else:
            mask_color = 'rgba(255, 77, 79, 0.8)'  # 红色
            mask_fill = 'rgba(255, 77, 79, 0.1)'
            violation_color = 'rgba(255, 77, 79, 1.0)'

        # 绘制频谱模版
        fig.add_trace(go.Scatter(
            x=mask_freq,
            y=mask_level,
            mode='lines',
            name='BLE 频谱模版',
            line=dict(color=mask_color, width=2, dash='dash'),
            hovertemplate='频偏: %{x:.1f} MHz<br>限制: %{y:.0f} dBc<extra></extra>'
        ))

        # 检测违规点
        violations = []
        violation_freq = []
        violation_psd = []

        # 创建模版插值函数 (台阶状: 使用 'previous' 插值)
        from scipy.interpolate import interp1d
        mask_interp = interp1d(mask_freq, mask_level, kind='previous',
                               bounds_error=False, fill_value=-40)

        # 检查每个频率点是否超过模版
        for i, (f, p) in enumerate(zip(freq_mhz, psd)):
            # 只检查模版覆盖范围内的频率
            if mask_freq[0] <= f <= mask_freq[-1]:
                mask_limit = mask_interp(f)
                if p > mask_limit + 0.5:  # 0.5 dB 容差
                    violations.append({
                        'freq_mhz': f,
                        'power_db': p,
                        'limit_db': float(mask_limit),
                        'excess_db': p - mask_limit
                    })
                    violation_freq.append(f)
                    violation_psd.append(p)

        # 标记违规点
        if violation_freq:
            # 限制显示的违规点数量，避免图表过于拥挤
            max_markers = 50
            if len(violation_freq) > max_markers:
                step = len(violation_freq) // max_markers
                violation_freq = violation_freq[::step]
                violation_psd = violation_psd[::step]

            fig.add_trace(go.Scatter(
                x=violation_freq,
                y=violation_psd,
                mode='markers',
                name=f'违规点 ({len(violations)})',
                marker=dict(
                    color=violation_color,
                    size=6,
                    symbol='x'
                ),
                hovertemplate='频率: %{x:.3f} MHz<br>功率: %{y:.1f} dB<br>超标<extra></extra>'
            ))

        return {
            'pass': len(violations) == 0,
            'violation_count': len(violations),
            'violations': violations[:10]  # 只返回前 10 个违规详情
        }

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

    def plot_iq_eye_diagram(self, signal: np.ndarray, samples_per_symbol: int,
                            title: str = 'IQ 眼图',
                            num_traces: int = 100,
                            interpolation_factor: int = 8,
                            sample_rate: float = 8e6) -> go.Figure:
        """
        绘制 IQ 眼图 (MATLAB eyediagram 风格)

        同时显示 I (In-Phase) 和 Q (Quadrature) 分量的眼图，
        与 MATLAB 的 eyediagram(signal, 2*sps) 输出一致。

        Args:
            signal: 复数 IQ 信号
            samples_per_symbol: 每符号采样数
            title: 图表标题
            num_traces: 叠加轨迹数
            interpolation_factor: 插值倍数 (使曲线更平滑)
            sample_rate: 采样率 (Hz)，用于计算真实时间轴

        Returns:
            Plotly Figure 对象 (2 行子图)
        """
        from plotly.subplots import make_subplots
        from scipy.interpolate import CubicSpline

        # 每个轨迹包含 2 个符号周期 (与 MATLAB 一致)
        trace_len = 2 * samples_per_symbol
        num_traces = min(num_traces, len(signal) // samples_per_symbol - 1)

        # 符号周期 (秒)
        symbol_period = samples_per_symbol / sample_rate
        # 时间轴范围: [-T, T] 其中 T = 符号周期 (与 MATLAB eyediagram 一致)
        t_max = symbol_period * 1e6  # 转换为微秒，与 MATLAB 显示一致

        # 原始时间轴 (微秒)
        t_orig = np.linspace(-t_max, t_max, trace_len)
        # 插值后的时间轴 (更密集的点使曲线更平滑)
        t_interp = np.linspace(-t_max, t_max, trace_len * interpolation_factor)

        # 创建 2 行子图
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['Eye Diagram for In-Phase Signal',
                          'Eye Diagram for Quadrature Signal'],
            vertical_spacing=0.12
        )

        # 根据主题选择颜色
        trace_color = self.COLORS['primary']
        trace_opacity = 0.6 if self.theme == 'instrument' else 0.4
        trace_width = 1.0 if self.theme == 'instrument' else 0.8

        # 绘制每个轨迹
        for i in range(num_traces):
            # 从符号边界开始
            start = i * samples_per_symbol
            trace = signal[start:start + trace_len]
            if len(trace) < trace_len:
                break

            # 使用三次样条插值使曲线平滑 (类似 MATLAB eyediagram)
            cs_i = CubicSpline(t_orig, trace.real)
            cs_q = CubicSpline(t_orig, trace.imag)
            i_interp = cs_i(t_interp)
            q_interp = cs_q(t_interp)

            # I 分量 (In-Phase)
            fig.add_trace(go.Scatter(
                x=t_interp,
                y=i_interp,
                mode='lines',
                line=dict(color=trace_color, width=trace_width),
                opacity=trace_opacity,
                showlegend=False,
                hoverinfo='skip'
            ), row=1, col=1)

            # Q 分量 (Quadrature)
            fig.add_trace(go.Scatter(
                x=t_interp,
                y=q_interp,
                mode='lines',
                line=dict(color=trace_color, width=trace_width),
                opacity=trace_opacity,
                showlegend=False,
                hoverinfo='skip'
            ), row=2, col=1)

        # 应用布局
        fig.update_layout(
            title=dict(text=title, font=dict(color=self.COLORS['text'])),
            paper_bgcolor=self.COLORS['background'],
            plot_bgcolor=self.COLORS.get('plot_bg', self.COLORS['background']),
            font=dict(color=self.COLORS['text']),
            height=600,
            showlegend=False,
        )

        # Y 轴范围 (归一化到 ±1)
        max_amp = max(np.max(np.abs(signal.real)), np.max(np.abs(signal.imag)))
        y_range = [-1.1, 1.1] if max_amp <= 1.0 else [-max_amp * 1.1, max_amp * 1.1]

        # X 轴刻度 (与 MATLAB 一致: 显示为 ×10^-6 格式)
        # t_max 已经是微秒
        tick_vals = [-t_max, -t_max/2, 0, t_max/2, t_max]

        for row in [1, 2]:
            fig.update_xaxes(
                title_text='Time (×10⁻⁶ s)' if row == 2 else '',
                gridcolor=self.COLORS['grid'],
                zerolinecolor=self.COLORS['grid'],
                range=[-t_max, t_max],
                tickvals=tick_vals,
                tickformat='.1f',
                row=row, col=1
            )
            fig.update_yaxes(
                title_text='Amplitude',
                gridcolor=self.COLORS['grid'],
                zerolinecolor=self.COLORS['grid'],
                range=y_range,
                row=row, col=1
            )

        # 更新子图标题颜色
        for annotation in fig.layout.annotations:
            annotation.font.color = self.COLORS['text']

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
