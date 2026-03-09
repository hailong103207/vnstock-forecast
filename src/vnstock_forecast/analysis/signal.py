"""Signal – cấu trúc tín hiệu thống nhất cho analysis module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SignalDirection(Enum):
    """Hướng tín hiệu phân tích."""

    BUY = "buy"
    SELL = "sell"


@dataclass(slots=True)
class TradePlan:
    """
    Kế hoạch giao dịch đi kèm tín hiệu BUY.

    Attributes:
        entry:       Giá vào lệnh đề xuất.
        stop_loss:   Giá cắt lỗ.
        take_profit: Giá chốt lời.
    """

    entry: float
    stop_loss: float
    take_profit: float

    def risk_percent(self) -> float:
        """Phần trăm rủi ro (khoảng cách entry → SL)."""
        if self.entry == 0:
            return 0.0
        return abs(self.entry - self.stop_loss) / self.entry * 100

    def reward_percent(self) -> float:
        """Phần trăm lợi nhuận kỳ vọng (khoảng cách entry → TP)."""
        if self.entry == 0:
            return 0.0
        return abs(self.take_profit - self.entry) / self.entry * 100

    def rr_ratio(self) -> float:
        """Tỷ lệ reward / risk."""
        risk = abs(self.entry - self.stop_loss)
        if risk == 0:
            return 0.0
        reward = abs(self.take_profit - self.entry)
        return reward / risk


@dataclass(slots=True)
class Signal:
    """
    Tín hiệu phân tích kỹ thuật.

    Mỗi technique trả về ``list[Signal]``. Bot sử dụng danh sách này
    để quyết định hành động (mua / bán).

    Attributes:
        technique:   Tên kỹ thuật phân tích tạo ra tín hiệu.
        symbol:      Mã cổ phiếu / tài sản.
        direction:   BUY hoặc SELL.
        timestamp:   Thời điểm phát hiện tín hiệu.
        trade_plan:  Kế hoạch giao dịch (bắt buộc với BUY).
        confidence:  Độ tin cậy [0.0, 1.0]. Mặc định 0.5.
        reason:      Mô tả lý do tín hiệu.
        tags:        Nhãn tùy chọn (vd: ``{"divergence", "oversold"}``).
        metadata:    Dữ liệu bổ sung tùy ý.
    """

    technique: str
    symbol: str
    direction: SignalDirection
    timestamp: datetime
    trade_plan: Optional[TradePlan] = None
    confidence: float = 0.5
    reason: str = ""
    tags: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate business rules."""
        if self.direction == SignalDirection.BUY and self.trade_plan is None:
            raise ValueError(
                "Tín hiệu BUY bắt buộc phải có TradePlan (entry / SL / TP)."
            )
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_buy(self) -> bool:
        return self.direction == SignalDirection.BUY

    @property
    def is_sell(self) -> bool:
        return self.direction == SignalDirection.SELL
