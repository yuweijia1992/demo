/* Shared monthly data layer for Investment Lab V2.5 — canonical source for macro, risk, backtest and FIRE.
   Policy: no zero-filling, no forward-fill, and no price/total-return substitution. */
(function(){
  "use strict";
  const STORAGE_KEY="ym_v21_imported_monthly_rows";
  const FIELDS=[
    "csi300_price_index_cny","csi300_price_return_pct","csi300_total_return_index_cny","csi300_total_return_pct",
    "sp500_total_return_index_usd","sp500_total_return_pct","sp500_total_return_cny_pct","sp500_cpi_index","sp500_shiller_total_return_pct","sp500_shiller_cpi_index",
    "hang_seng_price_index_hkd","hang_seng_total_return_pct","hang_seng_etf_2800_total_return_index_hkd","hang_seng_etf_2800_total_return_hkd_pct","hang_seng_etf_2800_total_return_cny_pct","hkd_per_usd",
    "cny_cash_index_h11025","china_treasury_etf_511010_adj_total_return_index_cny","china_treasury_etf_511010_total_return_cny_pct",
    "china_bond_total_return_index_cny","us_treasury_total_return_index_usd",
    "gold_usd_oz","gold_cny_per_oz_monthly_avg","gold_cny_return_pct","usd_cny","usd_cny_change_pct","china_cpi_mom_pct","china_cpi_yoy_pct",
    "us_cpi_index","us_cpi_yoy_pct","hang_seng_total_return_cny_pct","china_bond_wealth_return_cny_pct",
    "us_treasury_7_10y_total_return_pct","us_treasury_7_10y_total_return_cny_pct","cny_cash_return_pct","us_tbill_1m_return_cny_pct",
    "us_agg_etf_total_return_usd_pct","us_agg_etf_total_return_cny_pct",
    "us_ief_7_10y_etf_total_return_usd_pct","us_ief_7_10y_etf_total_return_cny_pct",
    "us_shy_1_3y_etf_total_return_usd_pct","us_shy_1_3y_etf_total_return_cny_pct",
    "fxi_china_largecap_etf_total_return_usd_pct","fxi_china_largecap_etf_total_return_cny_pct",
    "efa_developed_markets_etf_total_return_usd_pct","efa_developed_markets_etf_total_return_cny_pct",
    "eem_emerging_markets_etf_total_return_usd_pct","eem_emerging_markets_etf_total_return_cny_pct",
    "dgs10_pct","dfii10_pct","dxy_index",
    "vix_index","brent_usd_bbl","fedfunds_pct","china10y_pct",
    "cn_pmi","us_pmi","us_unemployment_pct","credit_spread_pct",
    "sp500_forward_pe","csi300_pe","cash_rate_cny_pct","portfolio_return_cny_pct"
  ];
  const isNum=v=>v!==null&&v!==undefined&&v!==""&&Number.isFinite(Number(v));
  function parseCSV(text){
    const lines=String(text||"").replace(/^\uFEFF/,"").split(/\r?\n/).filter(x=>x.trim().length);
    if(lines.length<2)throw new Error("CSV至少需要一行表头和一行数据。");
    function split(line){
      const out=[];let cur="",quoted=false;
      for(let i=0;i<line.length;i++){
        const c=line[i];
        if(c==='"'&&quoted&&line[i+1]==='"'){cur+='"';i++;}
        else if(c==='"')quoted=!quoted;
        else if(c===","&&!quoted){out.push(cur);cur="";}
        else cur+=c;
      }
      out.push(cur);return out;
    }
    const headers=split(lines[0]).map(x=>x.trim());
    return lines.slice(1).map(line=>{
      const cells=split(line),obj={};
      headers.forEach((h,i)=>obj[h]=(cells[i]||"").trim());
      return obj;
    });
  }
  const FRED_ALIASES={DGS10:"dgs10_pct",DFII10:"dfii10_pct",DTWEXBGS:"dxy_index",VIXCLS:"vix_index",DEXCHUS:"usd_cny",CPIAUCSL:"us_cpi_index",FEDFUNDS:"fedfunds_pct",DCOILBRENTEU:"brent_usd_bbl"};
  function normalizeRow(raw){
    let date=String(raw.date||raw.Date||raw.observation_date||raw.DATE||"").trim();
    if(!date&&raw.year&&raw.month)date=String(raw.year).padStart(4,"0")+"-"+String(raw.month).padStart(2,"0");
    if(/^\d{4}-\d{2}-\d{2}$/.test(date))date=date.slice(0,7);
    if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(date))return null;
    const row={date};
    for(const f of FIELDS)if(isNum(raw[f]))row[f]=Number(raw[f]);
    Object.entries(FRED_ALIASES).forEach(([source,target])=>{if(isNum(raw[source]))row[target]=Number(raw[source]);});
    // Source-specific adapter: Firenum / Shiller monthly CSV (CC BY 4.0).
    if(raw.nominalReturn!==undefined&&isNum(raw.nominalReturn))row.sp500_total_return_pct=Number(raw.nominalReturn)*100;
    if(raw.cpi!==undefined&&isNum(raw.cpi))row.sp500_cpi_index=Number(raw.cpi);
    // Source-specific adapter: IMF/World Price Index simple Date,Price monthly CSV.
    const price=raw.Price??raw.price;
    if(price!==undefined&&isNum(price))row.gold_usd_oz=Number(price);
    return Object.keys(row).length>1?row:null;
  }
  function mergeRows(base,extra){
    const map=new Map();
    base.forEach(r=>map.set(r.date,{...r}));
    extra.forEach(r=>{
      const old=map.get(r.date)||{date:r.date};
      Object.keys(r).forEach(k=>{if(k==="date")return;if(r[k]!==""&&r[k]!==null&&r[k]!==undefined)old[k]=r[k];});
      map.set(r.date,old);
    });
    return [...map.values()].sort((a,b)=>a.date.localeCompare(b.date));
  }
  async function load(){
    let base=[],manifest={};
    try{
      const res=await fetch("../data/investment-monthly.csv",{cache:"no-store"});
      if(res.ok)base=parseCSV(await res.text()).map(normalizeRow).filter(Boolean);
    }catch(e){console.warn("Base monthly data unavailable",e);}
    try{
      const res=await fetch("../data/investment-monthly-manifest.json",{cache:"no-store"});
      if(res.ok)manifest=await res.json();
    }catch(e){console.warn("Monthly manifest unavailable",e);}
    let extra=[];
    try{extra=JSON.parse(localStorage.getItem(STORAGE_KEY)||"[]");if(!Array.isArray(extra))extra=[];}catch(e){extra=[];}
    return {rows:mergeRows(base,extra),manifest,baseRows:base.length,importedRows:extra.length};
  }
  function inspect(text){
    const raw=parseCSV(text),rows=[],bad=[],duplicates=[];
    const byMonth=new Map();
    raw.forEach((r,i)=>{
      const x=normalizeRow(r);
      if(!x){bad.push(i+2);return;}
      if(byMonth.has(x.date))duplicates.push(x.date);
      const old=byMonth.get(x.date)||{date:x.date};
      Object.keys(x).forEach(k=>{if(k!=="date"&&x[k]!==""&&x[k]!==null&&x[k]!==undefined)old[k]=x[k];});
      byMonth.set(x.date,old);
    });
    rows.push(...byMonth.values());
    const fields=FIELDS.filter(f=>rows.some(r=>isNum(r[f])));
    if(!rows.length)throw new Error("没有识别到有效的月份和数值列。请使用模板列名，或导入Shiller/Firenum year,month,nominalReturn,cpi格式。");
    if(!fields.length)throw new Error("数据中没有可识别的指标字段。");
    return {rows:rows.sort((a,b)=>a.date.localeCompare(b.date)),badRows:bad,duplicateDates:duplicates,fields};
  }
  function importCSV(text){
    const result=inspect(text);
    const old=JSON.parse(localStorage.getItem(STORAGE_KEY)||"[]");
    const merged=mergeRows(Array.isArray(old)?old:[],result.rows);
    const encoded=JSON.stringify(merged);
    if(encoded.length>4_000_000)throw new Error("导入数据过大，超过本地浏览器安全存储上限。请按时间段拆分。");
    localStorage.setItem(STORAGE_KEY,encoded);
    return {...result,storedRows:merged.length};
  }
  function coverage(rows,field){
    const good=rows.filter(r=>isNum(r[field]));
    const expected=rows.length;
    return {count:good.length,expected,first:good[0]?.date||null,last:good.at(-1)?.date||null,missing:expected-good.length};
  }
  function latest(rows,field){
    for(let i=rows.length-1;i>=0;i--)if(isNum(rows[i][field]))return {date:rows[i].date,value:Number(rows[i][field])};
    return null;
  }
  function monthlyReturns(rows,field){
    return rows.filter(r=>isNum(r[field])).map(r=>({date:r.date,value:Number(r[field])/100}));
  }
  function deriveLevelReturns(rows,levelField){
    const out=[];let prev=null;
    rows.forEach(r=>{
      const v=isNum(r[levelField])?Number(r[levelField]):null;
      if(v!==null&&prev!==null&&v>0&&prev.value>0)out.push({date:r.date,value:v/prev.value-1});
      if(v!==null&&v>0)prev={date:r.date,value:v};
    });
    return out;
  }
  function stats(returns){
    const x=returns.map(r=>typeof r==="number"?r:r.value).filter(Number.isFinite);
    if(x.length<2)return {count:x.length,ready:false};
    let wealth=1,peak=1,maxdd=0,worst=Infinity;
    x.forEach(r=>{wealth*=1+r;peak=Math.max(peak,wealth);maxdd=Math.min(maxdd,wealth/peak-1);worst=Math.min(worst,r);});
    const mean=x.reduce((a,b)=>a+b,0)/x.length;
    const vol=Math.sqrt(x.reduce((s,r)=>s+(r-mean)**2,0)/(x.length-1))*Math.sqrt(12);
    const cagr=wealth**(12/x.length)-1;
    return {count:x.length,ready:true,cagr,vol,maxdd,worst,wealth};
  }
  function portfolioReturns(rows){return monthlyReturns(rows,"portfolio_return_cny_pct");}
  window.YM_DATA_CORE={version:"2.5.0",fields,load,parseCSV,inspect,importCSV,coverage,latest,monthlyReturns,deriveLevelReturns,stats,portfolioReturns};
})();