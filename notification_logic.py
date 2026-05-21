from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional

from report_logic import ExchangeReport, build_brief_report


STATE_PATH = Path("notification_state.json")


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"notifications": []}
    return {"notifications": []}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_state() -> None:
    if STATE_PATH.exists():
        STATE_PATH.unlink()


def parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(hour=int(hh), minute=int(mm))


def now_in_timezone(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def in_time_window(dt: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    start = parse_hhmm(start_hhmm)
    end = parse_hhmm(end_hhmm)
    current = dt.time()

    if start <= end:
        return start <= current <= end

    # Overnight window, e.g. 21:00 to 02:00
    return current >= start or current <= end


def get_last_notification(state: dict) -> Optional[dict]:
    items = state.get("notifications", [])
    return items[0] if items else None


def hours_since_last_notification(state: dict, now_local: datetime) -> Optional[float]:
    last = get_last_notification(state)
    if not last:
        return None
    try:
        last_time = datetime.fromisoformat(last["created_at_local"])
    except Exception:
        return None
    return (now_local - last_time).total_seconds() / 3600


def _rate_change_pct(current_rate: float, previous_rate: Optional[float]) -> Optional[float]:
    if previous_rate is None or previous_rate == 0:
        return None
    return (current_rate - previous_rate) / previous_rate * 100


def create_notification_if_due(
    *,
    report: ExchangeReport,
    cfg: dict,
    now_local: datetime,
    state: dict,
) -> tuple[dict, bool, str]:
    """
    Returns: updated_state, created, status_message

    It creates an in-app notification only when:
      - current day is allowed;
      - current time is inside the configured notification window;
      - the configured interval has passed.
    """

    weekdays_only = bool(cfg.get("notify_weekdays_only", True))
    if weekdays_only and not is_weekday(now_local):
        return state, False, "今天是周末，已按设置暂停 App 内提醒。"

    start_time = cfg.get("notify_start_time", "08:00")
    end_time = cfg.get("notify_end_time", "22:00")
    if not in_time_window(now_local, start_time, end_time):
        return state, False, f"当前不在提醒窗口内。提醒窗口：{start_time}–{end_time}。"

    interval_hours = float(cfg.get("notify_interval_hours", 2))
    elapsed = hours_since_last_notification(state, now_local)
    if elapsed is not None and elapsed < interval_hours:
        remaining = interval_hours - elapsed
        return state, False, f"距离上次 App 内提醒尚未达到 {interval_hours:g} 小时，约 {remaining:.1f} 小时后可再次生成。"

    last = get_last_notification(state)
    last_rate = None if last is None else float(last.get("current_rate", report.current_rate))
    change_pct = _rate_change_pct(report.current_rate, last_rate)
    threshold_pct = float(cfg.get("minor_update_rate_change_pct", 0.15))

    should_full_report = report.triggered
    if change_pct is not None and abs(change_pct) >= threshold_pct:
        should_full_report = True

    if should_full_report:
        notification_type = "full"
        title = f"{report.base_currency}/{report.quote_currency} 汇率状态报告：{report.label}"
        body = report.message
    else:
        notification_type = "brief"
        title = f"{report.base_currency}/{report.quote_currency} 简洁状态更新"
        body = build_brief_report(
            base_currency=report.base_currency,
            quote_currency=report.quote_currency,
            current_rate=report.current_rate,
            rate_date=report.rate_date,
            target_amount=report.target_amount,
            current_cost=report.current_cost,
            compare_rate=last_rate,
            compare_time_text="上次 App 内提醒",
        )

    notification = {
        "created_at_local": now_local.isoformat(timespec="seconds"),
        "type": notification_type,
        "title": title,
        "label": report.label,
        "trigger_type": report.trigger_type,
        "current_rate": report.current_rate,
        "rate_date": report.rate_date,
        "body": body,
    }

    notifications = state.get("notifications", [])
    notifications.insert(0, notification)
    state["notifications"] = notifications[:50]
    save_state(state)

    return state, True, "已生成新的 App 内提醒。"
