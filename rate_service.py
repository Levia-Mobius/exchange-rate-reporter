from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
import html
import re
import requests
import pandas as pd


class RateServiceError(RuntimeError):
    pass


@dataclass
class RatePoint:
    date: str
    rate: float
    source: str = "unknown"


class FrankfurterRateService:
    """
    Data-source design:
    - Current/report rate: Google Finance AUD-CNY quote page, parsed from public HTML.
    - Fallback current rate: Frankfurter v2 direct pair endpoint.
    - Historical rates: Frankfurter daily historical endpoint.

    Google Finance is not an official JSON API, so parsing may break if Google changes
    the page structure. The Frankfurter fallback keeps the App usable.
    """

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.v1_base_url = "https://api.frankfurter.dev/v1"
        self.v2_base_url = "https://api.frankfurter.dev/v2"

    def get_google_finance_current(
        self,
        base_currency: str = "AUD",
        quote_currency: str = "CNY",
    ) -> RatePoint:
        base_currency = base_currency.upper()
        quote_currency = quote_currency.upper()
        url = f"https://www.google.com/finance/quote/{base_currency}-{quote_currency}"

        headers = {
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "accept-language": "en-US,en;q=0.9",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            raw_html = resp.text
        except Exception as exc:
            raise RateServiceError(f"Failed to fetch Google Finance quote page: {exc}") from exc

        text = html.unescape(re.sub(r"<[^>]+>", "\n", raw_html))
        text = re.sub(r"\s+", " ", text)

        # Look for the section around:
        # AUD / CNY ... Australian Dollar / Chinese Yuan 4.8487 ... May 21, 4:53:00 AM UTC
        pair_marker = f"{base_currency} / {quote_currency}"
        currency_name_marker = "Australian Dollar / Chinese Yuan" if (base_currency, quote_currency) == ("AUD", "CNY") else None

        pos = text.find(pair_marker)
        if pos == -1 and currency_name_marker:
            pos = text.find(currency_name_marker)

        if pos == -1:
            raise RateServiceError("Could not locate currency pair marker on Google Finance page.")

        window = text[pos: pos + 1200]

        # The first plausible FX number after the AUD/CNY label is the quote.
        # Avoid percentages and bracketed changes by requiring a 1-3 digit integer part and decimals.
        candidates = re.findall(r"(?<![\d+\-])([0-9]{1,3}\.[0-9]{3,6})(?![%\d])", window)
        if not candidates:
            raise RateServiceError("Could not extract current rate from Google Finance page.")

        rate = float(candidates[0])

        # Optional timestamp. If not found, use today's date.
        time_match = re.search(
            r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{1,2}:\d{2}:\d{2}\s+(?:AM|PM)\s+UTC)",
            window,
        )
        rate_date = time_match.group(1) if time_match else date.today().isoformat()

        return RatePoint(date=rate_date, rate=rate, source="Google Finance")

    def get_frankfurter_latest(
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
            raise RateServiceError(f"Failed to fetch Frankfurter latest rate: {exc}") from exc

        rate = payload.get("rate")
        rate_date = payload.get("date")

        if rate is None or rate_date is None:
            raise RateServiceError(f"Frankfurter latest response is missing expected fields: {payload}")

        return RatePoint(date=str(rate_date), rate=float(rate), source="Frankfurter")

    def get_latest(
        self,
        base_currency: str = "AUD",
        quote_currency: str = "CNY",
    ) -> RatePoint:
        """
        Current-rate priority:
        1. Google Finance page quote.
        2. Frankfurter v2 direct pair endpoint as fallback.
        """
        try:
            return self.get_google_finance_current(base_currency, quote_currency)
        except Exception:
            return self.get_frankfurter_latest(base_currency, quote_currency)

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
    ) -> tuple[pd.DataFrame, RatePoint]:
        """
        Historical endpoint is used for lookback statistics.
        Current endpoint is used for the actual current report.
        """
        df = self.get_history(base_currency, quote_currency, days)
        latest = self.get_latest(base_currency, quote_currency)

        latest_date = date.today()
        # Google returns a timestamp string such as "May 21, 4:53:00 AM UTC".
        # We append it as today's observation for percentile calculations.
        df = df[df["date"] != latest_date].copy()
        df = pd.concat(
            [
                df,
                pd.DataFrame([{"date": latest_date, "rate": latest.rate}]),
            ],
            ignore_index=True,
        )
        df = df.sort_values("date").reset_index(drop=True)
        return df, latest
