"""Generate resistance levels based on historical price data."""

from __future__ import annotations

import pandas as pd


def compute_resistance_levels(
    closes: pd.Series,
    volumes: pd.Series,
    window: int = 20,
    num_levels: int = 3,
) -> list[tuple[float, int]]:
    """
    Compute resistance levels based on local maxima in the closing price.

    Args:
        closes: Chuỗi giá đóng cửa.
        volumes: Chuỗi khối lượng giao dịch.
        num_levels: Số lượng mức kháng cự cần trả về (mặc định 3).

    Returns:
        Danh sách các mức kháng cự dưới dạng tuple (giá, khối lượng).
    """
    # Tìm local maxima trong chuỗi giá đóng cửa
    local_max = (closes.shift(1) < closes) & (closes.shift(-1) < closes)
    resistance_points = closes[local_max]

    # Lấy khối lượng tương ứng với các điểm kháng cự
    resistance_volumes = volumes[local_max]

    # Kết hợp giá và khối lượng, sau đó sắp xếp theo giá giảm dần
    resistance_levels = list(zip(resistance_points, resistance_volumes))
    resistance_levels.sort(key=lambda x: x[0], reverse=True)

    # Trả về num_levels mức kháng cự cao nhất
    return resistance_levels[:num_levels]


def compute_support_levels(
    closes: pd.Series,
    volumes: pd.Series,
    window: int = 20,
    num_levels: int = 3,
) -> list[tuple[float, int]]:
    """
    Tính các mức hỗ trợ dựa trên local minima trong chuỗi giá đóng cửa.

    Args:
        closes:     Chuỗi giá đóng cửa.
        volumes:    Chuỗi khối lượng giao dịch.
        window:     Số nến lịch sử xét (mặc định 20).
        num_levels: Số mức hỗ trợ cần trả về (mặc định 3).

    Returns:
        Danh sách ``(giá, khối_lượng)`` sắp xếp theo giá **tăng dần**
        (mức hỗ trợ cao nhất ở đầu danh sách).
    """
    local_min = (closes.shift(1) > closes) & (closes.shift(-1) > closes)
    support_points = closes[local_min]
    support_volumes = volumes[local_min]

    support_levels = list(zip(support_points, support_volumes))
    # Sắp xếp giảm dần (gần giá nhất → đầu danh sách)
    support_levels.sort(key=lambda x: x[0], reverse=True)

    return support_levels[:num_levels]
