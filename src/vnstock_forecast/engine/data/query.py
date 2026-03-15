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

from vnstock_forecast.engine.shared.path import DATA_PATH_STR

OHLCV_BASE_DIR = Path(DATA_PATH_STR) / "ohlcv"
FINANCE_BASE_DIR = Path(DATA_PATH_STR) / "finance"

FINANCE_METADATA_COLUMNS = {
    "symbol",
    "statement",
    "metric",
    "description",
    "filename",
}


def _glob_pattern() -> str:
    """Return the glob pattern that covers all partitioned parquet files."""
    return str(OHLCV_BASE_DIR / "**" / "*.parquet")


def _finance_glob_pattern() -> str:
    """Return the glob pattern for all financial parquet files."""
    return str(FINANCE_BASE_DIR / "**" / "*.parquet")


def _has_parquet_files(base_dir: Path) -> bool:
    """Check if a directory tree contains any parquet files."""
    if not base_dir.exists():
        return False
    return any(base_dir.rglob("*.parquet"))


def _to_list(value: list[str] | str | None) -> list[str]:
    """Normalize optional string/list input to list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _escape_sql_identifier(name: str) -> str:
    """Escape a SQL identifier for DuckDB."""
    return '"' + name.replace('"', '""') + '"'


def _build_finance_long_sql(conn: duckdb.DuckDBPyConnection, finance_glob: str) -> str:
    """Build SQL to transform finance_raw wide table into long format without UNPIVOT."""
    schema_df = conn.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{finance_glob}', union_by_name=true, filename=true)"
    ).fetchdf()
    all_columns = [str(column) for column in schema_df["column_name"].tolist()]

    period_columns = [
        column for column in all_columns if column not in FINANCE_METADATA_COLUMNS
    ]

    if not period_columns:
        return """
        SELECT NULL::VARCHAR AS symbol,
               NULL::VARCHAR AS statement,
               NULL::VARCHAR AS metric,
               NULL::VARCHAR AS description,
               NULL::VARCHAR AS period,
               NULL::DOUBLE AS value
        WHERE FALSE
        """

    symbol_expr = (
        "COALESCE(CAST(symbol AS VARCHAR), "
        "regexp_extract(filename, '.*/finance/([^/]+)/[^/]+\\.parquet', 1))"
    )
    statement_expr = (
        "COALESCE(CAST(statement AS VARCHAR), "
        "regexp_extract(filename, '.*/finance/[^/]+/([^/]+)\\.parquet', 1))"
    )

    selects: list[str] = []
    for period_col in period_columns:
        period_literal = period_col.replace("'", "''")
        period_identifier = _escape_sql_identifier(period_col)
        selects.append(
            f"""
            SELECT
                {symbol_expr} AS symbol,
                {statement_expr} AS statement,
                CAST(metric AS VARCHAR) AS metric,
                CAST(description AS VARCHAR) AS description,
                '{period_literal}' AS period,
                TRY_CAST({period_identifier} AS DOUBLE) AS value
            FROM finance_raw
            """
        )

    union_sql = "\nUNION ALL\n".join(selects)
    return f"SELECT * FROM ({union_sql}) _long WHERE value IS NOT NULL"


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
    Execute an arbitrary SQL query against local parquet stores.

    Available views:
        - ``ohlcv``: OHLCV parquet data.
        - ``finance_raw``: Financial parquet data in original wide format.
        - ``finance_long``: Financial data unpivoted to long format
          (symbol, statement, metric, description, period, value).

    Example:

        >>> query_sql("SELECT * FROM ohlcv WHERE Symbol = $sym LIMIT 5",
        ...           {"sym": "VHM"})

    Args:
        sql: DuckDB SQL string. Reference the data as ``ohlcv``.
        params: Optional dict of named bind parameters.

    Returns:
        pd.DataFrame with the query results.
    """
    ohlcv_glob = _glob_pattern()
    finance_glob = _finance_glob_pattern()
    conn = duckdb.connect()
    try:
        if _has_parquet_files(OHLCV_BASE_DIR):
            conn.execute(
                f"CREATE VIEW ohlcv AS SELECT * FROM read_parquet('{ohlcv_glob}', hive_partitioning=true)"  # noqa E501
            )
        else:
            conn.execute(
                """
                CREATE VIEW ohlcv AS
                SELECT NULL::BIGINT AS Timestamp,
                       NULL::VARCHAR AS Symbol,
                       NULL::DOUBLE AS Open,
                       NULL::DOUBLE AS High,
                       NULL::DOUBLE AS Low,
                       NULL::DOUBLE AS Close,
                       NULL::DOUBLE AS Volume,
                       NULL::VARCHAR AS resolution
                WHERE FALSE
                """
            )

        if _has_parquet_files(FINANCE_BASE_DIR):
            conn.execute(
                f"CREATE VIEW finance_raw AS SELECT * FROM read_parquet('{finance_glob}', union_by_name=true, filename=true)"  # noqa E501
            )
            finance_long_sql = _build_finance_long_sql(conn, finance_glob)
            conn.execute(f"CREATE VIEW finance_long AS {finance_long_sql}")
        else:
            conn.execute(
                """
                CREATE VIEW finance_raw AS
                SELECT NULL::VARCHAR AS symbol,
                       NULL::VARCHAR AS statement,
                       NULL::VARCHAR AS metric,
                       NULL::VARCHAR AS description,
                       NULL::VARCHAR AS filename
                WHERE FALSE
                """
            )
            conn.execute(
                """
                CREATE VIEW finance_long AS
                SELECT NULL::VARCHAR AS symbol,
                       NULL::VARCHAR AS statement,
                       NULL::VARCHAR AS metric,
                       NULL::VARCHAR AS description,
                       NULL::VARCHAR AS period,
                       NULL::DOUBLE AS value
                WHERE FALSE
                """
            )

        return conn.execute(sql, params or {}).fetchdf()
    finally:
        conn.close()


