# 49家公司历史估值数据库

## 状态

**首轮公开历史估值抓取与交易日历清洗已完成；当前数据库属于“已有真实历史样本、但未达到49家公司三项指标全部完整”的研究版。** 截至2026-10-30，东方财富覆盖44/44只A股，89,695条日频记录；百度股市通经XSHG/XHKG交易日历过滤后保留14,907条记录，其中36/44只A股取得2018年前PE/PB，港股5/5只取得PE/PB。两源合并读取104,602条日频记录，生成8,993条月度记录，49/49只证券至少有一项历史数据。百度PS探测无有效返回；港股PS五家公司均为空。BaoStock因登录网络错误10002007取得0条记录，亿牛网港股备用补段本轮0条。月末时点质量仍须分别查看普通月内最后观测、距月末不超过5个交易日、精确月末三种口径；当前普通口径10年分位覆盖PE 10家、PB 12家、PS 0家，严格不超过5个交易日口径仅PE/PB各1家，精确月末口径10年三项均为0家。逐股数据与缺口见 [数据源与缺口审计](source-gap-assessment.md)。

- 发行人：49家
- 当前主证券：44只A股 + 5只港股
- 目标期间：2006-01 至 2026-10；各证券实际起点由供应商历史记录决定，公司上市前不补造数据
- 频率：每月最后一个有数据的交易日
- 指标：PE-TTM、PB、PS-TTM
- 统计窗口：最近60个日历月、120个日历月；5年/10年分别必须有完整60/120个有效月度观测，否则分位留空
- 原则：保留上市地币种、证券代码、原始日期、数据源与来源链接；负PE不进入PE分位；没有可靠数据时留空

## 证券口径

universe.json 冻结49家公司的主证券代码。对同一发行人存在A/H或ADR多地上市的情况，主证券与其他上市证券分开保存。不得把A股价格、港股价格、每股收益或估值序列拼在一起。需要研究另一上市地时，应增加独立 security 记录，而不是覆盖主证券。

## 数据源策略

### A股：直接使用网上公开历史数据（首批44家）

**2018年至今主源：东方财富数据中心 RPT_VALUEANALYSIS_DET，由 AKShare 的 stock_value_em 接口封装。**

AKShare 最新估值文档说明，stock_value_em(symbol) 可按单只A股代码获取全部历史估值记录，字段包含交易日期、收盘价、PE(TTM)、PE(静)、PB(MRQ)、PS(TTM)、市值等；接口底层为东方财富 Data Center，数据集为 RPT_VALUEANALYSIS_DET。本项目直接请求其公开 JSON 数据接口，不要求 Tushare 积分或个人 Token。
- AKShare 官方文档：https://akshare.akfamily.xyz/data/stock/stock_valuation.html （搜索“个股估值 / stock_value_em”）
- 东方财富个股估值页面示例：https://data.eastmoney.com/gzfx/detail/600887.html
- 接口实现参考：https://docs.rs/adaq-data-stock-cn/latest/src/adaq_data_stock_cn/stock/indicator.rs.html （RPT_VALUEANALYSIS_DET 请求参数与字段映射）
- 原始字段：PE_TTM、PB_MRQ、PS_TTM、CLOSE_PRICE、TRADE_DATE
- 口径：日频；下载后按每月最后一个有效交易日聚合。PE 为负值/亏损期保留在原始文件，但不纳入正PE历史分位。PB 使用 MRQ；PS 使用 TTM。

已完成首轮线上验证：44/44家A股成功，89,695条日频记录，生成4,446条月度记录，失败0家（此处仅指东方财富来源）。该公开接口的实际回溯起点为2018-01（新上市公司按上市日期起算），不等于目标区间2006年。GitHub Actions 每月自动更新东方财富段，并可手动运行。

脚本与工作流：
- scripts/fetch_eastmoney_a_share_valuation.py：从东方财富公开 JSON 接口抓取44只A股历史估值
- scripts/build_valuation_history.py：日频聚合月频、分位计算、缺口审计
- .github/workflows/refresh-valuation-history.yml：每月自动更新

**数据限制：** 东方财富个股估值页的历史长度取决于个股上市时间及上游返回记录数；本项目按上游可得历史记录入库，不对上市前月份补值。数据源为公开金融信息服务，不等同于交易所原始公告；建议对异常值及关键证券与第二来源抽样核验。


### A股历史回补：BaoStock（目标2015—2017）

