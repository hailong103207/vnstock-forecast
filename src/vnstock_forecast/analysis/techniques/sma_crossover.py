"""SMA Crossover – tín hiệu dựa trên giá cắt SMA."""

from __future__ import annotations

from typing import Any

import pandas as pd

from vnstock_forecast.backtest.context import StepContext

from ..base import BaseTechnique
from ..registry import register
from ..signal import Signal, SignalDirection, TradePlan


@register("sma_crossover")
class SMACrossover(BaseTechnique):
    """
    Kỹ thuật SMA Crossover.

    Tín hiệu:

    - **BUY**: Giá Close cắt lên trên SMA(period).
    - **SELL**: Giá Close cắt xuống dưới SMA(period).

    Params::

        period: Chu kỳ SMA (mặc định 20).
        sl_pct: Stop loss % (mặc định 7%).
        tp_pct: Take profit % (mặc định 10%).
    """

    name = "sma_crossover"

    def __init__(
        self,
        period: int = 20,
        sl_pct: float = 0.07,
        tp_pct: float = 0.10,
    ) -> None:
        self.period = period
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.required_lookback = period + 2

    @property
    def params(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "sl_pct": self.sl_pct,
            "tp_pct": self.tp_pct,
        }

    def analyze_step(self, ctx: StepContext, symbol: str) -> list[Signal]:
        """Phân tích SMA crossover tại bar hiện tại."""
        df = ctx.history(symbol, lookback=self.period + 5)
        if len(df) < self.period + 1:
            return []

        closes = df["Close"]
        sma = closes.rolling(self.period).mean()

        if sma.isna().iloc[-1] or sma.isna().iloc[-2]:
            return []

        prev_close = closes.iloc[-2]
        curr_close = closes.iloc[-1]
        prev_sma = sma.iloc[-2]
        curr_sma = sma.iloc[-1]
        price = ctx.price(symbol)
        signals: list[Signal] = []

        # BUY: giá cắt lên trên SMA
        if prev_close <= prev_sma and curr_close > curr_sma:
            signals.append(
                Signal(
                    technique=self.name,
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    timestamp=ctx.timestamp,
                    trade_plan=TradePlan(
                        entry=price,
                        stop_loss=round(price * (1 - self.sl_pct), 2),
                        take_profit=round(price * (1 + self.tp_pct), 2),
                    ),
                    confidence=0.5,
                    reason=f"Close cắt lên SMA({self.period}): "
                    f"{curr_close:.0f} > {curr_sma:.0f}",
                    tags={"sma_bullish"},
                    metadata={"sma": float(curr_sma)},
                )
            )

        # SELL: giá cắt xuống dưới SMA
        if prev_close >= prev_sma and curr_close < curr_sma:
            signals.append(
                Signal(
                    technique=self.name,
                    symbol=symbol,
                    direction=SignalDirection.SELL,
                    timestamp=ctx.timestamp,
                    confidence=0.5,
                    reason=f"Close cắt xuống SMA({self.period}): "
                    f"{curr_close:.0f} < {curr_sma:.0f}",
                    tags={"sma_bearish"},
                    metadata={"sma": float(curr_sma)},
                )
            )

        return signals

    def analyze_batch(self, df: pd.DataFrame, symbol: str) -> list[Signal]:
        """Phân tích SMA crossover trên toàn bộ DataFrame."""
        if len(df) < self.period + 1:
            return []

        closes = df["Close"]
        sma = closes.rolling(self.period).mean()
        signals: list[Signal] = []

        for i in range(1, len(closes)):
            if sma.isna().iloc[i] or sma.isna().iloc[i - 1]:
                continue

            prev_close = closes.iloc[i - 1]
            curr_close = closes.iloc[i]
            prev_sma = sma.iloc[i - 1]
            curr_sma = sma.iloc[i]
            price = float(curr_close)
            timestamp = df.index[i].to_pydatetime()

            # BUY
            if prev_close <= prev_sma and curr_close > curr_sma:
                signals.append(
                    Signal(
                        technique=self.name,
                        symbol=symbol,
                        direction=SignalDirection.BUY,
                        timestamp=timestamp,
                        trade_plan=TradePlan(
                            entry=price,
                            stop_loss=round(price * (1 - self.sl_pct), 2),
                            take_profit=round(price * (1 + self.tp_pct), 2),
                        ),
                        confidence=0.5,
                        reason=f"SMA({self.period}) bullish crossover",
                        metadata={"sma": float(curr_sma)},
                    )
                )

            # SELL
            if prev_close >= prev_sma and curr_close < curr_sma:
                signals.append(
                    Signal(
                        technique=self.name,
                        symbol=symbol,
                        direction=SignalDirection.SELL,
                        timestamp=timestamp,
                        confidence=0.5,
                        reason=f"SMA({self.period}) bearish crossover",
                        metadata={"sma": float(curr_sma)},
                    )
                )

        return signals
