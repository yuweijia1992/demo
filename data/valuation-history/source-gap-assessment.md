# 49家公司历史估值数据源与缺口审计

> 审计日期：2026-10-30。下列统计以仓库当前 `generated/coverage-audit.json` 为准，代表真实抓取、清洗与月度聚合结果，不代表49家公司的三项估值指标全部齐全或已通过最终发布门槛。

## 当前真实数据状态

- 研究池：49只主证券（44只A股、5只港股）；同一发行人的A/H与ADR其他代码不重复计入主证券数。
- 月度估值：参与清洗的日频输入记录 100,724 条，生成 8,942 条月度观测，49/49只主证券至少有一项历史记录。
- 每家公司实际历史起点不同；月度观测记录数量为 51—250 条，不能将“49/49有历史”解释为每家都有完整20年数据。
- 数据源：A股主要来自东方财富（2018年至今）与百度股市通的早期PE/PB补段；港股主证券使用独立港股代码与HKD价格口径。BaoStock登录失败（10002007），本轮未贡献有效数据；百度PS探测未返回有效数据，港股5家公司PS均为空。
- 月度数据保留真实观测；不对缺失月份插值、不向前填充。负PE及无效非正倍数不进入估值分位。
- 当前价格日期、估值观测日期和财报报告期是不同维度，不能把月度估值最后观测日冒充为实时价格或报告期数据。

## 最新5年/10年分位覆盖

分位窗口分别要求最近60/120个日历月且有效样本不少于60/120个。最新审计结果如下：

| 口径 | PE-TTM 5Y | PB 5Y | PS-TTM 5Y | PE-TTM 10Y | PB 10Y | PS-TTM 10Y |
|---|---:|---:|---:|---:|---:|---:|
| 月内最后可得观测 | 41 | 46 | 42 | 20 | 23 | 0 |
| 当前值及窗口样本均要求距月末不超过5个交易日 | 40 | 45 | 42 | 2 | 3 | 0 |
| 当前值及窗口样本均要求恰为最后交易日 | 39 | 42 | 42 | 0 | 0 | 0 |

**月末时点质量：** 共8,942条月度观测，其中严格落在月内最后交易日的5,010条；滞后1—2个交易日869条，3—5个交易日1,137条，6个及以上交易日1,926条（21.5%）。整体P90滞后10个交易日，最大21个交易日。因此“月内最后可得观测”并不总是严格月末价。按严格5个交易日口径，10年PE/PB/PS仅覆盖2/3/0家；精确月末10年覆盖为0/0/0家。

**重要区别：** 上表是从历史月度序列独立计算的审计覆盖。主财务估值JSON中的正式5年/10年分位字段目前仍未回填；不得将独立审计覆盖写成49家公司已拥有正式估值结论。

## 港股5家公司独立审计

港股序列使用港股代码与HKD计价，不与A股或ADR拼接。

| 公司 | 代码 | 月度记录 | 首月 | PE有效月 | PB有效月 | PS有效月 | 缺失月份 |
|---|---|---:|---|---:|---:|---:|---:|
| 腾讯控股 | `00700.HK` | 211 | 2006-01 | 211 | 211 | 0 | 39 |
| 申洲国际 | `02313.HK` | 245 | 2006-01 | 245 | 245 | 0 | 5 |
| 京东集团 | `09618.HK` | 77 | 2020-06 | 71 | 77 | 0 | 0 |
| 哔哩哔哩 | `09626.HK` | 68 | 2021-03 | 15 | 68 | 0 | 0 |
| 阿里巴巴 | `09988.HK` | 84 | 2019-11 | 84 | 84 | 0 | 0 |

结论：
- 腾讯、申洲国际的月度记录起点达到2006年研究区间起点；百度原始页面报告的最早日分别约为2004-06和2005-11，但本项目目标窗口从2006-01开始。
- 阿里巴巴从2019-11开始；京东从2020-06开始；哔哩哔哩从2021-03开始。更早月份属于上市前，不应造数。
- 京东PE有71个有效月、PB有77个有效月；哔哩哔哩PE仅15个有效月，须结合亏损/不可解释的PE空值处理；三家新上市港股均不足10年。
- 港股5家公司当前PS-TTM均为空。百度股市通的公开接口文档与实际返回均只支持PE/PB；亿牛网本轮未补入数据。GuruFocus页面可见部分历史PE曲线，但未取得可免费批量导出的原始三指标月度CSV。