为延长历史区间，已新增 BaoStock 官方公开日频接口作为2017年及以前的回补源。官方 Python API `query_history_k_data_plus` 支持 `peTTM`、`pbMRQ`、`psTTM` 与收盘价字段；无需个人 Token。
- 官方文档：https://github.com/baostock/baostock/blob/master/docs/pythonAPI.md
- 官方项目：https://github.com/baostock/baostock
- 下载脚本：`scripts/fetch_baostock_a_share_valuation.py`
- 回补区间：2015-01-01 至 2017-12-31；实际起点以每只股票上游返回的记录为准

自动更新任务先读取BaoStock已有数据（仅手动workflow_dispatch会尝试重新抓取），再运行百度补充源，最后抓取东方财富2018年至今数据，合并时保留每行来源。百度脚本对BaoStock已有同日记录跳过处理，尽量避免来源冲突；A股百度数据仅保留2018年前，东财仍负责2018年至今。若实际来源仍有同日冲突，构建程序会停止，不静默覆盖。BaoStock没有返回的早期月份保持缺失，不按日/月股价或年度财务指标插值。

**实测结果：** BaoStock已在2026-10-30首轮自动任务中按预期跳过（该数据源只在手动workflow_dispatch尝试）；此前手动抓取审计显示登录错误10002007、0条日频记录。未成功获取的2015—2017月份保持空白，不能把2006-01目标起点当作已实现覆盖。


### 新增公开回补源：百度股市通（A股 + 港股）

AKShare公开接口封装了百度股市通个股估值历史：
- A股：`stock_zh_valuation_baidu`，支持“市盈率(TTM)”“市净率”，周期选择包括“全部”；
- 港股：`stock_hk_valuation_baidu`，支持“市盈率(TTM)”“市净率”，周期选择包括“全部”；
- 接口文档：https://github.com/akfamily/akshare/blob/master/docs/data/stock/stock_valuation.md
- A股接口实现：https://github.com/akfamily/akshare/blob/master/akshare/stock/valuation/stock_zh_valuation_baidu.py
- 港股接口实现：https://github.com/akfamily/akshare/blob/master/akshare/stock/valuation/stock_hk_valuation_baidu.py

抓取脚本：`scripts/fetch_baidu_valuation_history.py`。使用公开接口请求“全部”历史；A股仅输出2018-01-01之前的记录，避免与东方财富2018年至今的主序列重复；港股保留每只主证券自接口最早返回日起的记录。与BaoStock同日记录冲突时跳过百度该日，以免重复覆盖。原始来源、请求周期、每只证券/指标的行数、起止日期和错误均记录在 `raw/baidu-fetch-audit.json`。

**重要口径限制：** 百度股市通官方文档只列PE-TTM和PB；抓取脚本额外探测“市销率(TTM)”和“市销率”标签，但不把接口能力当成事实。只有API确实返回可解析的日期与数值才写入PS；否则PS列保持空值，不从其他指标推算。港股5家公司分别使用港股代码、HKD口径和独立序列，绝不与其A股/ADR混接。接口支持“全部”只是文档能力；能否返回完整历史、实际起点和缺失日期以每次抓取审计为准。百度抓取已接入自动任务；当前首次运行编号与实际返回状态请以GitHub Actions及 baidu-fetch-audit.json 为准。在逐证券审计生成前，不宣称补齐了2015年前后或任何港股公司的完整覆盖。

### 公开估值百分位交叉核验：百分位（baifenwei.com）

百分位网站的公开说明显示：其横截面估值表覆盖5,317只A股，数据快照更新至2026-10-30；单股查询页面本地预生成了300只大市值股票近10年估值曲线，其他股票会尝试实时查询近10年估值。可用于逐公司核验当前PE/PB/PS百分位或交叉比较，但公开页面不等于可批量下载原始月度PE/PB/PS序列，因此本项目不将该网站百分位直接拼进月度历史数据库。
- 单股查询：https://baifenwei.com/stocks/
- 全市场估值百分位表：https://baifenwei.com/stocks/valuation-table/
- 核验口径：记录查询日、股票代码、指标、样本覆盖说明；只有取得可下载的真实月度原始数列后，才进入正式历史估值CSV。
### 港股公开网页样本核验（可见数据不等于可免费批量导出）

