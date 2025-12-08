"""
BLE Studio 报告生成模块
生成 HTML 格式的仿真报告和图表
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional
import numpy as np

from .visualizer import BLEVisualizer


def _decode_plotly_bdata(fig_dict):
    """将 Plotly 的 bdata 二进制格式解码为列表"""
    import base64
    import struct

    # dtype 映射到 struct 格式和大小
    dtype_map = {
        'f8': ('d', 8),  # float64
        'f4': ('f', 4),  # float32
        'i4': ('i', 4),  # int32
        'i2': ('h', 2),  # int16
        'i1': ('b', 1),  # int8
        'i8': ('q', 8),  # int64
        'u4': ('I', 4),  # uint32
        'u2': ('H', 2),  # uint16
        'u1': ('B', 1),  # uint8
    }

    def decode_bdata(obj):
        """递归解码 bdata 格式为列表"""
        if isinstance(obj, dict):
            # 检查是否为 bdata 格式: {"dtype": "f8", "bdata": "..."} 或带 shape 的 2D 数组
            if 'dtype' in obj and 'bdata' in obj:
                dtype = obj['dtype']
                bdata = obj['bdata']
                shape = obj.get('shape')  # 可能有 shape 字段 (2D 数组)

                if dtype in dtype_map:
                    fmt, size = dtype_map[dtype]
                    try:
                        decoded = base64.b64decode(bdata)
                        count = len(decoded) // size
                        values = list(struct.unpack(f'<{count}{fmt}', decoded))

                        # 如果有 shape，reshape 为 2D 列表
                        if shape:
                            # shape 格式如 "10, 20"
                            dims = [int(d.strip()) for d in shape.split(',')]
                            if len(dims) == 2:
                                rows, cols = dims
                                values = [values[i*cols:(i+1)*cols] for i in range(rows)]
                        return values
                    except Exception:
                        return obj
            # 否则递归处理 dict 的值
            return {k: decode_bdata(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [decode_bdata(item) for item in obj]
        return obj

    return decode_bdata(fig_dict)


def _fig_to_json(fig):
    """将 Plotly figure 转换为 JSON 字符串，确保数据为列表格式"""
    import json
    fig_dict = fig.to_dict()
    decoded = _decode_plotly_bdata(fig_dict)
    return json.dumps(decoded)


def _fig_to_html_div(fig, div_id: str):
    """将 Plotly figure 转换为 HTML div，使用列表格式数据"""
    import json
    fig_dict = fig.to_dict()
    decoded = _decode_plotly_bdata(fig_dict)
    json_str = json.dumps(decoded)
    return f'''<div id="{div_id}"></div>
<script>
(function() {{
    var data = {json_str};
    Plotly.newPlot('{div_id}', data.data, data.layout, {{responsive: true}});
}})();
</script>'''


class ReportGenerator:
    """HTML 报告生成器"""

    def __init__(self, output_dir: str = "results", theme: str = 'instrument'):
        self.output_dir = output_dir
        self.theme = theme
        # 根据主题创建可视化器
        self.viz = BLEVisualizer(theme=theme)
        # 默认风格用于其他页面
        self.viz_default = BLEVisualizer(theme='default')
        os.makedirs(output_dir, exist_ok=True)

    def generate_all(self, results: Dict[str, Any],
                     iq_signal: np.ndarray,
                     noisy_signal: np.ndarray,
                     bits: np.ndarray,
                     sample_rate: float = 8e6):
        """生成所有报告"""
        self.generate_index(results, iq_signal, noisy_signal, sample_rate)
        self.generate_charts(results, iq_signal, noisy_signal, bits, sample_rate)
        self.generate_report(results)
        print(f"报告已生成: {self.output_dir}")

    def generate_index(self, results: Dict[str, Any],
                       iq_signal: np.ndarray,
                       noisy_signal: np.ndarray,
                       sample_rate: float = 8e6):
        """生成首页"""
        tx = results.get('tx', {})
        mod = results.get('modulation', {})
        demod = results.get('demodulation', {})
        ch = results.get('channel', {})
        rf_test = results.get('rf_test', {})

        # 计算每符号采样数
        symbol_rate = mod.get('symbol_rate_msps', 1.0) * 1e6
        samples_per_symbol = int(sample_rate / symbol_rate)

        # 生成图表 JSON
        fig_iq = self.viz.plot_iq_combined(iq_signal, sample_rate, title='IQ 时域波形', max_samples=2000)
        fig_iq.update_layout(height=280, margin=dict(l=50, r=30, t=40, b=40))

        fig_spectrum = self.viz.plot_spectrum(iq_signal, sample_rate, title='频谱图')
        fig_spectrum.update_layout(height=280, margin=dict(l=50, r=30, t=40, b=40))

        fig_const = self.viz.plot_constellation(noisy_signal, title='星座图', downsample=8)
        fig_const.update_layout(height=280, margin=dict(l=50, r=30, t=40, b=40))

        fig_freq = self.viz.plot_frequency_deviation(iq_signal, sample_rate, title='瞬时频率')
        fig_freq.update_layout(height=280, margin=dict(l=50, r=30, t=40, b=40))

        # 新增: 频率眼图
        fig_eye = self.viz.plot_frequency_eye_diagram(
            iq_signal, sample_rate, samples_per_symbol,
            title='频率眼图', num_traces=80
        )
        fig_eye.update_layout(height=280, margin=dict(l=50, r=30, t=40, b=40))

        # 新增: 计算 RF 测试指标
        rf_metrics = self.viz.calculate_rf_metrics(iq_signal, sample_rate, samples_per_symbol)
        rf_metrics['payload_type'] = rf_test.get('payload_type', tx.get('test_mode', 'ADV'))

        # 新增: RF 测试仪表盘
        fig_rf_panel = self.viz.plot_rf_metrics_panel(rf_metrics, title='RF 测试指标')

        # 转换为 JSON (使用共享函数解码 bdata 格式)
        chart_iq_json = _fig_to_json(fig_iq)
        chart_spectrum_json = _fig_to_json(fig_spectrum)
        chart_const_json = _fig_to_json(fig_const)
        chart_freq_json = _fig_to_json(fig_freq)
        chart_eye_json = _fig_to_json(fig_eye)
        chart_rf_panel_json = _fig_to_json(fig_rf_panel)

        html = self._index_template(
            tx, mod, demod, ch, rf_metrics,
            chart_iq_json, chart_spectrum_json, chart_const_json,
            chart_freq_json, chart_eye_json, chart_rf_panel_json
        )

        with open(os.path.join(self.output_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(html)

    def generate_charts(self, results: Dict[str, Any],
                        iq_signal: np.ndarray,
                        noisy_signal: np.ndarray,
                        bits: np.ndarray,
                        sample_rate: float = 8e6):
        """生成图表页面"""
        mod = results.get('modulation', {})
        symbol_rate = mod.get('symbol_rate_msps', 1.0) * 1e6
        samples_per_symbol = int(sample_rate / symbol_rate)

        charts_data = [
            ('IQ 时域波形', 'chart-iq', self.viz.plot_iq_time(iq_signal, sample_rate, title='BLE IQ 时域波形')),
            ('频谱图', 'chart-spectrum', self.viz.plot_spectrum(iq_signal, sample_rate, title='BLE 信号频谱')),
            ('星座图 (理想)', 'chart-const-ideal', self.viz.plot_constellation(iq_signal, title='星座图 (理想信号)', downsample=8)),
            ('星座图 (加噪)', 'chart-const-noisy', self.viz.plot_constellation(noisy_signal, title='星座图 (加噪后)', downsample=8)),
            ('时频谱图', 'chart-spectrogram', self.viz.plot_spectrogram(iq_signal, sample_rate, title='BLE 信号时频谱图')),
            ('比特流', 'chart-bits', self.viz.plot_bits(bits, title='BLE 数据包比特流')),
            ('瞬时频率', 'chart-freq', self.viz.plot_frequency_deviation(iq_signal, sample_rate, title='GFSK 瞬时频率偏移')),
            ('频率眼图', 'chart-eye', self.viz.plot_frequency_eye_diagram(iq_signal, sample_rate, samples_per_symbol, title='GFSK 频率眼图', num_traces=100)),
        ]

        charts_html = []
        for title, div_id, fig in charts_data:
            chart_div = _fig_to_html_div(fig, div_id)
            charts_html.append(f'''
            <div class="chart-section">
                <h2>{title}</h2>
                <div class="chart-container">{chart_div}</div>
            </div>''')

        html = self._charts_template('\n'.join(charts_html))

        with open(os.path.join(self.output_dir, 'charts.html'), 'w', encoding='utf-8') as f:
            f.write(html)

    def generate_report(self, results: Dict[str, Any]):
        """生成详细报告"""
        html = self._report_template(results)
        with open(os.path.join(self.output_dir, 'report.html'), 'w', encoding='utf-8') as f:
            f.write(html)

    def _index_template(self, tx, mod, demod, ch, rf_metrics,
                        chart_iq, chart_spectrum, chart_const, chart_freq,
                        chart_eye, chart_rf_panel):
        """首页模板"""
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BLE Studio - 仿真平台</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; min-height: 100vh; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; }}
        .header h1 {{ font-size: 1.8em; }}
        .header .time {{ font-size: 0.9em; opacity: 0.8; }}
        .main-container {{ display: grid; grid-template-columns: 280px 1fr; gap: 20px; padding: 20px; max-width: 1900px; margin: 0 auto; }}
        .side-panel {{ display: flex; flex-direction: column; gap: 15px; }}
        .status-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .status-card h3 {{ font-size: 0.85em; color: #666; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .status-row {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }}
        .status-row:last-child {{ border-bottom: none; }}
        .status-row .label {{ color: #666; font-size: 0.9em; }}
        .status-row .value {{ font-weight: 600; font-size: 0.95em; }}
        .status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.8em; font-weight: 600; }}
        .status-badge.success {{ background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }}
        .status-badge.fail {{ background: #fff2f0; color: #ff4d4f; border: 1px solid #ffccc7; }}
        .nav-links {{ display: flex; flex-direction: column; gap: 10px; }}
        .nav-link {{ display: block; padding: 12px 16px; background: white; border-radius: 10px; text-decoration: none; color: #333; font-weight: 500; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: all 0.2s; }}
        .nav-link:hover {{ transform: translateX(5px); box-shadow: 0 4px 12px rgba(0,0,0,0.12); }}
        .nav-link.report {{ border-left: 4px solid #52c41a; }}
        .nav-link.charts {{ border-left: 4px solid #fa8c16; }}
        .charts-panel {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; }}
        .chart-card {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .chart-card .chart-title {{ padding: 10px 15px; font-size: 0.85em; font-weight: 600; color: #333; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center; }}
        .chart-card .chart-title a {{ font-size: 0.8em; color: #667eea; text-decoration: none; }}
        .chart-card .chart-content {{ padding: 8px; }}
        .chart-card.dark {{ background: #000000; }}
        .chart-card.dark .chart-title {{ background: #000000; color: #FFFF00; border-bottom: 1px solid #404040; }}
        .chart-card.dark .chart-title a {{ color: #00FFFF; }}
        .data-compare {{ grid-column: span 3; background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .data-compare h3 {{ font-size: 0.95em; color: #333; margin-bottom: 15px; }}
        .payload-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
        .payload-box {{ background: #f8f9fa; border-radius: 8px; padding: 15px; }}
        .payload-box.tx {{ border-left: 4px solid #52c41a; }}
        .payload-box.rx {{ border-left: 4px solid #1890ff; }}
        .payload-box h4 {{ font-size: 0.8em; color: #666; margin-bottom: 8px; }}
        .payload-box .hex {{ font-family: 'Monaco', 'Menlo', monospace; font-size: 0.85em; word-break: break-all; color: #333; }}
        .match-status {{ text-align: center; padding: 15px; margin-top: 15px; border-radius: 8px; font-weight: 600; }}
        .match-status.success {{ background: linear-gradient(135deg, #f6ffed 0%, #d9f7be 100%); color: #389e0d; }}
        .match-status.fail {{ background: linear-gradient(135deg, #fff2f0 0%, #ffccc7 100%); color: #cf1322; }}
        @media (max-width: 1400px) {{ .charts-panel {{ grid-template-columns: repeat(2, 1fr); }} .data-compare {{ grid-column: span 2; }} }}
        @media (max-width: 1000px) {{ .main-container {{ grid-template-columns: 1fr; }} .side-panel {{ flex-direction: row; flex-wrap: wrap; }} .status-card {{ flex: 1; min-width: 250px; }} .charts-panel {{ grid-template-columns: 1fr; }} .data-compare {{ grid-column: span 1; }} .payload-grid {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>BLE Studio</h1>
        <div class="time">仿真时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
    <div class="main-container">
        <div class="side-panel">
            <div class="status-card">
                <h3>解调状态</h3>
                <div class="status-row"><span class="label">状态</span><span class="status-badge {'success' if demod.get('success') else 'fail'}">{'成功' if demod.get('success') else '失败'}</span></div>
                <div class="status-row"><span class="label">CRC</span><span class="status-badge {'success' if demod.get('crc_valid') else 'fail'}">{'通过' if demod.get('crc_valid') else '失败'}</span></div>
                <div class="status-row"><span class="label">RSSI</span><span class="value">{demod.get('rssi_db', 0):.1f} dB</span></div>
                <div class="status-row"><span class="label">频偏</span><span class="value">{demod.get('freq_offset_khz', 0):.1f} kHz</span></div>
            </div>
            <div class="status-card">
                <h3>仿真参数</h3>
                <div class="status-row"><span class="label">SNR</span><span class="value">{ch.get('snr_db', 'N/A')} dB</span></div>
                <div class="status-row"><span class="label">采样率</span><span class="value">{mod.get('sample_rate_mhz', 'N/A')} MHz</span></div>
                <div class="status-row"><span class="label">调制指数</span><span class="value">{mod.get('modulation_index', 'N/A')}</span></div>
                <div class="status-row"><span class="label">Payload</span><span class="value">{tx.get('payload_len', 'N/A')} bytes</span></div>
            </div>
            <div class="status-card">
                <h3>RF 测试结果</h3>
                <div class="status-row"><span class="label">ΔF1 Avg</span><span class="value">{rf_metrics.get('delta_f1_avg', 0):.1f} kHz</span></div>
                <div class="status-row"><span class="label">ΔF2 Avg</span><span class="value">{rf_metrics.get('delta_f2_avg', 0):.1f} kHz</span></div>
                <div class="status-row"><span class="label">ΔF2/ΔF1</span><span class="value">{rf_metrics.get('delta_f2_ratio', 0):.2f}</span></div>
                <div class="status-row"><span class="label">ΔF2≥185kHz</span><span class="status-badge {'success' if rf_metrics.get('delta_f2_pass') else 'fail'}">{'PASS' if rf_metrics.get('delta_f2_pass') else 'FAIL'}</span></div>
            </div>
            <div class="nav-links">
                <a href="report.html" class="nav-link report">查看详细报告 &rarr;</a>
                <a href="charts.html" class="nav-link charts">查看全部图表 &rarr;</a>
            </div>
        </div>
        <div class="charts-panel">
            <div class="chart-card{' dark' if self.theme in ('instrument', 'dark') else ''}"><div class="chart-title">IQ 时域波形<a href="charts.html">详情 &rarr;</a></div><div class="chart-content"><div id="chart-iq"></div></div></div>
            <div class="chart-card{' dark' if self.theme in ('instrument', 'dark') else ''}"><div class="chart-title">频谱图<a href="charts.html">详情 &rarr;</a></div><div class="chart-content"><div id="chart-spectrum"></div></div></div>
            <div class="chart-card{' dark' if self.theme in ('instrument', 'dark') else ''}"><div class="chart-title">星座图<a href="charts.html">详情 &rarr;</a></div><div class="chart-content"><div id="chart-const"></div></div></div>
            <div class="chart-card{' dark' if self.theme in ('instrument', 'dark') else ''}"><div class="chart-title">瞬时频率<a href="charts.html">详情 &rarr;</a></div><div class="chart-content"><div id="chart-freq"></div></div></div>
            <div class="chart-card{' dark' if self.theme in ('instrument', 'dark') else ''}"><div class="chart-title">频率眼图<a href="charts.html">详情 &rarr;</a></div><div class="chart-content"><div id="chart-eye"></div></div></div>
            <div class="chart-card{' dark' if self.theme in ('instrument', 'dark') else ''}"><div class="chart-title">RF 测试仪表盘</div><div class="chart-content"><div id="chart-rf-panel"></div></div></div>
            <div class="data-compare">
                <h3>Payload 数据对比</h3>
                <div class="payload-grid">
                    <div class="payload-box tx"><h4>发送 (TX)</h4><div class="hex">{demod.get('tx_payload', 'N/A')}</div></div>
                    <div class="payload-box rx"><h4>接收 (RX)</h4><div class="hex">{demod.get('rx_payload', '解调失败')}</div></div>
                </div>
                <div class="match-status {'success' if demod.get('payload_match') else 'fail'}">{'&#10003; 数据完全一致' if demod.get('payload_match') else '&#10007; 数据不匹配'}</div>
            </div>
        </div>
    </div>
    <script>
        window.onload = function() {{
            var chartIqData = {chart_iq};
            var chartSpectrumData = {chart_spectrum};
            var chartConstData = {chart_const};
            var chartFreqData = {chart_freq};
            var chartEyeData = {chart_eye};
            var chartRfPanelData = {chart_rf_panel};
            Plotly.newPlot('chart-iq', chartIqData.data, chartIqData.layout, {{responsive: true}});
            Plotly.newPlot('chart-spectrum', chartSpectrumData.data, chartSpectrumData.layout, {{responsive: true}});
            Plotly.newPlot('chart-const', chartConstData.data, chartConstData.layout, {{responsive: true}});
            Plotly.newPlot('chart-freq', chartFreqData.data, chartFreqData.layout, {{responsive: true}});
            Plotly.newPlot('chart-eye', chartEyeData.data, chartEyeData.layout, {{responsive: true}});
            Plotly.newPlot('chart-rf-panel', chartRfPanelData.data, chartRfPanelData.layout, {{responsive: true}});
        }};
    </script>
</body>
</html>'''

    def _charts_template(self, charts_content):
        """图表页面模板"""
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BLE Studio - 信号图表</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; min-height: 100vh; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ font-size: 2em; margin-bottom: 10px; }}
        .header p {{ opacity: 0.9; }}
        .nav {{ background: white; padding: 15px 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 100; }}
        .nav a {{ color: #667eea; text-decoration: none; margin-right: 20px; font-weight: 500; }}
        .nav a:hover {{ text-decoration: underline; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 30px; }}
        .chart-section {{ background: white; border-radius: 15px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); margin-bottom: 30px; overflow: hidden; }}
        .chart-section h2 {{ background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 15px 25px; font-size: 1.2em; }}
        .chart-container {{ padding: 20px; }}
        .footer {{ text-align: center; padding: 30px; color: #666; }}
    </style>
</head>
<body>
    <div class="header"><h1>BLE Studio - 信号图表</h1><p>BLE 基带信号可视化分析</p></div>
    <div class="nav"><a href="index.html">首页</a><a href="report.html">仿真结果</a><a href="charts.html">信号图表</a></div>
    <div class="container">{charts_content}</div>
    <div class="footer"><p>BLE Studio - BLE 基带算法仿真平台</p></div>
</body>
</html>'''

    def _report_template(self, results):
        """详细报告模板"""
        tx = results.get('tx', {})
        mod = results.get('modulation', {})
        ch = results.get('channel', {})
        demod = results.get('demodulation', {})

        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BLE Studio - 仿真结果</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; min-height: 100vh; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ font-size: 2em; margin-bottom: 10px; }}
        .nav {{ background: white; padding: 15px 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 100; }}
        .nav a {{ color: #667eea; text-decoration: none; margin-right: 20px; font-weight: 500; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 30px; }}
        .card {{ background: white; border-radius: 15px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); margin-bottom: 20px; overflow: hidden; }}
        .card-header {{ background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 15px 25px; font-size: 1.2em; font-weight: 600; }}
        .card-body {{ padding: 25px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; color: #666; font-weight: 600; width: 40%; }}
        td {{ color: #333; font-family: 'Monaco', 'Menlo', monospace; }}
        .status-badge {{ display: inline-block; padding: 5px 15px; border-radius: 20px; font-weight: 600; font-size: 0.9em; }}
        .status-success {{ background: #d4edda; color: #155724; }}
        .status-fail {{ background: #f8d7da; color: #721c24; }}
        .comparison {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px; }}
        .comparison-item {{ background: #f8f9fa; border-radius: 10px; padding: 20px; }}
        .comparison-item h4 {{ color: #666; margin-bottom: 10px; font-size: 0.9em; }}
        .comparison-item .value {{ font-family: 'Monaco', 'Menlo', monospace; font-size: 0.85em; word-break: break-all; }}
        .match-result {{ text-align: center; padding: 20px; margin-top: 15px; border-radius: 10px; }}
        .match-result.success {{ background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); }}
        .match-result.fail {{ background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%); }}
    </style>
</head>
<body>
    <div class="header"><h1>BLE Studio - 仿真结果</h1><p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p></div>
    <div class="nav"><a href="index.html">首页</a><a href="report.html">仿真结果</a><a href="charts.html">信号图表</a></div>
    <div class="container">
        <div class="card"><div class="card-header">发送端 (TX)</div><div class="card-body">
            <table>
                <tr><th>数据包比特数</th><td>{tx.get('bits', 'N/A')} bits</td></tr>
                <tr><th>Payload 长度</th><td>{tx.get('payload_len', 'N/A')} bytes</td></tr>
                <tr><th>广播地址</th><td>{tx.get('adv_address', 'N/A')}</td></tr>
            </table>
        </div></div>
        <div class="card"><div class="card-header">GFSK 调制</div><div class="card-body">
            <table>
                <tr><th>采样率</th><td>{mod.get('sample_rate_mhz', 'N/A')} MHz</td></tr>
                <tr><th>符号率</th><td>{mod.get('symbol_rate_msps', 'N/A')} Msps</td></tr>
                <tr><th>调制指数</th><td>{mod.get('modulation_index', 'N/A')}</td></tr>
                <tr><th>高斯滤波器 BT</th><td>{mod.get('bt', 'N/A')}</td></tr>
            </table>
        </div></div>
        <div class="card"><div class="card-header">信道模型</div><div class="card-body">
            <table>
                <tr><th>信噪比 (SNR)</th><td>{ch.get('snr_db', 'N/A')} dB</td></tr>
                <tr><th>载波频偏</th><td>{ch.get('freq_offset_khz', 'N/A')} kHz</td></tr>
            </table>
        </div></div>
        <div class="card"><div class="card-header">接收端 (RX)</div><div class="card-body">
            <table>
                <tr><th>解调状态</th><td><span class="status-badge {'status-success' if demod.get('success') else 'status-fail'}">{'成功' if demod.get('success') else '失败'}</span></td></tr>
                <tr><th>CRC 校验</th><td><span class="status-badge {'status-success' if demod.get('crc_valid') else 'status-fail'}">{'通过' if demod.get('crc_valid') else '失败'}</span></td></tr>
                <tr><th>RSSI</th><td>{demod.get('rssi_db', 0):.2f} dB</td></tr>
                <tr><th>频偏估计</th><td>{demod.get('freq_offset_khz', 0):.2f} kHz</td></tr>
            </table>
            <div class="comparison">
                <div class="comparison-item"><h4>发送 Payload (TX)</h4><div class="value">{demod.get('tx_payload', 'N/A')}</div></div>
                <div class="comparison-item"><h4>接收 Payload (RX)</h4><div class="value">{demod.get('rx_payload', '解调失败')}</div></div>
            </div>
            <div class="match-result {'success' if demod.get('payload_match') else 'fail'}">
                <span style="font-size: 2em;">{'OK' if demod.get('payload_match') else 'FAIL'}</span>
                <h3>{'数据完全一致' if demod.get('payload_match') else '数据不匹配'}</h3>
            </div>
        </div></div>
    </div>
</body>
</html>'''
