const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
// Requires running local services, stored real quotes, Playwright and Chrome.
const outputDir = process.env.YPROJECT_TEST_OUTPUT || fs.mkdtempSync(path.join(os.tmpdir(), 'yproject-range-'));
fs.mkdirSync(outputDir, { recursive: true });
let browser;
(async () => {
  browser = await chromium.launch({ executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless:true });
  const page = await browser.newPage({viewport:{width:1450,height:1100}});
  const errors=[], requests=[], stages=[]; let payload;
  page.on('pageerror', e=>errors.push(e.message));
  page.on('response', async response=> {
    if (/\/structure\/chart\?/.test(response.url()) && response.ok()) { payload = await response.json(); requests.push(response.url()); }
  });
  await page.route('**/node_modules/.vite/deps/lightweight-charts.js*', async route=> {
    const response=await route.fetch({url:route.request().url().replace('localhost','127.0.0.1')});
    let body=(await response.text()).split('//# sourceMappingURL')[0];
    body += `\nfunction auditCreateChart(...args) { const chart = createChart(...args); const rec={chart,series:[],removed:false}; (window.__charts??=[]).push(rec); for(const method of ['addCandlestickSeries','addHistogramSeries','addLineSeries']){const original=chart[method].bind(chart);chart[method]=(...a)=>{const series=original(...a);const item={series,method,rows:[]};rec.series.push(item);const set=series.setData.bind(series);series.setData=(rows)=>{item.rows=rows;return set(rows)};return series;};} const remove=chart.remove.bind(chart);chart.remove=()=>{rec.removed=true;remove()};return chart; }\n`;
    body=body.replace('createChart, createChartEx, customSeries', 'auditCreateChart as createChart, createChartEx, customSeries');
    await route.fulfill({response,body});
  });
  async function ready(period){await page.waitForFunction(p=>document.querySelector('.chart-band')?.getAttribute('aria-busy')==='false' && document.querySelector('.chart-status strong')?.textContent?.includes(p),period,{timeout:180000}); await page.waitForTimeout(200);}
  async function verify(stage) {
    const actual=await page.evaluate(()=> {
      const [main,macd]=window.__charts.filter(x=>!x.removed); if(!main)return null;
      const candles=main.series.find(x=>x.method==='addCandlestickSeries').rows.filter(x=>'open' in x);
      const indicators=macd.series.find(x=>x.method==='addHistogramSeries').rows.filter(x=>'value' in x);
      return {candles,indicators,main:main.chart.timeScale().getVisibleRange(),macd:macd.chart.timeScale().getVisibleRange(),delta:Math.max(0,...candles.map(x=>Math.abs(main.chart.timeScale().timeToCoordinate(x.time)-macd.chart.timeScale().timeToCoordinate(x.time))))};
    });
    assert(actual);assert.deepEqual(actual.main,actual.macd);assert(actual.delta<.5);
    const time=t=>t.includes('T')?Date.parse(t+'Z')/1000:t;
    assert.deepEqual(actual.candles,payload.klines.map(k=>({time:time(k.time),open:k.open,high:k.high,low:k.low,close:k.close})));
    assert.deepEqual(actual.indicators,payload.indicators.map(k=>({time:time(k.time),value:k.histogram,color:k.histogram>=0?'#dc2626':'#047857'})));
    stages.push({stage,period:payload.period,count:actual.candles.length,range:actual.main,pixelDelta:actual.delta});
    console.log(JSON.stringify(stages.at(-1)));
  }
  await page.goto('http://localhost:5173'); await ready('日K'); await verify('initial');
  // Use actual dates common to daily, 4h and 60m local history.
  const query=async period=>(await (await fetch('http://127.0.0.1:8000/api/stocks/002475.SZ/chart?period='+period)).json()).klines;
  const [hour4,hour1]=await Promise.all([query('hour4'),query('minute60')]);
  const days4=new Set(hour4.map(x=>x.time.slice(0,10))),days1=new Set(hour1.map(x=>x.time.slice(0,10)));
  const common=payload.klines.filter(x=>days4.has(x.time)&&days1.has(x.time)).slice(-6).map(x=>x.time);
  assert(common.length>=2); const start=common[0],end=common.at(-1);
  await page.evaluate(({start,end})=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleRange({from:start,to:end}),{start,end});
  await page.getByRole('button',{name:'在图上选起止',exact:true}).click();
  await page.locator('.chart-surface').scrollIntoViewIfNeeded();
  for(const day of [end,start]) { // reverse selection
    const x=await page.evaluate(day=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().timeToCoordinate(day),day);
    const box=await page.locator('.chart-surface').boundingBox();await page.mouse.click(box.x+x,box.y+350); await page.waitForTimeout(100);
  }
  assert((await page.locator('.range-navigation').innerText()).includes(`${start} 至 ${end}`));
  await page.getByRole('button',{name:'下钻分析',exact:true}).click();await ready('4H');await verify('daily-to-4h');
  assert(payload.klines.every(k=>k.time.slice(0,10)>=start&&k.time.slice(0,10)<=end));
  assert.equal(new URL(requests.at(-1)).searchParams.get('basePeriod'),'minute5');
  assert.equal(new URL(requests.at(-1)).searchParams.get('startDate'),start);
  await page.getByRole('button',{name:'使用当前可见区间',exact:true}).click();
  await page.getByRole('button',{name:'下钻分析',exact:true}).click(); await ready('60m');await verify('4h-to-60m');
  await page.getByRole('button',{name:'返回上一层',exact:true}).click();await ready('4H');await verify('back-to-4h');
  await page.getByRole('button',{name:'返回上一层',exact:true}).click();await ready('日K');await verify('back-to-daily');
  const range=stages.at(-1).range; assert.equal(range.from,start); assert.equal(range.to,end);
  // Request error must keep the original chart and history.
  await page.getByRole('button',{name:'使用当前可见区间',exact:true}).click();
  await page.route('**/api/stocks/*/structure/chart?*',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'验证加载失败'})}));
  await page.getByRole('button',{name:'下钻分析',exact:true}).click();await page.getByText('区间切换失败，已保留原图：验证加载失败',{exact:true}).waitFor();
  await verify('failed-request-retains-chart'); assert.equal(await page.getByRole('button',{name:'返回上一层',exact:true}).count(),0);
  await page.unroute('**/api/stocks/*/structure/chart?*');
  // Select a plotted stroke/segment using its real canvas coordinates.
  await page.getByLabel('信号中枢',{exact:true}).uncheck();
  await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleRange({from:'2026-08-03',to:'2026-09-30'}));
  await page.locator('.chart-surface').scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);
  const candidate=await page.evaluate(()=>{
    const main=window.__charts.filter(x=>!x.removed)[0], ts=main.chart.timeScale();
    const candle=main.series.find(x=>x.method==='addCandlestickSeries').series;
    for(const series of [...main.series].reverse()) {
      if(series.method!=='addLineSeries'||series.rows.length!==2)continue;
      const [a,b]=series.rows, x1=ts.timeToCoordinate(a.time), x2=ts.timeToCoordinate(b.time), y1=candle.priceToCoordinate(a.value),y2=candle.priceToCoordinate(b.value);
      if(x1>20&&x2<ts.width()-20&&x2-x1>30&&y1>100&&y1<480&&y2>100&&y2<480) return {x:(x1+x2)/2,y:(y1+y2)/2};
    }
  });
  assert(candidate,'real line available for selection');
  const box=await page.locator('.chart-surface').boundingBox();await page.mouse.click(box.x+candidate.x,box.y+candidate.y);
  const useLine=page.getByRole('button',{name:/使用选中.*区间/});await useLine.waitFor();await useLine.click();
  assert(await page.getByRole('button',{name:'下钻分析',exact:true}).isEnabled());
  stages.push({stage:'select-plotted-structure',description:await page.locator('.range-navigation [role="status"]').innerText()});
  // Actual old daily interval has no stored minute data; no synthetic candles.
  await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleRange({from:'2023-01-03',to:'2023-01-10'}));
  await page.getByRole('button',{name:'使用当前可见区间',exact:true}).click();
  await page.getByRole('button',{name:'下钻分析',exact:true}).click();await ready('4H');
  assert.equal(payload.klines.length,0); await page.getByText('暂无K线数据',{exact:true}).waitFor();
  assert(await page.getByRole('button',{name:'返回上一层',exact:true}).isEnabled()); stages.push({stage:'empty-real-history',count:0});
  await page.getByRole('button',{name:'返回上一层',exact:true}).click();await ready('日K');await verify('back-from-empty');
  // Partial coverage is shown explicitly, rather than treated as a full selection.
  await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleRange({from:'2026-08-21',to:'2026-09-03'}));
  await page.getByRole('button',{name:'使用当前可见区间',exact:true}).click();
  await page.getByRole('button',{name:'下钻分析',exact:true}).click(); await ready('4H');await verify('partial-coverage');
  assert((await page.locator('.range-history').innerText()).includes('4 个交易日'));
  await page.getByRole('button',{name:'返回上一层',exact:true}).click();await ready('日K');
  // Selecting a single day (two quick clicks at one position) is supported.
  await page.evaluate(({start,end})=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleRange({from:start,to:end}),{start,end});
  await page.getByRole('button',{name:'在图上选起止',exact:true}).click();await page.locator('.chart-surface').scrollIntoViewIfNeeded();
  const x=await page.evaluate(day=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().timeToCoordinate(day),start);
  const singleBox=await page.locator('.chart-surface').boundingBox();
  await page.mouse.click(singleBox.x+x,singleBox.y+350);await page.mouse.click(singleBox.x+x,singleBox.y+350);
  await page.getByRole('button',{name:'下钻分析',exact:true}).click();await ready('4H');await verify('single-day');assert.equal(payload.klines.length,1);
  await page.getByRole('button',{name:'返回上一层',exact:true}).click();await ready('日K');
  await page.locator('.range-navigation').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(outputDir, 'range-navigation.png'),fullPage:false});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(outputDir, 'range-results.json'),JSON.stringify({selection:{start,end},stages,errors,requests},null,2));
  await browser.close();
})().catch(async e=>{console.error(e); if(browser) await browser.close(); process.exitCode=1;});
