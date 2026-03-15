"""Volume Surge – xác nhận tín hiệu khi khối lượng tăng đột biến."""

from __future__ import annotations

import pandas as pd

from .base import MAX_BOOST_PER_CONFIRMATION, ConfirmationResult


def check_volume_surge(
    df: pd.DataFrame,
    *,
    lookback: int = 20,
    surge_threshold: float = 1.5,
) -> ConfirmationResult:
    """
    Xác nhận tín hiệu dựa trên khối lượng giao dịch tăng đột biến.

    So sánh volume nến hiện tại (``iloc[-1]``) với trung bình volume
    của ``lookback`` nến trước đó.

    Công thức boost (tuyến tính từ ``surge_threshold`` đến ``2*surge_threshold``):

    .. math::

        ratio = \\frac{V_{current}}{\\overline{V}_{lookback}}

        boost = \\min\\!\\left(\\frac{ratio - surge\\_threshold}{surge\\_threshold}
                              \\times MAX\\_BOOST,\\ MAX\\_BOOST\\right)

    Args:
        df:               DataFrame OHLCV (phải có cột ``"Volume"``).
        lookback:         Số nến tính trung bình volume (mặc định 20).
        surge_threshold:  Ngưỡng tối thiểu để coi là surge
                          (mặc định 1.5 = volume gấp 1.5 lần trung bình).

    Returns:
        :class:`ConfirmationResult` với ``confirmed=True`` nếu
        ``current_volume >= surge_threshold * avg_volume``.
    """
    if "Volume" not in df.columns or len(df) < lookback + 1:
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason="Không đủ dữ liệu volume",
        )

    volumes = df["Volume"]
    current_vol = float(volumes.iloc[-1])
    avg_vol = float(volumes.iloc[-lookback - 1 : -1].mean())

    if avg_vol == 0:
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason="Trung bình volume = 0",
        )

    ratio = current_vol / avg_vol

    if ratio < surge_threshold:
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason=f"Volume không đột biến (ratio={ratio:.2f} < {surge_threshold})",
        )

    # Boost tuyến tính: đạt MAX_BOOST khi ratio >= 2 * surge_threshold
    raw_boost = (ratio - surge_threshold) / surge_threshold * MAX_BOOST_PER_CONFIRMATION
    boost = min(raw_boost, MAX_BOOST_PER_CONFIRMATION)

    return ConfirmationResult(
        confirmed=True,
        boost=boost,
        reason=f"Volume surge: {ratio:.2f}x trung bình {lookback} nến (boost={boost:.3f})",  # noqa E501
    )
