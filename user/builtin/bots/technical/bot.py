"""AnalysisBot – bot tổ hợp nhiều technique, tự động phân tích & ra Action."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from vnstock_forecast.engine.backtest.bot_base import Action, ActionType, BotBase
from vnstock_forecast.engine.backtest.context import StepContext
from vnstock_forecast.forecast.profile import SignalProfile
from vnstock_forecast.forecast.signal import Signal

from .base import BaseTechnique

logger = logging.getLogger(__name__)


class AnalysisBot(BotBase):
    """
    Bot phân tích kỹ thuật – tổ hợp N technique thành 1 bot.

    Mỗi bar (``on_step``), bot sẽ:

    1. Gọi ``analyze_step()`` của từng technique cho từng symbol.
    2. Tổng hợp tất cả Signal thu được.
    3. Lọc Signal qua ``accept_signal()`` (customizable).
    4. Chuyển Signal đã lọc thành ``Action`` (BUY/SELL).

    Có thể tùy chỉnh:

    - ``accept_signal(signal, ctx)`` – override để lọc tín hiệu theo
      confidence, profile, hoặc logic tùy ý. Mặc định chấp nhận tất cả.
    - ``allocation`` – phần trăm vốn dùng cho mỗi lệnh mua (0.0–1.0).
    - ``profiles`` – dict ``{technique_name: SignalProfile}`` nạp từ local.
      Nếu có profile, bot sẽ gắn confidence từ profile vào Signal.

    Ngưỡng confidence được cấu hình trên từng technique (``technique.min_confidence``)
    thay vì trên bot, để mỗi technique trong cùng một bot có thể có ngưỡng riêng.

    Example::

        bot = AnalysisBot(
            name="RSI_MACD_Combo",
            techniques=[RSICrossover(period=14), MACDCrossover()],
            allocation=0.3,
        )

        # Tùy chỉnh logic lọc
        class SmartBot(AnalysisBot):
            def accept_signal(self, signal, ctx):
                # Chỉ chấp nhận BUY khi confidence > 0.6
                if signal.is_buy and signal.confidence < 0.6:
                    return False
                return True
    """

    def __init__(
        self,
        name: str = "AnalysisBot",
        description: str = "Bot tổ hợp techniques",
        techniques: Optional[list[BaseTechnique]] = None,
        allocation: float = 0.1,
        sl_pct: float = 0.07,
        tp_pct: float = 0.10,
        profiles: Optional[dict[str, SignalProfile]] = None,
    ) -> None:
        """
        Args:
            name:        Tên bot.
            description: Mô tả bot.
            techniques:  Danh sách technique instances.
            allocation:  Phần trăm vốn cho mỗi lệnh mua.
            sl_pct:      Stop loss mặc định (%) nếu Signal không có TradePlan.
            tp_pct:      Take profit mặc định (%) nếu Signal không có TradePlan.
            profiles:    Dict profile đã load. ``None`` = không dùng profile.

        Note:
            Ngưỡng confidence được cấu hình trực tiếp trên từng technique
            qua thuộc tính ``min_confidence`` của ``BaseTechnique``, thay vì
            trên bot. Điều này cho phép mỗi technique có ngưỡng riêng khi
            dùng nhiều technique trong cùng một bot.
        """
        self.name = name
        self.description = description
        self.techniques: list[BaseTechnique] = techniques or []
        self.allocation = allocation
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.profiles = profiles or {}

        # Lịch sử signal (ghi lại để profiler phân tích sau)
        self.signal_history: list[Signal] = []

    # ------------------------------------------------------------------
    #  Technique management
    # ------------------------------------------------------------------

    def add_technique(self, technique: BaseTechnique) -> None:
        """Thêm technique vào bot."""
        self.techniques.append(technique)

    def load_profiles(self, directory: str | Path) -> None:
        """
        Nạp tất cả profile từ thư mục.

        Args:
            directory: Thư mục chứa các file ``*.json`` profile.
        """
        self.profiles = SignalProfile.load_all(directory)
        logger.info(
            "Đã nạp %d profiles: %s",
            len(self.profiles),
            list(self.profiles.keys()),
        )

    # ------------------------------------------------------------------
    #  Bot lifecycle (BotBase interface)
    # ------------------------------------------------------------------

    def on_step(self, ctx: StepContext) -> list[Action]:
        """
        Gọi mỗi bar. Pipeline: analyze → filter → convert to Action.

        Returns:
            Danh sách Action (BUY/SELL) cho engine thực thi.
        """
        # 1) Thu thập signals từ tất cả techniques
        all_signals = self._collect_signals(ctx)

        # 2) Gắn confidence từ profile (nếu có)
        all_signals = self._enrich_with_profiles(all_signals)

        # 3) Lọc signals
        accepted = [s for s in all_signals if self.accept_signal(s, ctx)]

        # 4) Chuyển thành Actions (signal_history được ghi bên trong)
        return self._signals_to_actions(accepted, ctx)

    # ------------------------------------------------------------------
    #  Customizable hooks
    # ------------------------------------------------------------------

    def accept_signal(self, signal: Signal, ctx: StepContext) -> bool:
        """
        Quyết định có chấp nhận signal không.

        Override để thêm logic lọc tùy ý (dựa trên confidence, profile,
        trạng thái portfolio, v.v.).

        Mặc định:
        - Chỉ chấp nhận SELL khi đang có vị thế của symbol đó.

        Note:
            Lọc theo ``min_confidence`` đã được thực hiện per-technique
            trong ``_collect_signals`` – không cần kiểm tra lại ở đây.
        """
        if signal.is_sell and not ctx.has_sellable_position(signal.symbol):
            return False

        return True

    # ------------------------------------------------------------------
    #  Internal
    # ------------------------------------------------------------------

    def _collect_signals(self, ctx: StepContext) -> list[Signal]:
        """Gọi analyze_step() cho mọi technique × mọi symbol.

        Sau khi thu thập, lọc ngay các signal có confidence thấp hơn
        ngưỡng ``min_confidence`` của technique tương ứng.
        """
        signals: list[Signal] = []

        for technique in self.techniques:
            for symbol in ctx.symbols:
                try:
                    result = technique.analyze_step(ctx, symbol)
                    # Lọc theo ngưỡng của chính technique phát ra signal
                    result = [
                        s for s in result if s.confidence >= technique.min_confidence
                    ]
                    signals.extend(result)
                except Exception as exc:
                    logger.warning(
                        "[%s] %s.analyze_step(%s) lỗi: %s",
                        ctx.timestamp,
                        technique.name,
                        symbol,
                        exc,
                    )

        return signals

    def _enrich_with_profiles(self, signals: list[Signal]) -> list[Signal]:
        """Gắn confidence từ profile nếu có."""
        if not self.profiles:
            return signals

        for signal in signals:
            profile = self.profiles.get(signal.technique)
            if profile is None:
                continue

            # Lấy win_rate của direction tương ứng làm confidence
            if signal.is_buy and profile.buy_stats.total_signals > 0:
                signal.confidence = profile.buy_stats.win_rate
            elif signal.is_sell and profile.sell_stats.total_signals > 0:
                signal.confidence = profile.sell_stats.win_rate

        return signals

    def _signals_to_actions(
        self, signals: list[Signal], ctx: StepContext
    ) -> list[Action]:
        """Chuyển danh sách Signal đã lọc thành Action.

        Mỗi symbol chỉ được xử lý 1 lần BUY và 1 lần SELL trong cùng bar
        để tránh duplicate actions khi nhiều technique cùng phát signal.
        """
        actions: list[Action] = []
        handled_buy: set[str] = set()
        handled_sell: set[str] = set()

        for signal in signals:
            if signal.is_buy:
                if signal.symbol in handled_buy:
                    continue
                action = self._buy_action(signal, ctx)
                if action is not None:
                    actions.append(action)
                    handled_buy.add(signal.symbol)
                    self.signal_history.append(signal)

            elif signal.is_sell:
                if signal.symbol in handled_sell:
                    continue
                sell_actions = self._sell_actions(signal, ctx)
                if sell_actions:
                    actions.extend(sell_actions)
                    handled_sell.add(signal.symbol)
                    self.signal_history.append(signal)

        return actions

    def _buy_action(self, signal: Signal, ctx: StepContext) -> Optional[Action]:
        """Chuyển BUY signal thành Action."""
        # Không mua nếu đã có vị thế
        if ctx.has_position(signal.symbol):
            return None

        price = ctx.price(signal.symbol)

        # Lấy SL/TP từ TradePlan hoặc mặc định
        if signal.trade_plan:
            sl = signal.trade_plan.stop_loss
            tp = signal.trade_plan.take_profit
        else:
            sl = round(price * (1 - self.sl_pct), 2)
            tp = round(price * (1 + self.tp_pct), 2)

        # Lượng tiền vào lệnh tỷ lệ với confidence:
        # capital_to_use = cash * allocation * confidence
        # confidence cao → vào nhiều hơn, confidence thấp → vào ít hơn.
        effective_allocation = self.allocation * signal.confidence
        qty = int(ctx.cash * effective_allocation // price)
        if qty <= 0:
            return None

        return Action(
            type=ActionType.BUY,
            symbol=signal.symbol,
            quantity=qty,
            stop_loss=sl,
            take_profit=tp,
            reason=f"[{signal.technique}] {signal.reason}",
        )

    def _sell_actions(self, signal: Signal, ctx: StepContext) -> list[Action]:
        """Chuyển SELL signal thành danh sách Action (FIFO, chỉ bán lô đã qua T+N)."""
        sellable = ctx.sellable_positions(signal.symbol)
        if not sellable:
            return []

        # FIFO: sắp xếp theo thời gian mua tăng dần, bán lô cũ nhất trước
        sellable.sort(key=lambda p: p.entry_time)

        return [
            Action(
                type=ActionType.SELL,
                symbol=signal.symbol,
                quantity=pos.quantity,
                position_id=pos.id,
                reason=f"[{signal.technique}] {signal.reason}",
            )
            for pos in sellable
        ]
