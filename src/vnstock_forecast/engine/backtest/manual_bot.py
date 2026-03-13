"""
ManualBot – bot đặt lệnh thủ công qua terminal.

Mỗi bar engine gọi ``on_step()``, bot sẽ in thông tin thị trường rồi
hỏi người dùng nhập lệnh cho từng symbol.

Usage::

    from vnstock_forecast.backtest import BacktestEngine
    from vnstock_forecast.backtest.manual_bot import ManualBot

    engine = BacktestEngine(initial_cash=100_000_000)
    report = engine.run(
        bot=ManualBot(),
        data={"VNM": df_vnm, "VHM": df_vhm},
        start="2024-01-01",
        end="2024-03-31",
    )
    report.print_summary()
"""

from __future__ import annotations

from typing import Optional

from .bot_base import Action, ActionType, BotBase
from .context import StepContext

_SEP = "─" * 60
_DSEP = "═" * 60


# ======================================================================
#  Helpers nhập liệu
# ======================================================================


def _ask(prompt: str, default: str = "") -> str:
    """Nhập chuỗi, cho phép dùng Enter chọn giá trị mặc định."""
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise KeyboardInterrupt("Người dùng dừng bot.")
    return val if val else default


def _ask_float(prompt: str, default: Optional[float] = None) -> Optional[float]:
    """Nhập số thực, trả ``None`` nếu bỏ trống và không có default."""
    default_str = str(default) if default is not None else ""
    raw = _ask(prompt, default_str)
    if raw == "":
        return None
    try:
        return float(raw.replace(",", "").replace("_", ""))
    except ValueError:
        print(f"  ⚠  Giá trị không hợp lệ: '{raw}'. Bỏ qua.")
        return None


def _ask_int(prompt: str, default: Optional[int] = None) -> Optional[int]:
    """Nhập số nguyên."""
    default_str = str(default) if default is not None else ""
    raw = _ask(prompt, default_str)
    if raw == "":
        return None
    try:
        return int(raw.replace(",", "").replace("_", ""))
    except ValueError:
        print(f"  ⚠  Giá trị không hợp lệ: '{raw}'. Bỏ qua.")
        return None


# ======================================================================
#  Hiển thị thông tin
# ======================================================================


def _print_bar_header(ctx: StepContext, symbol: str) -> None:
    bar = ctx.latest(symbol)
    price = ctx.price(symbol)
    print()
    print(_SEP)
    print(f"  📅  {ctx.timestamp.strftime('%Y-%m-%d %H:%M')}  |  {symbol}")
    print(_SEP)
    print(
        f"  Open={bar['Open']:,.0f}  High={bar['High']:,.0f}  "
        f"Low={bar['Low']:,.0f}  Close={price:,.0f}  Vol={int(bar['Volume']):,}"
    )
    print(f"  Tiền mặt: {ctx.cash:,.0f} đ  |  Tổng tài sản: {ctx.equity:,.0f} đ")


def _print_positions(ctx: StepContext, symbol: str) -> None:
    positions = ctx.positions_for(symbol)
    sellable = {p.id for p in ctx.sellable_positions(symbol)}

    if not positions:
        print(f"  Vị thế {symbol}: (trống)")
        return

    print(f"  Vị thế {symbol}:")
    for p in positions:
        tag = "✓ có thể bán" if p.id in sellable else "⏳ T+N chưa đến"
        sl_str = f"  SL={p.stop_loss:,.0f}" if p.stop_loss else ""
        tp_str = f"  TP={p.take_profit:,.0f}" if p.take_profit else ""
        pnl = (ctx.price(symbol) - p.entry_price) * p.quantity
        print(
            f"    [{p.id[:8]}]  qty={p.quantity:,.0f}  "
            f"entry={p.entry_price:,.0f}{sl_str}{tp_str}  "
            f"PnL≈{pnl:+,.0f} đ  {tag}"
        )


# ======================================================================
#  ManualBot
# ======================================================================


