"""Portfolio, Position management & TradeEvent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional

from .bot_base import Action

# ======================================================================
#  Settlement helpers (T+N)
# ======================================================================


def _business_days_between(d1: date, d2: date) -> int:
    """
    Đếm số ngày giao dịch (Mon-Fri) giữa *d1* và *d2*.

    Không tính ngày *d1*, có tính ngày *d2*.
    Ví dụ: Monday → Thursday = 3 business days.
    """
    if d2 <= d1:
        return 0
    total_days = (d2 - d1).days
    weeks, remainder = divmod(total_days, 7)
    bd = weeks * 5
    start_wd = d1.weekday()  # Mon=0 ... Sun=6
    for i in range(1, remainder + 1):
        if (start_wd + i) % 7 < 5:
            bd += 1
    return bd


# ======================================================================
#  Enums & Data classes
# ======================================================================


class CloseReason(Enum):
    """Lý do đóng vị thế."""

    MANUAL = "manual"  # Bot chủ động bán
    STOP_LOSS = "stop_loss"  # Chạm SL
    TAKE_PROFIT = "take_profit"  # Chạm TP
    END_OF_DATA = "end_of_data"  # Hết dữ liệu backtest


@dataclass
class Position:
    """
    Một vị thế (lệnh) đang mở hoặc đã đóng.

    Khi đang mở: ``exit_price`` / ``exit_time`` / ``close_reason`` = None.
    Khi đã đóng: tất cả đều có giá trị.
    """

    id: str
    symbol: str
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    close_reason: Optional[CloseReason] = None

    entry_action: Optional[Action] = None
    exit_action: Optional[Action] = None

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    @property
    def cost(self) -> float:
        """Tổng giá trị vào lệnh (chưa tính phí)."""
        return self.entry_price * self.quantity

    @property
    def pnl(self) -> Optional[float]:
        """Lãi/lỗ tuyệt đối (chỉ khi đã đóng)."""
        if self.exit_price is None:
            return None
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def pnl_percent(self) -> Optional[float]:
        """Lãi/lỗ phần trăm (chỉ khi đã đóng)."""
        if self.exit_price is None or self.entry_price == 0:
            return None
        return (self.exit_price - self.entry_price) / self.entry_price * 100

    def unrealized_pnl(self, current_price: float) -> float:
        """Lãi/lỗ chưa thực hiện tại giá ``current_price``."""
        return (current_price - self.entry_price) * self.quantity

    def market_value(self, current_price: float) -> float:
        """Giá trị thị trường theo giá ``current_price``."""
        return current_price * self.quantity

    def can_sell(self, current_time: datetime, settlement_days: int) -> bool:
        """
        Kiểm tra vị thế này đã qua thời hạn T+N chưa.

        Args:
            current_time:    Thời điểm hiện tại.
            settlement_days: Số ngày giao dịch phải chờ (VN: 3).

        Returns:
            ``True`` nếu đã đủ N ngày giao dịch kể từ ngày mua.
        """
        if settlement_days <= 0:
            return True
        return (
            _business_days_between(self.entry_time.date(), current_time.date())
            >= settlement_days
        )


@dataclass
class TradeEvent:
    """Sự kiện giao dịch ghi lại trong quá trình backtest."""

    timestamp: datetime
    action: str  # buy / sell / stop_loss / take_profit / end_of_data
    symbol: str
    price: float
    quantity: float
    position_id: str
    equity: float
    reason: str = ""


# ======================================================================
#  Portfolio
# ======================================================================


class Portfolio:
    """
    Quản lý danh mục đầu tư: tiền mặt, vị thế, lịch sử giao dịch.

    Hỗ trợ phí giao dịch (commission) và tự động đóng lệnh khi chạm
    SL/TP.

    Attributes:
        cash:             Tiền mặt hiện có.
        initial_cash:     Vốn ban đầu.
        commission_rate:  Phí giao dịch mỗi chiều (mặc định 0.15%).
    """

    def __init__(
        self,
        initial_cash: float = 100_000_000.0,
        commission_rate: float = 0.0015,
        settlement_days: int = 3,
    ) -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.settlement_days = settlement_days
        self._open: dict[str, Position] = {}
        self._closed: list[Position] = []

    # ------------------------------------------------------------------
    #  Open / Close
    # ------------------------------------------------------------------

    def open_position(self, action: Action, timestamp: datetime) -> Position:
        """
        Mở vị thế mới từ ``Action``.

        Trừ tiền = (giá × số lượng) + phí.

        Raises:
            ValueError: Không đủ tiền.
            AssertionError: ``action.price`` chưa được resolve.
        """
        assert action.price is not None, "Price phải được resolve trước khi mở lệnh"

        cost = action.price * action.quantity
        commission = cost * self.commission_rate
        total_cost = cost + commission

        if total_cost > self.cash:
            raise ValueError(
                f"Không đủ tiền: cần {total_cost:,.0f}, có {self.cash:,.0f}"
            )

        pos = Position(
            id=uuid.uuid4().hex[:8],
            symbol=action.symbol,
            entry_price=action.price,
            quantity=action.quantity,
            entry_time=timestamp,
            stop_loss=action.stop_loss,
            take_profit=action.take_profit,
            entry_action=action,
        )
        self._open[pos.id] = pos
        self.cash -= total_cost
        return pos

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_time: datetime,
        reason: CloseReason,
        exit_action: Optional[Action] = None,
    ) -> Position:
        """
        Đóng vị thế. Cộng tiền = (giá bán × số lượng) − phí.

        Tuân thủ luật T+N: vị thế phải đủ ``settlement_days`` ngày giao
        dịch kể từ ngày mua mới được bán (trừ ``END_OF_DATA``).

        Raises:
            KeyError: ``position_id`` không tồn tại hoặc đã đóng.
            ValueError: Chưa đủ T+N ngày giao dịch.
        """
        if position_id not in self._open:
            raise KeyError(f"Position '{position_id}' không tồn tại hoặc đã đóng")

        # Luật T+N: chỉ bỏ qua khi engine đóng cuối kỳ (END_OF_DATA)
        pos = self._open[position_id]
        if reason != CloseReason.END_OF_DATA:
            if not pos.can_sell(exit_time, self.settlement_days):
                held = _business_days_between(pos.entry_time.date(), exit_time.date())
                raise ValueError(
                    f"T+{self.settlement_days}: '{pos.symbol}' mua ngày "
                    f"{pos.entry_time.date()}, mới T+{held}, "
                    f"chưa đủ {self.settlement_days} ngày giao dịch để bán."
                )

        pos = self._open.pop(position_id)  # noqa: used `pos` above for T+N check
        pos.exit_price = exit_price
        pos.exit_time = exit_time
        pos.close_reason = reason
        pos.exit_action = exit_action

        proceeds = exit_price * pos.quantity
        commission = proceeds * self.commission_rate
        self.cash += proceeds - commission

        self._closed.append(pos)
        return pos

    # ------------------------------------------------------------------
    #  Auto SL / TP
    # ------------------------------------------------------------------

    def check_sl_tp(
        self,
        symbol: str,
        high: float,
        low: float,
        timestamp: datetime,
    ) -> list[Position]:
        """
        Kiểm tra Stop Loss / Take Profit cho tất cả vị thế mở của symbol.

        SL ưu tiên trước TP nếu cả hai trigger trong cùng bar
        (giả định bi quan – conservative).

        Luật T+N: chỉ trigger SL/TP khi vị thế đã đủ ngày settlement.
        """
        closed: list[Position] = []

        for pos in list(self._open.values()):
            if pos.symbol != symbol:
                continue

            # T+N: chưa đủ ngày → bỏ qua (chưa được phép bán)
            if not pos.can_sell(timestamp, self.settlement_days):
                continue

            if pos.stop_loss is not None and low <= pos.stop_loss:
                closed.append(
                    self.close_position(
                        pos.id, pos.stop_loss, timestamp, CloseReason.STOP_LOSS
                    )
                )
            elif pos.take_profit is not None and high >= pos.take_profit:
                closed.append(
                    self.close_position(
                        pos.id, pos.take_profit, timestamp, CloseReason.TAKE_PROFIT
                    )
                )

        return closed

    # ------------------------------------------------------------------
    #  Query helpers
    # ------------------------------------------------------------------

    @property
    def open_positions(self) -> list[Position]:
        """Tất cả vị thế đang mở."""
        return list(self._open.values())

    @property
    def closed_positions(self) -> list[Position]:
        """Tất cả vị thế đã đóng."""
        return list(self._closed)

    def equity(self, current_prices: dict[str, float]) -> float:
        """Tổng tài sản = tiền mặt + giá trị thị trường vị thế mở."""
        market_val = sum(
            pos.market_value(current_prices.get(pos.symbol, pos.entry_price))
            for pos in self._open.values()
        )
        return self.cash + market_val

    def positions_for(self, symbol: str) -> list[Position]:
        """Các vị thế đang mở của một symbol."""
        return [p for p in self._open.values() if p.symbol == symbol]

    def sellable_positions(self, symbol: str, current_time: datetime) -> list[Position]:
        """Các vị thế đang mở của *symbol* đã qua T+N, có thể bán."""
        return [
            p
            for p in self._open.values()
            if p.symbol == symbol and p.can_sell(current_time, self.settlement_days)
        ]

    def has_position(self, symbol: str) -> bool:
        """Có đang giữ ít nhất 1 vị thế của symbol không."""
        return any(p.symbol == symbol for p in self._open.values())

    def has_sellable_position(self, symbol: str, current_time: datetime) -> bool:
        """Có vị thế nào của symbol đã qua T+N không."""
        return any(
            p.symbol == symbol and p.can_sell(current_time, self.settlement_days)
            for p in self._open.values()
        )
