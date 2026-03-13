"""Signal plotter – vẽ biểu đồ nến từ ``SignalSnapshot`` bằng mplfinance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from .snapshot import SignalSnapshot

if TYPE_CHECKING:
    from vnstock_forecast.forecast.signal import Signal

logger = logging.getLogger(__name__)


# ======================================================================
#  Helpers
# ======================================================================


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """Đảm bảo DataFrame có ``DatetimeIndex`` hợp lệ cho mplfinance."""
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index, unit="s")
        except Exception:
            df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    return df


def _ts_to_bar_idx(ohlcv: pd.DataFrame, ts: pd.Timestamp) -> int:
    """Chuyển timestamp thành chỉ số bar gần nhất trong *ohlcv*."""
    diffs = abs(ohlcv.index - ts)
    return int(diffs.argmin())


def _extend_ohlcv(snapshot: SignalSnapshot, extend_bars: int) -> pd.DataFrame:
    """Query thêm *extend_bars* bars OHLCV của *snapshot* kể từ bar cuối cùng.

    Args:
        snapshot:     ``SignalSnapshot`` nguồn.
        extend_bars:  Số bars tối đa muốn lấy thêm (> 0).

    Returns:
        DataFrame OHLCV đã nối thêm dữ liệu (hoặc nguyên bản nếu thất bại).
    """
    from vnstock_forecast.engine.data.query import query_ohlcv

    ohlcv = _ensure_datetime_index(snapshot.ohlcv)

    last_ts = int(ohlcv.index[-1].timestamp())
    extend_ts = (ohlcv.index[1] - ohlcv.index[0]).total_seconds() * (extend_bars - 1)
    try:
        extra = query_ohlcv(
            symbols=snapshot.symbol,
            resolutions=snapshot.resolution,
            from_ts=last_ts,
            to_ts=last_ts + int(extend_ts),
        )
    except Exception as exc:
        logger.warning("Không thể query thêm dữ liệu: %s", exc)
        return ohlcv
    if extra.empty:
        return ohlcv

    ohlcv_cols = [
        c for c in ("Open", "High", "Low", "Close", "Volume") if c in extra.columns
    ]
    extra_df = extra.set_index("Timestamp")[ohlcv_cols].sort_index()
    extra_df = _ensure_datetime_index(extra_df)

    combined = pd.concat([ohlcv[ohlcv_cols], extra_df])
    combined = combined[~combined.index.duplicated(keep="first")]
    return combined.sort_index()


# ======================================================================
#  Public API
# ======================================================================


def plot_signal(
    signal_or_snapshot: "Signal | SignalSnapshot",
    *,
    extend_bars: Optional[int] = 40,
    figsize: tuple[int, int] = (16, 10),
    style: str = "charles",
    title: str | None = None,
    savefig: str | None = None,
    show: bool = True,
) -> plt.Figure:
    """Vẽ biểu đồ nến với mọi overlay từ ``SignalSnapshot``.

    Hàm này đọc snapshot đính kèm signal (hoặc nhận trực tiếp một
    ``SignalSnapshot``) rồi dùng **mplfinance** render biểu đồ nến kèm:

    * Đường Entry / SL / TP tại vị trí chính xác.
    * Vùng tô risk (đỏ nhạt) & reward (xanh nhạt).
    * Indicator lines trên main chart hoặc subplots riêng.
    * HLine / VLine / Rectangle / TrendLine tuỳ ý.
    * Mũi tên đánh dấu thời điểm phát signal.
    * Đường time-limit nếu có.

    Nếu ``extend_bars`` là số nguyên dương, hàm sẽ tự động query thêm
    *N* bars OHLCV tiếp theo qua ``engine.data.query`` để hiển thị diễn
    biến giá sau signal.

    Args:
        signal_or_snapshot: Đối tượng ``Signal`` (cần có ``snapshot``) hoặc
                            ``SignalSnapshot`` trực tiếp.
        extend_bars:        Số bars muốn mở rộng thêm sau bar cuối.
                            ``None`` (mặc định) → không query thêm.
        figsize:            Kích thước figure ``(width, height)``.
        style:              mplfinance style (charles, yahoo, nightclouds…).
        title:              Tiêu đề. ``None`` → tự sinh từ symbol.
        savefig:            Đường dẫn lưu ảnh. ``None`` → không lưu.
        show:               Gọi ``plt.show()``.

    Returns:
        ``matplotlib.figure.Figure``

    Raises:
        ValueError: Nếu *signal_or_snapshot* là ``Signal`` mà không có snapshot.
    """
    # --- Resolve snapshot ---
    if isinstance(signal_or_snapshot, SignalSnapshot):
        snapshot = signal_or_snapshot
    else:
        snapshot = getattr(signal_or_snapshot, "snapshot", None)
        if snapshot is None:
            raise ValueError(
                "Signal không có snapshot. Hãy đảm bảo attach_snapshot=True "
                "trên technique trước khi chạy."
            )

    # --- 1) OHLCV ---
    ohlcv = _ensure_datetime_index(snapshot.ohlcv)
    if extend_bars is not None and extend_bars > 0:
        ohlcv = _extend_ohlcv(snapshot, extend_bars)

    ohlcv_cols = [
        c for c in ("Open", "High", "Low", "Close", "Volume") if c in ohlcv.columns
    ]
    ohlcv = ohlcv[ohlcv_cols]

    # --- 2) Build addplots cho indicators ---
    addplots: list[dict] = []
    for ind in snapshot.indicators:
        aligned = ind.data.reindex(ohlcv.index)
        kwargs: dict = dict(
            panel=ind.panel,
            color=ind.color,
            secondary_y=ind.secondary_y,
            ylabel=ind.ylabel or ind.name,
        )
        if ind.type == "bar":
            kwargs.update(type="bar", width=0.7, alpha=ind.alpha)
        else:
            kwargs.update(linestyle=ind.linestyle, width=ind.linewidth)
        addplots.append(mpf.make_addplot(aligned, **kwargs))

    # HLines trên indicator panels → constant-series addplots
    for hline in snapshot.hlines:
        if hline.panel > 0:
            const = pd.Series(hline.value, index=ohlcv.index, dtype=float)
            addplots.append(
                mpf.make_addplot(
                    const,
                    panel=hline.panel,
                    color=hline.color,
                    linestyle=hline.linestyle,
                    width=hline.linewidth,
                    secondary_y=False,
                )
            )

    # --- 3) mplfinance plot ---
    if title is None:
        title = snapshot.symbol or "Signal Chart"

    plot_kwargs: dict = dict(
        type="candle",
        style=style,
        volume="Volume" in ohlcv.columns,
        figsize=figsize,
        title=title,
        returnfig=True,
        warn_too_much_data=10_000,
    )
    if addplots:
        plot_kwargs["addplot"] = addplots

    fig, axes = mpf.plot(ohlcv, **plot_kwargs)
    ax_main = axes[0]

    # --- Compute signal bar index (used in sections 4 & 5) ---
    signal_idx: int | None = None
    if snapshot.signal_time is not None:
        signal_idx = _ts_to_bar_idx(ohlcv, pd.Timestamp(snapshot.signal_time))

    # --- 4) Entry / SL / TP (start from signal bar, extend to last bar) ---
    sig_x: int = signal_idx if signal_idx is not None else 0
    n_bar: int = len(ohlcv) - 1

    if snapshot.entry is not None:
        ax_main.hlines(
            snapshot.entry,
            sig_x,
            n_bar,
            colors="#2196F3",
            linestyles="-",
            linewidth=1.6,
            label=f"Entry {snapshot.entry:,.0f}",
            alpha=0.9,
        )
    if snapshot.stop_loss is not None:
        ax_main.hlines(
            snapshot.stop_loss,
            sig_x,
            n_bar,
            colors="#F44336",
            linestyles="--",
            linewidth=1.4,
            label=f"SL {snapshot.stop_loss:,.0f}",
            alpha=0.9,
        )
    if snapshot.take_profit is not None:
        ax_main.hlines(
            snapshot.take_profit,
            sig_x,
            n_bar,
            colors="#4CAF50",
            linestyles="--",
            linewidth=1.4,
            label=f"TP {snapshot.take_profit:,.0f}",
            alpha=0.9,
        )

    # Tô vùng risk / reward (chỉ từ thời điểm signal)
    x_fill = list(range(sig_x, n_bar + 1))
    if snapshot.entry is not None and snapshot.stop_loss is not None:
        sl_lo = min(snapshot.entry, snapshot.stop_loss)
        sl_hi = max(snapshot.entry, snapshot.stop_loss)
        ax_main.fill_between(x_fill, sl_lo, sl_hi, alpha=0.06, color="red")
    if snapshot.entry is not None and snapshot.take_profit is not None:
        tp_lo = min(snapshot.entry, snapshot.take_profit)
        tp_hi = max(snapshot.entry, snapshot.take_profit)
        ax_main.fill_between(x_fill, tp_lo, tp_hi, alpha=0.06, color="green")

    # --- 5) Signal marker ---
    if snapshot.signal_time is not None and signal_idx is not None:
        if snapshot.entry is not None:
            ax_main.annotate(
                " SIGNAL",
                xy=(signal_idx, snapshot.entry),
                xytext=(max(0, signal_idx - 3), snapshot.entry * 1.015),
                fontsize=9,
                fontweight="bold",
                color="#2196F3",
                arrowprops=dict(arrowstyle="->", color="#2196F3", lw=1.5),
            )

    # --- 6) Time-limit vertical ---
    if snapshot.time_limit is not None:
        limit_ts = pd.Timestamp(snapshot.time_limit)
        if limit_ts in ohlcv.index or (
            ohlcv.index.min() <= limit_ts <= ohlcv.index.max()
        ):
            limit_idx = _ts_to_bar_idx(ohlcv, limit_ts)
            ax_main.axvline(
                limit_idx,
                color="orange",
                linestyle=":",
                linewidth=1.3,
                label="Time Limit",
                alpha=0.7,
            )

    # --- 7) Custom HLines (panel 0 only – panel>0 đã xử lý ở bước 2) ---
    for hline in snapshot.hlines:
        if hline.panel == 0:
            ax_main.axhline(
                hline.value,
                color=hline.color,
                linestyle=hline.linestyle,
                linewidth=hline.linewidth,
                label=hline.label,
                alpha=0.7,
            )

    # --- 8) Custom VLines ---
    for vline in snapshot.vlines:
        idx = _ts_to_bar_idx(ohlcv, pd.Timestamp(vline.timestamp))
        ax_main.axvline(
            idx,
            color=vline.color,
            linestyle=vline.linestyle,
            linewidth=vline.linewidth,
            label=vline.label,
            alpha=0.7,
        )

    # --- 9) Rectangles ---
    for rect in snapshot.rectangles:
        x1 = _ts_to_bar_idx(ohlcv, pd.Timestamp(rect.x_start))
        x2 = _ts_to_bar_idx(ohlcv, pd.Timestamp(rect.x_end))
        width = max(x2 - x1, 1)
        height = rect.y_top - rect.y_bottom
        patch = mpatches.FancyBboxPatch(
            (x1, rect.y_bottom),
            width,
            height,
            boxstyle="round,pad=0",
            facecolor=rect.color,
            alpha=rect.alpha,
            edgecolor=rect.color,
            linewidth=0.5,
        )
        ax_main.add_patch(patch)

    # --- 10) TrendLines ---
    for tl in snapshot.trendlines:
        xs = [_ts_to_bar_idx(ohlcv, pd.Timestamp(t)) for t, _ in tl.points]
        ys = [p for _, p in tl.points]
        ax_main.plot(
            xs,
            ys,
            color=tl.color,
            linestyle=tl.linestyle,
            linewidth=tl.linewidth,
            label=tl.label,
            alpha=0.8,
        )

    # --- 11) Legend ---
    handles, labels = ax_main.get_legend_handles_labels()
    if handles:
        ax_main.legend(handles, labels, loc="upper left", fontsize=8, framealpha=0.85)

    # --- Kết thúc ---
    if savefig:
        fig.savefig(savefig, dpi=150, bbox_inches="tight")
    if show:
        plt.show()

    return fig
