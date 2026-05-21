from __future__ import annotations

import json
from pathlib import Path

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


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return json.loads(Path("config.example.json").read_text(encoding="utf-8"))


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


st.set_page_config(page_title="汇率状态提醒 App", page_icon="💱", layout="wide")

cfg = load_config()

# Refresh the page every 60 seconds. The app only creates a new notification when the interval rule is due.
st_autorefresh(interval=60 * 1000, key="rate_app_autorefresh")

st.title("汇率状态提醒 App")
st.caption("面向留学生家庭：只显示汇率状态、历史位置和金额影响，不提供换汇建议。当前汇率使用 Frankfurter v2 direct pair endpoint。")

with st.sidebar:
    st.header("基础设置")
    base_currency = st.selectbox(
        "要买入的外币",
        ["AUD", "USD", "GBP", "EUR", "JPY", "NZD", "CAD"],
        index=["AUD", "USD", "GBP", "EUR", "JPY", "NZD", "CAD"].index(cfg.get("base_currency", "AUD")),
    )
    quote_currency = st.selectbox(
        "用于支付的货币",
        ["CNY", "AUD", "USD", "EUR"],
        index=["CNY", "AUD", "USD", "EUR"].index(cfg.get("quote_currency", "CNY")),
    )
    target_amount = st.number_input("计划观察金额（外币）", min_value=100.0, value=float(cfg.get("target_amount", 10000)), step=100.0)
    watch_threshold = st.number_input("关注阈值：1 外币 ≤ 多少本币", min_value=0.0001, value=float(cfg.get("watch_threshold", 4.75)), step=0.01, format="%.4f")

    st.header("历史判断设置")
    history_days = st.slider("历史窗口（天）", min_value=30, max_value=365, value=int(cfg.get("history_days", 90)), step=30)
    low_percentile = st.slider("低位区间分位数", min_value=5, max_value=40, value=int(cfg.get("low_percentile", 25)), step=5)
    high_percentile = st.slider("高位区间分位数", min_value=60, max_value=95, value=int(cfg.get("high_percentile", 75)), step=5)
    cost_change_alert_cny = st.number_input("成本变化提醒阈值（本币）", min_value=50.0, value=float(cfg.get("cost_change_alert_cny", 500)), step=50.0)

    st.header("App 内提醒设置")
    timezone = st.selectbox(
        "提醒时区",
        ["Asia/Shanghai", "Australia/Sydney", "UTC"],
        index=["Asia/Shanghai", "Australia/Sydney", "UTC"].index(cfg.get("timezone", "Asia/Shanghai")),
    )
    notify_start_time = st.time_input("提醒开始时间", value=__import__("datetime").time.fromisoformat(cfg.get("notify_start_time", "08:00")))
    notify_end_time = st.time_input("提醒结束时间", value=__import__("datetime").time.fromisoformat(cfg.get("notify_end_time", "22:00")))
    notify_interval_hours = st.number_input("提醒间隔（小时）", min_value=0.5, max_value=24.0, value=float(cfg.get("notify_interval_hours", 2)), step=0.5)
    notify_weekdays_only = st.checkbox("周末不提醒", value=bool(cfg.get("notify_weekdays_only", True)))
    minor_update_rate_change_pct = st.number_input(
        "显著变化阈值（较上次提醒的百分比）",
        min_value=0.01,
        max_value=5.0,
        value=float(cfg.get("minor_update_rate_change_pct", 0.15)),
        step=0.01,
        format="%.2f",
    )

    baidu_reference_url = f"https://finance.baidu.com/foreign/global-{base_currency}{quote_currency}"

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
        "notify_interval_hours": notify_interval_hours,
        "notify_weekdays_only": notify_weekdays_only,
        "minor_update_rate_change_pct": minor_update_rate_change_pct,
        "baidu_reference_url": baidu_reference_url,
    }

    if st.button("保存设置", use_container_width=True):
        save_config(new_cfg)
        st.success("设置已保存。")

    if st.button("清空 App 内提醒记录", use_container_width=True):
        reset_state()
        st.success("已清空提醒记录。")
        st.rerun()

cfg = new_cfg

service = FrankfurterRateService()

try:
    df = service.get_history_with_current(base_currency, quote_currency, history_days)
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
    state, created, schedule_status = create_notification_if_due(
        report=report,
        cfg=cfg,
        now_local=now_local,
        state=state,
    )

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("当前汇率", f"{report.current_rate:.4f}", help=f"当前汇率来自 Frankfurter v2 direct pair endpoint；数据日期：{report.rate_date}")
    top2.metric("状态标签", report.label)
    top3.metric("当前时间", now_local.strftime("%Y-%m-%d %H:%M"))
    top4.metric("当前成本", f"{report.current_cost:,.0f} {quote_currency}")

    boc_estimated_rate = report.current_rate + 0.0236
    st.markdown(
        f"""
        <div style="background-color:#fff3cd; border-left:6px solid #ff9800; padding:14px 18px; border-radius:8px; margin:12px 0 18px 0;">
            <h2 style="margin:0; color:#8a4b00;">中行换汇汇率约为 {boc_estimated_rate:.4f}</h2>
            <div style="margin-top:6px; color:#5f4300;">计算方式：当前 Frankfurter 汇率 {report.current_rate:.4f} + 0.0236。仅作为估算参考。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    allowed_day = (not notify_weekdays_only) or is_weekday(now_local)
    allowed_window = in_time_window(now_local, cfg["notify_start_time"], cfg["notify_end_time"])
    if allowed_day and allowed_window:
        st.success(schedule_status)
    else:
        st.info(schedule_status)

    tab_notifications, tab_current, tab_chart, tab_settings = st.tabs(["App 内提醒", "当前状态报告", "历史走势", "设置说明"])

    with tab_notifications:
        st.subheader("App 内提醒")
        st.caption("页面每 60 秒自动刷新一次；只有达到你设置的提醒间隔时，才会生成新的 App 内提醒。")

        notifications = state.get("notifications", [])
        if not notifications:
            st.info("还没有 App 内提醒。到达提醒时间窗口和间隔后会自动生成。")
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
### 当前版本的提醒逻辑

1. App 每 60 秒自动刷新一次页面。
2. 只有在你设置的提醒时间窗口内，才会生成 App 内提醒。
3. 如果开启“周末不提醒”，周六和周日不会生成提醒。
4. 到达提醒间隔后：
   - 如果触发关注阈值、低位区间、高位区间或成本变化，会生成完整状态报告；
   - 如果没有值得更新的变化，会生成简洁状态更新，只显示当前汇率、目标金额成本，以及与上次提醒是否基本一致。
5. 这些提醒只显示在 App 页面里，不发送邮件，也不触发系统级手机推送。

### 关于“开盘/收盘”

外汇市场本身接近 24/5 交易。这里的“提醒开始时间”和“提醒结束时间”更准确地说是家庭用户自己的提醒窗口，例如每天 08:00–22:00。
            """
        )

except RateServiceError as exc:
    st.error(f"获取汇率失败：{exc}")
    st.write("可以检查网络连接，或稍后再试。")
except Exception as exc:
    st.error(f"程序出错：{exc}")
