# Investment Lab V2.5 — 数据口径与研究方法

## 1. 研究边界

月度矩阵覆盖 2006-01 至 2026-10，共 250 个自然月。回测使用所有研究组合资产均有有效收益的共同完整样本，当前为 2006-01 至 2026-07，共 241 个月。未观测月份保持空白；不以前值填充、不把缺失收益当作 0。

本报告的策略权重是为了先跑通可复现研究而设置的**临时代理组合**，不是用户已批准的最终投资政策：
- A股沪深300全收益代理：20%
- 美国股票 S&P 500 总回报：12%
- 美国以外发达市场 EFA：10%
- 新兴市场 EEM：10%
- 美国综合债券 AGG：28%
- 黄金人民币估值代理：10%
- 人民币现金 H11025：10%

股票合计52%、债券28%、黄金10%、现金10%。但 EEM 含中国/台湾敞口，AGG 是美国综合债券ETF而非中债财富指数，港股HSIDV缺失；因此此结果不能作为最终地区配置建议或真实可投资组合收益。

## 2. 原始序列与数据来源

| 序列 | 原始字段/来源 | 口径与限制 |
|---|---|---|
| 沪深300价格、全收益指数水平 | [CSI300 index-level archive](https://raw.githubusercontent.com/dongzhaohe321418-lab/csi300-spmo-index/main/output/performance/index_levels.csv) | 含 CSI300 与 CSI300_TR；需将其视为公开归档数据，非交易产品净值 |
| S&P 500总回报 | [SP500TR monthly archive](https://raw.githubusercontent.com/vanexymx/sp500-historical-analysis/main/data/SP500TR_monthly.json) | 美元总回报指数月度水平 |
| 黄金美元价格 | [World Bank Pink Sheet monthly archive](https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv) | 美元/金衡盎司月均价；非黄金基金可投资总回报 |
| USD/CNY | [Monthly exchange-rate archive](https://raw.githubusercontent.com/datasets/exchange-rates/main/data/monthly.csv) | China、CNY per USD，月均口径；归档源标注为Fed G.5 |
| AGG/IEF/SHY/FXI/EFA/EEM | [Yahoo adjusted ETF monthly-return archive](https://raw.githubusercontent.com/HerdingAI/stock-price-returns/main/output/monthly_returns_by_ticker.csv) | Yahoo自动复权ETF月收益代理；并非指数官方总回报，受数据归档与Yahoo条款约束 |
| H11025现金 | [中证指数官网](https://www.csindex.com.cn/) / [H11025详情](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H11025factsheet.pdf) | 官方货币基金全收益指数；基日2005-12-30，发布日期2016-08-31，发布日期前是回溯历史 |
| 511010国债ETF | [Yahoo Finance 511010.SS](https://finance.yahoo.com/quote/511010.SS/history/) | 自动复权日收盘价取月末；2013年后代理，不等于中债财富指数 |
| 2800.HK盈富基金 | [Yahoo Finance 2800.HK](https://finance.yahoo.com/quote/2800.HK/history/) | 自动复权ETF总回报代理；不等于恒生官方HSIDV总股息累计指数 |
| 中债综合财富指数CBA00201 | [中国债券信息网](https://www.chinabond.com.cn/) | 公开接口当前返回HTTP 405，未落库；数据授权和再分发权限仍需确认 |
| 港元兑美元 | [FRED EXHKUS](https://fred.stlouisfed.org/data/EXHKUS) | 美联储G.5月均 HKD per USD；2006-01至2026-10共250个月，原始序列存于 `data/sources/fred-exhkus-monthly.csv` |

## 3. 指数水平到月收益

对于具有连续月末指数水平的序列：
`r_t = I_t / I_{t-1} - 1`

- 沪深300价格收益使用 CSI300 指数水平；全收益使用 CSI300_TR。
- S&P 500总回报使用美元总回报指数水平。
- H11025、CBA00201和511010若有连续月末指数/复权净值，也按上述方式计算。
- Yahoo ETF月收益归档已经是月收益率，不重复从价格再计算。

## 4. 人民币换算

美元资产人民币收益：
`r_CNY,t = (1 + r_USD,t) × (USD/CNY_t ÷ USD/CNY_(t-1)) - 1`

黄金人民币月均估值：
`Gold_CNY,t = Gold_USD_oz,t × USD/CNY_t`
`r_Gold_CNY,t = Gold_CNY,t ÷ Gold_CNY,(t-1) - 1`

港元资产人民币收益（本轮已用于2800.HK代理）：
`r_CNY,t = (1 + r_HKD,t) × (USD/CNY_t ÷ USD/CNY_(t-1)) × (HKD/USD_(t-1) ÷ HKD/USD_t) - 1`

注意 EXHKUS 单位为 HKD per USD，不能误用倒数方向。

## 5. 策略回测

- 买入持有：初始权重买入后自然漂移，不主动再平衡。
- 年度再平衡：每年1月恢复目标权重。
- 阈值再平衡：任一资产权重相对目标偏离超过5个百分点时恢复目标权重。
- 本轮八档敏感性：单边交易成本10bp；共同样本216个月，2008-02至2026-07。
- 年化收益：`(期末财富/期初财富)^(12/月数)-1`。
- 年化波动：月收益样本标准差乘以 `sqrt(12)`。
- 最大回撤：累计财富相对历史峰值的最大跌幅。
- 最差滚动期：对连续12/36/60/120个月复合收益取最小值。
- 完整样本：要求所有研究组合成分同月均有收益；本轮共同样本由2800.HK港股ETF代理及其他权益代理的可用月份共同决定。

## 6. 50年提款模拟

初始资产400万元；第一年支出8万、9万、10万元三档；支出按年度通胀上调、按月初提取。确定性情景包括3%/5%名义收益配2%通胀，以及4%名义收益配4%通胀；分别测试首月一次性30%资产冲击。

区块抽样先对各资产的联合月收益向量抽取圆形连续12/24/36个月区块，拼接为600个月路径；在每条合成路径上重新执行对应的买入持有/年度/阈值再平衡规则，再计算提款结果。每个策略、支出档、2%/4%通胀和0%/30%早期冲击组合按脚本配置抽样；当前脚本为每种情景100条路径，结果仅作敏感性比较。输出50年存活率、期末资产中位数/P10/P90和耗尽时间中位数。区块抽样是对历史收益序列的重排情景，不代表未来真实概率；历史样本短于50年，结果对起始区间和资产代理敏感。

## 7. 当前不可验收为正式投资决策的缺口

1. 中债查询端点已抓取出CBA00201候选序列，但返回的index ID与CBA00201代码映射、指数名称及数据使用/再分发权仍需中债书面确认。
2. 官方恒生HSI Gross TRI完整历史序列尚未入库；2800.HK只是ETF代理。已单独建立恒生授权获取审计文件。
3. H11025发布前回溯历史不能当成当时真实可投资业绩。
4. 511010仅2013年后；不适合单独支撑2006年以来的完整中国债券回测。
5. 股票52%袖套含EEM，EEM与A股存在中国地域重叠；本轮地区袖套与正式投资产品映射仍有差异。
6. 海外债券袖套使用未做人民币对冲的AGG代理，不能视为目标人民币对冲海外债券的真实收益。
7. 本研究尚未纳入税费、个人税务身份、租金增长、医疗支出冲击及未来新增收入/现金流。
8. 50年bootstrap每个情景当前仅100条路径，属于初筛；候选方案需增加到500–1,000条路径。

## 8. 2026-11-12 数据补齐记录

- FRED EXHKUS月均港元/美元汇率250个月（2006-01至2026-10），单位为HKD per USD。
- 2800.HK自动复权ETF月收益通过月均USD/CNY和HKD/USD交叉汇率转换为人民币收益，225个月（2008-02至2026-10）；不等于恒生官方TRI。
- 中债查询端点抓取成功：日频6,216条（2002-01-04至2026-11-11），抽取月末299个月（2002-01至2026-11）。主矩阵2006-01至2026-10包含250个月的中债财富指数水平和月收益。
- 中债月度原始文件：`data/sources/chinabond-cba00201-monthly.csv`；抓取状态：`data/research/chinabond_fetch_status.json`。中债指数代码映射和再分发权限仍需书面核验。
- 新抓取器会同步更新主矩阵、月度覆盖审计和数据manifest，避免抓取成功但manifest仍显示0条的状态不一致。

## 9. 八档股票权重敏感性新口径

2026-11-12起，新增一套更贴近战略地区配置的敏感性样本：A股、港股、美国、美国以外发达市场、EEM新兴市场代理的52%股票基准袖套权重分别为8%、2%、25%、11%、6%，按比例缩放到52/45/42/38/35/30/25/20八档。港股以2800.HK自动复权ETF人民币总回报代理替代官方恒生TRI，因此共同样本为2008-02至2026-07共216个月。债券袖套本轮已使用中债CBA00201候选财富指数23/28、AGG 5/28；但中债代码映射和许可尚待核验。

港元汇率使用美联储G.5 / FRED EXHKUS月均数据，原始值保存在 `data/sources/fred-exhkus-monthly.csv`；2800.HK人民币换算使用月均 USD/CNY 与 HKD/USD 交叉汇率。官方恒生总收益指数 `.HSIDV`（Reuters）/`HSIRH`（Bloomberg）历史数据仍需向恒生指数公司或授权数据商取得；获取路径与许可边界见 `data/research/hang_seng_tri_license_audit.md`。

### CBA00201官方抓取路径

已从公开AKShare实现中定位到中债官网查询端点 `https://yield.chinabond.com.cn/cbweb-mn/indices/singleIndexQuery`，其“中债-综合指数/财富/总值”查询使用 `CFZS_00` 序列。仓库新增 `scripts/fetch_chinabond_cba00201.py`，由GitHub Actions尝试抓取日频序列并抽取每月最后一个交易日，先保留原始月末指数，再计算月收益；缺少前月时不跨月伪造单月收益。该抓取器尚需CI实测确认返回的指数代码确为CBA00201，并核验中债的数据使用/再分发授权。公开代码实现是技术线索，不替代中债官方数据授权。
