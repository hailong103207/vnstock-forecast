"""Breakout Resistance – xác nhận khi giá phá vỡ mức kháng cự gần nhất."""

from __future__ import annotations

import pandas as pd

from ..indicators.resistance import compute_resistance_levels
from .base import MAX_BOOST_PER_CONFIRMATION, ConfirmationResult


def check_breakout_resistance(
    df: pd.DataFrame,
    current_price: float,
    *,
    lookback: int = 60,
    num_levels: int = 3,
    tolerance: float = 0.005,
) -> ConfirmationResult:
    """
    Xác nhận tín hiệu khi giá phá vỡ mức kháng cự gần nhất.

    Tìm mức kháng cự gần nhất **phía trên** hoặc **ngang bằng** giá hiện tại
    (trong khoảng ``tolerance``). Nếu giá hiện tại vừa vượt qua mức đó,
    xác nhận breakout.

    Args:
        df:            DataFrame OHLCV dùng để tính resistance.
        current_price: Giá hiện tại (thường là ``Close`` của bar cuối).
        lookback:      Số nến lịch sử dùng để tính resistance (mặc định 60).
        num_levels:    Số mức kháng cự tính toán (mặc định 3).
        tolerance:     Ngưỡng % để coi giá "vừa phá qua" mức kháng cự
                       (mặc định 0.5%). Ví dụ: resistance=100, tolerance=0.005
                       thì giá trong [99.5, 100.5] coi là breakout zone.

    Returns:
        :class:`ConfirmationResult` với ``confirmed=True`` nếu phát hiện
        breakout. Boost luôn bằng ``MAX_BOOST_PER_CONFIRMATION`` vì breakout
        là xác nhận mạnh.
    """
    window = min(lookback, len(df))
    if window < 5:
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason="Không đủ dữ liệu để tính kháng cự",
        )

    sub_df = df.iloc[-window:]
    levels = compute_resistance_levels(
        sub_df["Close"],
        sub_df["Volume"],
        window=window,
        num_levels=num_levels,
    )

    if not levels:
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason="Không tìm thấy mức kháng cự",
        )

    # Tìm mức kháng cự gần nhất phía trên hoặc vừa bị phá
    # (resistance <= current_price * (1 + tolerance))
    upper_bound = current_price * (1 + tolerance)
    candidates = [(lvl, vol) for lvl, vol in levels if lvl <= upper_bound]

    if not candidates:
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason="Giá chưa chạm / phá kháng cự",
        )

    # Lấy mức kháng cự gần nhất (cao nhất trong candidates)
    nearest_resistance, _ = max(candidates, key=lambda x: x[0])

    if current_price < nearest_resistance:
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason=f"Giá ({current_price:.0f}) chưa vượt kháng cự ({nearest_resistance:.0f})",  # noqa E501
        )

    return ConfirmationResult(
        confirmed=True,
        boost=MAX_BOOST_PER_CONFIRMATION,
        reason=(
            f"Breakout kháng cự {nearest_resistance:.0f} "
            f"(giá hiện tại {current_price:.0f}, boost={MAX_BOOST_PER_CONFIRMATION})"
        ),
    )
