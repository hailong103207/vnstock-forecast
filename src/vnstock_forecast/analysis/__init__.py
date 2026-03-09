"""
Analysis Module
===============

Module phân tích kỹ thuật – cung cấp framework để xây dựng và đánh giá
các kỹ thuật phân tích (technical analysis) dưới dạng plugin.

Kiến trúc chính:

- **Signal**:  Cấu trúc tín hiệu thống nhất (BUY / SELL) kèm metadata.
- **BaseTechnique**:  Lớp cơ sở cho mọi kỹ thuật phân tích. Kế thừa
  class này và implement ``analyze_step()`` để tạo technique mới.
- **Registry**:  Đăng ký / tra cứu technique bằng decorator
  ``@register("tên")``.
- **AnalysisBot**:  Bot tổ hợp N technique, tự động gọi analyze →
  lọc signal → chuyển thành Action cho BacktestEngine.
- **SignalProfile / Profiler**:  Chạy backtest hàng loạt cho mọi
  technique đã đăng ký, tính toán độ tin cậy tín hiệu, lưu local.

Quick start::

    from vnstock_forecast.analysis import (
        AnalysisBot,
        Signal, SignalDirection,
        registry,
    )
    from vnstock_forecast.analysis.techniques import RSICrossover, MACDCrossover

    # Tạo bot từ technique
    bot = AnalysisBot(
        name="RSI_MACD_Bot",
        techniques=[RSICrossover(), MACDCrossover()],
    )

    # Chạy backtest bình thường
    from vnstock_forecast.backtest import BacktestEngine
    engine = BacktestEngine(initial_cash=100_000_000)
    report = engine.run(bot=bot, data={"VNM": df}, start="2023-01-01")
    report.print_summary()

Profiling::

    from vnstock_forecast.analysis.profiler import Profiler

    profiler = Profiler()
    profiles = profiler.run(data={"VNM": df}, start="2023-01-01")
    profiler.save()
"""

from .base import BaseTechnique
from .bot import AnalysisBot
from .profile import SignalProfile
from .profiler import Profiler
from .registry import get_all_techniques, get_technique, register
from .signal import Signal, SignalDirection, TradePlan

__all__ = [
    # Signal
    "Signal",
    "SignalDirection",
    "TradePlan",
    # Technique
    "BaseTechnique",
    # Registry
    "register",
    "get_technique",
    "get_all_techniques",
    # Bot
    "AnalysisBot",
    # Profile
    "SignalProfile",
    "Profiler",
]
