"""StepContext – ngữ cảnh bot nhận được mỗi bar."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from .portfolio import Portfolio, Position


class StepContext:
    """
    Ngữ cảnh đầy đủ bot nhận được tại mỗi bar / bước thời gian.

    Cung cấp truy cập tới:

    - **Tài khoản**: ``cash``, ``positions``, ``equity``
    - **Thị trường**: ``history()``, ``latest()``, ``price()``
    - **Metadata**: ``timestamp``, ``symbols``

    Đảm bảo **không có future data leak** – ``history()`` chỉ trả dữ
    liệu đến ``timestamp`` hiện tại.

    Interface hoàn toàn giống nhau cho backtest và live trading – chỉ
    khác nguồn dữ liệu phía sau.
    """

    __slots__ = (
        "_timestamp",
        "_portfolio",
        "_data",
        "_current_prices",
        "_symbols",
    )

    def __init__(
        self,
        timestamp: datetime,
        portfolio: Portfolio,
        data: dict[str, pd.DataFrame],
        current_prices: dict[str, float],
        symbols: list[str],
    ) -> None:
        self._timestamp = timestamp
        self._portfolio = portfolio
        self._data = data
        self._current_prices = current_prices
        self._symbols = symbols

    # ------------------------------------------------------------------
    #  Tài khoản
    # ------------------------------------------------------------------

    @property
    def timestamp(self) -> datetime:
        """Thời điểm bar hiện tại."""
        return self._timestamp

    @property
    def cash(self) -> float:
        """Tiền mặt hiện có."""
        return self._portfolio.cash

    @property
    def positions(self) -> list[Position]:
        """Sổ lệnh – tất cả vị thế đang mở."""
        return self._portfolio.open_positions

    @property
    def equity(self) -> float:
        """Tổng giá trị tài sản (tiền mặt + vị thế mở)."""
        return self._portfolio.equity(self._current_prices)

    # ------------------------------------------------------------------
    #  Thị trường
    # ------------------------------------------------------------------

    @property
    def symbols(self) -> list[str]:
        """Danh sách symbols có dữ liệu."""
        return self._symbols

    def price(self, symbol: str) -> float:
        """
        Giá Close hiện tại của *symbol*.

        Raises:
            KeyError: Không có dữ liệu giá tại thời điểm này.
        """
        if symbol not in self._current_prices:
            raise KeyError(f"Không có giá cho '{symbol}' tại {self._timestamp}")
        return self._current_prices[symbol]

    def history(
        self,
        symbol: str,
        lookback: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Lịch sử OHLCV không có future leak.

        Args:
            symbol:   Mã cổ phiếu.
            lookback: Số bars cuối cùng cần lấy. ``None`` = toàn bộ.

        Returns:
            DataFrame với DatetimeIndex, cột Open/High/Low/Close/Volume.

        Raises:
            KeyError: Symbol không có trong data.
        """
        if symbol not in self._data:
            raise KeyError(
                f"Không có dữ liệu cho '{symbol}'. " f"Có: {', '.join(self._symbols)}"
            )

        df = self._data[symbol]
        df = df[df.index <= pd.Timestamp(self._timestamp)]

        if lookback is not None and not df.empty:
            df = df.tail(lookback)

        return df

    def latest(self, symbol: str) -> pd.Series:
        """
        Bar mới nhất (OHLCV) của *symbol* tại hoặc trước thời điểm hiện tại.

        Raises:
            ValueError: Không có dữ liệu nào.
        """
        hist = self.history(symbol, lookback=1)
        if hist.empty:
            raise ValueError(f"Không có dữ liệu cho '{symbol}' tại {self._timestamp}")
        return hist.iloc[-1]

    # ------------------------------------------------------------------
    #  Vị thế helpers
    # ------------------------------------------------------------------

    def positions_for(self, symbol: str) -> list[Position]:
        """Các vị thế đang mở của *symbol*."""
        return self._portfolio.positions_for(symbol)

    def sellable_positions(self, symbol: str) -> list[Position]:
        """Các vị thế đang mở của *symbol* đã qua T+N, có thể bán."""
        return self._portfolio.sellable_positions(symbol, self._timestamp)

    def has_position(self, symbol: str) -> bool:
        """Kiểm tra có đang giữ vị thế của *symbol* không."""
        return self._portfolio.has_position(symbol)

    def has_sellable_position(self, symbol: str) -> bool:
        """Kiểm tra có vị thế nào của *symbol* đã qua T+N không."""
        return self._portfolio.has_sellable_position(symbol, self._timestamp)
