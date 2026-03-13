"""
Example bots minh họa cách dùng backtest module.

Dùng để test engine và làm template cho bot thật.

Usage::

    from vnstock_forecast.backtest.examples import SMABot
    from vnstock_forecast.backtest import BacktestEngine

    engine = BacktestEngine(initial_cash=100_000_000)
    report = engine.run(
        bot=SMABot(period=20, sl_pct=0.07, tp_pct=0.10),
        data={"VNM": df_vnm},
        start="2023-01-01",
        end="2024-12-31",
    )
    report.print_summary()
"""

from __future__ import annotations

from .bot_base import Action, ActionType, BotBase
from .context import StepContext


class SMABot(BotBase):
    """
    Bot đơn giản: SMA Crossover.

    - Mua khi giá Close cắt lên trên SMA(period).
    - Bán khi giá Close cắt xuống dưới SMA(period).
    - Tự đặt SL/TP theo phần trăm.

    Chạy trên tất cả symbols trong data.
    """

    name = "SMA_Crossover"

    def __init__(
        self,
        period: int = 20,
        sl_pct: float = 0.07,
        tp_pct: float = 0.10,
        allocation: float = 0.9,
    ) -> None:
        """
        Args:
            period:     Số bars tính SMA.
            sl_pct:     Stop loss (7% = 0.07).
            tp_pct:     Take profit (10% = 0.10).
            allocation: Phần trăm vốn dùng cho mỗi lệnh mua.
        """
        self.period = period
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.allocation = allocation

    def on_step(self, ctx: StepContext) -> list[Action]:
        actions: list[Action] = []

        for symbol in ctx.symbols:
            df = ctx.history(symbol, lookback=self.period + 1)
            if len(df) < self.period + 1:
                continue

            # Tính SMA
            closes = df["Close"]
            sma = closes.rolling(self.period).mean()

            price = ctx.price(symbol)
            prev_close = closes.iloc[-2]
            prev_sma = sma.iloc[-2]
            curr_sma = sma.iloc[-1]

            # Thiếu SMA (đầu chuỗi) → bỏ qua
            if prev_sma != prev_sma or curr_sma != curr_sma:  # NaN check
                continue

            # Crossover lên → MUA
            if prev_close <= prev_sma and price > curr_sma:
                if not ctx.has_position(symbol):
                    qty = int(ctx.cash * self.allocation // price)
                    if qty > 0:
                        actions.append(
                            Action(
                                type=ActionType.BUY,
                                symbol=symbol,
                                quantity=qty,
                                stop_loss=round(price * (1 - self.sl_pct), 2),
                                take_profit=round(price * (1 + self.tp_pct), 2),
                                reason=f"SMA{self.period} crossover up",
                            )
                        )

            # Crossover xuống → BÁN
            elif prev_close >= prev_sma and price < curr_sma:
                if ctx.has_position(symbol):
                    actions.append(
                        Action(
                            type=ActionType.SELL,
                            symbol=symbol,
                            quantity=0,
                            reason=f"SMA{self.period} crossover down",
                        )
                    )

        return actions


class BuyAndHoldBot(BotBase):
    """
    Bot mua và giữ – dùng làm benchmark.

    Mua tất cả symbols ở bar đầu tiên (chia đều vốn), giữ đến hết.
    """

    name = "BuyAndHold"

    def __init__(self, allocation: float = 0.95) -> None:
        self.allocation = allocation
        self._bought = False

    def on_step(self, ctx: StepContext) -> list[Action]:
        if self._bought:
            return []

        self._bought = True
        actions: list[Action] = []
        n_symbols = len(ctx.symbols)
        cash_per_symbol = ctx.cash * self.allocation / n_symbols

        for symbol in ctx.symbols:
            price = ctx.price(symbol)
            qty = int(cash_per_symbol // price)
            if qty > 0:
                actions.append(
                    Action(
                        type=ActionType.BUY,
                        symbol=symbol,
                        quantity=qty,
                        reason="Buy and Hold",
                    )
                )

        return actions
