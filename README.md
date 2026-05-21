# 汇率状态提醒 App

这是一个面向留学生家庭的轻量型汇率状态报告工具，主要用于辅助查看 **AUD/CNY（澳币/人民币）** 的汇率状态。

当前在线版本：

```text
https://exchange-rate-reporter.streamlit.app/
```

---

## 1. 产品定位

本工具不是交易软件，也不提供换汇建议。

它只报告：

```text
当前参考汇率
预计中行换汇汇率
目标金额下的大致人民币成本
当前汇率在近期历史中的位置
是否触达用户自己设置的关注阈值
```

最终是否换汇，由用户自行决定。

---

## 2. 当前数据源设计

本 App 将 **当前 report 汇率** 和 **历史 report 数据** 分开处理。

### 2.1 当前 report 汇率

当前 report 汇率使用：

```text
Google Finance 优先
如果 Google Finance 读取失败，则 fallback 到 Frankfurter
```

AUD/CNY 的 Google Finance 页面为：

```text
https://www.google.com/finance/quote/AUD-CNY
```

使用 Google Finance 的原因是：它提供的 AUD/CNY 当前参考值相对更接近常见财经页面，例如百度财经，因此更适合作为 report 当前汇率。

但需要注意：

```text
Google Finance 不是官方 JSON API
```

因此，本 App 是通过解析 Google Finance 页面来读取当前汇率。如果 Google 修改页面结构，解析可能失败。因此，App 保留 Frankfurter 作为 fallback。

如果 Google Finance 成功读取，页面会显示：

```text
Report 当前汇率来源：Google Finance
```

如果 Google Finance 读取失败，页面会显示：

```text
Report 当前汇率来源：Frankfurter
```

---

### 2.2 Historical report / 历史数据

历史 report 和历史分位数计算使用：

```text
Frankfurter 日频历史数据
```

它用于：

```text
30 / 90 / 180 / 365 天历史窗口
低位参考线
高位参考线
当前汇率历史位置
历史走势图
```

Frankfurter 是日频数据，因此适合做历史趋势和历史位置判断，但不作为当前 report 汇率的优先来源。

---

## 3. 黄色高亮：预计中行换汇汇率

页面顶部黄色高亮区域显示：

```text
预计中行换汇汇率 = 当前 report 汇率 + 0.0201
```

例如：

```text
Google Finance 当前汇率：4.8481
预计中行换汇汇率：4.8481 + 0.0201 = 4.8682
```

页面会明确标注该计算基于：

```text
Google Finance
```

或：

```text
Frankfurter fallback
```

这个数值只是估算参考，不是银行官方实时成交价。真正换汇前，应以中国银行 App、网银、智能柜台或柜台实际显示的成交汇率为准。

---

## 4. 防滥用与刷新保护机制

为了避免频繁抓取 Google Finance 页面，v6 版本加入了保护机制。

### 4.1 Report update 默认关闭

打开网页时，`report update` 默认关闭。

当 report update 关闭时：

```text
页面不会自动刷新
不会自动生成新的 App 内 report
不会因为网页持续打开而反复抓取数据
```

页面只展示当前缓存状态。

---

### 4.2 Report update 最低间隔为 2 小时

Report update 的最小间隔被硬性限制为：

```text
notify_interval_hours >= 2
```

UI 不允许选择低于 2 小时的值。

后端也进行了强制保护：

```python
interval_hours = max(2.0, float(cfg.get("notify_interval_hours", 2)))
```

如果旧配置中保存过低于 2 小时的值，App 会自动按 2 小时处理，并显示红色提示。

---

### 4.3 Streamlit cache 保护

外部数据读取使用 Streamlit cache，并设置至少 2 小时的缓存 TTL。

这意味着：

```text
用户手动刷新浏览器，不会导致高频抓取
页面 rerun 不会重复抓取 Google Finance
report update 不可能低于 2 小时触发
```

当前版本采用保守策略，以减少对外部页面的请求频率。

---

## 5. 当前功能

当前版本支持：

```text
AUD/CNY 当前 report 汇率
Google Finance 当前汇率来源
Frankfurter fallback
预计中行换汇汇率高亮
目标换汇金额设置
目标金额下的大致人民币成本
用户自定义关注阈值
历史窗口设置：30 / 90 / 180 / 365 天
低位 / 高位历史分位线
App 内 report 卡片
周末不提醒选项
自定义 report update 时间窗口
最低 2 小时 report update 间隔
```

---

## 6. 本地运行方法

### 6.1 进入项目文件夹

```bat
cd /d ...\exchange_rate_reporter_app
```

### 6.2 激活 conda 环境

```bat
conda activate exchange
```

### 6.3 启动 App

```bat
streamlit run app.py
```

本地页面通常会打开在：

```text
http://localhost:8501
```

---


## 7. 当前限制

### 7.1 Google Finance 不是官方 API

Google Finance 用于提供相对实时的当前参考汇率，但它不是官方 JSON API。

如果 Google 修改页面结构，解析可能失败。

本 App 通过 Frankfurter fallback 保证页面仍然可用。

---

### 7.2 本工具不提供金融建议

本工具只展示汇率状态、历史位置和目标金额下的成本影响。

---

### 7.3 App 内 report 不是手机推送

当前 report 只显示在网页 App 内；用户需要打开网页查看 report。



