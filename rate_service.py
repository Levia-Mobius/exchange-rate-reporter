from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
import requests
import pandas as pd


class RateServiceError(RuntimeError):
    pass


@dataclass
class RatePoint:
    date: str
    rate: float


class FrankfurterRateService:
    """
    Uses Frankfurter API.

    Important design:
    - get_latest() uses the direct current pair endpoint:
        https://api.frankfurter.dev/v2/rate/AUD/CNY
      This is used for the App's "current rate".
    - get_history() uses the time-series endpoint:
        https://api.frankfurter.dev/v1/YYYY-MM-DD..YYYY-MM-DD?base=AUD&symbols=CNY
      This is used for historical percentile calculation.
    - get_history_with_current() appends or overwrites the latest observation with get_latest(),
      so the App report always uses the current available pair rate.
    """

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.v1_base_url = "https://api.frankfurter.dev/v1"
        self.v2_base_url = "https://api.frankfurter.dev/v2"

    def get_latest(
        self,
        base_currency: str = "AUD",
        quote_currency: str = "CNY",
    ) -> RatePoint:
        base_currency = base_currency.upper()
        quote_currency = quote_currency.upper()
        url = f"{self.v2_base_url}/rate/{base_currency}/{quote_currency}"

        try:
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise RateServiceError(f"Failed to fetch latest rate: {exc}") from exc

        # Expected:
        # {"date":"2026-05-21","base":"AUD","quote":"CNY","rate":4.8396}
        rate = payload.get("rate")
        rate_date = payload.get("date")

        if rate is None or rate_date is None:
            raise RateServiceError(f"Latest rate response is missing expected fields: {payload}")

        return RatePoint(date=str(rate_date), rate=float(rate))

    def get_history(
        self,
        base_currency: str = "AUD",
        quote_currency: str = "CNY",
        days: int = 90,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        base_currency = base_currency.upper()
        quote_currency = quote_currency.upper()
        end_date = end_date or date.today()
        start_date = end_date - timedelta(days=days)

        url = (
            f"{self.v1_base_url}/{start_date.isoformat()}..{end_date.isoformat()}"
            f"?base={base_currency}&symbols={quote_currency}"
        )

        try:
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise RateServiceError(f"Failed to fetch rate history: {exc}") from exc

        rates = payload.get("rates", {})
        rows = []
        for d, values in rates.items():
            if quote_currency in values:
                rows.append({"date": pd.to_datetime(d).date(), "rate": float(values[quote_currency])})

        if not rows:
            raise RateServiceError("No exchange-rate records returned. Check currency codes or API availability.")

        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        return df

    def get_history_with_current(
        self,
        base_currency: str = "AUD",
        quote_currency: str = "CNY",
        days: int = 90,
    ) -> pd.DataFrame:
        """
        Historical endpoint can lag behind the direct current endpoint.
        This method uses history for the lookback window, then appends/overwrites
        the current pair quote from get_latest().

        This keeps:
        - historical percentile: based on daily observations;
        - current report: based on the latest direct pair quote.
        """
        df = self.get_history(base_currency, quote_currency, days)
        latest = self.get_latest(base_currency, quote_currency)
        latest_date = pd.to_datetime(latest.date).date()

        # Remove any existing row for the latest date, then append the current direct quote.
        df = df[df["date"] != latest_date].copy()
        df = pd.concat(
            [
                df,
                pd.DataFrame([{"date": latest_date, "rate": latest.rate}]),
            ],
            ignore_index=True,
        )
        df = df.sort_values("date").reset_index(drop=True)
        return df