def query_financial(
    symbols: list[str] | str | None = None,
    statements: list[str] | str | None = None,
    metrics: list[str] | str | None = None,
    periods: list[str] | str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    order_by: str = "symbol, statement, metric, period",
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Query financial data in long format for flexible stock screening.

    Returns columns:
        symbol, statement, metric, description, period, value
    """
    if not _has_parquet_files(FINANCE_BASE_DIR):
        return pd.DataFrame(
            columns=["symbol", "statement", "metric", "description", "period", "value"]
        )

    finance_glob = _finance_glob_pattern()
    conn = duckdb.connect()
    try:
        conn.execute(
            f"CREATE VIEW finance_raw AS SELECT * FROM read_parquet('{finance_glob}', union_by_name=true, filename=true)"  # noqa E501
        )
        finance_long_sql = _build_finance_long_sql(conn, finance_glob)
        conn.execute(f"CREATE VIEW finance_long AS {finance_long_sql}")

        sql = "SELECT * FROM finance_long"

        conditions: list[str] = []
        params: dict = {}

        normalized_symbols = _to_list(symbols)
        if normalized_symbols:
            placeholders = ", ".join(
                f"${f'sym_{i}'}" for i in range(len(normalized_symbols))
            )
            conditions.append(f"symbol IN ({placeholders})")
            for i, item in enumerate(normalized_symbols):
                params[f"sym_{i}"] = item.upper()

        normalized_statements = _to_list(statements)
        if normalized_statements:
            placeholders = ", ".join(
                f"${f'statement_{i}'}" for i in range(len(normalized_statements))
            )
            conditions.append(f"statement IN ({placeholders})")
            for i, item in enumerate(normalized_statements):
                params[f"statement_{i}"] = item

        normalized_metrics = _to_list(metrics)
        if normalized_metrics:
            placeholders = ", ".join(
                f"${f'metric_{i}'}" for i in range(len(normalized_metrics))
            )
            conditions.append(f"metric IN ({placeholders})")
            for i, item in enumerate(normalized_metrics):
                params[f"metric_{i}"] = item.lower()

        normalized_periods = _to_list(periods)
        if normalized_periods:
            placeholders = ", ".join(
                f"${f'period_{i}'}" for i in range(len(normalized_periods))
            )
            conditions.append(f"period IN ({placeholders})")
            for i, item in enumerate(normalized_periods):
                params[f"period_{i}"] = item

        if min_value is not None:
            conditions.append("value >= $min_value")
            params["min_value"] = min_value

        if max_value is not None:
            conditions.append("value <= $max_value")
            params["max_value"] = max_value

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        if order_by:
            sql += f" ORDER BY {order_by}"

        if limit is not None:
            sql += f" LIMIT {limit}"

        return conn.execute(sql, params).fetchdf()
    finally:
        conn.close()
