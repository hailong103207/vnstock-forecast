"""
Techniques – các kỹ thuật phân tích kỹ thuật cụ thể.

Import module này để tự động đăng ký techniques vào registry::

    from vnstock_forecast.analysis.techniques import RSICrossover, MACDCrossover

    # Hoặc import toàn bộ để đăng ký tất cả
    import vnstock_forecast.analysis.techniques
"""

from .macd_crossover import MACDCrossover
from .rsi_crossover import RSICrossover
from .sma_crossover import SMACrossover

__all__ = [
    "RSICrossover",
    "MACDCrossover",
    "SMACrossover",
]
