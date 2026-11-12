# 恒生指数官方总收益数据：授权获取与数据审计

**审计日期：2026-11-12**  
**目标序列：恒生指数 Gross Total Return Index，优先核验 Reuters .HSIDV / Bloomberg HSIRH 对应的官方毛总收益序列。**

## 1. 研究用途与目标数据规格

| 项目 | 要求 |
|---|---|
| 指数 | Hang Seng Index Gross Total Return Index（HSI TRI） |
| 代码候选 | Reuters .HSIDV；Bloomberg HSIRH（需恒生确认当前有效代码及vendor symbology） |
| 备选 | Net Total Return：Reuters .HSIDVN / Bloomberg HSINH，仅作交叉核验 |
| 目标区间 | 2006-01 至 2026-10 |
| 首选频率 | 日收盘指数点位；若报价/许可限制，则至少提供月末收盘点位 |
| 币种 | HKD |
| 计算要求 | 官方总收益指数，现金股息按指数方法再投资；保留原始指数点位 |
| 交付格式 | CSV/XLSX，附字段说明、指数方法版本、数据修订规则、许可用途范围 |
| 研究整合 | 月末最后交易日取值，计算月度总收益；按现有HKD/USD与USD/CNY月度汇率换算为人民币收益 |

## 2. 官方来源核验

1. 恒生指数公司说明，TRI同时计入价格变化与现金股息，并假设股息按成分股市值权重再投资。官方说明：https://www.hsi.com.hk/index-resources/total-return-index-series/
2. 恒生数据可用性文件（2025-11-07生效）列出Gross Total Return Index历史数据：恒生指数日收盘数据可用起点为2004-10-11；该文件的日收盘数据价格栏标示HK$1,000 / consecutive 5 years。目标2006-01至2026-10在可用起点之后，但实际订购范围、分段计费和当前库存仍须书面确认。文件：https://www.hsi.com.hk/static/uploads/contents/en/products/data_subscription/pdf_eng.pdf
3. 恒生Index360介绍其平台可下载指数历史数据、表现摘要和基本面数据；需注册后确认HSI Gross TRI是否在账户产品权限内、历史区间是否完整：https://www.hsi.com.hk/en-hk/index360/
4. 恒生数据分析与解决方案页面区分指数数据订阅和指数数据许可（包括内部使用、数据传播等用途）：https://www.hsi.com.hk/solutions/data-analytics/

## 3. 授权边界（关键）

恒生指数家族使用指引说明，指数信息提供给信息供应商/终端用户的用途限于内部使用；如需向其他人进一步传播，须与Hang Seng Indexes Company Limited另行签署许可协议。公开GitHub仓库和公开网页展示原始指数点位/CSV属于需要特别核实的传播场景，不能默认个人订阅就包含公开再分发权。

官方指引：https://www.hkex.com.hk/-/media/HKEX-Market/Services/Market-Data-Services/Real-Time-Data-Services/Data-Licensing_/HKEX_IS-Guiding-Note/Guiding-Note-on-Use-of-Hang-Seng-Family-of-Indexes-%28v202304%29.pdf

采购询价必须分开问清：
- 个人/研究用途的内部使用许可；
- 将原始历史指数点位保存于私人研究环境的权利；
- 在公开GitHub Pages展示原始数据、下载CSV或对外提供API的再分发许可；
- 若不允许再分发，是否可公开展示基于该数据计算的汇总统计、图表和回测结果，以及是否需要注明来源/许可编号。

未经书面许可前，不将官方HSI TRI原始历史数据提交到公开仓库；可在私人环境研究，公开页面继续使用明确标注的2800.HK ETF代理或只发布获准的汇总结果。

## 4. 正式申请路径

**路径A：恒生Index360自助平台**
1. 打开 https://www.hsi.com.hk/en-hk/index360/ 并注册。
2. 搜索 Hang Seng Index / Gross Total Return Index，核对代码、币种、日收盘历史数据选项。
3. 检查可下载历史区间是否覆盖2006-01至2026-10，下载样例并核对字段/日期/股息口径。
4. 在付款前保存产品规格、样例文件、报价和许可条款。

