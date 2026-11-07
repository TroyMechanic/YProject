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


  await page.goto('http://localhost:5173');await ready('日K');
  const stamp=t=>Date.parse(t+'Z')/1000;
  async function select(label,period) {
    const response=page.waitForResponse(r=>r.url().includes('/structure/chart?')&&new URL(r.url()).searchParams.get('period')===period);
    await page.locator('.period-control').getByRole('button',{name:label,exact:true}).click();
    await response;await ready(label);
  }
  async function scaleInfo(){return page.evaluate(()=>{
    const main=window.__charts.filter(x=>!x.removed)[0],scale=main.chart.timeScale(),range=scale.getVisibleLogicalRange();
    return {range,width:scale.width(),spacing:scale.width()/(range.to-range.from+1)};
  });}
  async function readable(stage) {
    const info=await scaleInfo(); assert(info.spacing>=8&&info.spacing<=24.01,JSON.stringify(info));
    await verify(stage);stages.push({stage:stage+'-density',spacing:info.spacing});
  }
  await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleRange({from:'2026-08-24',to:'2026-08-28'}));
  await select('30m','minute30');await readable('daily-button-to-30m');
  const center=await page.evaluate(time=>{
    const scale=window.__charts.filter(x=>!x.removed)[0].chart.timeScale();return {x:scale.timeToCoordinate(time),width:scale.width()};
  },stamp('2026-08-26T15:00:00'));
  assert(Math.abs(center.x-center.width/2)<=1.1,JSON.stringify(center));stages.push({stage:'visible-center-retained',...center});
  // One wheel tick must stay within the explicitly chosen period.
  await page.locator('.chart-surface').scrollIntoViewIfNeeded();const box=await page.locator('.chart-surface').boundingBox();
  await page.mouse.move(box.x+center.x,box.y+300);const n=requests.length;
  await page.mouse.wheel(0,-100);await page.waitForTimeout(500);assert.equal(requests.length,n);await ready('30m');
  stages.push({stage:'first-wheel-stays-on-chosen-period'});
  // Clicking the already-selected period resets an extreme zoom.
  await page.evaluate(({from,to})=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleRange({from,to}),{from:stamp('2026-08-26T10:00:00'),to:stamp('2026-08-26T11:00:00')});
  await select('30m','minute30');await readable('same-period-resets-zoom');
  // Keep the user settings while replacing old wheel path/scale state.
  await page.getByLabel('笔',{exact:true}).uncheck();await page.getByLabel('滚轮自动切换周期',{exact:true}).uncheck();
  for(const [label,period] of [['1m','minute1'],['5m','minute5'],['60m','minute60'],['4H','hour4'],['日K','daily'],['周K','weekly'],['月K','monthly']]) {
    await select(label,period);await readable('button-'+period);
    assert.equal(await page.getByRole('button',{name:'返回上一层',exact:true}).count(),0);
    assert.equal(await page.getByLabel('笔',{exact:true}).isChecked(),false);
    assert.equal(await page.getByLabel('滚轮自动切换周期',{exact:true}).isChecked(),false);
    if(period==='minute5') assert((await page.locator('.status-line').innerText()).includes('无对应5m行情'));
  }
  // Failed requests leave both the chosen period and the rendered data unchanged.
  const before=await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].series.find(x=>x.method==='addCandlestickSeries').rows);
  await page.route('**/api/stocks/*/structure/chart?*',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'按钮切换错误验证'})}));
  await page.locator('.period-control').getByRole('button',{name:'周K',exact:true}).click();
  await page.locator('.status-line').filter({hasText:'周期切换失败，已保留原图'}).waitFor();
  assert.equal(await page.locator('.period-control button.active').innerText(),'月K');
  assert.deepEqual(await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].series.find(x=>x.method==='addCandlestickSeries').rows),before);
  await page.unroute('**/api/stocks/*/structure/chart?*');stages.push({stage:'button-failure-keeps-chart'});
  await page.setViewportSize({width:800,height:1000});await select('日K','daily');await readable('narrow-screen-adapts');
  await page.locator('.chart-status').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(outputDir,'period-buttons.png')});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(outputDir,'period-button-results.json'),JSON.stringify({stages,errors,requests},null,2));
  await browser.close();
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exitCode=1;});
