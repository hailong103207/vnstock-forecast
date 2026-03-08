"""
OHLCV data updater — Parquet + DuckDB local store.

Storage layout (Hive-style partitioning):
    data/ohlcv/
        resolution=D/
            VHM.parquet
            SHB.parquet
        resolution=W/
            ...

Each .parquet file stores one (symbol, resolution) pair with columns:
    Timestamp | Symbol | Open | High | Low | Close | Volume

Update strategy:
    1. If parquet already exists → read last timestamp
        → fetch only newer data → append & deduplicate.
    2. If parquet does not exist → fetch from (now − lookback_days) → write new file.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from vnstock_forecast.client.vietstock import OHLCV
from vnstock_forecast.schemas import UpdaterConfig
from vnstock_forecast.shared.path import DATA_PATH_STR
from vnstock_forecast.utils import time_utils

logger = logging.getLogger(__name__)

OHLCV_BASE_DIR = Path(DATA_PATH_STR) / "ohlcv"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parquet_path(resolution: str, symbol: str) -> Path:
    """Return the canonical parquet file path for a (resolution, symbol) pair."""
    return OHLCV_BASE_DIR / f"resolution={resolution}" / f"{symbol}.parquet"


def _read_existing(path: Path) -> pd.DataFrame | None:
    """Read an existing parquet file, or return None if it doesn't exist."""
    if path.exists():
        df = pd.read_parquet(path)
        if not df.empty:
            return df
    return None


def _merge_and_deduplicate(
    existing: pd.DataFrame | None, new: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge new data into existing data, drop duplicates on Timestamp,
    keep the latest version, and sort chronologically.
    """
    if existing is not None and not existing.empty:
        combined = pd.concat([existing, new], ignore_index=True)
    else:
        combined = new.copy()

    combined = (
        combined.drop_duplicates(subset=["Timestamp", "Symbol"], keep="last")
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )
    return combined


def _save_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to parquet, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_symbol(
    client: OHLCV,
    symbol: str,
    resolution: str,
    lookback_days: int = 365,
) -> pd.DataFrame | None:
    """
    Fetch and persist the latest OHLCV data for a single (symbol, resolution) pair.

    Supports **bidirectional** updates:
      - Forward: fetch data newer than the local max timestamp.
      - Backfill: if lookback_days extends earlier than the local min timestamp,
        fetch the missing historical gap as well.

    Args:
        client: An initialised OHLCV API client.
        symbol: Stock ticker (e.g. "VHM").
        resolution: Vietstock resolution string (e.g. "D", "5", "W").
        lookback_days: How far back to fetch from today.

    Returns:
        The updated DataFrame, or None if nothing was fetched.
    """
    path = _parquet_path(resolution, symbol)
    existing_df = _read_existing(path)

    now_ts = time_utils.get_current_timestamp()
    lookback_ts = time_utils.add_days_to_timestamp(
        time_utils.get_current_date_timestamp(), -lookback_days
    )

    parts: list[pd.DataFrame] = []

    if existing_df is not None:
        local_min_ts = int(existing_df["Timestamp"].min())
        local_max_ts = int(existing_df["Timestamp"].max())

        # --- Backfill: fetch older data if lookback extends before local min ---
        if lookback_ts < local_min_ts:
            logger.info(
                "[%s/%s] Backfill: local starts at %s, lookback wants %s.",
                resolution,
                symbol,
                time_utils.timestamp_to_str(local_min_ts),
                time_utils.timestamp_to_str(lookback_ts),
            )
            backfill_df = client.fetch(
                lookback_ts, local_min_ts - 1, symbol, resolution
            )
            if backfill_df is not None and not backfill_df.empty:
                parts.append(backfill_df)
                logger.info(
                    "[%s/%s] Backfill fetched %d rows.",
                    resolution,
                    symbol,
                    len(backfill_df),
                )

        # --- Forward: fetch newer data after local max ---
        forward_from = local_max_ts + 1
        if forward_from < now_ts:
            logger.info(
                "[%s/%s] Forward: local ends at %s — fetching to now.",
                resolution,
                symbol,
                time_utils.timestamp_to_str(local_max_ts),
            )
            forward_df = client.fetch(forward_from, now_ts, symbol, resolution)
            if forward_df is not None and not forward_df.empty:
                parts.append(forward_df)
                logger.info(
                    "[%s/%s] Forward fetched %d rows.",
                    resolution,
                    symbol,
                    len(forward_df),
                )
        else:
            logger.info("[%s/%s] Already up-to-date (forward).", resolution, symbol)
    else:
        # --- No local data: full fetch from lookback ---
        logger.info(
            "[%s/%s] No local data — fetching last %d days.",
            resolution,
            symbol,
            lookback_days,
        )
        full_df = client.fetch(lookback_ts, now_ts, symbol, resolution)
        if full_df is not None and not full_df.empty:
            parts.append(full_df)

    if not parts:
        logger.warning("[%s/%s] No new data fetched.", resolution, symbol)
        return existing_df

    merged = _merge_and_deduplicate(existing_df, pd.concat(parts, ignore_index=True))
    _save_parquet(merged, path)
    logger.info(
        "[%s/%s] Saved %d rows → %s",
        resolution,
        symbol,
        len(merged),
        path,
    )
    return merged


def update(cfg: UpdaterConfig) -> bool:
    """
    Run a full OHLCV update for every (symbol × resolution) in the config.

    Args:
        cfg: UpdaterConfig with symbols, resolutions, and lookback_days.

    Returns:
        True if ALL (symbol, resolution) pairs succeeded, False otherwise.
    """
    client = OHLCV()
    symbols: list[str] = list(cfg.symbols)
    resolutions: list[str] = list(cfg.resolutions)
    lookback_days: int = cfg.lookback_days

    total = len(symbols) * len(resolutions)
    logger.info(
        "Starting OHLCV update: %d symbols × %d resolutions = %d jobs",
        len(symbols),
        len(resolutions),
        total,
    )

    success_count = 0
    fail_count = 0

    for resolution in resolutions:
        for symbol in symbols:
            try:
                result = update_symbol(client, symbol, resolution, lookback_days)
                if result is not None:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception:
                logger.exception("[%s/%s] Unexpected error.", resolution, symbol)
                fail_count += 1

    logger.info(
        "Update complete: %d/%d succeeded, %d failed.",
        success_count,
        total,
        fail_count,
    )
    return fail_count == 0
