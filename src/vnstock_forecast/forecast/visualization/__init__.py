"""vnstock_forecast.forecast.visualization – plot & persist signals."""

from .pdf_report import PDFProfileReport
from .plotter import plot_signal
from .snapshot import (
    HLine,
    IndicatorLine,
    PlotOverlays,
    Rectangle,
    SignalSnapshot,
    TrendLine,
    VLine,
)
from .store import SignalStore

__all__ = [
    # Snapshot data-structures
    "SignalSnapshot",
    "PlotOverlays",
    "IndicatorLine",
    "HLine",
    "VLine",
    "Rectangle",
    "TrendLine",
    # Plotter
    "plot_signal",
    # Store
    "SignalStore",
    # PDF Report
    "PDFProfileReport",
]
