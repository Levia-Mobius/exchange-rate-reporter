from __future__ import annotations

import json
from pathlib import Path
from datetime import time as dt_time

import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from rate_service import FrankfurterRateService, RateServiceError
from report_logic import build_report
from notification_logic import (
    load_state,
    save_state,
    reset_state,
    now_in_timezone,
    create_notification_if_due,
    is_weekday,
    in_time_window,
)


CONFIG_PATH = Path("config.json")
MIN_UPDATE_HOURS = 2.0
BOC_ESTIMATED_SPREAD = 0.0201


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return json.loads(Path("config.example.json").read_text(encoding="utf-8"))


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


@st.cache_data(ttl=int(MIN_UPDATE_HOURS * 3600), show_spinner=False)
def load_rate_data(
    base_currency: str,
    quote_currency: str,
    history_days: int,
) -> tuple:
    """
    Cached data loader.

    Protection mechanism:
    - Page reruns or refreshes will not repeatedly scrape Google Finance.
    - The cache TTL is at least 2 hours.
    - The app only performs a new external fetch after the cache expires, or when the user
      explicitly clears Streamlit cache / redeploys the app.

    Current/report rate:
    - Google Finance first.
    - Frankfurter fallback.

    Historical report:
    - Frankfurter daily historical data.
    """
    service = FrankfurterRateService()
    return service.get_history_with_current(base_currency, quote_currency, history_days)


st.set_page_config(page_title="汇率状态提醒 App", page_icon="💱", layout="wide")

cfg = load_config()

st.title("汇率状态提醒 App")
st.caption(
    "面向留学生家庭：只显示汇率状态、历史位置和金额影响，不提供换汇建议。"
    "Report 当前汇率优先使用 Google Finance；失败时回退到 Frankfurter。"
)

with st.sidebar:
    st.header("基础设置")
    currency_options = ["AUD", "USD", "GBP", "EUR", "JPY", "NZD", "CAD"]
    quote_options = ["CNY", "AUD", "USD", "EUR"]

    base_currency = st.selectbox(
        "要买入的外币",
        currency_options,
        index=currency_options.index(cfg.get("base_currency", "AUD")) if cfg.get("base_currency", "AUD") in currency_options else 0,
    )
    quote_currency = st.selectbox(
        "用于支付的货币",
        quote_options,
        index=quote_options.index(cfg.get("quote_currency", "CNY")) if cfg.get("quote_currency", "CNY") in quote_options else 0,
    )
    target_amount = st.number_input("计划观察金额（外币）", min_value=100.0, value=float(cfg.get("target_amount", 10000)), step=100.0)
    watch_threshold = st.number_input("关注阈值：1 外币 ≤ 多少本币", min_value=0.0001, value=float(cfg.get("watch_threshold", 4.75)), step=0.01, format="%.4f")

    st.header("历史判断设置")
    history_days = st.slider("历史窗口（天）", min_value=30, max_value=365, value=int(cfg.get("history_days", 90)), step=30)
    low_percentile = st.slider("低位区间分位数", min_value=5, max_value=40, value=int(cfg.get("low_percentile", 25)), step=5)
    high_percentile = st.slider("高位区间分位数", min_value=60, max_value=95, value=int(cfg.get("high_percentile", 75)), step=5)
    cost_change_alert_cny = st.number_input("成本变化提醒阈值（本币）", min_value=50.0, value=float(cfg.get("cost_change_alert_cny", 500)), step=50.0)

    st.header("App 内 report update 设置")
    enable_report_update = st.checkbox(
        "开启 report update",
        value=bool(cfg.get("enable_report_update", False)),
        help="关闭时，页面不会自动刷新生成新 report；只显示缓存中的当前状态。",
    )

    timezone_options = ["Asia/Shanghai", "Australia/Sydney", "UTC"]
    timezone = st.selectbox(
        "提醒时区",
        timezone_options,
        index=timezone_options.index(cfg.get("timezone", "Asia/Shanghai")) if cfg.get("timezone", "Asia/Shanghai") in timezone_options else 0,
    )

    notify_start_time = st.time_input("提醒开始时间", value=dt_time.fromisoformat(cfg.get("notify_start_time", "08:00")))
    notify_end_time = st.time_input("提醒结束时间", value=dt_time.fromisoformat(cfg.get("notify_end_time", "22:00")))

    previous_interval = float(cfg.get("notify_interval_hours", 2))
    if previous_interval < MIN_UPDATE_HOURS:
        st.error("提醒间隔不能低于 2 小时。旧配置已被自动按 2 小时处理。")

    notify_interval_hours = st.number_input(
        "Report update 间隔（小时，最低 2 小时）",
        min_value=MIN_UPDATE_HOURS,
        max_value=24.0,
        value=max(MIN_UPDATE_HOURS, previous_interval),
        step=0.5,
    )

    notify_weekdays_only = st.checkbox("周末不提醒", value=bool(cfg.get("notify_weekdays_only", True)))
    minor_update_rate_change_pct = st.number_input(
        "显著变化阈值（较上次 report 的百分比）",
        min_value=0.01,
        max_value=5.0,
        value=float(cfg.get("minor_update_rate_change_pct", 0.15)),
        step=0.01,
        format="%.2f",
    )

    baidu_reference_url = f"https://finance.baidu.com/foreign/global-{base_currency}{quote_currency}"
    google_reference_url = f"https://www.google.com/finance/quote/{base_currency}-{quote_currency}"

    new_cfg = {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "watch_threshold": watch_threshold,
        "target_amount": target_amount,
        "history_days": history_days,
        "low_percentile": low_percentile,
        "high_percentile": high_percentile,
        "cost_change_alert_cny": cost_change_alert_cny,
        "timezone": timezone,
        "notify_start_time": notify_start_time.strftime("%H:%M"),
        "notify_end_time": notify_end_time.strftime("%H:%M"),
        "notify_interval_hours": max(MIN_UPDATE_HOURS, notify_interval_hours),
        "notify_weekdays_only": notify_weekdays_only,
        "minor_update_rate_change_pct": minor_update_rate_change_pct,
        "enable_report_update": enable_report_update,
        "baidu_reference_url": baidu_reference_url,
        "google_reference_url": google_reference_url,
    }

    if st.button("保存设置", use_container_width=True):
        save_config(new_cfg)
        st.success("设置已保存。")

    if st.button("清空 App 内 report 记录", use_container_width=True):
        reset_state()
        st.success("已清空 report 记录。")
        st.rerun()

