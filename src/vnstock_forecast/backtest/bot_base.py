"""Abstract base class cho trading bot & Action model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .context import StepContext


# ======================================================================
#  Action - hành động bot yêu cầu engine thực hiện
# ======================================================================


class ActionType(Enum):
    """Loại hành động giao dịch."""

    BUY = "buy"
    SELL = "sell"


@dataclass
class Action:
    """
    Hành động bot yêu cầu engine thực hiện.

    - BUY:  Mua cổ phiếu.
            price=None → engine tự dùng giá Close hiện tại.
    - SELL: Bán cổ phiếu.
            position_id → bán vị thế cụ thể.
            Không có position_id → bán TẤT CẢ vị thế của symbol đó.

    Examples::

        # Mua 100 cổ VNM, tự đặt SL/TP
        Action(ActionType.BUY, "VNM", 100,
               stop_loss=58_000, take_profit=72_000)

        # Bán tất cả VNM đang giữ
        Action(ActionType.SELL, "VNM", 0)

        # Bán vị thế cụ thể
        Action(ActionType.SELL, "VNM", 0, position_id="abc123")
    """

    type: ActionType
    symbol: str
    quantity: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_id: Optional[str] = None
    reason: str = ""


# ======================================================================
#  BotBase - abstract class cho mọi trading bot
# ======================================================================


class BotBase(ABC):
    """
    Mọi bot kế thừa class này.

    Chỉ cần implement ``on_step()`` – mỗi bar engine gọi hàm này và
    truyền vào ``StepContext`` chứa đầy đủ: sổ lệnh, tiền, dữ liệu
    thị trường.

    Lifecycle::

        on_start(ctx)   ← 1 lần, trước bar đầu tiên (optional)
        on_step(ctx)    ← mỗi bar, trả về list[Action]
        on_end(ctx)     ← 1 lần, sau bar cuối cùng (optional)

    Trong ``on_step``, bot truy cập qua ctx::

        ctx.cash              tiền mặt hiện tại
        ctx.positions         danh sách vị thế đang mở (sổ lệnh)
        ctx.equity            tổng giá trị tài sản
        ctx.timestamp         thời điểm hiện tại
        ctx.symbols           danh sách symbols có dữ liệu
        ctx.price(sym)        giá Close hiện tại
        ctx.history(sym, n)   n bars gần nhất (DataFrame OHLCV)
        ctx.latest(sym)       bar mới nhất (Series)
        ctx.has_position(sym) có đang giữ symbol không
        ctx.positions_for(sym)   vị thế đang mở của symbol

    Interface này tương thích cả backtest lẫn live trading – chỉ cần
    thay engine cung cấp dữ liệu real-time thay vì historical.

    Example::

        class MyBot(BotBase):
            name = "SimpleMA"

            def on_step(self, ctx):
                df = ctx.history("VNM", lookback=20)
                if len(df) < 20:
                    return []

                ma20 = df["Close"].mean()
                price = ctx.price("VNM")

                if price > ma20 and not ctx.has_position("VNM"):
                    qty = int(ctx.cash * 0.9 // price)
                    return [Action(ActionType.BUY, "VNM", qty,
                                   stop_loss=price * 0.93,
                                   take_profit=price * 1.10)]
                return []
    """

    name: str = "Bot name"
    description: str = "Bot description"

    def on_start(self, ctx: StepContext) -> None:
        """Hook – chạy 1 lần trước bar đầu tiên. Dùng để khởi tạo state."""

    @abstractmethod
    def on_step(self, ctx: StepContext) -> list[Action]:
        """
        Gọi mỗi bar/ngày. Trả về danh sách Action (mua/bán).

        Returns:
            Danh sách ``Action``. Trả về ``[]`` nếu không hành động.
        """
        ...

    def on_end(self, ctx: StepContext) -> None:
        """Hook – chạy 1 lần sau bar cuối cùng."""