已核实 GuruFocus 的个股页面可展示部分港股日频 PE-TTM 历史：
- 申洲国际 02313：页面显示自2005年至今的日频PE历史；
- 腾讯控股 00700：页面显示自2004年至今的日频PE历史；
- 阿里巴巴 09988：页面显示自2019年至今的日频PE历史；
- 京东集团 09618：页面显示自2020年至今的日频PE历史。
以上页面均提示完整历史数据导出需免费试用/订阅；公开搜索页面当前仅显示部分样本，因此不能据此宣称已取得完整原始CSV。哔哩哔哩 09626 的公开估值页面目前展示年度/季度历史PE数据，不足以构成完整月度序列。
- 申洲国际：https://www.gurufocus.com/stock/HKSE%3A02313/data/pe-ratio
- 腾讯控股：https://www.gurufocus.com/stock/HKSE%3A00700/data/pe-ratio
- 阿里巴巴：https://www.gurufocus.com/stock/HKSE%3A09988/data/pe-ratio
- 京东集团：https://www.gurufocus.com/stock/HKSE%3A09618/data/pe-ratio
- 哔哩哔哩：https://www.gurufocus.com/term/pe-ratio/HKSE%3A09626

### 港股：5家公司单独维护，暂不混用A股源

当前49家研究池中有5家主证券为港股：申洲国际、腾讯控股、阿里巴巴、京东集团、哔哩哔哩。东方财富 stock_value_em 的个股历史估值接口按A股证券代码查询，不能将它直接用于港股。现加入百度股市通港股接口作为公开PE-TTM/PB补充源，逐只按港股代码独立抓取；另加入亿牛网历史图表端点作为百度最早有效日期以前的后备补段。港股PS-TTM只有在百度/亿牛网未文档化探测真正返回日期和数值时才入库，否则仍为空。

可用的线上来源：
1. **理杏仁港股历史估值API**：提供PE-TTM、PB、PS-TTM的日数据及5/10年分位统计，但需要用户专属Token。文档：https://www.lixinger.com/api/open-api/html-doc/hk/company/fundamental/security
2. **亿牛网 Enniu（历史补充备选）**：AKShare公开实现显示可从 `https://eniu.com/chart/peh/hk{代码}` 与 `pbh` 读取港股PE/PB历史JSON；AKShare文档明确提示该数据源暂未更新。本项目仅保留严格早于百度最早有效日期的记录，不覆盖较新百度数据。另探测 `psh`，未返回真实带日期数据前不计入PS覆盖。接口实现：https://github.com/akfamily/akshare/blob/master/akshare/stock/valuation/stock_a_indicator.py 。
3. **GuruFocus**：公开个股页面展示历史PE等日频估值历史，但批量导出/下载权限及使用限制需以其账户和许可规则为准。示例：https://www.gurufocus.com/stock/HKSE%3A00700/data/pe-ratio
4. **StockAnalysis / Macrotrends**：可用来交叉核验部分港股/ADR的年度或季度估值历史，但不能把这些低频样本伪装成完整月度序列。示例：https://stockanalysis.com/quote/hkg/2313/financials/ratios/ 、https://www.macrotrends.net/stocks/charts/BABA/alibaba/price-book

在百度接口首次实测并核验数据之前，港股5家公司仍按“等待数据源验证”处理，不得写成已取得完整历史序列；即使取得PE/PB，PS仍然是独立缺口。不混用A股、ADR与港股交易价格，也不以年度报告比率插值出月度值。

### 付费/授权备选

- TuShare daily_basic 提供A股日频 pe_ttm、pb、ps_ttm，但需要至少2000积分；官方文档：https://tushare.pro/document/2?doc_id=32
- BigQuant cn_stock_valuation 提供A股日频PE/PB/PS及公告日财务口径，但数据下载和再发布须符合平台权限与许可：https://bigquant.com/data/datasources/cn_stock_valuation
- 不将上述需授权数据与免费来源无标识混接；如改用付费源，应在每行保留供应商和口径。

**Token 安全：** 任何第三方Token只放在GitHub Actions Secrets或本地环境变量中；禁止写入公开代码、网页JavaScript、CSV或日志。当前A股Eastmoney公开数据抓取不需要Token。

## 统一输入CSV

将供应商日频导出整理为 raw/daily-valuation.csv，UTF-8或UTF-8-SIG，至少包含：

| 列 | 含义 |
|---|---|
| code | 主证券代码，例如 600887.SH、02313.HK |
| date | 实际交易日，YYYY-MM-DD 或 YYYYMMDD |
| peTtm | PE-TTM；亏损/无意义值留空 |
| pb | PB |
| psTtm | PS-TTM |
| close | 当日收盘价（可空） |
| currency | 证券交易币种 |
| source | 数据供应商与数据集名称 |
| sourceUrl | 对应来源/接口文档/下载页面 |