## A股2015年前后覆盖概况

从合并后的逐证券月度审计计算：
- 44只A股中，**35只首个有效月度观测早于2015-01**；
- **36只首个有效月度观测不晚于2015-12**，即至少有2015年或更早的历史起点；
- 36/44只A股获得百度股市通2018年前PE/PB补充；其余8只的历史起点来自2018年以后上市或当前公开接口未返回更早记录；
- 这只说明历史起点覆盖，不代表2015年每个月都有PE、PB、PS完整样本。个股缺月、指标有效样本、月末时点滞后必须看逐证券字段。
- A股PS-TTM目前仍主要依赖东方财富2018年起记录；截至2026-10，不足120个有效月度样本，因此A股10年PS分位也没有达到正式发布门槛。

### 逐证券数据明细（A/H独立列示）

百度公开接口已使36/44只A股出现2018年前的PE/PB观测；另外8只A股目前仅有东方财富源。仅靠“起始月份”不足以认定每个月都有数据，逐股记录数量、缺月数及各指标有效月数见下表。当前数据库并未达到全部证券、全部指标的10年严格月末覆盖。

| 市场 | 公司 | 代码 | 首月 | 月度记录 | 缺月 | PE有效月 | PB有效月 | PS有效月 | 主要来源 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| CN | 美的集团 | `000333.SZ` | 2013-09 | 158 | 0 | 158 | 158 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 兴蓉环境 | `000598.SZ` | 2006-01 | 235 | 15 | 206 | 235 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 格力电器 | `000651.SZ` | 2006-01 | 235 | 15 | 235 | 235 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 分众传媒 | `002027.SZ` | 2006-01 | 238 | 12 | 197 | 238 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 顺丰控股 | `002352.SZ` | 2010-02 | 201 | 0 | 201 | 201 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 北方华创 | `002371.SZ` | 2010-03 | 200 | 0 | 200 | 200 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 比亚迪 | `002594.SZ` | 2011-07 | 184 | 0 | 184 | 184 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中公教育 | `002607.SZ` | 2011-08 | 183 | 0 | 136 | 183 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 牧原股份 | `002714.SZ` | 2014-02 | 153 | 0 | 129 | 153 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 爱尔眼科 | `300015.SZ` | 2009-11 | 203 | 1 | 203 | 203 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 东方财富 | `300059.SZ` | 2010-03 | 200 | 0 | 190 | 200 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 汇川技术 | `300124.SZ` | 2010-10 | 193 | 0 | 193 | 193 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 阳光电源 | `300274.SZ` | 2011-11 | 180 | 0 | 180 | 180 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中际旭创 | `300308.SZ` | 2012-05 | 174 | 0 | 160 | 174 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 宁德时代 | `300750.SZ` | 2018-06 | 101 | 0 | 101 | 101 | 101 | Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 迈瑞医疗 | `300760.SZ` | 2018-10 | 97 | 0 | 97 | 97 | 97 | Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中信证券 | `600030.SH` | 2006-01 | 250 | 0 | 250 | 250 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 招商银行 | `600036.SH` | 2006-01 | 226 | 24 | 226 | 226 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 宇通客车 | `600066.SH` | 2006-01 | 235 | 15 | 235 | 235 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 恒瑞医药 | `600276.SH` | 2006-01 | 226 | 24 | 226 | 226 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 瀚蓝环境 | `600323.SH` | 2006-01 | 226 | 24 | 226 | 226 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 海澜之家 | `600398.SH` | 2006-01 | 226 | 24 | 226 | 226 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 国电南瑞 | `600406.SH` | 2006-01 | 250 | 0 | 250 | 250 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 国药股份 | `600511.SH` | 2006-01 | 250 | 0 | 250 | 250 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 川投能源 | `600674.SH` | 2006-02 | 217 | 32 | 217 | 217 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 海尔智家 | `600690.SH` | 2006-02 | 217 | 32 | 217 | 217 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 锦江酒店 | `600754.SH` | 2006-01 | 235 | 15 | 222 | 235 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 伊利股份 | `600887.SH` | 2006-01 | 235 | 15 | 211 | 235 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 长江电力 | `600900.SH` | 2006-01 | 238 | 12 | 238 | 238 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中国移动 | `600941.SH` | 2022-01 | 58 | 0 | 58 | 58 | 58 | Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中国神华 | `601088.SH` | 2007-10 | 228 | 1 | 228 | 228 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中国平安 | `601318.SH` | 2007-03 | 235 | 1 | 229 | 235 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 工商银行 | `601398.SH` | 2006-10 | 239 | 2 | 239 | 239 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中国太保 | `601601.SH` | 2008-01 | 225 | 1 | 219 | 225 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中国建筑 | `601668.SH` | 2009-07 | 207 | 1 | 207 | 207 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中国电信 | `601728.SH` | 2021-08 | 63 | 0 | 63 | 63 | 63 | Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 京沪高铁 | `601816.SH` | 2020-01 | 82 | 0 | 82 | 82 | 82 | Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中国中免 | `601888.SH` | 2009-10 | 204 | 1 | 204 | 204 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中远海控 | `601919.SH` | 2007-07 | 231 | 1 | 169 | 231 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中国核电 | `601985.SH` | 2015-06 | 137 | 0 | 137 | 137 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 药明康德 | `603259.SH` | 2018-05 | 102 | 0 | 102 | 102 | 102 | Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 海天味业 | `603288.SH` | 2014-02 | 153 | 0 | 153 | 153 | 106 | Baidu Stock Tong / valuation history (AKShare endpoint specification) + Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 海光信息 | `688041.SH` | 2022-08 | 51 | 0 | 51 | 51 | 51 | Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| CN | 中芯国际 | `688981.SH` | 2020-07 | 76 | 0 | 76 | 76 | 76 | Eastmoney Data Center / RPT_VALUEANALYSIS_DET |
| HK | 腾讯控股 | `00700.HK` | 2006-01 | 211 | 39 | 211 | 211 | 0 | Baidu Stock Tong / valuation history (AKShare endpoint specification) |
| HK | 申洲国际 | `02313.HK` | 2006-01 | 245 | 5 | 245 | 245 | 0 | Baidu Stock Tong / valuation history (AKShare endpoint specification) |
| HK | 京东集团 | `09618.HK` | 2020-06 | 77 | 0 | 71 | 77 | 0 | Baidu Stock Tong / valuation history (AKShare endpoint specification) |
| HK | 哔哩哔哩 | `09626.HK` | 2021-03 | 68 | 0 | 15 | 68 | 0 | Baidu Stock Tong / valuation history (AKShare endpoint specification) |
| HK | 阿里巴巴 | `09988.HK` | 2019-11 | 84 | 0 | 84 | 84 | 0 | Baidu Stock Tong / valuation history (AKShare endpoint specification) |

