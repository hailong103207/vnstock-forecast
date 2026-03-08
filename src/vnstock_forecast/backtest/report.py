"""BacktestReport – tổng hợp kết quả backtest và tính chỉ số."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from .portfolio import CloseReason, Portfolio, TradeEvent


@dataclass
class BacktestReport:
    """
    Kết quả backtest đầy đủ.

    Cung cấp:

    - ``summary()``        – dict tóm tắt các chỉ số chính.
    - ``trade_history()``  – DataFrame lịch sử giao dịch.
    - ``event_log()``      – DataFrame timeline tất cả sự kiện.
    - ``equity_df()``      – DataFrame đường equity.
    - ``print_summary()``  – in ra console.
    """

    bot_name: str
    symbols: list[str]
    start: datetime
    end: datetime
    initial_cash: float
    commission_rate: float
    portfolio: Portfolio
    events: list[TradeEvent]
    equity_curve: list[tuple[datetime, float]]

    # ==================================================================
    #  Summary
    # ==================================================================

    def summary(self) -> dict[str, Any]:
        """Tóm tắt kết quả dưới dạng dict."""
        closed = self.portfolio.closed_positions

        base = {
            "bot": self.bot_name,
            "symbols": self.symbols,
            "period": f"{self.start.date()} → {self.end.date()}",
            "initial_cash": self.initial_cash,
            "commission_rate": self.commission_rate,
        }

        if not closed:
            return {**base, "warning": "Không có giao dịch nào được thực hiện."}

        # Bỏ qua lệnh đóng cuối kỳ khi tính trade stats
        real_trades = [p for p in closed if p.close_reason != CloseReason.END_OF_DATA]

        wins = [p for p in real_trades if (p.pnl or 0) > 0]
        losses = [p for p in real_trades if (p.pnl or 0) <= 0]

        total_pnl = sum(p.pnl or 0 for p in closed)
        # Khi all positions đã đóng, equity = cash
        final_equity = self.portfolio.equity({})
        total_return = (final_equity - self.initial_cash) / self.initial_cash * 100

        avg_win = (sum(p.pnl_percent or 0 for p in wins) / len(wins)) if wins else 0.0
        avg_loss = (
            (sum(p.pnl_percent or 0 for p in losses) / len(losses)) if losses else 0.0
        )
        rr = abs(avg_win / avg_loss) if avg_loss else float("inf")

        by_reason: dict[str, int] = {}
        for p in closed:
            key = p.close_reason.value if p.close_reason else "unknown"
            by_reason[key] = by_reason.get(key, 0) + 1

        return {
            **base,
            "final_equity": round(final_equity, 0),
            "total_pnl": round(total_pnl, 0),
            "total_return_pct": round(total_return, 2),
            "total_trades": len(real_trades),
            "wins": len(wins),
            "losses": len(losses),
            "winrate_pct": (
                round(len(wins) / len(real_trades) * 100, 1) if real_trades else 0
            ),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "reward_risk_ratio": round(rr, 2),
            "max_drawdown_pct": round(self._max_drawdown(), 2),
            "close_reasons": by_reason,
        }

    # ==================================================================
    #  DataFrames
    # ==================================================================

    def trade_history(self) -> pd.DataFrame:
        """Bảng lịch sử tất cả giao dịch đã đóng."""
        rows = [
            {
                "id": p.id,
                "symbol": p.symbol,
                "entry_time": p.entry_time,
                "exit_time": p.exit_time,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "quantity": p.quantity,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "pnl": round(p.pnl or 0, 0),
                "pnl_pct": round(p.pnl_percent or 0, 2),
                "close_reason": (p.close_reason.value if p.close_reason else None),
            }
            for p in self.portfolio.closed_positions
        ]
        return pd.DataFrame(rows)

    def event_log(self) -> pd.DataFrame:
        """Timeline đầy đủ mọi sự kiện giao dịch."""
        rows = [
            {
                "timestamp": e.timestamp,
                "action": e.action,
                "symbol": e.symbol,
                "price": e.price,
                "quantity": e.quantity,
                "position_id": e.position_id,
                "equity": e.equity,
                "reason": e.reason,
            }
            for e in self.events
        ]
        return pd.DataFrame(rows)

    def equity_df(self) -> pd.DataFrame:
        """Đường equity theo thời gian – dùng để plot."""
        return pd.DataFrame(
            self.equity_curve, columns=["timestamp", "equity"]
        ).set_index("timestamp")

    # ==================================================================
    #  Print
    # ==================================================================

    def print_summary(self) -> None:
        """In bảng tóm tắt kết quả ra console."""
        s = self.summary()

        print("=" * 60)
        print(f"  BACKTEST REPORT: {s['bot']}")
        print("=" * 60)
        print(f"  Symbols:        {', '.join(s['symbols'])}")
        print(f"  Period:         {s['period']}")
        print(f"  Commission:     {s.get('commission_rate', 0) * 100:.2f}%")
        print("-" * 60)

        if "warning" in s:
            print(f"  ! {s['warning']}")
            print("=" * 60)
            return

        print(f"  Initial Cash:   {s['initial_cash']:>15,.0f}")
        print(f"  Final Equity:   {s['final_equity']:>15,.0f}")
        print(f"  Total PnL:      {s['total_pnl']:>15,.0f}")
        print(f"  Total Return:   {s['total_return_pct']:>14.2f}%")
        print("-" * 60)
        print(f"  Trades:         {s['total_trades']:>15d}")
        print(f"  Wins:           {s['wins']:>15d}")
        print(f"  Losses:         {s['losses']:>15d}")
        print(f"  Win Rate:       {s['winrate_pct']:>14.1f}%")
        print(f"  Avg Win:        {s['avg_win_pct']:>14.2f}%")
        print(f"  Avg Loss:       {s['avg_loss_pct']:>14.2f}%")
        print(f"  R:R Ratio:      {s['reward_risk_ratio']:>15.2f}")
        print(f"  Max Drawdown:   {s['max_drawdown_pct']:>14.2f}%")
        print("-" * 60)
        print(f"  Close Reasons:  {s['close_reasons']}")
        print("=" * 60)

    def plot_equity(self) -> None:
        """Plot đường equity theo thời gian."""
        import matplotlib.pyplot as plt

        df = self.equity_df()
        plt.figure(figsize=(12, 6))
        plt.plot(df.index, df["equity"], label="Equity Curve")
        plt.title(f"Equity Curve - {self.bot_name}")
        plt.xlabel("Time")
        plt.ylabel("Equity")
        plt.grid()
        plt.legend()
        plt.show()

    # ==================================================================
    #  Private
    # ==================================================================

    def _max_drawdown(self) -> float:
        """Max drawdown (%) từ equity curve."""
        if not self.equity_curve:
            return 0.0

        equities = [eq for _, eq in self.equity_curve]
        peak = equities[0]
        max_dd = 0.0

        for eq in equities:
            peak = max(peak, eq)
            if peak > 0:
                dd = (peak - eq) / peak * 100
                max_dd = max(max_dd, dd)

        return max_dd
