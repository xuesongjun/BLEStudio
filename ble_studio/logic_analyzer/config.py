"""逻辑分析仪 YAML 配置加载与兼容转换。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .models import BleRxConfig, LogicAnalyzerConfig


VALID_MODES = {"ddr", "sdr"}
VALID_FORMATS = {"txt", "csv", "npy", "npz", "mat", "mem", "html", "vcd", "json"}


def _as_int(value: Any) -> int:
    if isinstance(value, str):
        return int(value, 0)
    return int(value)


def _resolve_input_path(value: str, config_path: Path, warnings: list[str]) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()

    config_relative = (config_path.parent / path).resolve()
    if config_relative.exists():
        return config_relative

    cwd_relative = (Path.cwd() / path).resolve()
    if cwd_relative.exists():
        warnings.append(
            f"输入路径按旧 CWD 规则解析: {path}; 请迁移为相对配置文件路径"
        )
        return cwd_relative

    return config_relative


def _resolve_output_dir(value: str, config_path: Path, legacy: bool) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    if legacy:
        return (Path.cwd() / path).resolve()
    return (config_path.parent / path).resolve()


def _tuple_of_ints(values: Iterable[Any]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)


def _validate(config: LogicAnalyzerConfig) -> LogicAnalyzerConfig:
    errors = []

    if config.mode not in VALID_MODES:
        errors.append(f"mode 必须是 {sorted(VALID_MODES)}，当前为 {config.mode!r}")
    if config.sample_rate <= 0:
        errors.append("sample_rate 必须大于 0")
    if config.data_rate <= 0:
        errors.append("data_rate 必须大于 0")
    if config.bit_width <= 0 or config.bit_width > 16:
        errors.append("bit_width 必须在 1-16 之间")
    if len(config.data_bits) != config.bit_width:
        errors.append("data_bits 数量必须与 bit_width 一致")
    if len(set(config.data_bits)) != len(config.data_bits):
        errors.append("data_bits 不能重复")

    all_channels = list(config.data_bits) + list(config.extra_signals.values())
    if config.clk_channel is not None:
        all_channels.append(config.clk_channel)
    invalid_channels = sorted({ch for ch in all_channels if ch < 0 or ch > 15})
    if invalid_channels:
        errors.append(f"Kingst channel 必须在 0-15，非法值: {invalid_channels}")

    if config.mode == "ddr":
        if config.clk_channel is None:
            errors.append("DDR 模式必须配置 clk_channel")
        if config.rising_edge_data not in {"I", "Q"}:
            errors.append("rising_edge_data 必须是 I 或 Q")
        if config.falling_edge_data not in {"I", "Q"}:
            errors.append("falling_edge_data 必须是 I 或 Q")
        if config.rising_edge_data == config.falling_edge_data:
            errors.append("DDR 上升沿和下降沿必须分别映射到 I/Q")

    if config.search_range < 1:
        errors.append("search_range 必须大于 0")
    if config.max_plot_samples < 100:
        errors.append("max_plot_samples 不能小于 100")

    unknown_formats = sorted(set(config.save_formats) - VALID_FORMATS)
    if unknown_formats:
        errors.append(f"不支持的输出格式: {unknown_formats}")

    if config.ble_rx.enabled:
        if config.mode != "ddr":
            errors.append("BLE RX 验证只支持 DDR IQ 结果")
        if config.ble_rx.target_samples_per_symbol < 2:
            errors.append("target_samples_per_symbol 不能小于 2")

    if not config.input_file.exists():
        errors.append(f"输入文件不存在: {config.input_file}")
    elif not config.input_file.is_file():
        errors.append(f"输入路径不是文件: {config.input_file}")

    if errors:
        raise ValueError("逻辑分析仪配置无效:\n- " + "\n- ".join(errors))

    return config


def load_config(config_file: str | Path) -> LogicAnalyzerConfig:
    """加载新配置，同时兼容现有 flat YAML。"""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("需要安装 PyYAML 才能读取逻辑分析仪配置") from exc

    config_path = Path(config_file).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    is_legacy = "capture" not in raw and "input" not in raw
    warnings: list[str] = []

    if is_legacy:
        input_value = str(raw.get("input_file", ""))
        output_value = str(raw.get("output_file", ""))
        output_path = Path(output_value) if output_value else Path(input_value).with_suffix("")
        output_dir = _resolve_output_dir(str(output_path.parent or "."), config_path, True)
        output_stem = output_path.name or Path(input_value).stem

        mode = str(raw.get("mode", "ddr")).lower()
        extra_signals = {
            str(name): int(ch) for name, ch in raw.get("extra_signals", {}).items()
        }
        is_raw_sdr = mode == "sdr" and bool(extra_signals)
        default_profile = (
            "iq_ddr"
            if mode == "ddr"
            else "rssi_raw_sdr" if is_raw_sdr else "parallel_sdr"
        )
        profile = str(raw.get("profile", default_profile))
        config = LogicAnalyzerConfig(
            input_file=_resolve_input_path(input_value, config_path, warnings),
            output_dir=output_dir,
            output_stem=output_stem,
            config_path=config_path,
            profile=profile,
            sample_rate=float(raw.get("sample_rate", 500e6)),
            data_rate=float(raw.get("data_rate", 32e6)),
            mode=mode,
            data_bits=_tuple_of_ints(raw.get("data_bits", range(10))),
            clk_channel=(
                int(raw.get("clk_channel", raw.get("data_indicator", 10)))
                if mode == "ddr" or "clk_channel" in raw or "data_indicator" in raw
                else None
            ),
            bit_width=int(raw.get("bit_width", len(raw.get("data_bits", range(10))))),
            rising_edge_data=str(raw.get("rising_edge_data", "I")).upper(),
            falling_edge_data=str(raw.get("falling_edge_data", "Q")).upper(),
            eye_align=bool(raw.get("eye_align", True)),
            search_range=int(raw.get("search_range", 15)),
            glitch_filter=bool(raw.get("glitch_filter", False)),
            glitch_threshold=float(raw.get("glitch_threshold", 0.3)),
            adaptive_filter=bool(raw.get("adaptive_filter", not is_raw_sdr)),
            output_spike_filter=bool(raw.get("output_spike_filter", not is_raw_sdr)),
            extra_signals=extra_signals,
            save_formats=tuple(str(value).lower() for value in raw.get("save_formats", ["mat", "html"])),
            max_plot_samples=int(raw.get("max_plot_samples", 50_000)),
            show_plot=bool(raw.get("plot", False)),
            include_debug_data=bool(raw.get("include_debug_data", False)),
            warnings=warnings,
        )
        config.warnings.append("已加载 legacy flat YAML 配置")
        return _validate(config)

    input_cfg: Dict[str, Any] = raw.get("input", {})
    capture_cfg: Dict[str, Any] = raw.get("capture", {})
    processing_cfg: Dict[str, Any] = raw.get("processing", {})
    output_cfg: Dict[str, Any] = raw.get("output", {})
    ble_cfg: Dict[str, Any] = raw.get("ble_rx", {})

    input_value = str(input_cfg.get("file", ""))
    output_dir = _resolve_output_dir(
        str(output_cfg.get("directory", "../../artifacts/logic_analyzer")),
        config_path,
        False,
    )
    mode = str(capture_cfg.get("mode", "ddr")).lower()
    data_bits = _tuple_of_ints(capture_cfg.get("data_bits", range(10)))

    config = LogicAnalyzerConfig(
        input_file=_resolve_input_path(input_value, config_path, warnings),
        output_dir=output_dir,
        output_stem=str(output_cfg.get("stem", Path(input_value).stem or "capture")),
        config_path=config_path,
        profile=str(capture_cfg.get("profile", "iq_ddr" if mode == "ddr" else "parallel_sdr")),
        sample_rate=float(capture_cfg.get("sample_rate", 500e6)),
        data_rate=float(capture_cfg.get("data_rate", 32e6)),
        mode=mode,
        data_bits=data_bits,
        clk_channel=(
            int(capture_cfg["clock_channel"])
            if capture_cfg.get("clock_channel") is not None
            else None
        ),
        bit_width=int(capture_cfg.get("bit_width", len(data_bits))),
        rising_edge_data=str(capture_cfg.get("rising_edge_data", "I")).upper(),
        falling_edge_data=str(capture_cfg.get("falling_edge_data", "Q")).upper(),
        eye_align=bool(processing_cfg.get("eye_align", True)),
        search_range=int(processing_cfg.get("search_range", 15)),
        glitch_filter=bool(processing_cfg.get("glitch_filter", False)),
        glitch_threshold=float(processing_cfg.get("glitch_threshold", 0.3)),
        adaptive_filter=bool(processing_cfg.get("adaptive_filter", True)),
        output_spike_filter=bool(processing_cfg.get("output_spike_filter", True)),
        extra_signals={
            str(name): int(ch)
            for name, ch in capture_cfg.get("extra_signals", {}).items()
        },
        save_formats=tuple(str(value).lower() for value in output_cfg.get("formats", ["mat", "html", "json"])),
        max_plot_samples=int(output_cfg.get("max_plot_samples", 50_000)),
        show_plot=bool(output_cfg.get("show_plot", False)),
        include_debug_data=bool(output_cfg.get("include_debug_data", False)),
        ble_rx=BleRxConfig(
            enabled=bool(ble_cfg.get("enabled", False)),
            phy_mode=str(ble_cfg.get("phy_mode", "LE_1M")),
            access_address=_as_int(ble_cfg.get("access_address", 0x71764129)),
            channel=int(ble_cfg.get("channel", 0)),
            whitening=bool(ble_cfg.get("whitening", False)),
            target_samples_per_symbol=int(ble_cfg.get("target_samples_per_symbol", 16)),
        ),
        warnings=warnings,
    )
    return _validate(config)


def create_default_config(input_file: str | Path) -> LogicAnalyzerConfig:
    """为直接传入 BIN 的兼容入口创建默认 DDR 配置。"""
    path = Path(input_file).expanduser().resolve()
    config = LogicAnalyzerConfig(
        input_file=path,
        output_dir=(Path.cwd() / "artifacts" / "logic_analyzer").resolve(),
        output_stem=path.stem,
    )
    return _validate(config)
