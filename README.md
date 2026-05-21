# 汇率状态提醒 App

这是一个面向留学生家庭的轻量型汇率状态提醒 App 原型。

它不提供换汇建议，只显示：

1. 当前汇率；
2. 当前汇率在历史窗口中的位置；
3. 达到用户关注阈值、低位/高位区间或成本变化时的触发原因；
4. 按目标金额折算的成本变化；
5. App 内提醒记录。

本版本已经移除邮件提醒。提醒只显示在 App 内。

---

## 1. 重要定位

这不是实时交易工具，也不是换汇建议工具。

它的定位是：

> 在用户设定的时间窗口内，定时生成 App 内汇率状态报告，帮助用户判断当前是否值得重新查看换汇计划。

报告不会出现：

- 建议换多少；
- 建议现在换；
- 建议分批换；
- 买入/卖出信号。

---

## 2. 数据来源

默认使用 Frankfurter API 的日频公开参考汇率。

百度财经页面仍然保留为人工核对入口，例如：

```text
https://finance.baidu.com/foreign/global-AUDCNY
```

不建议把百度网页作为程序唯一数据源，因为网页结构变化可能导致程序失效。

---



## 当前汇率与历史数据的口径修正

v2 版本开始，App 不再直接用历史序列最后一行作为“当前汇率”。

原因是：历史时间序列 endpoint 有时会比单一货币对 current endpoint 慢一步更新。

现在的逻辑是：

```text
当前汇率：
使用 Frankfurter v2 direct pair endpoint
例如：https://api.frankfurter.dev/v2/rate/AUD/CNY

历史区间：
使用 Frankfurter 历史时间序列 endpoint
用于计算过去 30/90 天分位数、低位线和高位线
```

程序会先读取历史序列，然后用 direct pair endpoint 返回的最新汇率覆盖/追加到历史序列中。

这样可以保证：

```text
App 顶部显示的当前汇率
当前状态报告中的当前汇率
App 内提醒中的当前汇率
```

都尽量对应“当前可查询到的最新 direct pair rate”，而不是历史 endpoint 的滞后值。

---

## 3. 历史数据定义

第一版采用：

> API 返回的每日公开参考汇率/最近工作日汇率，作为每个历史观察日的代表值。

不使用盘中平均值。原因是家庭换汇规划不需要秒级数据，日频数据更稳定，也更容易解释。

---

## 4. App 内提醒逻辑

用户可以设置：

- 提醒开始时间；
- 提醒结束时间；
- 提醒间隔，例如每 2 小时；
- 是否周末不提醒；
- 显著变化阈值，例如较上次提醒变化 0.15%。

运行逻辑：

1. 页面每 60 秒自动刷新一次；
2. 如果当前时间不在提醒窗口内，不生成新提醒；
3. 如果是周末，并且开启“周末不提醒”，不生成新提醒；
4. 如果距离上次提醒不足设定间隔，不生成新提醒；
5. 到达提醒间隔后：
   - 如果触发阈值、低位区间、高位区间或成本变化，生成完整报告；
   - 如果没有值得更新的变化，生成简洁状态更新。

简洁状态更新示例：

```text
【AUD/CNY 简洁状态更新】

当前汇率：
1 AUD ≈ 4.8000 CNY

金额影响：
若兑换 10,000 AUD，按当前汇率约需 48,000 CNY。

状态：
与上次 App 内提醒基本一致。

说明：
本报告只展示汇率状态和金额折算，不构成换汇建议。
```

---

## 5. 本地运行方式

开发者或你自己测试时可以本地运行。