cfg = new_cfg

# Auto-refresh protection:
# - No 60-second refresh.
# - If report update is enabled, refresh no more frequently than the user-selected interval.
# - The minimum interval is hard-limited to 2 hours.
if enable_report_update:
    st_autorefresh(
        interval=int(max(MIN_UPDATE_HOURS, notify_interval_hours) * 3600 * 1000),
        key="rate_app_autorefresh_protected",
    )
else:
    st.info("Report update 当前关闭：页面不会自动刷新抓取数据；只显示当前缓存状态。")

try:
    with st.spinner("正在读取汇率数据。页面刷新不会重复抓取；缓存最短保留 2 小时。"):
        df, current_point = load_rate_data(base_currency, quote_currency, history_days)

    report = build_report(
        df=df,
        base_currency=base_currency,
        quote_currency=quote_currency,
        target_amount=target_amount,
        watch_threshold=watch_threshold,
        low_percentile=low_percentile,
        high_percentile=high_percentile,
        cost_change_alert_cny=cost_change_alert_cny,
        baidu_reference_url=baidu_reference_url,
    )

    state = load_state()
    now_local = now_in_timezone(timezone)

    if enable_report_update:
        state, created, schedule_status = create_notification_if_due(
            report=report,
            cfg=cfg,
            now_local=now_local,
            state=state,
        )
    else:
        created = False
        schedule_status = "Report update 已关闭，因此不会生成新的 App 内 report。"

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("当前汇率", f"{report.current_rate:.4f}", help=f"当前汇率来源：{current_point.source}；时间/日期：{current_point.date}")
    top2.metric("状态标签", report.label)
    top3.metric("当前时间", now_local.strftime("%Y-%m-%d %H:%M"))
    top4.metric("当前成本", f"{report.current_cost:,.0f} {quote_currency}")

    estimated_boc_rate = report.current_rate + BOC_ESTIMATED_SPREAD
    source_note = "Google Finance" if current_point.source == "Google Finance" else "Frankfurter fallback"
    source_color = "#8a4b00" if current_point.source == "Google Finance" else "#8a1f11"
    source_extra = (
        "当前汇率来自 Google Finance。"
        if current_point.source == "Google Finance"
        else "Google Finance 读取失败，当前使用 Frankfurter fallback。"
    )

    st.markdown(
        f"""
        <div style="background-color:#fff3cd; border-left:6px solid #ff9800; padding:14px 18px; border-radius:8px; margin:12px 0 18px 0;">
            <h2 style="margin:0; color:{source_color};">中行换汇汇率约为 {estimated_boc_rate:.4f}</h2>
            <div style="margin-top:6px; color:#5f4300;">
                计算方式：当前 {source_note} 汇率 {report.current_rate:.4f} + {BOC_ESTIMATED_SPREAD:.4f}。
                {source_extra} 仅作为估算参考。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        f"Report 当前汇率来源：{current_point.source}；"
        f"historical report / 历史分位数来源：Frankfurter 日频历史数据；"
        f"数据抓取缓存 TTL：至少 {MIN_UPDATE_HOURS:g} 小时。"
    )

    allowed_day = (not notify_weekdays_only) or is_weekday(now_local)
    allowed_window = in_time_window(now_local, cfg["notify_start_time"], cfg["notify_end_time"])

    if enable_report_update:
        if allowed_day and allowed_window:
            st.success(schedule_status)
        else:
            st.info(schedule_status)
    else:
        st.warning(schedule_status)

    tab_notifications, tab_current, tab_chart, tab_settings = st.tabs(["App 内 report", "当前状态报告", "历史走势", "设置说明"])

    with tab_notifications:
        st.subheader("App 内 report")
        st.caption(
            "只有开启 report update，并且达到最低 2 小时间隔后，才会生成新的 App 内 report。"
            "关闭 report update 时不会自动抓取或生成新 report。"
        )

        notifications = state.get("notifications", [])
        if not notifications:
            st.info("还没有 App 内 report。开启 report update 后，到达提醒时间窗口和间隔才会自动生成。")
        else:
            for item in notifications[:10]:
                with st.container(border=True):
                    st.markdown(f"**{item['title']}**")
                    st.caption(f"{item['created_at_local']}｜数据日期：{item['rate_date']}｜类型：{item['type']}")
                    st.text_area(
                        "报告内容",
                        value=item["body"],
                        height=260 if item["type"] == "brief" else 420,
                        key=f"body_{item['created_at_local']}_{item['type']}",
                    )

    with tab_current:
        st.subheader("当前状态报告")
        st.text_area("当前完整报告", value=report.message, height=460)

    with tab_chart:
        st.subheader("历史走势")
        fig = px.line(
            df,
            x="date",
            y="rate",
            markers=True,
            labels={"date": "日期", "rate": f"1 {base_currency} ≈ ? {quote_currency}"},
        )
        fig.add_hline(y=watch_threshold, line_dash="dash", annotation_text="关注阈值")
        fig.add_hline(y=report.low_cutoff, line_dash="dot", annotation_text="低位参考线")
        fig.add_hline(y=report.high_cutoff, line_dash="dot", annotation_text="高位参考线")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("查看原始历史数据"):
            st.dataframe(df, use_container_width=True)

    with tab_settings:
        st.markdown(
            """
### 当前版本的 report update 逻辑

1. Report 当前汇率优先使用 Google Finance；如果读取失败，回退到 Frankfurter。
2. Historical report / 历史分位数只使用 Frankfurter 日频历史数据。
3. 页面不会再每 60 秒自动刷新。
4. 只有开启 `report update` 后，才会按设定间隔自动刷新和生成 App 内 report。
5. Report update 间隔最低为 2 小时；低于 2 小时的旧配置会被自动按 2 小时处理，并显示红色提示。
6. 页面数据读取使用 Streamlit cache；页面刷新或参数轻微变动不会造成高频抓取。
7. 关闭 report update 时，页面只展示当前缓存状态，不会生成新的 App 内 report。

### 关于中行换汇估算

顶部黄色高亮使用：

```text
中行换汇估算 = 当前 report 汇率 + 0.0201
```

如果当前 report 汇率来自 Google Finance，页面会标注 `Google Finance`。
如果 Google Finance 失败并回退到 Frankfurter，页面会明确标注 `Frankfurter fallback`。

### 关于数据源

Google Finance 用于当前 report 汇率，但它不是官方 JSON API，因此保留 Frankfurter fallback。
Frankfurter 用于历史分位数和趋势判断。
百度财经和真实银行成交价仍建议作为人工核对。
            """
        )

except RateServiceError as exc:
    st.error(f"获取汇率失败：{exc}")
    st.write("可以检查网络连接，或稍后再试。")
except Exception as exc:
    st.error(f"程序出错：{exc}")
