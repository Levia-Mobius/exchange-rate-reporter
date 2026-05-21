# Exchange Rate Reporter

A lightweight exchange-rate status reporter designed for international students and their families.

The app focuses on **clear exchange-rate status reporting**, not financial advice. It reports the current AUD/CNY reference rate, an estimated bank exchange rate, historical position, and cost impact for a user-defined target amount.

Live app:

```text
https://exchange-rate-reporter.streamlit.app/
```

---

## 1. Product positioning

This app is not a trading tool and does not provide exchange recommendations.

It does **not** say:

```text
Exchange now
Exchange 20%
Buy AUD
Sell AUD
```

Instead, it reports:

```text
Current exchange-rate reference
Estimated bank exchange-rate reference
Historical position
Cost impact for the selected amount
Whether the value has entered a user-defined attention range
```

The final decision is left to the user.

---

## 2. Current data-source design

The app uses separate data sources for **current report rate** and **historical report**.

### 2.1 Current / report rate

Current report rate uses:

```text
Google Finance first
Frankfurter fallback if Google Finance fails
```

For AUD/CNY, the Google Finance reference page is:

```text
https://www.google.com/finance/quote/AUD-CNY
```

Google Finance is used because it provides a relatively up-to-date AUD/CNY reference and is closer to common finance-page values such as Baidu Finance.

However, Google Finance is not an official JSON API. The app parses the public page, so the parser may break if Google changes its page structure. For this reason, the app keeps Frankfurter as a fallback.

If Google Finance is successfully parsed, the page displays:

```text
Report 当前汇率来源：Google Finance
```

If Google Finance fails, the page displays:

```text
Report 当前汇率来源：Frankfurter
```

### 2.2 Historical report

Historical report and historical percentile calculation use:

```text
Frankfurter daily historical data
```

This is used for:

```text
30/90-day historical window
Low/high percentile lines
Historical position
Historical trend chart
```

Frankfurter is daily-frequency data, so it is stable for historical reporting but not used as the preferred current report rate.

---

## 3. Highlighted estimated bank exchange rate

The yellow highlighted section shows:

```text
Estimated BOC exchange rate = current report rate + 0.0201
```

Example:

```text
Google Finance current rate: 4.8481
Estimated BOC exchange rate: 4.8481 + 0.0201 = 4.8682
```

The page clearly states whether the calculation is based on:

```text
Google Finance
```

or

```text
Frankfurter fallback
```

This value is only an estimate. The actual exchange rate should always be checked in the bank app, online banking, or counter system before making a transaction.

---

## 4. Anti-abuse and refresh protection

To avoid excessive data fetching, the app includes several protection mechanisms.

### 4.1 Report update is disabled by default

When the app is opened, `report update` is off by default.

If report update is off:

```text
The page does not auto-refresh
The app does not automatically generate new in-app reports
The app only displays the current cached state
```

### 4.2 Minimum update interval is 2 hours

The report update interval has a hard minimum:

```text
notify_interval_hours >= 2
```

The UI does not allow values below 2 hours.

The backend also enforces this rule:

```python
interval_hours = max(2.0, float(cfg.get("notify_interval_hours", 2)))
```

If an old configuration contains a value below 2 hours, the app automatically treats it as 2 hours and displays a red warning.

### 4.3 Streamlit cache protection

External data fetching is cached with a minimum TTL of 2 hours.

This means:

```text
Repeated page refreshes do not repeatedly scrape Google Finance
Manual browser refresh does not trigger high-frequency fetching
Report update cannot run more frequently than the configured interval
```

The default behavior is conservative to reduce unnecessary requests.

---

## 5. App features

The current version supports:

```text
AUD/CNY current report rate
Google Finance current-rate source with Frankfurter fallback
Estimated BOC exchange rate highlight
Target exchange amount
Cost impact calculation
User-defined attention threshold
Historical 30/90/180/365-day window
Low/high historical percentile lines
In-app report cards
Weekend pause option
Custom report update time window
Minimum 2-hour report update interval
```

---

## 6. How to run locally

### 6.1 Enter the project folder

```bat
cd /d C:\0_Levia\0_Code\MiniProject\exchange_rate_reporter_app
```

### 6.2 Activate the conda environment

```bat
conda activate exchange
```

### 6.3 Run the app

```bat
streamlit run app.py
```

The local app usually opens at:

```text
http://localhost:8501
```

---

## 7. Files included

```text
app.py
rate_service.py
report_logic.py
notification_logic.py
config.example.json
requirements.txt
README.md
```

Do not upload these files/folders to GitHub:

```text
__pycache__/
notification_state.json
config.json
.venv/
```

`notification_state.json` is local runtime state and should not be included in the public repository.

---

## 8. Deploying to Streamlit Community Cloud

The app is deployed from GitHub to Streamlit Community Cloud.

To update the online app, upload or commit the following files to the GitHub repository:

```text
app.py
rate_service.py
report_logic.py
notification_logic.py
config.example.json
README.md
```

If `requirements.txt` has not changed, it does not need to be re-uploaded.

After GitHub is updated, Streamlit Cloud will automatically redeploy the app.

---

## 9. Current limitations

### 9.1 Google Finance is not an official API

Google Finance is used as a relatively up-to-date reference source, but it is not an official JSON API. If the page structure changes, the parser may fail.

The app handles this by falling back to Frankfurter.

### 9.2 The app does not provide financial advice

The app only reports exchange-rate status and cost impact.

It does not provide instructions on whether, when, or how much to exchange.

### 9.3 In-app reports are not phone push notifications

Current reports appear inside the web app.

They are not:

```text
SMS notifications
WeChat notifications
Mobile push notifications
Email alerts
```

The user needs to open the web page to view the report.

---

## 10. Suggested user-facing explanation

A short explanation for family users:

```text
这个网页只用于查看澳币兑人民币的汇率状态。
它会显示当前参考汇率、预计中行换汇汇率、目标金额大约需要多少人民币，以及当前汇率在近期历史中的位置。
本工具不提供换汇建议，是否换汇需要用户自行决定。
```