```bash
cd exchange_rate_reporter_app
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

启动：

```bash
streamlit run app.py
```

---

## 6. 给父母使用的推荐方式

父母不应该接触 Python、本地环境、命令行或配置文件。

更适合的流程是：

1. 你把这个项目上传到 GitHub；
2. 用 Streamlit Community Cloud、Render、Railway 或自己的服务器部署；
3. 生成一个网页链接；
4. 父母只需要打开这个网页；
5. 你帮他们设置好阈值、提醒窗口和观察金额；
6. 之后他们只需要看 App 内的提醒卡片。

注意：

- 当前版本是 App 内提醒，不是手机系统推送；
- 如果网页没有打开，父母不会看到 App 内提醒；
- 如果需要手机系统通知，需要额外实现 PWA Push Notification、微信服务号/企业微信/Telegram Bot 或短信服务。

---

## 7. 配置文件

`config.example.json` 是默认配置模板。

如果部署平台允许持久化文件，可以复制为：

```bash
cp config.example.json config.json
```

Windows:

```bash
copy config.example.json config.json
```

不过在云部署里，更好的方式是让用户直接在 App 侧边栏设置。

---

## 8. 文件结构

```text
exchange_rate_reporter_app/
├── app.py                    # Streamlit App 主界面
├── rate_service.py           # 汇率数据获取
├── report_logic.py           # 状态报告生成
├── notification_logic.py     # App 内提醒调度逻辑
├── config.example.json       # 默认设置
├── requirements.txt          # 依赖包
└── README.md                 # 使用说明
```

---

## 9. 后续可扩展方向

如果要做成真正的手机 App 或小程序，建议后续改成：

- 前端：React Native / Flutter / 微信小程序；
- 后端：FastAPI；
- 数据库：SQLite / Supabase / PostgreSQL；
- 定时任务：APScheduler / Celery / Cloud Scheduler；
- 通知：PWA Push、微信服务号模板消息、企业微信机器人、Telegram Bot 或短信。

当前版本适合验证产品逻辑和交互设计。


## 中行换汇估算提示

v3 版本在 App 顶部增加了一个高亮提示：

```text
中行换汇汇率约为 current_rate + 0.0236
```

例如当前 Frankfurter 汇率为 4.8396，则页面会显示：

```text
中行换汇汇率约为 4.8632
```

这个值只是基于用户观察到的固定差值进行估算，不是中国银行官方实时牌价。真正办理换汇时，应以银行实际成交汇率为准。


## v5 当前汇率数据源：Google Finance 优先

v5 版本开始，App 的 report 当前汇率优先读取 Google Finance AUD/CNY 页面：

```text
https://www.google.com/finance/quote/AUD-CNY
```

数据源逻辑：

```text
Report 当前汇率：
优先使用 Google Finance 页面报价

如果 Google Finance 解析失败：
自动回退到 Frankfurter v2 direct pair endpoint

历史区间：
继续使用 Frankfurter 日频历史数据
```

注意：Google Finance 不是官方 JSON API，本项目采用网页解析方式读取页面中的 AUD/CNY 报价。如果 Google 修改页面结构，解析可能失效，因此保留 Frankfurter fallback。

## v5 提醒间隔限制

App 内提醒间隔被硬性限制为最低 2 小时：

```text
notify_interval_hours >= 2
```

即使旧配置中保存过 0.5 或 1 小时，程序也会自动按 2 小时处理。


## v6 protection and data-source policy

v6 keeps the current/report rate as:

```text
Google Finance first
Frankfurter fallback if Google Finance fails
```

The highlighted estimated BOC exchange rate is now calculated as:

```text
estimated BOC rate = current report rate + 0.0201
```

The page clearly labels whether the current report rate came from `Google Finance` or from `Frankfurter fallback`.

### Anti-abuse / scraping protection

The App no longer refreshes every 60 seconds.

Protection rules:

```text
1. Report update is disabled by default.
2. If report update is disabled, the App does not auto-refresh or generate new App reports.
3. Report update interval is hard-limited to at least 2 hours.
4. Old configs below 2 hours are automatically clamped to 2 hours.
5. Data loading uses Streamlit cache with a minimum TTL of 2 hours.
```

This means page reruns or manual refreshes should not repeatedly scrape Google Finance.

### Historical report

Historical report and percentile calculation continue to use Frankfurter daily historical data only.
