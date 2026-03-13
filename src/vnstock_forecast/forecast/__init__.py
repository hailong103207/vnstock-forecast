"""vnstock_forecast.forecast – analysis, strategies, profiling & forecasting."""

from .profile import SignalProfile
from .profiler import Profiler
from .signal import Signal, SignalDirection, TradePlan
from .technical.base import BaseTechnique
from .technical.bot import AnalysisBot
from .technical.registry import get_all_techniques, get_technique, register
from .visualization import (
    HLine,
    IndicatorLine,
    PlotOverlays,
    Rectangle,
    SignalSnapshot,
    SignalStore,
    TrendLine,
    VLine,
    plot_signal,
)

__all__ = [
    "Signal",
    "SignalDirection",
    "TradePlan",
    "BaseTechnique",
    "register",
    "get_technique",
    "get_all_techniques",
    "AnalysisBot",
    "SignalProfile",
    "Profiler",
    # Visualization
    "SignalSnapshot",
    "PlotOverlays",
    "IndicatorLine",
    "HLine",
    "VLine",
    "Rectangle",
    "TrendLine",
    "plot_signal",
    "SignalStore",
]
