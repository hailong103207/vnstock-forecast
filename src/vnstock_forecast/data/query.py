"""
DuckDB-powered query layer for OHLCV parquet store.

The parquet files are stored in Hive-style partitioning:
    data/ohlcv/resolution=<res>/<SYMBOL>.parquet

DuckDB reads them with automatic partition pruning, so queries that
filter on ``resolution`` only touch the relevant folders.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from vnstock_forecast.shared.path import DATA_PATH_STR

OHLCV_BASE_DIR = Path(DATA_PATH_STR) / "ohlcv"


def _glob_pattern() -> str:
    """Return the glob pattern that covers all partitioned parquet files."""
    return str(OHLCV_BASE_DIR / "**" / "*.parquet")


def query_ohlcv(
    symbols: list[str] | str | None = None,
    resolutions: list[str] | str | None = None,
    from_ts: int | None = None,
    to_ts: int | None = None,
    columns: list[str] | None = None,
    order_by: str = "Symbol, Timestamp",
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Query the local OHLCV parquet store using DuckDB.

    Args:
        symbols: Filter by one or more ticker symbols (e.g. "VHM" or ["VHM", "SHB"]).
        resolutions: Filter by resolution partition (e.g. "D" or ["D", "W"]).
        from_ts: Minimum Unix timestamp (inclusive).
        to_ts: Maximum Unix timestamp (inclusive).
        columns: Columns to select; defaults to all.
        order_by: SQL ORDER BY clause (default: "Symbol, Timestamp").
        limit: Max number of rows to return.

    Returns:
        pd.DataFrame with the queried data.
    """
    glob = _glob_pattern()

    select_cols = ", ".join(columns) if columns else "*"
    sql = f"SELECT {select_cols} FROM read_parquet('{glob}', hive_partitioning=true)"

    conditions: list[str] = []
    params: dict = {}

    # --- Symbol filter ---
    if isinstance(symbols, str):
        symbols = [symbols]
    if symbols:
        placeholders = ", ".join(f"${f'sym_{i}'}" for i in range(len(symbols)))
        conditions.append(f"Symbol IN ({placeholders})")
        for i, s in enumerate(symbols):
            params[f"sym_{i}"] = s

    # --- Resolution filter (Hive partition column) ---
    if isinstance(resolutions, str):
        resolutions = [resolutions]
    if resolutions:
        placeholders = ", ".join(f"${f'res_{i}'}" for i in range(len(resolutions)))
        conditions.append(f"resolution IN ({placeholders})")
        for i, r in enumerate(resolutions):
            params[f"res_{i}"] = r

    # --- Timestamp range ---
    if from_ts is not None:
        conditions.append("Timestamp >= $from_ts")
        params["from_ts"] = from_ts
    if to_ts is not None:
        conditions.append("Timestamp <= $to_ts")
        params["to_ts"] = to_ts

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    if order_by:
        sql += f" ORDER BY {order_by}"

    if limit is not None:
        sql += f" LIMIT {limit}"

    conn = duckdb.connect()
    try:
        return conn.execute(sql, params).fetchdf()
    finally:
        conn.close()


def query_latest(
    symbols: list[str] | str | None = None,
    resolutions: list[str] | str | None = None,
) -> pd.DataFrame:
    """
    Return the latest row for each (Symbol, resolution) pair.

    Useful for checking how fresh the local data is before deciding
    whether to trigger an update.
    """
    glob = _glob_pattern()

    sql = f"""
    SELECT *
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY resolution, Symbol
                   ORDER BY Timestamp DESC
               ) AS _rn
        FROM read_parquet('{glob}', hive_partitioning=true)
    ) sub
    WHERE _rn = 1
    """

    conditions: list[str] = []
    params: dict = {}

    if isinstance(symbols, str):
        symbols = [symbols]
    if symbols:
        placeholders = ", ".join(f"${f'sym_{i}'}" for i in range(len(symbols)))
        conditions.append(f"Symbol IN ({placeholders})")
        for i, s in enumerate(symbols):
            params[f"sym_{i}"] = s

    if isinstance(resolutions, str):
        resolutions = [resolutions]
    if resolutions:
        placeholders = ", ".join(f"${f'res_{i}'}" for i in range(len(resolutions)))
        conditions.append(f"resolution IN ({placeholders})")
        for i, r in enumerate(resolutions):
            params[f"res_{i}"] = r

    # Wrap extra conditions around the outer query
    if conditions:
        sql = f"""
        SELECT * FROM ({sql}) _outer
        WHERE {" AND ".join(conditions)}
        """

    sql += " ORDER BY resolution, Symbol"

    conn = duckdb.connect()
    try:
        df = conn.execute(sql, params).fetchdf()
        if "_rn" in df.columns:
            df = df.drop(columns=["_rn"])
        return df
    finally:
        conn.close()


def query_ohlcv_grouped(
    symbols: list[str] | str | None = None,
    resolutions: list[str] | str | None = None,
    from_ts: int | None = None,
    to_ts: int | None = None,
) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Query OHLCV data and return a nested dict for easy access by resolution and symbol.

    Structure: result[resolution][symbol]
        → pd.DataFrame (Timestamp-indexed, OHLCV columns only)

    Example:
        data = query_ohlcv_grouped(symbols=["VHM", "SHB"], resolutions=["D", "W"])
        data["D"]["VHM"]   # daily VHM
        data["W"]["SHB"]   # weekly SHB

    Args:
        symbols: One or more ticker symbols.
        resolutions: One or more resolution strings.
        from_ts: Minimum Unix timestamp (inclusive).
        to_ts: Maximum Unix timestamp (inclusive).

    Returns:
        Nested dict: {resolution: {symbol: DataFrame}}
    """
    df = query_ohlcv(
        symbols=symbols,
        resolutions=resolutions,
        from_ts=from_ts,
        to_ts=to_ts,
        order_by="resolution, Symbol, Timestamp",
    )

    if df.empty:
        return {}

    ohlcv_cols = ["Timestamp", "Open", "High", "Low", "Close", "Volume"]
    result: dict[str, dict[str, pd.DataFrame]] = {}

    for (resolution, symbol), group in df.groupby(["resolution", "Symbol"], sort=False):
        sub = group[ohlcv_cols].set_index("Timestamp").sort_index()
        result.setdefault(resolution, {})[symbol] = sub

    return result


def query_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    """
    Execute an arbitrary SQL query against the OHLCV parquet store.

    Use the table alias ``ohlcv`` which points to all parquet files:

        >>> query_sql("SELECT * FROM ohlcv WHERE Symbol = $sym LIMIT 5",
        ...           {"sym": "VHM"})

    Args:
        sql: DuckDB SQL string. Reference the data as ``ohlcv``.
        params: Optional dict of named bind parameters.

    Returns:
        pd.DataFrame with the query results.
    """
    glob = _glob_pattern()
    conn = duckdb.connect()
    try:
        # Register the parquet glob as a view named "ohlcv"
        conn.execute(
            f"CREATE VIEW ohlcv AS SELECT * FROM read_parquet('{glob}', hive_partitioning=true)"  # noqa E501
        )
        return conn.execute(sql, params or {}).fetchdf()
    finally:
        conn.close()
