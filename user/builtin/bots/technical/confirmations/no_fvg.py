"""No Large Fair Value Gap – xác nhận khi không có FVG lớn gần điểm entry."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .base import MAX_BOOST_PER_CONFIRMATION, ConfirmationResult


@dataclass
class FVGZone:
    """
    Một vùng Fair Value Gap (FVG).

    Attributes:
        kind:      ``"bullish"`` (gap lên) hoặc ``"bearish"`` (gap xuống).
        top:       Cạnh trên của vùng FVG.
        bottom:    Cạnh dưới của vùng FVG.
        bar_index: Index thanh nến thứ 3 trong mẫu 3 nến tạo ra FVG.
    """

    kind: str
    top: float
    bottom: float
    bar_index: int

    @property
    def size(self) -> float:
        """Khoảng rộng tuyệt đối của FVG."""
        return self.top - self.bottom

    def distance_to(self, price: float) -> float:
        """
        Khoảng cách từ ``price`` đến vùng FVG.

        Trả về ``0.0`` nếu giá nằm trong FVG.
        """
        if self.bottom <= price <= self.top:
            return 0.0
        return min(abs(price - self.top), abs(price - self.bottom))


def detect_fvg_zones(
    df: pd.DataFrame,
    *,
    lookback: int = 50,
) -> list[FVGZone]:
    """
    Phát hiện tất cả Fair Value Gap trong ``lookback`` nến gần nhất.

    **Bullish FVG** (gap lên): High[i-2] < Low[i]
    – vùng giá [High[i-2], Low[i]] bị bỏ qua khi giá tăng vọt.

    **Bearish FVG** (gap xuống): Low[i-2] > High[i]
    – vùng giá [High[i], Low[i-2]] bị bỏ qua khi giá giảm mạnh.

    Chỉ quét từ ``iloc[-(lookback+2)]`` đến ``iloc[-2]``
    (không dùng nến cuối hiện tại để tránh look-ahead).

    Args:
        df:       DataFrame OHLCV với cột ``High``, ``Low``.
        lookback: Số nến lịch sử cần quét (mặc định 50).

    Returns:
        Danh sách :class:`FVGZone` tìm được.
    """
    if "High" not in df.columns or "Low" not in df.columns:
        return []

    # Cắt cửa sổ: không dùng nến hiện tại (iloc[-1])
    window = df.iloc[-(lookback + 2) : -1] if len(df) >= lookback + 3 else df.iloc[:-1]
    if len(window) < 3:
        return []

    highs = window["High"].values
    lows = window["Low"].values
    zones: list[FVGZone] = []

    for i in range(2, len(highs)):
        # Bullish FVG: nến i-2 đỉnh < nến i đáy
        if highs[i - 2] < lows[i]:
            zones.append(
                FVGZone(
                    kind="bullish",
                    top=lows[i],
                    bottom=highs[i - 2],
                    bar_index=i,
                )
            )
        # Bearish FVG: nến i-2 đáy > nến i đỉnh
        elif lows[i - 2] > highs[i]:
            zones.append(
                FVGZone(
                    kind="bearish",
                    top=lows[i - 2],
                    bottom=highs[i],
                    bar_index=i,
                )
            )

    return zones


def check_no_large_fvg(
    df: pd.DataFrame,
    current_price: float,
    *,
    fvg_threshold: float = 0.01,
    proximity_pct: float = 0.02,
    lookback: int = 50,
) -> ConfirmationResult:
    """
    Xác nhận entry khi **không** có FVG lớn gần điểm vào lệnh.

    Nếu tồn tại một Fair Value Gap có kích thước >= ``fvg_threshold``
    (tính theo % giá) và nằm trong phạm vi ``proximity_pct`` tính từ
    ``current_price``, tín hiệu **không** được xác nhận (risky entry).

    Ngược lại, entry sạch → ``confirmed=True``, boost = ``MAX_BOOST_PER_CONFIRMATION``.

    Args:
        df:              DataFrame OHLCV.
        current_price:   Giá hiện tại (thường là Close bar cuối).
        fvg_threshold:   Ngưỡng kích thước FVG để coi là "lớn",
                         tính theo tỷ lệ với giá (mặc định 1%).
        proximity_pct:   Khoảng cách tối đa từ giá đến FVG để coi là "gần"
                         (mặc định 2%).
        lookback:        Số nến lịch sử quét FVG (mặc định 50).

    Returns:
        :class:`ConfirmationResult`:
        - ``confirmed=True``  → không có FVG lớn gần entry → cộng boost.
        - ``confirmed=False`` → phát hiện FVG lớn gần entry → không cộng.
    """
    if current_price <= 0:
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason="Giá không hợp lệ",
        )

    zones = detect_fvg_zones(df, lookback=lookback)
    if not zones:
        # Không tìm thấy FVG nào → entry sạch
        return ConfirmationResult(
            confirmed=True,
            boost=MAX_BOOST_PER_CONFIRMATION,
            reason=f"Không có FVG trong {lookback} nến gần nhất (boost={MAX_BOOST_PER_CONFIRMATION})",  # noqa E501
        )

    size_threshold = fvg_threshold * current_price
    prox_threshold = proximity_pct * current_price

    blocking: list[FVGZone] = []
    for zone in zones:
        if (
            zone.size >= size_threshold
            and zone.distance_to(current_price) <= prox_threshold
        ):
            blocking.append(zone)

    if blocking:
        # Lấy FVG gần nhất để báo cáo
        nearest = min(blocking, key=lambda z: z.distance_to(current_price))
        dist_pct = nearest.distance_to(current_price) / current_price * 100
        return ConfirmationResult(
            confirmed=False,
            boost=0.0,
            reason=(
                f"FVG {nearest.kind} lớn gần entry: "
                f"vùng [{nearest.bottom:.0f}, {nearest.top:.0f}] "
                f"(size={nearest.size / current_price * 100:.2f}%, "
                f"cách giá {dist_pct:.2f}%)"
            ),
        )

    return ConfirmationResult(
        confirmed=True,
        boost=MAX_BOOST_PER_CONFIRMATION,
        reason=(
            f"Không có FVG lớn (>={fvg_threshold * 100:.1f}%) "
            f"trong phạm vi {proximity_pct * 100:.1f}% quanh entry "
            f"(boost={MAX_BOOST_PER_CONFIRMATION})"
        ),
    )
