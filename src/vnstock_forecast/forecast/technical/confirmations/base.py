"""Base types cho confirmation signals."""

from __future__ import annotations

from dataclasses import dataclass

#: Mức boost tối đa mỗi tín hiệu xác nhận được cộng vào confidence.
MAX_BOOST_PER_CONFIRMATION = 0.1


@dataclass
class ConfirmationResult:
    """
    Kết quả của một tín hiệu xác nhận (confirmation).

    Attributes:
        confirmed: Tín hiệu có được xác nhận không.
        boost:     Lượng confidence được cộng thêm. Luôn trong
                    [0, MAX_BOOST_PER_CONFIRMATION].
                   Bằng 0 nếu ``confirmed=False``.
        reason:    Mô tả ngắn gọn lý do xác nhận / không xác nhận.
    """

    confirmed: bool
    boost: float
    reason: str = ""

    def __post_init__(self) -> None:
        # Đảm bảo boost không vượt quá giới hạn và không âm
        self.boost = max(0.0, min(MAX_BOOST_PER_CONFIRMATION, self.boost))
        if not self.confirmed:
            self.boost = 0.0


def apply_confirmations(
    base_confidence: float,
    results: list[ConfirmationResult],
) -> tuple[float, list[str]]:
    """
    Áp dụng danh sách ConfirmationResult lên base_confidence.

    Rule:
    - Mỗi confirmation đã ``confirmed`` cộng thêm ``boost`` của nó.
    - ``boost`` của mỗi confirmation tối đa ``MAX_BOOST_PER_CONFIRMATION``.
    - Kết quả cuối clamp vào [0.0, 1.0].

    Args:
        base_confidence: Confidence khởi đầu từ tín hiệu chính.
        results:         Danh sách kết quả từ các hàm confirmation.

    Returns:
        Tuple ``(final_confidence, reasons)`` trong đó ``reasons`` là
        danh sách mô tả các confirmation đã được tính.
    """
    confidence = base_confidence
    reasons: list[str] = []

    for result in results:
        if result.confirmed:
            confidence += result.boost
            reasons.append(result.reason)

    return max(0.0, min(1.0, confidence)), reasons
