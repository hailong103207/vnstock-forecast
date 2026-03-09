"""
Profiler – chạy backtest hàng loạt cho mọi technique đã đăng ký,
tính toán SignalProfile, lưu ra local.

Usage::

    from vnstock_forecast.analysis.profiler import Profiler

    profiler = Profiler()
    profiles = profiler.run(
        data={"VNM": df_vnm, "VHM": df_vhm},
        start="2023-01-01",
        end="2024-12-31",
    )

    # In kết quả
    for name, profile in profiles.items():
        profile.print_summary()

    # Lưu xuống local
    profiler.save()

    # Hoặc profile technique cụ thể
    from vnstock_forecast.analysis.techniques import RSICrossover
    profiler.run_single(
        technique=RSICrossover(period=14),
        data={"VNM": df_vnm},
    )
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from vnstock_forecast.backtest.bot_base import Action, ActionType  # noqa: F401
from vnstock_forecast.backtest.context import StepContext  # noqa: F401
from vnstock_forecast.backtest.engine import BacktestEngine
from vnstock_forecast.backtest.portfolio import CloseReason
from vnstock_forecast.backtest.report import BacktestReport
from vnstock_forecast.shared.path import ROOT_PATH_STR

from .base import BaseTechnique
from .bot import AnalysisBot
from .profile import DirectionStats, SignalProfile
from .registry import get_all_techniques
from .signal import Signal, SignalDirection

logger = logging.getLogger(__name__)

# Thư mục lưu profile mặc định
DEFAULT_PROFILE_DIR = Path(ROOT_PATH_STR) / "profile"


class Profiler:
    """
    Chạy backtest cho từng technique đã đăng ký, tính toán SignalProfile.

    Quy trình cho mỗi technique:

    1. Tạo ``AnalysisBot`` wrapper chỉ chứa 1 technique.
    2. Chạy ``BacktestEngine.run()`` để backtest.
    3. Phân tích signal_history của bot + kết quả backtest.
    4. Tính ``DirectionStats`` cho BUY và SELL.
    5. Tạo ``SignalProfile`` và lưu vào dict.

    Attributes:
        profiles:     Dict kết quả: ``{technique_name: SignalProfile}``.
        profile_dir:  Thư mục lưu JSON profile.
    """

    def __init__(
        self,
        profile_dir: str | Path = DEFAULT_PROFILE_DIR,
        initial_cash: float = 100_000_000.0,
        commission_rate: float = 0.0015,
        settlement_days: int = 3,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.settlement_days = settlement_days
        self.profiles: dict[str, SignalProfile] = {}

    # ==================================================================
    #  Public API
    # ==================================================================

    def run(
        self,
        data: dict[str, pd.DataFrame],
        start: Optional[str] = None,
        end: Optional[str] = None,
        techniques: Optional[list[BaseTechnique]] = None,
    ) -> dict[str, SignalProfile]:
        """
        Chạy profiling cho tất cả technique (hoặc danh sách chỉ định).

        Args:
            data:       ``{symbol: DataFrame}`` OHLCV data.
            start:      Ngày bắt đầu backtest.
            end:        Ngày kết thúc backtest.
            techniques: Danh sách technique instances cần profile.
                        ``None`` = lấy tất cả từ registry.

        Returns:
            Dict ``{technique_name: SignalProfile}``.
        """
        if techniques is None:
            registry = get_all_techniques()
            if not registry:
                logger.warning("Registry trống – không có technique nào để profile.")
                return {}
            techniques = [cls() for cls in registry.values()]

        logger.info(
            "Bắt đầu profiling %d technique(s): %s",
            len(techniques),
            [t.name for t in techniques],
        )

        for technique in techniques:
            try:
                profile = self.run_single(technique, data, start, end)
                self.profiles[technique.name] = profile
                logger.info(
                    "✓ %s – win_rate=%.1f%%",
                    technique.name,
                    profile.overall_win_rate * 100,
                )
            except Exception as exc:
                logger.error("✗ %s – lỗi: %s", technique.name, exc)

        return self.profiles

    def run_single(
        self,
        technique: BaseTechnique,
        data: dict[str, pd.DataFrame],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> SignalProfile:
        """
        Chạy profiling cho 1 technique.

        Args:
            technique: Instance của BaseTechnique.
            data:      OHLCV data.
            start:     Ngày bắt đầu.
            end:       Ngày kết thúc.

        Returns:
            ``SignalProfile`` đã tính toán xong.
        """
        # Tạo bot wrapper chỉ chứa 1 technique, allocation cao để
        # đảm bảo đủ tiền thực thi nhiều signals
        bot = AnalysisBot(
            name=f"Profiler_{technique.name}",
            techniques=[technique],
            allocation=0.5,
        )

        # Chạy backtest
        engine = BacktestEngine(
            initial_cash=self.initial_cash,
            commission_rate=self.commission_rate,
            settlement_days=self.settlement_days,
        )
        report = engine.run(bot=bot, data=data, start=start, end=end)

        # Tính profile từ signal_history và backtest report
        profile = self._compute_profile(
            technique=technique,
            bot=bot,
            report=report,
            data=data,
        )

        return profile

    def save(self, directory: Optional[str | Path] = None) -> None:
        """
        Lưu tất cả profile ra JSON files.

        Args:
            directory: Thư mục đích. ``None`` = dùng ``self.profile_dir``.
        """
        save_dir = Path(directory) if directory else self.profile_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        for name, profile in self.profiles.items():
            filepath = save_dir / f"{name}.json"
            profile.save(filepath)

        logger.info("Đã lưu %d profile(s) vào %s", len(self.profiles), save_dir)

    def load(self, directory: Optional[str | Path] = None) -> dict[str, SignalProfile]:
        """
        Đọc tất cả profile từ thư mục.

        Args:
            directory: Thư mục chứa JSON. ``None`` = dùng ``self.profile_dir``.

        Returns:
            Dict ``{technique_name: SignalProfile}``.
        """
        load_dir = Path(directory) if directory else self.profile_dir
        self.profiles = SignalProfile.load_all(load_dir)
        return self.profiles

    # ==================================================================
    #  Internal
    # ==================================================================

    def _compute_profile(
        self,
        technique: BaseTechnique,
        bot: AnalysisBot,
        report: BacktestReport,
        data: dict[str, pd.DataFrame],
    ) -> SignalProfile:
        """Tính toán SignalProfile từ kết quả backtest."""
        signals = bot.signal_history
        summary = report.summary()
        closed = report.portfolio.closed_positions

        # Tính tổng bars
        total_bars = len(report.equity_curve) if report.equity_curve else 0

        # Phân loại signals theo direction
        buy_signals = [s for s in signals if s.is_buy]
        sell_signals = [s for s in signals if s.is_sell]

        # Phân loại closed positions theo entry action reason
        # (mỗi position tương ứng với 1 BUY signal)
        buy_stats = self._compute_direction_stats(
            buy_signals, closed, total_bars, SignalDirection.BUY
        )
        sell_stats = self._compute_direction_stats(
            sell_signals, closed, total_bars, SignalDirection.SELL
        )

        return SignalProfile(
            technique_name=technique.name,
            technique_params=technique.params,
            symbols=report.symbols,
            period=f"{report.start.date()} → {report.end.date()}",
            total_bars=total_bars,
            buy_stats=buy_stats,
            sell_stats=sell_stats,
            backtest_summary=summary,
            created_at=datetime.now().isoformat(),
        )

    @staticmethod
    def _compute_direction_stats(
        signals: list[Signal],
        closed_positions: list,
        total_bars: int,
        direction: SignalDirection,
    ) -> DirectionStats:
        """Tính DirectionStats cho 1 hướng (BUY hoặc SELL)."""
        total = len(signals)
        if total == 0:
            return DirectionStats()

        # Lọc closed positions thực tế (không tính end_of_data)
        real_trades = [
            p for p in closed_positions if p.close_reason != CloseReason.END_OF_DATA
        ]

        if direction == SignalDirection.BUY:
            # BUY signals → tra cứu kết quả qua closed positions
            # Mỗi BUY tạo 1 position → kết quả = position.pnl
            wins = [p for p in real_trades if (p.pnl or 0) > 0]
            losses = [p for p in real_trades if (p.pnl or 0) <= 0]

            win_count = len(wins)
            loss_count = len(losses)
            trade_count = win_count + loss_count

            win_rate = win_count / trade_count if trade_count > 0 else 0.0

            avg_return = (
                sum(p.pnl_percent or 0 for p in real_trades) / trade_count
                if trade_count > 0
                else 0.0
            )
            avg_win = sum(p.pnl_percent or 0 for p in wins) / len(wins) if wins else 0.0
            avg_loss = (
                sum(p.pnl_percent or 0 for p in losses) / len(losses) if losses else 0.0
            )
            rr = abs(avg_win / avg_loss) if avg_loss else 0.0

        else:
            # SELL signals – đánh giá bằng giá sau khi bán có giảm không
            # (Đơn giản: tính từ closed positions do MANUAL close)
            manual_closes = [
                p for p in closed_positions if p.close_reason == CloseReason.MANUAL
            ]
            # SELL thành công nếu giá đóng < giá vào (tức đã bán đúng lúc)
            wins = [p for p in manual_closes if (p.pnl or 0) > 0]
            losses = [p for p in manual_closes if (p.pnl or 0) <= 0]

            win_count = len(wins)
            loss_count = len(losses)
            trade_count = win_count + loss_count

            win_rate = win_count / trade_count if trade_count > 0 else 0.0
            avg_return = avg_win = avg_loss = rr = 0.0

            if wins:
                avg_win = sum(p.pnl_percent or 0 for p in wins) / len(wins)
            if losses:
                avg_loss = sum(p.pnl_percent or 0 for p in losses) / len(losses)
            if trade_count > 0:
                avg_return = (
                    sum(p.pnl_percent or 0 for p in manual_closes) / trade_count
                )
            rr = abs(avg_win / avg_loss) if avg_loss else 0.0

        frequency = total / total_bars if total_bars > 0 else 0.0

        return DirectionStats(
            total_signals=total,
            win_count=win_count,
            loss_count=loss_count,
            win_rate=round(win_rate, 4),
            avg_return_pct=round(avg_return, 4),
            avg_win_pct=round(avg_win, 4),
            avg_loss_pct=round(avg_loss, 4),
            risk_reward=round(rr, 4),
            frequency=round(frequency, 6),
        )
