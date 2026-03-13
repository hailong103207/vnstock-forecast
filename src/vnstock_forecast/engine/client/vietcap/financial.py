from typing import Any

import pandas as pd
import requests


class FinancialReport:
    """Client lấy dữ liệu tài chính từ Vietcap phục vụ mục đích nghiên cứu."""

    BASE_URL: str = "https://iq.vietcap.com.vn"
    STATEMENT_ENDPOINT: str = (
        "/api/iq-insight-service/v1/company/{symbol}/financial-statement"
    )
    DICTIONARY_ENDPOINT: str = (
        "/api/iq-insight-service/v1/company/{symbol}/financial-statement/metrics"
    )

    HEADERS: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0",  # noqa: E501
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Referer": "https://trading.vietcap.com.vn/",
        "Origin": "https://trading.vietcap.com.vn",
        "Sec-GPC": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _make_request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Thực hiện GET request và trả về JSON payload."""
        url = f"{self.BASE_URL}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            print(f"[Network Error] Lỗi khi gọi API {url}: {exc}")
            return {}

    def _get_financial_statement_payload(
        self, symbol: str, section: str
    ) -> dict[str, Any]:
        """Lấy báo cáo tài chính theo section: BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, NOTE."""  # noqa: E501
        endpoint = self.STATEMENT_ENDPOINT.format(symbol=symbol.upper())
        return self._make_request(endpoint, params={"section": section.upper()})

    def _get_financial_dictionary_payload(self, symbol: str) -> dict[str, Any]:
        """Lấy dictionary dùng để map field code sang tên chỉ tiêu."""
        return self._make_request(
            self.DICTIONARY_ENDPOINT.format(symbol=symbol.upper())
        )

    def get_financial_statement(
        self,
        symbol: str,
        section: str,
        period: str = "quarters",
        language: str = "vi",
    ) -> pd.DataFrame:
        return self.get_statement_dataframe(
            symbol=symbol,
            section=section,
            period=period,
            language=language,
        )

    def get_financial_dictionary(self, symbol: str) -> pd.DataFrame:
        payload = self._get_financial_dictionary_payload(symbol=symbol)
        dictionary_data = payload.get("data", {})
        if not isinstance(dictionary_data, dict):
            return pd.DataFrame()

        rows: list[dict[str, Any]] = []
        for section, items in dictionary_data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                rows.append({"section": section, **item})

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    def get_balance_sheet(
        self, symbol: str, period: str = "quarters", language: str = "vi"
    ) -> pd.DataFrame:
        return self.get_financial_statement(
            symbol, section="BALANCE_SHEET", period=period, language=language
        )

    def get_income_statement(
        self, symbol: str, period: str = "quarters", language: str = "vi"
    ) -> pd.DataFrame:
        return self.get_financial_statement(
            symbol, section="INCOME_STATEMENT", period=period, language=language
        )

    def get_cash_flow(
        self, symbol: str, period: str = "quarters", language: str = "vi"
    ) -> pd.DataFrame:
        return self.get_financial_statement(
            symbol, section="CASH_FLOW", period=period, language=language
        )

    def get_footnote(
        self, symbol: str, period: str = "quarters", language: str = "vi"
    ) -> pd.DataFrame:
        return self.get_financial_statement(
            symbol, section="NOTE", period=period, language=language
        )

    def get_statistics_financial(self, symbol: str) -> pd.DataFrame:
        endpoint = (
            f"/api/iq-insight-service/v1/company/{symbol.upper()}/statistics-financial"
        )
        payload = self._make_request(endpoint)
        return self._build_statistics_dataframe(payload.get("data"))

    def get_last_quarter_financial(self, symbol: str) -> pd.DataFrame:
        endpoint = f"/api/iq-insight-service/v1/company/{symbol.upper()}/last-quarter-financial"  # noqa: E501
        payload = self._make_request(endpoint)
        return self._build_last_quarter_dataframe(payload.get("data"))

    def get_financial_statement_metrics(self, symbol: str) -> pd.DataFrame:
        endpoint = f"/api/iq-insight-service/v1/company/{symbol.upper()}/financial-statement/metrics"  # noqa: E501
        payload = self._make_request(endpoint)
        return self._to_generic_dataframe(payload.get("data"))

    def get_statement_dataframe(
        self,
        symbol: str,
        section: str,
        period: str = "quarters",
        language: str = "vi",
        dictionary_payload: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        """
        Trả về DataFrame có cột là thời điểm.

        Ví dụ cột quý: Q1_2023, Q2_2023, ...
        Hàng là các chỉ tiêu đã map bằng dictionary.
        """
        statement_payload = self._get_financial_statement_payload(
            symbol=symbol, section=section
        )
        if not dictionary_payload:
            dictionary_payload = self._get_financial_dictionary_payload(symbol=symbol)

        return self._build_statement_dataframe(
            statement_payload=statement_payload,
            dictionary_payload=dictionary_payload,
            section=section,
            period=period,
            language=language,
        )

    def _build_statement_dataframe(
        self,
        statement_payload: dict[str, Any],
        dictionary_payload: dict[str, Any],
        section: str,
        period: str,
        language: str,
    ) -> pd.DataFrame:
        rows = statement_payload.get("data", {}).get(period, [])
        if not rows:
            return pd.DataFrame()

        field_map = self._build_field_map(
            dictionary_payload=dictionary_payload, section=section, language=language
        )
        if not field_map:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame()

        df["yearReport"] = pd.to_numeric(df.get("yearReport"), errors="coerce")
        df["lengthReport"] = pd.to_numeric(df.get("lengthReport"), errors="coerce")
        df = df.dropna(subset=["yearReport"]).copy()
        if df.empty:
            return pd.DataFrame()

        df["yearReport"] = df["yearReport"].astype(int)
        df["lengthReport"] = df["lengthReport"].fillna(0).astype(int)

        df["period"] = df.apply(
            lambda row: self._format_period(
                row["yearReport"], row["lengthReport"], period
            ),
            axis=1,
        )
        df = df.sort_values(["yearReport", "lengthReport"]).drop_duplicates(
            subset=["period"], keep="last"
        )

        metric_fields = [field for field in field_map if field in df.columns]
        if not metric_fields:
            return pd.DataFrame()

        value_df = df[["period", *metric_fields]].set_index("period").T
        value_df = value_df.apply(pd.to_numeric, errors="coerce")
        value_df = value_df.dropna(how="all")
        if value_df.empty:
            return pd.DataFrame()

        descriptions: list[str] = []
        normalized_metrics: list[str] = []
        for field in value_df.index:
            meta = field_map.get(field, {"metric": field, "description": ""})
            normalized_metrics.append(str(meta.get("metric", field)))
            descriptions.append(str(meta.get("description", "")))

        value_df.index = normalized_metrics
        value_df.insert(0, "description", descriptions)
        value_df.index.name = "metric"
        value_df.columns.name = "time"
        return value_df

    @staticmethod
    def _to_generic_dataframe(data: Any) -> pd.DataFrame:
        if data is None:
            return pd.DataFrame()

        if isinstance(data, list):
            if not data:
                return pd.DataFrame()
            return pd.DataFrame(data)

        if isinstance(data, dict):
            if not data:
                return pd.DataFrame()

            if all(not isinstance(value, (dict, list)) for value in data.values()):
                return pd.DataFrame([data])

            try:
                return pd.DataFrame(data)
            except ValueError:
                return pd.json_normalize(data, sep=".")

        return pd.DataFrame()

    @staticmethod
    def _build_statistics_dataframe(data: Any) -> pd.DataFrame:
        if not isinstance(data, list) or not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame()

        if "year" not in df.columns:
            return pd.DataFrame()

        quarter_series = pd.to_numeric(df.get("quarter"), errors="coerce")
        year_series = pd.to_numeric(df.get("year"), errors="coerce")

        df = df.assign(year=year_series, quarter=quarter_series)
        df = df.dropna(subset=["year"]).copy()
        if df.empty:
            return pd.DataFrame()

        df["year"] = df["year"].astype(int)
        df["quarter"] = df["quarter"].fillna(0).astype(int)
        df["period"] = df.apply(
            lambda row: FinancialReport._format_statistics_period(
                row["year"], row["quarter"]
            ),
            axis=1,
        )

        df = df.sort_values(["year", "quarter"]).drop_duplicates(
            subset=["period"], keep="last"
        )

        excluded_columns = {
            "period",
            "year",
            "quarter",
            "ratioTTMId",
            "ratioYearId",
            "ratioType",
            "organCode",
            "yearReport",
        }
        metric_fields = [
            column
            for column in df.columns
            if column not in excluded_columns
            and not str(column).lower().endswith("id")
            and not str(column).lower().startswith("unnamed")
        ]
        if not metric_fields:
            return pd.DataFrame()

        value_df = df[["period", *metric_fields]].set_index("period").T
        value_df = value_df.apply(pd.to_numeric, errors="coerce")
        value_df = value_df.dropna(how="all")
        if value_df.empty:
            return pd.DataFrame()

        value_df.insert(0, "description", "")
        value_df.index = [str(metric).strip().lower() for metric in value_df.index]
        value_df.index.name = "metric"
        value_df.columns.name = "time"
        return value_df

    @staticmethod
    def _build_last_quarter_dataframe(data: Any) -> pd.DataFrame:
        if data is None:
            return pd.DataFrame()

        if isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            return pd.DataFrame()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame()

        period_series: pd.Series | None = None
        if "quarter" in df.columns:
            period_series = df["quarter"].apply(
                FinancialReport._normalize_quarter_label
            )
        elif "yearReport" in df.columns and "lengthReport" in df.columns:
            year_series = pd.to_numeric(df["yearReport"], errors="coerce")
            quarter_series = pd.to_numeric(df["lengthReport"], errors="coerce")
            period_series = [
                (
                    FinancialReport._format_statistics_period(int(year), int(quarter))
                    if pd.notna(year)
                    else None
                )
                for year, quarter in zip(year_series, quarter_series)
            ]
        elif "year" in df.columns:
            year_series = pd.to_numeric(df["year"], errors="coerce")
            period_series = [
                f"Y{int(year)}" if pd.notna(year) else None for year in year_series
            ]

        if period_series is None:
            period_series = ["LATEST"] * len(df)

        df = df.assign(period=period_series)
        df = df.dropna(subset=["period"]).copy()
        if df.empty:
            return pd.DataFrame()

        excluded_columns = {
            "period",
            "ticker",
            "quarter",
            "year",
            "yearReport",
            "lengthReport",
            "tradingTime",
            "updateDate",
        }
        metric_fields = [
            column
            for column in df.columns
            if column not in excluded_columns
            and not str(column).lower().endswith("id")
            and not str(column).lower().startswith("unnamed")
        ]
        if not metric_fields:
            return pd.DataFrame()

        df = df.drop_duplicates(subset=["period"], keep="last")
        value_df = df[["period", *metric_fields]].set_index("period").T
        value_df = value_df.apply(pd.to_numeric, errors="coerce")
        value_df = value_df.dropna(how="all")
        if value_df.empty:
            return pd.DataFrame()

        value_df.insert(0, "description", "")
        value_df.index = [str(metric).strip().lower() for metric in value_df.index]
        value_df.index.name = "metric"
        value_df.columns.name = "time"
        return value_df

    @staticmethod
    def _format_period(year: int, length_report: int, period: str) -> str:
        normalized_period = period.lower()
        if normalized_period == "quarters":
            return f"Q{length_report}_{year}"
        return f"Y{year}"

    @staticmethod
    def _format_statistics_period(year: int, quarter: int) -> str:
        if quarter in {1, 2, 3, 4}:
            return f"Q{quarter}_{year}"
        return f"Y{year}"

    @staticmethod
    def _normalize_quarter_label(raw_quarter: Any) -> str | None:
        if raw_quarter is None:
            return None

        normalized = str(raw_quarter).strip().upper()
        if not normalized:
            return None

        normalized = normalized.replace("-", " ").replace("_", " ")
        parts = normalized.split()

        if len(parts) >= 2 and parts[0].startswith("Q"):
            quarter_text = parts[0].replace("Q", "")
            if quarter_text.isdigit() and parts[1].isdigit():
                return f"Q{int(quarter_text)}_{int(parts[1])}"

        return normalized.replace(" ", "_")

    @staticmethod
    def _build_field_map(
        dictionary_payload: dict[str, Any], section: str, language: str
    ) -> dict[str, dict[str, str]]:
        section_data = dictionary_payload.get("data", {}).get(section.upper(), [])
        if not section_data:
            return {}

        field_map: dict[str, dict[str, str]] = {}

        for item in section_data:
            field = str(item.get("field", "")).strip().lower()
            if not field:
                continue

            title_en = str(
                item.get("titleEn")
                or item.get("fullTitleEn")
                or item.get("name")
                or field
            ).strip()
            title_vi = str(item.get("titleVi") or item.get("fullTitleVi") or "").strip()
            normalized_title_en = "_".join(title_en.lower().split())
            field_map[field] = {
                "metric": normalized_title_en,
                "description": title_vi,
            }

        return field_map


if __name__ == "__main__":
    client = FinancialReport()
    symbol = "VHM"
    last = client.get_last_quarter_financial(symbol=symbol)
    print(last)
    last.to_csv(f"{symbol}_last_quarter.csv")