**路径B：直接向恒生指数公司询价**
- 官方数据订阅/数据许可入口：https://www.hsi.com.hk/solutions/data-analytics/
- 恒生当前数据与分析页面公布的联系号码：+852 2877 0704；邮箱：info@hsi.com.hk。
- 询价邮件主题建议：Historical HSI Gross Total Return Index Data (2006-01 to 2026-10) – Personal Research and Website Display Licence
- 询价内容：确认Reuters .HSIDV / Bloomberg HSIRH是否为当前对应代码；报价日频/月底数据；确认HK$1,000 / 连续5年报价单位的适用性、最小订购区间、交付格式、历史修订、内部研究与公开再分发的分别许可费用。

**路径C：HKEX Data Marketplace**
- 官方说明历史数据产品可通过HKEX Data Marketplace目录订购；如目录没有所需产品，可邮件联系协助：https://www.hkex.com.hk/Global/Exchange/FAQ/Market-Data?sc_lang=en
- 联系：datamarketplace@hkex.com.hk。
- 对恒生指数家族数据，仍应向指数编制方确认相应许可，不要假设通过交易所数据平台购买就自动获得指数再分发许可。

## 5. 可直接发送的询价邮件

**Subject:** Historical HSI Gross Total Return Index Data (2006-01 to 2026-10) – Personal Research and Website Display Licence

Dear Hang Seng Indexes Data Team,

I am conducting a long-term RMB-based asset-allocation and portfolio backtesting research project. I would like to obtain the official Hang Seng Index Gross Total Return Index history for January 2006 to October 2026.

Could you please confirm:

1. The current Reuters and Bloomberg identifiers for the Hang Seng Index Gross Total Return Index (previously referenced as .HSIDV and HSIRH), and the corresponding Net Total Return identifiers if available.
2. Whether daily closing index levels are available for the full requested period, and whether a month-end historical extract is available as a lower-cost alternative.
3. The available file formats, fields, index currency, dividend-reinvestment convention, methodology/version history and any adjustment or revision policy.
4. The applicable subscription price and whether the published HK$1,000 per consecutive five-year data period applies to this TRI series and requested historical range.
5. The licence terms and fees separately for (a) personal/internal research and backtesting, (b) retaining the raw data in a private research environment, and (c) displaying or distributing raw index levels/CSV files through a public GitHub Pages research website.
6. If public redistribution is not available, whether derived performance statistics, charts and backtest results may be published, and what attribution or restrictions apply.

Please also provide a sample file, product specification and the relevant licence agreement before purchase.

Kind regards,

Investment Research Project

## 6. 当前数据状态

| 数据项 | 当前状态 | 可用于正式回测？ |
|---|---|---|
| 官方HSI Gross TRI原始序列 | 未取得 | 否 |
| 2800.HK调整后总回报代理（人民币换算） | 225个月，2008-02至2026-10 | 仅临时代理 |
| HKD/USD月均汇率 | 250个月，2006-01至2026-10 | 可用于当前月度交叉换算 |
| 公开展示/再分发许可 | 未申请、未确认 | 不得默认允许 |

**审计结论：**官方数据的获取路径已经明确为Index360订阅、恒生指数公司直接询价、HKEX Data Marketplace三条路径。当前阻塞点是确认目标Gross TRI的历史交付范围、价格和许可范围。拿到样例与书面许可后，再入库、做逐月缺失审计并替换2800.HK代理。


## 7. 官方可用性与联系方式复核（2026-11-12）

恒生《Notes on Data Availability》（生效日2025-11-07）第8页“Gross Total Return Index”部分，明确列示：
- Hang Seng Index：Daily Close data available from 11 Oct 2004；
- 同表标价：HK$1,000 / consecutive 5 years；
- 因而2006-01至2026-10的目标区间在官方标注的数据可用起点之后，按连续5年计费需要至少覆盖四个连续5年区段及最后不足5年的区段，实际如何计价必须向恒生确认，不能自行推算最终报价。
- Reuters .HSIDV / Bloomberg HSIRH仍是待恒生确认的vendor代码，不是该可用性文件中的官方产品代码。

当前官方联系信息以恒生数据与分析页面为准：+852 2877 0704，info@hsi.com.hk；服务时间为香港时间周一至周五08:45–18:00（公众假期除外）。数据订阅页面将历史数据订阅与数据传播许可分列，采购时必须分别核对内部研究和公开展示许可。
