# V1.2 历史数据扩展：数据字典与准入规则

## 目标

把宏观模型的历史研究拆成两套数据层：

1. **长期历史描述层**：尽可能延长标普500含股息总回报，覆盖更早的牛熊周期。
2. **点时宏观层**：每个月末保留当时可获得的宏观数据 vintage，避免用今天修订后的历史值冒充当时已知数据。

## 计划接入的文件

| 文件 | 内容 | 频率 | 用途 |
|---|---|---|---|
| `sp500-long-run-total-return-monthly.csv` | Shiller派生标普500名义总回报、CPI | 月度 | 长期收益、回撤、区块抽样 |
| `alfred-nfci-vintages.csv.gz` | NFCI历史时点快照 | 周度原始观测 × 月末vintage | 金融条件点时重建 |
| `alfred-dfii10-vintages.csv.gz` | 10年期TIPS实际收益率历史快照 | 日度原始观测 × 月末vintage | 实际利率点时重建 |
| `alfred-fedfunds-vintages.csv.gz` | 联邦基金有效利率历史快照 | 月度原始观测 × 月末vintage | 政策利率水平与方向 |
| `alfred-gs10-vintages.csv.gz` | 10年期国债收益率历史快照 | 月度原始观测 × 月末vintage | 名义利率与利率周期 |
| `alfred-cpiaucsl-vintages.csv.gz` | CPI历史时点快照 | 月度原始观测 × 月末vintage | 通胀环境分类 |

ALFRED快照从2003-01月末开始，按月末日期取值。文件是宽表：首列为观测日期，后续每列代表一个vintage日期。不能把宽表直接当成最终月频信号；必须在每个vintage列内按原始频率聚合，并遵循数据发布日期。

## 重要口径

- 标普500总回报为美元名义收益，股息再投资；不等于价格指数收益。
- Shiller月价格为月内日收盘价平均值，因此和月末收盘到月末收盘收益并不完全相同。
- 1871—1925历史数据由更早的历史资料拼接/重建，精度低于现代指数数据；建议主分析至少从1926年或1957年起，1871年起仅作长期敏感性分析。
- CPI只用于计算实际收益或通胀状态；不能把实际收益与已经通胀调整过的支出重复调整。
- ALFRED vintage date表示该日期当时可见的数据版本，不是观测期本身。月度、周度和日度序列的发布时间不同，信号构建时要使用vintage列中的最新可用观测，不可简单把观测日期等同发布日期。
- NFCI历史值会修订；必须优先使用对应月末vintage，不再使用单一最新历史序列做严格点时回测。
- DFII10从2003年开始；所以包含实际利率的五因子共同样本不可能延长到1971年。更早时期只能单独建立“长期名义利率/金融条件”扩展模型，不得把GS10冒充TIPS实际利率。
- 这些历史总回报数据是美元口径。人民币回报必须另行合并同频USD/CNY汇率，不能直接将美元收益当成人民币收益。

## 数据许可与来源

- 标普500月度总回报：Firenum发布的Shiller派生CSV，页面声明CC BY 4.0；再利用需署名Firenum并注明Robert J. Shiller/Yale为底层数据来源。来源页：https://firenum.com/tools/shiller-data ，下载文件：https://firenum.com/data/shiller-monthly.csv
- 宏观vintage：ALFRED/St. Louis Fed公开下载端点。FRED官方说明：ALFRED可按历史日期还原当时可获得的数据版本。说明：https://alfred.stlouisfed.org/help/downloaddata
- ALFRED公开图表CSV端点不是正式API文档接口；脚本对每个返回列名做严格核验，若格式改变即中止，不会静默把当前值标成历史vintage。

## 运行方式

```bash
python scripts/extend_macro_history_v12.py
```

默认从2003-01到最近一个完整月份，下载5条序列的月末vintage。可通过 `--start`、`--end` 和 `--series` 缩小范围。无需FRED API key。

## 下一步建模准入

1. 先逐列验证ALFRED vintage的日期标签、观测范围和缺失值。
2. 对DFII10按月计算截至信号月末可获得的日度均值；对NFCI按既定发布时间滞后规则取最新周度观测。
3. 对FEDFUNDS、GS10、CPIAUCSL使用每个vintage下最新可用月份，而不是回填未来发布值。
4. 将点时宏观数据与标普总回报对齐，生成2003年以来的月频点时因子面板。
5. 单独报告1971年以来NFCI可用的历史周期研究；不与2003年以来完整五因子模型混为一谈。
6. 做至少8—10个非重叠年度样本外窗口，再进入V1.3策略回测。