## 继续寻找公开历史数据的结论

| 数据源 | 公开能力/本轮结论 | 是否进入正式历史序列 |
|---|---|---|
| 东方财富 Data Center / `RPT_VALUEANALYSIS_DET` | 44只A股2018年至今日频PE-TTM、PB-MRQ、PS-TTM | 是 |
| 百度股市通公开历史接口 | 36只A股2018年前PE/PB，港股5只PE/PB；无有效PS返回 | 是，仅写入实测返回字段 |
| BaoStock | API字段设计支持PE-TTM、PB-MRQ、PS-TTM；实际连接登录报10002007，未取到记录 | 否，等待网络重试 |
| 亿牛网 Enniu | 港股PE/PB图表端点可调用，但本次抓取0条有效补段；上游文档提示数据源可能陈旧 | 否 |
| 乐咕乐股 Legulegu | 发现旧版单股公开端点 `/api/s/base-info/`；历史客户端代码显示需先取首页CSRF/Cookie，再POST日期MD5令牌和证券代码，返回字段曾含 `trade_date / pe_ttm / pb / ps_ttm`。当前AKShare已不再提供该个股函数，上游是否仍开放尚未实测 | 否；已新增隔离探测脚本 `scripts/probe_legulegu_a_share_history.py`，等待真实工作流运行审计，未把候选记录并入主库 |
| 百分位（Baifenwei） | 可查看A股横截面估值百分位和部分个股近10年曲线，但未取得可批量下载的逐股原始月度PE/PB/PS序列 | 只作交叉核验 |
| GuruFocus | 港股个股页面可显示部分PE历史；完整数据导出涉及试用/订阅，尚未取得49只证券可用的开放CSV | 否 |
| 理杏仁 Lixinger | 港股个股日频PE/PB/PS API文档明确，但需用户专属Token | 暂不接入；非匿名公开数据 |
| TuShare | A股daily_basic含PE/PB/PS，但需要积分；不作为免费源 | 否 |
| BigQuant | 存在历史估值数据集候选，下载权限与再发布许可需核实 | 仅备选，不能按免费公开源处理 |

