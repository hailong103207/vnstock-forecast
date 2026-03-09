"""BacktestEngine – core engine chạy backtest bar-by-bar."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from .bot_base import Action, ActionType, BotBase
from .context import StepContext
from .portfolio import CloseReason, Portfolio, TradeEvent
from .report import BacktestReport

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Engine backtest chạy bar-by-bar, tương thích mọi khung thời gian.

    Mỗi bar engine sẽ:

    1. Kiểm tra SL/TP tự động cho tất cả vị thế mở.
    2. Xây dựng ``StepContext`` (sổ lệnh, tiền, dữ liệu thị trường).
    3. Gọi ``bot.on_step(ctx)`` → nhận danh sách ``Action``.
    4. Thực thi các Action (mua/bán).
    5. Ghi lại equity curve.

    Usage::

        engine = BacktestEngine(initial_cash=100_000_000)
        report = engine.run(
            bot=my_bot,
            data={"VNM": df_vnm, "VHM": df_vhm},
            start="2023-01-01",
            end="2024-12-31",
        )
        report.print_summary()

    Data format::

        data: dict[str, pd.DataFrame]
        - Key   = symbol (vd: "VNM", "VHM")
        - Value = DataFrame OHLCV, bắt buộc có:
            * DatetimeIndex (hoặc Unix-timestamp index – auto convert)
            * Cột: Open, High, Low, Close, Volume

    Để load từ parquet store::

        from vnstock_forecast.data.query import query_ohlcv_grouped
        grouped = query_ohlcv_grouped(symbols=["VNM"], resolutions=["D"])
        data = grouped["D"]  # {"VNM": DataFrame}
    """

    def __init__(
        self,
        initial_cash: float = 100_000_000.0,
        commission_rate: float = 0.0015,
        settlement_days: int = 3,
    ) -> None:
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.settlement_days = settlement_days

    # ==================================================================
    #  Public API
    # ==================================================================

    def run(
        self,
        bot: BotBase,
        data: dict[str, pd.DataFrame],
        start: Optional[str | datetime] = None,
        end: Optional[str | datetime] = None,
    ) -> BacktestReport:
        """
        Chạy backtest.

        Args:
            bot:   Đối tượng kế thừa ``BotBase``.
            data:  ``{symbol: DataFrame}`` – OHLCV với DatetimeIndex.
            start: Ngày bắt đầu (inclusive). ``None`` = từ đầu dữ liệu.
            end:   Ngày kết thúc (inclusive). ``None`` = đến cuối dữ liệu.

        Returns:
            ``BacktestReport`` chứa toàn bộ kết quả.
        """
        data = self._prepare_data(data)
        symbols = list(data.keys())

        all_timestamps = self._collect_timestamps(data, start, end)
        if not all_timestamps:
            raise ValueError("Không có dữ liệu trong khoảng thời gian chỉ định.")

        portfolio = Portfolio(
            self.initial_cash, self.commission_rate, self.settlement_days
        )
        events: list[TradeEvent] = []
        equity_curve: list[tuple[datetime, float]] = []

        # --- on_start ------------------------------------------------
        first_ts = all_timestamps[0]
        first_prices = self._prices_at(data, first_ts)
        bot.on_start(
            StepContext(self._to_dt(first_ts), portfolio, data, first_prices, symbols)
        )

        # --- Iterate (bắt đầu từ bar thứ 2 để luôn có ≥1 bar lịch sử) ---
        for i in range(1, len(all_timestamps)):
            ts = all_timestamps[i]
            timestamp = self._to_dt(ts)
            current_prices = self._prices_at(data, ts)

            # 1) SL / TP tự động
            sl_tp_events = self._check_all_sl_tp(
                portfolio, data, symbols, ts, timestamp, current_prices
            )
            events.extend(sl_tp_events)

            # 2) Build context
            ctx = StepContext(timestamp, portfolio, data, current_prices, symbols)

            # 3) Gọi bot
            actions = bot.on_step(ctx)

            # 4) Thực thi actions
            action_events = self._execute_actions(
                actions, portfolio, current_prices, timestamp
            )
            events.extend(action_events)

            # 5) Ghi equity
            equity_curve.append((timestamp, portfolio.equity(current_prices)))

        # --- Đóng tất cả vị thế còn mở cuối kỳ ----------------------
        last_ts = all_timestamps[-1]
        last_dt = self._to_dt(last_ts)
        last_prices = self._prices_at(data, last_ts)

        for pos in list(portfolio.open_positions):
            price = last_prices.get(pos.symbol, pos.entry_price)
            closed = portfolio.close_position(
                pos.id, price, last_dt, CloseReason.END_OF_DATA
            )
            events.append(
                TradeEvent(
                    timestamp=last_dt,
                    action="end_of_data",
                    symbol=closed.symbol,
                    price=price,
                    quantity=closed.quantity,
                    position_id=closed.id,
                    equity=portfolio.equity(last_prices),
                    reason="Đóng cuối kỳ backtest",
                )
            )

        # --- on_end --------------------------------------------------
        final_ctx = StepContext(last_dt, portfolio, data, last_prices, symbols)
        bot.on_end(final_ctx)

        return BacktestReport(
            bot_name=bot.name,
            symbols=symbols,
            start=self._to_dt(all_timestamps[0]),
            end=last_dt,
            initial_cash=self.initial_cash,
            commission_rate=self.commission_rate,
            portfolio=portfolio,
            events=events,
            equity_curve=equity_curve,
        )

    # ==================================================================
    #  Internal helpers
    # ==================================================================

    @staticmethod
    def _prepare_data(
        data: dict[str, pd.DataFrame],
    ) -> dict[str, pd.DataFrame]:
        """Validate và chuẩn hóa input data."""
        if not data:
            raise ValueError("data không được rỗng")

        required_cols = {"Open", "High", "Low", "Close", "Volume"}
        prepared: dict[str, pd.DataFrame] = {}

        for symbol, df in data.items():
            # print(symbol, df)
            df = df.copy()

            # Auto-convert index sang DatetimeIndex
            if not isinstance(df.index, pd.DatetimeIndex):
                try:
                    df.index = pd.to_datetime(df.index, unit="s")
                except Exception:
                    df.index = pd.to_datetime(df.index)

            df = df.sort_index()

            missing = required_cols - set(df.columns)
            if missing:
                raise ValueError(f"DataFrame của '{symbol}' thiếu cột: {missing}")

            prepared[symbol] = df

        return prepared

    @staticmethod
    def _collect_timestamps(
        data: dict[str, pd.DataFrame],
        start: Optional[str | datetime],
        end: Optional[str | datetime],
    ) -> list:
        """Thu thập tất cả timestamps duy nhất, lọc theo khoảng thời gian."""
        all_ts = sorted(set().union(*(df.index for df in data.values())))

        if start is not None:
            start_ts = pd.Timestamp(start)
            all_ts = [t for t in all_ts if t >= start_ts]
        if end is not None:
            end_ts = pd.Timestamp(end)
            all_ts = [t for t in all_ts if t <= end_ts]

        return all_ts

    @staticmethod
    def _prices_at(
        data: dict[str, pd.DataFrame],
        ts: pd.Timestamp,
    ) -> dict[str, float]:
        """Giá Close mới nhất của tất cả symbols tại hoặc trước *ts*."""
        prices: dict[str, float] = {}
        for symbol, df in data.items():
            available = df[df.index <= ts]
            if not available.empty:
                prices[symbol] = float(available.iloc[-1]["Close"])
        return prices

    @staticmethod
    def _to_dt(ts: pd.Timestamp) -> datetime:
        if hasattr(ts, "to_pydatetime"):
            return ts.to_pydatetime()
        return ts  # type: ignore[return-value]

    # ------------------------------------------------------------------

    def _check_all_sl_tp(
        self,
        portfolio: Portfolio,
        data: dict[str, pd.DataFrame],
        symbols: list[str],
        ts: pd.Timestamp,
        timestamp: datetime,
        current_prices: dict[str, float],
    ) -> list[TradeEvent]:
        """Kiểm tra SL/TP cho tất cả symbols tại bar hiện tại."""
        events: list[TradeEvent] = []

        for symbol in symbols:
            df = data[symbol]
            bar_data = df[df.index == ts]
            if bar_data.empty:
                continue

            bar = bar_data.iloc[-1]
            closed_positions = portfolio.check_sl_tp(
                symbol,
                float(bar["High"]),
                float(bar["Low"]),
                timestamp,
            )

            for pos in closed_positions:
                assert pos.exit_price is not None
                assert pos.close_reason is not None
                events.append(
                    TradeEvent(
                        timestamp=timestamp,
                        action=pos.close_reason.value,
                        symbol=pos.symbol,
                        price=pos.exit_price,
                        quantity=pos.quantity,
                        position_id=pos.id,
                        equity=portfolio.equity(current_prices),
                        reason=f"Auto {pos.close_reason.value}",
                    )
                )

        return events

    # ------------------------------------------------------------------

    def _execute_actions(
        self,
        actions: list[Action],
        portfolio: Portfolio,
        current_prices: dict[str, float],
        timestamp: datetime,
    ) -> list[TradeEvent]:
        """Thực thi danh sách Action từ bot."""
        events: list[TradeEvent] = []

        for action in actions:
            try:
                if action.type == ActionType.BUY:
                    events.extend(
                        self._exec_buy(action, portfolio, current_prices, timestamp)
                    )
                elif action.type == ActionType.SELL:
                    events.extend(
                        self._exec_sell(action, portfolio, current_prices, timestamp)
                    )
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "[%s] Không thể %s %s: %s",
                    timestamp,
                    action.type.value,
                    action.symbol,
                    exc,
                )

        return events

    # ------------------------------------------------------------------

    @staticmethod
    def _exec_buy(
        action: Action,
        portfolio: Portfolio,
        current_prices: dict[str, float],
        timestamp: datetime,
    ) -> list[TradeEvent]:
        # Resolve giá nếu bot không chỉ định
        if action.price is None:
            if action.symbol not in current_prices:
                raise ValueError(f"Không có giá cho '{action.symbol}'")
            action.price = current_prices[action.symbol]

        pos = portfolio.open_position(action, timestamp)

        return [
            TradeEvent(
                timestamp=timestamp,
                action="buy",
                symbol=action.symbol,
                price=action.price,
                quantity=action.quantity,
                position_id=pos.id,
                equity=portfolio.equity(current_prices),
                reason=action.reason,
            )
        ]

    @staticmethod
    def _exec_sell(
        action: Action,
        portfolio: Portfolio,
        current_prices: dict[str, float],
        timestamp: datetime,
    ) -> list[TradeEvent]:
        events: list[TradeEvent] = []

        price = action.price or current_prices.get(action.symbol)
        if price is None:
            raise ValueError(f"Không có giá cho '{action.symbol}'")

        # Tìm vị thế cần đóng
        if action.position_id:
            pos_ids = [action.position_id]
        else:
            # Bán các vị thế đã qua T+N (FIFO) – không bán lô chưa đến hạn
            pos_ids = [
                p.id for p in portfolio.sellable_positions(action.symbol, timestamp)
            ]

        for pid in pos_ids:
            pos = portfolio.close_position(
                pid, price, timestamp, CloseReason.MANUAL, action
            )
            events.append(
                TradeEvent(
                    timestamp=timestamp,
                    action="sell",
                    symbol=pos.symbol,
                    price=price,
                    quantity=pos.quantity,
                    position_id=pos.id,
                    equity=portfolio.equity(current_prices),
                    reason=action.reason,
                )
            )
        return events