class ManualBot(BotBase):
    """
    Bot đặt lệnh thủ công qua terminal.

    Mỗi bar, với từng symbol trong danh sách theo dõi, bot sẽ:

    1. In thông tin bar hiện tại (OHLCV, tiền mặt, vị thế đang giữ).
    2. Hỏi quyết định: **buy / sell / ignore**.
    3. Với **buy**: hỏi quantity, stop_loss, take_profit.
    4. Với **sell**: liệt kê vị thế có thể bán, hỏi chọn (id/all).

    Args:
        symbols:          Danh sách symbol cần hỏi mỗi bar.
                          ``None`` = dùng tất cả symbols trong data.
        default_sl_pct:   Stop loss mặc định tính theo % giá Close
                          (vd: 0.07 = 7%). Dùng làm gợi ý khi hỏi.
        default_tp_pct:   Take profit mặc định (vd: 0.15 = 15%).
        allocation:       Phần trăm tiền mặt gợi ý cho mỗi lệnh mua.
        skip_no_signal:   ``True`` → chỉ hỏi khi *có tín hiệu* từ
                          ``signal_fn``. ``False`` → hỏi mỗi bar.
        signal_fn:        Hàm ``(ctx, symbol) -> bool`` – trả ``True``
                          khi cần hỏi người dùng. Mặc định hỏi mỗi bar.

    Example::

        # Hỏi mỗi bar cho mọi symbol
        bot = ManualBot()

        # Chỉ hỏi khi RSI < 30 hoặc > 70
        def rsi_signal(ctx, sym):
            df = ctx.history(sym, lookback=15)
            delta = df["Close"].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = -delta.clip(upper=0).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - 100 / (1 + rs)
            val = rsi.iloc[-1]
            return val < 30 or val > 70

        bot = ManualBot(signal_fn=rsi_signal)
    """

    name = "ManualBot"
    description = "Bot đặt lệnh thủ công – hỏi người dùng mỗi khi cần ra tín hiệu"

    def __init__(
        self,
        symbols: Optional[list[str]] = None,
        default_sl_pct: float = 0.07,
        default_tp_pct: float = 0.10,
        allocation: float = 0.9,
        skip_no_signal: bool = False,
        signal_fn=None,
    ) -> None:
        self._watch_symbols = symbols
        self.default_sl_pct = default_sl_pct
        self.default_tp_pct = default_tp_pct
        self.allocation = allocation
        self.skip_no_signal = skip_no_signal
        self._signal_fn = signal_fn  # callable(ctx, symbol) -> bool

    # ------------------------------------------------------------------
    #  on_start – giới thiệu một lần
    # ------------------------------------------------------------------

    def on_start(self, ctx: StepContext) -> None:
        print()
        print(_DSEP)
        print("  ManualBot – đặt lệnh thủ công")
        print(_DSEP)
        print(f"  Symbols  : {', '.join(ctx.symbols)}")
        print(f"  Vốn ban đầu: {ctx.cash:,.0f} đ")
        print(
            f"  SL mặc định: {self.default_sl_pct:.1%}  |  TP mặc định: {self.default_tp_pct:.1%}"  # noqa E501
        )
        print()
        print("  Mỗi bar bạn sẽ được hỏi: buy / sell / ignore")
        print("  Nhấn Enter để chọn giá trị mặc định (trong []).")
        print("  Ctrl+C để dừng và kết thúc backtest sớm.")
        print(_DSEP)

    # ------------------------------------------------------------------
    #  on_step – hỏi người dùng mỗi bar
    # ------------------------------------------------------------------

    def on_step(self, ctx: StepContext) -> list[Action]:
        symbols = self._watch_symbols or ctx.symbols
        actions: list[Action] = []

        for symbol in symbols:
            if symbol not in ctx.symbols:
                continue

            # Kiểm tra tín hiệu (nếu skip_no_signal=True)
            if self.skip_no_signal and self._signal_fn is not None:
                try:
                    has_signal = self._signal_fn(ctx, symbol)
                except Exception:
                    has_signal = True
                if not has_signal:
                    continue

            try:
                action = self._prompt_symbol(ctx, symbol)
            except KeyboardInterrupt:
                # Người dùng nhấn Ctrl+C → dừng bot
                print("\n  [ManualBot] Dừng theo yêu cầu.")
                return actions

            if action is not None:
                actions.append(action)

        return actions

    # ------------------------------------------------------------------
    #  on_end – tóm tắt
    # ------------------------------------------------------------------

    def on_end(self, ctx: StepContext) -> None:
        print()
        print(_DSEP)
        print("  ManualBot kết thúc.")
        print(f"  Equity cuối: {ctx.equity:,.0f} đ  |  Cash: {ctx.cash:,.0f} đ")
        open_pos = ctx.positions
        if open_pos:
            print(f"  Vị thế còn mở ({len(open_pos)}):")
            for p in open_pos:
                print(
                    f"    {p.symbol}  qty={p.quantity:,.0f}  entry={p.entry_price:,.0f}"
                )
        print(_DSEP)

    # ------------------------------------------------------------------
    #  Internal: hỏi lệnh cho 1 symbol
    # ------------------------------------------------------------------

    def _prompt_symbol(self, ctx: StepContext, symbol: str) -> Optional[Action]:
        """Hỏi người dùng và trả về Action (hoặc None nếu ignore)."""
        _print_bar_header(ctx, symbol)
        _print_positions(ctx, symbol)

        # Xác định lựa chọn hợp lệ
        has_open = ctx.has_position(symbol)
        has_sellable = ctx.has_sellable_position(symbol)

        options = "buy"
        if has_sellable:
            options += "/sell"
        options += "/ignore"

        while True:
            choice = _ask(f"Lệnh ({options})", "ignore").lower()
            if choice in {"b", "buy"}:
                return self._prompt_buy(ctx, symbol)
            elif choice in {"s", "sell"}:
                if not has_open:
                    print("  ⚠  Không có vị thế nào đang mở. Chọn ignore hoặc buy.")
                    continue
                if not has_sellable:
                    print("  ⚠  Chưa đến T+N – không thể bán. Chọn ignore hoặc buy.")
                    continue
                return self._prompt_sell(ctx, symbol)
            elif choice in {"i", "ignore", ""}:
                print("  → Bỏ qua.")
                return None
            else:
                print(f"  ⚠  Không hiểu '{choice}'. Gõ buy, sell hoặc ignore.")

    # ------------------------------------------------------------------

    def _prompt_buy(self, ctx: StepContext, symbol: str) -> Optional[Action]:
        price = ctx.price(symbol)

        # Gợi ý số lượng dựa trên allocation
        suggested_qty = max(1, int(ctx.cash * self.allocation // price))
        qty = _ask_int("Số lượng cổ phiếu (qty)", suggested_qty)
        if not qty or qty <= 0:
            print("  → Hủy lệnh mua.")
            return None

        # SL
        default_sl = round(price * (1 - self.default_sl_pct), 0)
        sl = _ask_float(
            f"Stop loss (giá, Enter=bỏ qua), default={default_sl:,.0f}", default_sl
        )

        # TP
        default_tp = round(price * (1 + self.default_tp_pct), 0)
        tp = _ask_float(
            f"Take profit (giá, Enter=bỏ qua), default={default_tp:,.0f}", default_tp
        )

        print(
            f"  ✅  MUA {qty:,} {symbol} @ {price:,.0f}"
            + (f"  SL={sl:,.0f}" if sl else "")
            + (f"  TP={tp:,.0f}" if tp else "")
        )
        return Action(
            type=ActionType.BUY,
            symbol=symbol,
            quantity=qty,
            stop_loss=sl,
            take_profit=tp,
            reason="Manual buy",
        )

    # ------------------------------------------------------------------

    def _prompt_sell(self, ctx: StepContext, symbol: str) -> Optional[Action]:
        sellable = ctx.sellable_positions(symbol)

        if not sellable:
            print("  ⚠  Không có vị thế nào có thể bán.")
            return None

        # In danh sách ID rút gọn để chọn
        print("  Vị thế có thể bán:")
        for i, p in enumerate(sellable, 1):
            print(
                f"    {i}. [{p.id[:8]}]  qty={p.quantity:,.0f}  "
                f"entry={p.entry_price:,.0f}"
            )

        if len(sellable) > 1:
            choice = _ask("Chọn vị thế (số thứ tự / 'all' / id prefix)", "all").lower()
        else:
            choice = _ask("Bán vị thế này? (all/1/id prefix)", "all").lower()

        price = ctx.price(symbol)

        # Chọn all
        if choice in {"all", "a", ""}:
            print(f"  ✅  BÁN TẤT CẢ {symbol} @ {price:,.0f}")
            return Action(
                type=ActionType.SELL,
                symbol=symbol,
                quantity=0,
                reason="Manual sell all",
            )

        # Chọn theo số thứ tự
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(sellable):
                pos = sellable[idx]
                return self._confirm_partial_sell(symbol, pos, price)
            else:
                print("  ⚠  Số thứ tự không hợp lệ. Bỏ qua.")
                return None

        # Chọn theo id prefix
        matched = [p for p in sellable if p.id.startswith(choice)]
        if len(matched) == 1:
            pos = matched[0]
            return self._confirm_partial_sell(symbol, pos, price)
        elif len(matched) > 1:
            print(f"  ⚠  Có {len(matched)} vị thế khớp với '{choice}'. Bỏ qua.")
            return None
        else:
            print(f"  ⚠  Không tìm thấy vị thế '{choice}'. Bỏ qua.")
            return None

    # ------------------------------------------------------------------

    def _confirm_partial_sell(
        self, symbol: str, pos, price: float
    ) -> "Optional[Action]":
        """Hỏi số lượng cụ thể muốn bán cho 1 vị thế."""
        qty = _ask_int(
            f"Số lượng bán (tối đa {pos.quantity:,.0f}, Enter=bán tất)",
            default=int(pos.quantity),
        )
        if qty is None or qty <= 0:
            print("  → Hủy lệnh bán.")
            return None
        if qty > pos.quantity:
            print(
                f"  ⚠  Số lượng ({qty:,}) vượt quá vị thế ({pos.quantity:,.0f}). Bỏ qua."  # noqa E501
            )
            return None
        partial = qty < pos.quantity
        label = (
            f"BÁN {qty:,}/{pos.quantity:,.0f}"
            if partial
            else f"BÁN [{pos.id[:8]}]  qty={pos.quantity:,.0f}"
        )
        print(f"  ✅  {label} {symbol} @ {price:,.0f}")
        return Action(
            type=ActionType.SELL,
            symbol=symbol,
            quantity=qty,
            position_id=pos.id,
            reason="Manual sell" + (" (partial)" if partial else ""),
        )