## 候选源实测：乐咕单股历史估值接口（未成功接入）

旧版AKShare兼容实现及独立客户端记录了乐咕单股接口：
- 请求路径：`https://legulegu.com/api/s/base-info/`
- 请求流程：访问首页建立Cookie并读取 `meta[name=_csrf]`，再POST日期MD5令牌与证券代码。
- 历史客户端响应字段样例：`trade_date, pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm`。
- 本项目探测器严格只映射明确的 `pe_ttm`、`pb`、`ps_ttm`字段，未将静态PE/PS冒充TTM。

**2026-10-30首轮实际探测结果：** 44/44只A股均为 `REQUEST_ERROR`，0家公司有映射记录，0条日频候选数据。审计错误主要为首页CSRF请求HTTP 504，以及API请求HTTP 401/429。候选CSV仅有表头。后续改为共用Cookie/CSRF会话、单线程顺序限速后，试运行被下一次工作流刷新取消；因此没有得到可以验证的第二轮完整样本。现已将乐咕探测调整为仅手动重试，不让失败端点拖慢常规数据更新。

结论：乐咕历史接口的旧版字段与协议有参考价值，但**当前匿名公开访问不可用/不稳定**，没有取得任何可并入数据库的真实数值；不能把旧客户端代码当作当前可访问性证据。

## 新增待实测来源：亿牛网A股历史估值图表

公开客户端 `jstarcraft-crawler` 的 `EniuHistory.java` 将以下亿牛网接口映射为全历史估值字段：
- `/chart/pea/{sh|sz代码}/t/all` → 日期数组与 `pe_ttm`；
- `/chart/pba/{sh|sz代码}/t/all` → 日期数组与 `pb`；
- `/chart/psa/{sh|sz代码}/t/all` → 日期数组与 `ps`；
- `/chart/pricea/{sh|sz代码}/t/all` → 日期数组与 `price`。

与乐咕不同，该来源的客户端代码直接读JSON列式数组，无需CSRF会话。已新增 `scripts/probe_eniu_a_share_history.py`，并纳入常规数据刷新工作流，候选输出与正式数据库隔离：
- `raw/eniu-a-share-candidate.csv`
- `raw/eniu-a-share-fetch-audit.json`

**口径限制：** `pe_ttm` 明确为TTM，`pb` 为PB；图表的 `ps` 字段暂未确认是否为TTM，因此单独存为 `psRaw`，不直接计入正式PS-TTM覆盖。脚本已修正为请求 `t/all` 全历史区间，而非较短的 `t/1`。接口能否返回、覆盖起止日期与是否陈旧，均以本轮GitHub Actions的实际审计为准。


## 后续工作顺序

1. 优先完成可匿名公开获取的A股2015—2017回补，并保留每只证券的逐月记录与来源日期；BaoStock只在手动重试中验证，另行评估乐咕乐股单股接口是否可公开稳定使用。
2. 对港股五家分别继续找PS-TTM历史和PE/PB缺月补段；不能用ADR数据代替港股，也不能用年度/季度估值线性插成月度。
3. 在计算正式10年分位前，明确采用“月内最后可得观测”还是“距月末不超过5个交易日”；两套结果并列展示，精确月末口径作为质量对照。
4. 将合格分位与财务报表、股本、BVPS、正常化EPS、FCF及股息输入行业专属估值模型；银行用PB-ROE，保险用EV/NBV，券商用中周期盈利与PB，周期股用正常化利润，成长企业用DCF/SOTP。
5. 只有当原始数据、币种、证券身份、披露时点、指标口径和样本数通过审计后，才输出悲观/基准/乐观价值区间与分批买入价格。历史低分位本身不能直接转化为买入价。

## 可核验文件

- 原始百度逐证券逐指标审计：`raw/baidu-fetch-audit.json`
- 原始百度历史序列：`raw/baidu-valuation-history.csv`
- 东方财富原始历史序列：`raw/eastmoney-a-share-daily.csv`
- 月度数据库：`generated/valuation-monthly.csv`
- 逐证券覆盖审计：`generated/coverage-audit.json`
- 统一证券池：`universe.json`
