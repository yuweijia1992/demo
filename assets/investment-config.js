/* Investment Lab shared configuration — single source of truth.
   Strategic weights are policy targets, not live holdings or market signals.
   Browser-held inputs are local to this device and are not synced to a server. */
(function () {
  const config = {
    version: "2.0.0",
    capitalDefault: 4000000,
    rebalanceThresholdPct: 5,
    currency: "CNY",
    allocation: [
      { id: "equity", name: "全球股票", weight: 52, detail: "覆盖A股、美国股票及其他市场；内部地区比例待独立研究，不在此虚构。" },
      { id: "bonds", name: "债券", weight: 28, detail: "以高质量债券作为组合防守与再平衡资产。" },
      { id: "gold", name: "黄金", weight: 10, detail: "组合分散与尾部风险对冲，不以短期涨跌追仓。" },
      { id: "cash", name: "现金", weight: 10, detail: "流动性储备与长期支出缓冲。" }
    ],
    backtestProxy: [
      { id: "sp500", weight: 26, group: "equity", label: "美国股票代理" },
      { id: "csi300", weight: 26, group: "equity", label: "A股代理" },
      { id: "tlt", weight: 14, group: "bonds", label: "美国长期国债代理" },
      { id: "chinaBond", weight: 14, group: "bonds", label: "中国长期国债代理" },
      { id: "gold", weight: 10, group: "gold", label: "黄金价格代理" },
      { id: "cash", weight: 10, group: "cash", label: "美元短期国债收益率代理" }
    ],
    backtestProxyNote: "研究代理：股票部分暂以美国与A股各占一半，债券部分暂以美国长期国债与中国长期国债各占一半。它不包含其他市场股票，且原始序列存在币种与总回报口径差异；不得视为完整全球组合或人民币正式回测。"
  };
  window.YM_INVESTMENT_CONFIG = Object.freeze(config);
})();