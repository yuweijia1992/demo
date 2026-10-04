window.YM_HISTORICAL = {
  meta:{
    version:"V1.0-annual-core",
    period:"2006-2026",
    updated:"2026-10-04",
    frequency:"annual core + current monthly/daily reference layer",
    note:"2006-2025为完整年度序列；2026为截至最新可得日期的YTD。中国长期国债2026年度收益暂缺，不用估值填充。月度层先接入公开来源的近期窗口，日度由仪表盘当前宏观输入承接。"
  },
  years:[2006,2007,2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024,2025,2026],
  assets:{
    sp500:{name:"S&P 500总回报",unit:"%",returns:[15.79,5.49,-37.00,26.46,15.06,2.11,16.00,32.39,13.69,1.38,11.96,21.83,-4.38,31.49,18.40,28.71,-18.11,26.29,25.02,17.88,13.81],source:"Slickcharts / S&P 500 Total Return"},
    csi300:{name:"沪深300价格回报",unit:"%",returns:[121.02,161.55,-65.95,96.71,-12.51,-25.01,7.55,-7.65,51.66,5.58,-11.28,21.78,-25.31,36.07,27.21,-5.20,-21.63,-11.38,14.68,26.00,-4.12],source:"CSI 300 annual history + 2026 YTD public market data"},
    tlt:{name:"美国长期国债ETF(TLT)总回报",unit:"%",returns:[-0.44,6.00,28.30,-24.70,4.70,30.20,0.80,-13.40,27.30,-1.80,1.20,9.20,-1.60,14.10,18.20,-4.60,-31.20,2.80,-8.10,4.20,-8.40],source:"ChartRow / TLT total return"},
    gold:{name:"黄金价格回报",unit:"%",returns:[23.20,30.90,5.80,24.40,29.60,10.10,6.60,-28.30,-2.20,-10.70,8.00,12.80,-1.90,17.90,24.80,-4.10,-0.80,12.70,26.70,63.70,-4.10],source:"ChartRow / Gold"},
    cash:{name:"美国1个月国债收益率代理",unit:"%",returns:[4.75,4.41,1.29,0.10,0.11,0.04,0.07,0.05,0.03,0.04,0.25,0.85,1.84,2.12,0.35,0.04,1.67,5.14,5.27,4.26,3.83],source:"FRED RIFLGFCM01NA / current 2026 rate reference"},
    chinaBond:{name:"中国长期国债总回报",unit:"%",returns:[3.10,-5.26,19.64,-3.31,1.64,7.06,2.67,-3.54,11.43,9.03,1.86,-2.94,8.67,4.40,2.52,5.76,3.00,4.80,9.38,0.89,null],source:"有知有行 SBBI 2025附表2"}
  },
  monthly:{
    sp500:{
      "2026":[1.5,-0.9,-4.9,10.5,5.3,-1.0,0.1,2.7,-0.3,0.9],
      "2025":[3.0,-1.9,-5.9,-0.7,6.3,5.2,2.3,2.4,3.4,2.2,0.3,0.0]
    },
    csi300:{
      "2026":[1.6,0.1,-5.5,8.0,1.8,1.8,-9.0,2.1,-4.0],
      "2025":[-3.0,1.9,-0.1,-3.0,1.9,2.5,3.5,10.3,3.2,0.0,-2.5,2.3],
      "2024":[-6.3,9.3,0.6,1.9,-0.7,-3.3,-0.6,-3.5,21.0,-3.2,0.7,0.5],
      "2023":[7.4,-2.1,-0.5,-0.5,-5.7,1.2,4.5,-6.2,-2.0,-3.2,-2.1,-1.9]
    }
  },
  sources:[
    {name:"S&P 500 annual total return",url:"https://www.slickcharts.com/sp500/returns"},
    {name:"CSI 300 annual history",url:"https://wiki.sizzltek.com/content/wikipedia_en_all_maxi_2025-08/CSI_300_Index"},
    {name:"CSI 300 2026 monthly/YTD",url:"https://returnsview.com/stock/CSI300/"},
    {name:"TLT annual total return",url:"https://chartrow.com/treasury-bonds/returns"},
    {name:"Gold annual return",url:"https://chartrow.com/gold/returns"},
    {name:"FRED 1-month Treasury rate",url:"https://fred.stlouisfed.org/data/RIFLGFCM01NA"},
    {name:"China asset annual returns",url:"https://youzhiyouxing.cn/sbbi2025/appendix/"}
  ]
};