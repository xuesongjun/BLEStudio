import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

file_path = 'C:/workspace/BLEStudio/template_data/test.bin'

with open(file_path, 'rb') as f:
    data = f.read()

raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 2)
low_byte = raw[:, 0]
high_byte = raw[:, 1]

channels = {}
for ch in range(10):
    if ch < 8:
        channels[ch] = (low_byte >> ch) & 1
    else:
        channels[ch] = (high_byte >> (ch - 8)) & 1

clk = (high_byte >> 2) & 1

clk_diff = np.diff(clk.astype(np.int8))
rising_edges = np.where(clk_diff == 1)[0] + 1
falling_edges = np.where(clk_diff == -1)[0] + 1

# 分开的延迟
i_delays = {0: 2, 1: 1, 2: 9, 3: 1, 4: 9, 5: 2, 6: 1, 7: 2, 8: 0, 9: 1}
q_delays = {0: 5, 1: 4, 2: 5, 3: 3, 4: 4, 5: 5, 6: 5, 7: 3, 8: 3, 9: 3}

def extract_value(edge_idx, delays):
    value = 0
    for bit in range(10):
        sample_idx = edge_idx + delays[bit]
        if 0 <= sample_idx < len(channels[bit]):
            value |= (int(channels[bit][sample_idx]) << bit)
    return value

# 提取 I (上升沿) 和 Q (下降沿)
I_raw = np.array([extract_value(idx, i_delays) for idx in rising_edges if idx + 15 < len(clk)])
Q_raw = np.array([extract_value(idx, q_delays) for idx in falling_edges if idx + 15 < len(clk)])

# 对齐长度
min_len = min(len(I_raw), len(Q_raw))
I_raw = I_raw[:min_len]
Q_raw = Q_raw[:min_len]

# 10-bit 有符号转换
def to_signed(x, bits=10):
    x = x.astype(np.int32)
    x[x >= (1 << (bits-1))] -= (1 << bits)
    return x

I = to_signed(I_raw)
Q = to_signed(Q_raw)

print(f'IQ 对数: {len(I)}')
print(f'I: range [{I.min()}, {I.max()}], mean={I.mean():.2f}')
print(f'Q: range [{Q.min()}, {Q.max()}], mean={Q.mean():.2f}')

I_diff = np.abs(np.diff(I))
Q_diff = np.abs(np.diff(Q))
print(f'I diff: max={I_diff.max()}, mean={I_diff.mean():.1f}')
print(f'Q diff: max={Q_diff.max()}, mean={Q_diff.mean():.1f}')

# 创建 3 行子图
fig = make_subplots(
    rows=3, cols=1,
    subplot_titles=(
        f'I Channel ({len(I)} samples) - Separate Eye Aligned',
        f'Q Channel ({len(Q)} samples) - Separate Eye Aligned',
        'I & Q Overlay'
    ),
    vertical_spacing=0.08
)

# I 通道
fig.add_trace(
    go.Scattergl(y=I, mode='lines', name='I',
                 line=dict(color='blue', width=1)),
    row=1, col=1
)

# Q 通道
fig.add_trace(
    go.Scattergl(y=Q, mode='lines', name='Q',
                 line=dict(color='red', width=1)),
    row=2, col=1
)

# I & Q 叠加
fig.add_trace(
    go.Scattergl(y=I, mode='lines', name='I',
                 line=dict(color='blue', width=1), opacity=0.7),
    row=3, col=1
)
fig.add_trace(
    go.Scattergl(y=Q, mode='lines', name='Q',
                 line=dict(color='red', width=1), opacity=0.7),
    row=3, col=1
)

# 更新布局
fig.update_yaxes(title_text='Amplitude', row=1, col=1)
fig.update_yaxes(title_text='Amplitude', row=2, col=1)
fig.update_yaxes(title_text='Amplitude', row=3, col=1)
fig.update_xaxes(title_text='Sample Index', row=3, col=1)

fig.update_layout(
    height=900,
    title_text='IQ Data - Separate Eye Aligned',
    title_x=0.5,
    showlegend=True,
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5)
)

# 保存 HTML
html_path = 'C:/workspace/BLEStudio/template_data/test_bin_iq.html'
fig.write_html(html_path, config={'responsive': True})
print(f'Saved: {html_path}')

# 显示
fig.show()