脚本也识别常见供应商字段别名：ts_code / stockCode、trade_date、pe_ttm、ps_ttm、sp。若行内没有 source 和 sourceUrl，运行时必须用参数提供，确保数据可追溯。

## 生成月度序列

在本仓库根目录运行（支持多个来源文件，按证券与日期合并）：

~~~bash
python scripts/build_valuation_history.py \\
  --input data/valuation-history/raw/baostock-pre2018-daily.csv \\
  --input data/valuation-history/raw/baidu-valuation-history.csv \\
  --input data/valuation-history/raw/eastmoney-a-share-daily.csv \\
  --out-dir data/valuation-history/generated
~~~

生成：
- valuation-monthly.csv：每只主证券每月最后一条实际交易记录，以及PE/PB/PS滚动分位和P20/P50/P80估值带
- coverage-audit.json：逐证券起止日期、月度样本量、缺月、无效值、估值分位覆盖、来源及审计状态

脚本只做日频转月频、字段清洗、滚动分位和缺口审计，不会填充缺失月份、不做线性插值、不把负PE替换为正值。

## 分位算法

对某指标当前值 x_t，窗口内有效值为 x_1,...,x_N：

P(x_t) = 100 × [计数(x_i < x_t) + 0.5 × 计数(x_i = x_t)] / N

- 5年：当前月及此前59个日历月；有效样本必须达到60个
- 10年：当前月及此前119个日历月；有效样本必须达到120个
- P20/P50/P80阈值使用线性插值分位数，和“当前值处于历史分位”的百分比不是同一个概念
- PE仅接受正值；亏损时PE为空。PB、PS也仅对正且可解释的口径计算
- 上市不足5年或10年的公司，不输出对应完整窗口分位；可以单独展示“上市以来分位”，但不得冒充5年/10年分位

## 如何连接行业估值与买入价

| 公司类型 | 主估值模型 | 历史倍数的用途 | 买入价连接方式 |
|---|---|---|---|
| 成熟消费 / 高质量制造 | 正常化EPS、FCF、DCF交叉验证 | 在盈利质量稳定时使用PE分位作倍数参考 | 正常化EPS × 历史PE P20/P50/P80，再乘安全边际 |
| 银行 | PB-ROE、股利折现 | PB分位用于校验，不替代可持续ROE和资本成本 | BVPS × 历史PB分位，结合ROE/COE、资产质量调整 |
| 券商 | PB-ROE + 中周期盈利 | PB与周期位置交叉验证 | BVPS × 合理PB；同时用中周期ROE、资本约束复核 |
| 保险 | EV/NBV、内含价值分部估值 | PE/PB只作观察，不直接作为核心定价倍数 | 每股内含价值/新业务价值 × 经验证倍数 |
| 周期行业 | 完整周期正常化利润、EV/EBITDA、资产价值 | 历史PE通常反周期，不自动映射买入价 | 正常化EPS × 独立设定的中周期倍数；用PB/资产负债表辅助 |
| 成长科技 | 多阶段DCF、SOTP | PE仅在稳定盈利后作交叉检查；PS需利润率校准 | DCF情景价值 × 安全边际，不用历史PE机械定价 |
| 公用事业 | 股息折现、DCF | PE/PB为合理性校验 | 可持续DPS / (股权成本 - 长期增长)，并校验净债务和资本开支 |

**特别注意：** 低历史分位不等于低估。若ROE、增长率、盈利周期、资本结构、监管环境或商业模式已发生变化，历史倍数必须进行结构性调整。模型产生的是情景区间，不是市场事实或收益保证。

## 发布门槛

一个证券在满足以下条件前，不写回正式 china-stocks-financial-valuation.json：
1. 月度日期唯一且按交易日排序；
2. 价格、PE、PB、PS均明确来自同一证券；
3. 财务口径为点时披露，不能前视；
4. 5年/10年分位达到有效样本门槛；
5. 价格币种、供应商、来源URL、最后观测日期齐全；
6. 对停牌、亏损、负净资产、上市时间不足及重大业务变化有明确标记。

本目录当前 raw/baidu-valuation-history.csv 与 raw/baidu-fetch-audit.json 已包含百度股市通实测返回的原始历史与逐证券逐指标审计，不再是空表头占位文件。generated/valuation-monthly.csv 与 generated/coverage-audit.json 是两源合并后的月度库及质量审计。任何未返回指标仍保持空值；generated/ 中不得填入模拟历史值。完整现状和逐证券缺口见 [source-gap-assessment.md](source-gap-assessment.md)。
