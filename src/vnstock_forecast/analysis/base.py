"""BaseTechnique – lớp cơ sở cho mọi kỹ thuật phân tích kỹ thuật."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import pandas as pd

from .signal import Signal

if TYPE_CHECKING:
    from vnstock_forecast.backtest.context import StepContext


class BaseTechnique(ABC):
    """
    Lớp cơ sở cho tất cả kỹ thuật phân tích kỹ thuật.

    Mỗi technique cần implement:

    - ``analyze_step(ctx, symbol)`` – phân tích tại 1 bar (incremental).
      Được gọi mỗi bước bởi ``AnalysisBot``.

    Tùy chọn override:

    - ``analyze_batch(df)`` – phân tích toàn bộ DataFrame OHLCV một lần.
      Hữu ích cho profiler hoặc batch analysis.
    - ``required_lookback`` – số bars tối thiểu cần để phân tích.
    - ``params`` – dict tham số kỹ thuật (dùng cho profiling / logging).

    Lifecycle trong AnalysisBot::

        for symbol in ctx.symbols:
            for technique in self.techniques:
                signals = technique.analyze_step(ctx, symbol)
                # → bot tổng hợp signals

    Example::

        class RSICrossover(BaseTechnique):
            name = "RSI_Crossover"
            required_lookback = 15

            def __init__(self, period=14, oversold=30, overbought=70):
                self.period = period
                self.oversold = oversold
                self.overbought = overbought

            @property
            def params(self):
                return {"period": self.period, "oversold": self.oversold,
                        "overbought": self.overbought}

            def analyze_step(self, ctx, symbol):
                df = ctx.history(symbol, lookback=self.required_lookback + 5)
                # ... tính RSI, phát hiện tín hiệu ...
                return signals
    """

    name: str = "BaseTechnique"

    #: Số bars tối thiểu cần có trước khi technique có thể phân tích.
    required_lookback: int = 1

    @property
    def params(self) -> dict[str, Any]:
        """
        Tham số kỹ thuật hiện tại. Override để liệt kê params cụ thể.

        Dùng bởi profiler để log / so sánh cấu hình.
        """
        return {}

    @abstractmethod
    def analyze_step(self, ctx: StepContext, symbol: str) -> list[Signal]:
        """
        Phân tích tại bar hiện tại (incremental mode).

        Được gọi mỗi bước bởi ``AnalysisBot.on_step()``.
        Chỉ sử dụng dữ liệu từ ``ctx`` – không future data leak.

        Args:
            ctx:    StepContext chứa dữ liệu thị trường & tài khoản.
            symbol: Mã cổ phiếu cần phân tích.

        Returns:
            Danh sách ``Signal`` nếu phát hiện tín hiệu. ``[]`` nếu không.
        """
        ...

    def analyze_batch(self, df: pd.DataFrame, symbol: str) -> list[Signal]:
        """
        Phân tích toàn bộ DataFrame OHLCV một lần (batch mode).

        Mặc định raise NotImplementedError. Override nếu technique hỗ trợ
        batch analysis (hữu ích cho profiler).

        Args:
            df:     DataFrame OHLCV đầy đủ (DatetimeIndex + OHLCV columns).
            symbol: Mã cổ phiếu.

        Returns:
            Danh sách ``Signal`` phát hiện trên toàn bộ dữ liệu.
        """
        raise NotImplementedError(
            f"{self.name} chưa implement analyze_batch(). "
            "Override phương thức này để hỗ trợ batch analysis."
        )

    def __repr__(self) -> str:
        params_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.__class__.__name__}({params_str})"
