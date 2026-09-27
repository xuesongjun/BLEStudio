"""CaptureResult 的有界抽样 HTML 可视化。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .models import CaptureResult


def select_plot_indices(sample_count: int, max_plot_samples: int) -> np.ndarray:
    """返回单调且不超过上限的均匀抽样索引。"""
    if sample_count < 0:
        raise ValueError("sample_count 不能为负数")
    if max_plot_samples < 1:
        raise ValueError("max_plot_samples 必须大于 0")
    if sample_count <= max_plot_samples:
        return np.arange(sample_count, dtype=np.int64)
    return np.linspace(
        0, sample_count - 1, max_plot_samples, dtype=np.int64
    )


def create_figure(
    result: CaptureResult,
    max_plot_samples: Optional[int] = None,
):
    """创建 Plotly Figure，所有 trace 均使用有界抽样数据。"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError as exc:
        raise ImportError("生成 HTML 需要安装 plotly") from exc

    limit = (
        result.config.max_plot_samples
        if max_plot_samples is None
        else max_plot_samples
    )
    indices = select_plot_indices(result.sample_count, limit)
    time_us = indices.astype(np.float64) / result.sample_rate * 1e6
    sampled_extra_signals = result.extra_signals
    raw_extra_signals = (
        {} if sampled_extra_signals else result.raw_capture.extra_signals
    )
    has_extra_signals = bool(sampled_extra_signals or raw_extra_signals)

    if result.is_iq:
        rows = 2 + (1 if has_extra_signals else 0)
        titles = ["I/Q Time Domain", "IQ Constellation"]
        if has_extra_signals:
            titles.append("Extra Signals")
        figure = make_subplots(
            rows=rows,
            cols=1,
            subplot_titles=titles,
            vertical_spacing=0.09,
        )
        if result.signed_data2 is None:
            raise ValueError("IQ CaptureResult 缺少 signed_data2")
        i_values = result.signed_data1[indices]
        q_values = result.signed_data2[indices]
        figure.add_trace(
            go.Scattergl(
                x=time_us,
                y=i_values,
                mode="lines",
                name="I signed",
                line=dict(color="#2563eb", width=1),
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scattergl(
                x=time_us,
                y=q_values,
                mode="lines",
                name="Q signed",
                line=dict(color="#dc2626", width=1),
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scattergl(
                x=i_values,
                y=q_values,
                mode="markers",
                name="IQ",
                marker=dict(size=3, color="#059669", opacity=0.55),
            ),
            row=2,
            col=1,
        )
        figure.update_xaxes(title_text="Time (us)", row=1, col=1)
        figure.update_yaxes(title_text="ADC code", row=1, col=1)
        figure.update_xaxes(title_text="I signed", row=2, col=1)
        figure.update_yaxes(title_text="Q signed", row=2, col=1)
        extra_row = 3
    else:
        rows = 1 + (1 if has_extra_signals else 0)
        titles = ["Parallel Data"]
        if has_extra_signals:
            titles.append("Extra Signals")
        figure = make_subplots(
            rows=rows,
            cols=1,
            subplot_titles=titles,
            vertical_spacing=0.12,
        )
        figure.add_trace(
            go.Scattergl(
                x=time_us,
                y=result.signed_data1[indices],
                mode="lines",
                name="Data signed",
                line=dict(color="#2563eb", width=1),
            ),
            row=1,
            col=1,
        )
        figure.update_xaxes(title_text="Time (us)", row=1, col=1)
        figure.update_yaxes(title_text="Code", row=1, col=1)
        extra_row = 2

    if sampled_extra_signals:
        for signal_index, (name, values) in enumerate(
            sorted(sampled_extra_signals.items())
        ):
            array = np.asarray(values).reshape(-1)
            valid = indices[indices < len(array)]
            figure.add_trace(
                go.Scattergl(
                    x=valid.astype(np.float64) / result.sample_rate * 1e6,
                    y=array[valid] + signal_index * 1.25,
                    mode="lines",
                    name=name,
                    line=dict(width=1),
                ),
                row=extra_row,
                col=1,
            )
        figure.update_xaxes(title_text="Extracted sample time (us)", row=extra_row, col=1)
        figure.update_yaxes(title_text="Logic level + offset", row=extra_row, col=1)
    elif raw_extra_signals:
        raw_count = result.raw_capture.sample_count
        raw_indices = select_plot_indices(raw_count, limit)
        raw_time_us = (
            raw_indices.astype(np.float64)
            / result.raw_capture.sample_rate
            * 1e6
        )
        for signal_index, (name, values) in enumerate(sorted(raw_extra_signals.items())):
            array = np.asarray(values).reshape(-1)
            valid = raw_indices[raw_indices < len(array)]
            figure.add_trace(
                go.Scattergl(
                    x=raw_time_us[:len(valid)],
                    y=array[valid] + signal_index * 1.25,
                    mode="lines",
                    name=name,
                    line=dict(width=1),
                ),
                row=extra_row,
                col=1,
            )
        figure.update_xaxes(title_text="Raw capture time (us)", row=extra_row, col=1)
        figure.update_yaxes(title_text="Logic level + offset", row=extra_row, col=1)

    measured = (
        f"{result.sample_rate_measured / 1e6:.6f} MHz"
        if result.sample_rate_measured is not None
        else "N/A"
    )
    figure.update_layout(
        title=(
            f"Logic Analyzer: {result.config.output_stem} | "
            f"Fs nominal {result.sample_rate / 1e6:.6f} MHz | "
            f"Fs measured {measured} | "
            f"plotted {len(indices)}/{result.sample_count} samples"
        ),
        height=420 * rows,
        template="plotly_white",
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
    )
    return figure


def export_html(
    result: CaptureResult,
    path: Optional[str | Path] = None,
    max_plot_samples: Optional[int] = None,
    show: Optional[bool] = None,
) -> Path:
    """写出仅含抽样数据的 HTML；Plotly runtime 使用 CDN。"""
    try:
        import plotly.io as pio
    except ImportError as exc:
        raise ImportError("生成 HTML 需要安装 plotly") from exc

    output = (
        Path(path)
        if path is not None
        else result.config.output_dir / f"{result.config.output_stem}.html"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure = create_figure(result, max_plot_samples=max_plot_samples)
    pio.write_html(
        figure,
        file=str(output),
        include_plotlyjs="cdn",
        full_html=True,
        auto_open=False,
    )
    should_show = result.config.show_plot if show is None else show
    if should_show:
        figure.show()
    return output


__all__ = ["create_figure", "export_html", "select_plot_indices"]
