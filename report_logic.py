from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional
import pandas as pd


@dataclass
class ExchangeReport:
    label: str
    trigger_type: str
    triggered: bool
    base_currency: str
    quote_currency: str
    rate_date: str
    current_rate: float
    watch_threshold: Optional[float]
    target_amount: float
    current_cost: float
    percentile_position: float
    low_cutoff: float
    high_cutoff: float
    previous_rate_date: Optional[str]
    previous_rate: Optional[float]
    previous_cost_change: Optional[float]
    seven_day_rate_date: Optional[str]
    seven_day_rate: Optional[float]
    seven_day_cost_change: Optional[float]
    thirty_day_rate_date: Optional[str]
    thirty_day_rate: Optional[float]
    thirty_day_cost_change: Optional[float]
    message: str
    generated_at_utc: str

    def to_dict(self) -> dict:
        return asdict(self)


def _nearest_previous_rate(df: pd.DataFrame, current_date, min_days_before: int):
    target_date = current_date - pd.Timedelta(days=min_days_before)
    candidates = df[df["date"] <= target_date.date()]
    if candidates.empty:
        return None
    return candidates.iloc[-1]


def build_report(
    df: pd.DataFrame,
    base_currency: str = "AUD",
    quote_currency: str = "CNY",
    target_amount: float = 10000,
    watch_threshold: Optional[float] = None,
    low_percentile: float = 25,
    high_percentile: float = 75,
    cost_change_alert_cny: float = 500,
    baidu_reference_url: str = "https://finance.baidu.com/foreign/global-AUDCNY",
) -> ExchangeReport:
    if df.empty:
        raise ValueError("History dataframe is empty.")

    df = df.copy().sort_values("date").reset_index(drop=True)
    current = df.iloc[-1]
    current_date = pd.to_datetime(current["date"])
    current_rate = float(current["rate"])

    rates = df["rate"].astype(float)
    low_cutoff = float(rates.quantile(low_percentile / 100))
    high_cutoff = float(rates.quantile(high_percentile / 100))
    percentile_position = float((rates <= current_rate).mean() * 100)

    current_cost = current_rate * target_amount

    prev = df.iloc[-2] if len(df) >= 2 else None
    r7 = _nearest_previous_rate(df, current_date, 7)
    r30 = _nearest_previous_rate(df, current_date, 30)

    previous_change = None if prev is None else current_cost - float(prev["rate"]) * target_amount
    seven_day_change = None if r7 is None else current_cost - float(r7["rate"]) * target_amount
    thirty_day_change = None if r30 is None else current_cost - float(r30["rate"]) * target_amount

    if watch_threshold is not None and current_rate <= watch_threshold:
        label = "触达关注阈值"
        trigger_type = "threshold"
        triggered = True
        trigger_sentence = f"当前汇率已低于你设置的关注阈值 {watch_threshold:.4f}。"
    elif current_rate <= low_cutoff:
        label = "低位区间"
        trigger_type = "low_percentile"
        triggered = True
        trigger_sentence = (
            f"当前汇率处于历史窗口的较低区间，低于约 {100 - percentile_position:.0f}% "
            f"的历史观察值。"
        )
    elif current_rate >= high_cutoff:
        label = "高位区间"
        trigger_type = "high_percentile"
        triggered = True
        trigger_sentence = (
            f"当前汇率处于历史窗口的较高区间，高于约 {percentile_position:.0f}% "
            f"的历史观察值。"
        )
    elif seven_day_change is not None and abs(seven_day_change) >= cost_change_alert_cny:
        label = "成本明显变化"
        trigger_type = "cost_change"
        triggered = True
        direction = "增加" if seven_day_change > 0 else "减少"
        trigger_sentence = f"按目标金额计算，当前成本较约 7 天前{direction}约 {abs(seven_day_change):,.0f} {quote_currency}。"
    else:
        label = "常规区间"
        trigger_type = "normal"
        triggered = False
        trigger_sentence = "当前汇率未触发关注阈值、历史区间或成本变化提醒。"

    message = format_report_text(
        label=label,
        base_currency=base_currency,
        quote_currency=quote_currency,
        current_rate=current_rate,
        rate_date=str(current["date"]),
        trigger_sentence=trigger_sentence,
        target_amount=target_amount,
        current_cost=current_cost,
        percentile_position=percentile_position,
        low_cutoff=low_cutoff,
        high_cutoff=high_cutoff,
        prev=prev,
        previous_change=previous_change,
        r7=r7,
        seven_day_change=seven_day_change,
        r30=r30,
        thirty_day_change=thirty_day_change,
        baidu_reference_url=baidu_reference_url,
    )

    return ExchangeReport(
        label=label,
        trigger_type=trigger_type,
        triggered=triggered,
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate_date=str(current["date"]),
        current_rate=current_rate,
        watch_threshold=watch_threshold,
        target_amount=target_amount,
        current_cost=current_cost,
        percentile_position=percentile_position,
        low_cutoff=low_cutoff,
        high_cutoff=high_cutoff,
        previous_rate_date=None if prev is None else str(prev["date"]),
        previous_rate=None if prev is None else float(prev["rate"]),
        previous_cost_change=previous_change,
        seven_day_rate_date=None if r7 is None else str(r7["date"]),
        seven_day_rate=None if r7 is None else float(r7["rate"]),
        seven_day_cost_change=seven_day_change,
        thirty_day_rate_date=None if r30 is None else str(r30["date"]),
        thirty_day_rate=None if r30 is None else float(r30["rate"]),
        thirty_day_cost_change=thirty_day_change,
        message=message,
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _fmt_change(change: Optional[float], quote_currency: str) -> str:
    if change is None:
        return "暂无足够历史数据"
    direction = "增加" if change > 0 else "减少"
    return f"{direction}约 {abs(change):,.0f} {quote_currency}"


def build_brief_report(
    *,
    base_currency: str,
    quote_currency: str,
    current_rate: float,
    rate_date: str,
    target_amount: float,
    current_cost: float,
    compare_rate: Optional[float] = None,
    compare_time_text: str = "上次提醒",
) -> str:
    if compare_rate is None:
        change_text = "目前暂无足够的 App 内历史提醒记录用于比较。"
    else:
        pct = (current_rate - compare_rate) / compare_rate * 100
        if abs(pct) < 0.05:
            change_text = f"与{compare_time_text}基本一致。"
        else:
            direction = "上升" if pct > 0 else "下降"
            change_text = f"较{compare_time_text}{direction}约 {abs(pct):.2f}%。"

    boc_estimated_rate = current_rate + 0.0201

    return f"""【{base_currency}/{quote_currency} 简洁状态更新】

当前汇率：
1 {base_currency} ≈ {current_rate:.4f} {quote_currency}
数据日期：{rate_date}

中行换汇参考：
中行换汇汇率约为 {boc_estimated_rate:.4f}

金额影响：
若兑换 {target_amount:,.0f} {base_currency}，按当前汇率约需 {current_cost:,.0f} {quote_currency}。

状态：
{change_text}

说明：
本报告只展示汇率状态和金额折算，不构成换汇建议。
"""


def format_report_text(
    label,
    base_currency,
    quote_currency,
    current_rate,
    rate_date,
    trigger_sentence,
    target_amount,
    current_cost,
    percentile_position,
    low_cutoff,
    high_cutoff,
    prev,
    previous_change,
    r7,
    seven_day_change,
    r30,
    thirty_day_change,
    baidu_reference_url,
) -> str:
    prev_line = "上一观察日：暂无足够历史数据"
    if prev is not None:
        prev_line = (
            f"上一观察日 {prev['date']}：1 {base_currency} ≈ {float(prev['rate']):.4f} {quote_currency}，"
            f"目标金额成本较当时{_fmt_change(previous_change, quote_currency)}"
        )

    r7_line = "约 7 天前：暂无足够历史数据"
    if r7 is not None:
        r7_line = (
            f"约 7 天前 {r7['date']}：1 {base_currency} ≈ {float(r7['rate']):.4f} {quote_currency}，"
            f"目标金额成本较当时{_fmt_change(seven_day_change, quote_currency)}"
        )

    r30_line = "约 30 天前：暂无足够历史数据"
    if r30 is not None:
        r30_line = (
            f"约 30 天前 {r30['date']}：1 {base_currency} ≈ {float(r30['rate']):.4f} {quote_currency}，"
            f"目标金额成本较当时{_fmt_change(thirty_day_change, quote_currency)}"
        )

    return f"""【{base_currency}/{quote_currency} 汇率状态报告：{label}】

当前汇率：
1 {base_currency} ≈ {current_rate:.4f} {quote_currency}
数据日期：{rate_date}

中行换汇参考：
中行换汇汇率约为 {current_rate + 0.0201:.4f}

触发原因：
{trigger_sentence}

金额影响：
若兑换 {target_amount:,.0f} {base_currency}，按当前汇率约需 {current_cost:,.0f} {quote_currency}。

历史位置：
当前汇率位于历史窗口约第 {percentile_position:.0f} 百分位。
低位参考线：{low_cutoff:.4f}
高位参考线：{high_cutoff:.4f}

成本变化：
{prev_line}
{r7_line}
{r30_line}

人工核对：
可在百度财经页面查看行情：{baidu_reference_url}

说明：
本报告只展示汇率状态、历史位置和目标金额下的成本变化，不构成换汇建议。
"""
