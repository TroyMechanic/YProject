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
    if (/\/chart\?/.test(response.url()) && response.ok()) { payload = await response.json(); requests.push(response.url()); }
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
      const [main]=window.__charts.filter(x=>!x.removed); if(!main)return null;
      const candles=main.series.find(x=>x.method==='addCandlestickSeries').rows.filter(x=>'open' in x);
      return {candles,main:main.chart.timeScale().getVisibleRange()};
    });
    assert(actual?.main);
    const time=t=>t.includes('T')?Date.parse(t+'Z')/1000:t;
    assert.deepEqual(actual.candles,payload.klines.map(k=>({time:time(k.time),open:k.open,high:k.high,low:k.low,close:k.close})));
    stages.push({stage,period:payload.period,count:actual.candles.length,range:actual.main});
    console.log(JSON.stringify(stages.at(-1)));
  }

  await page.goto('http://localhost:5173'); await ready('日K');
  const stamp=t=>Date.parse(t+'Z')/1000;
  async function locate(time, pane='.chart-surface') {
    await page.locator(pane).scrollIntoViewIfNeeded();
    const point=await page.evaluate(time=>{
      const main=window.__charts.filter(x=>!x.removed)[0];
      return {x:main.chart.timeScale().timeToCoordinate(time),width:main.chart.timeScale().width()};
    },time);
    const box=await page.locator(pane).boundingBox();assert(point.x>0&&point.x<point.width,JSON.stringify({time,...point,title:await page.locator('.chart-status strong').innerText()}));
    await page.mouse.move(box.x+point.x,box.y+(pane==='.chart-surface'?300:80));
    return point.x;
  }
  async function viewport(from,to){await page.evaluate(({from,to})=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleRange({from,to}),{from,to});await page.waitForTimeout(100);}
  async function assertAnchor(time,x,label) {
    const actual=await page.evaluate(time=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().timeToCoordinate(time),time);
    assert(Math.abs(actual-x)<2,`${label}: anchor moved from ${x} to ${actual}`);
    stages.push({stage:label,anchor:time,beforeX:x,afterX:actual});
  }
  await viewport('2026-08-19','2026-08-28');
  let x=await locate('2026-08-24');
  const n=requests.length;
  for(let i=0;i<8;i++){await page.mouse.wheel(0,-100);await page.waitForTimeout(35);}
  await ready('60m');await verify('wheel-daily-to-60m');
  assert.equal(requests.length-n,1,'one request per continuous wheel burst');
  await assertAnchor(stamp('2026-08-24T15:00:00'),x,'daily-anchor-retained');
  // Reverse zoom in the price chart returns to the original daily period.
  await page.waitForTimeout(400);
  for(let i=0;i<12;i++){
    if((await page.locator('.chart-status strong').innerText()).includes('日K')) break;
    x=await locate(stamp('2026-08-24T15:00:00'),'.chart-surface');
    await page.mouse.wheel(0,120);await page.waitForTimeout(400);
  }
  await ready('日K');await verify('wheel-out-to-daily');await assertAnchor('2026-08-24',x,'reverse-anchor-retained');
  // Disabling semantic zoom must preserve ordinary wheel zoom and period.
  await page.getByLabel('滚轮自动切换周期',{exact:true}).uncheck();
  await viewport('2026-08-19','2026-08-28');await locate('2026-08-24');const off=requests.length;
  await page.mouse.wheel(0,-100);await page.waitForTimeout(400);assert.equal(requests.length,off);await ready('日K');
  stages.push({stage:'automatic-switch-disabled',period:payload.period});
  await page.getByLabel('滚轮自动切换周期',{exact:true}).check();await page.waitForTimeout(400);
  await locate('2026-08-24');await page.mouse.wheel(0,-100);await ready('60m');
  await viewport(stamp('2026-08-24T10:30:00'),stamp('2026-08-25T15:00:00'));await page.waitForTimeout(400);
  x=await locate(stamp('2026-08-24T11:30:00'));await page.mouse.wheel(0,-100);await ready('30m');await verify('wheel-60m-to-30m');
  await assertAnchor(stamp('2026-08-24T11:30:00'),x,'minute-anchor-retained');
  // August has no local 5m history: retain 30m, show available dates, suppress repeated calls.
  await viewport(stamp('2026-08-24T10:30:00'),stamp('2026-08-24T11:30:00'));await page.waitForTimeout(400);
  await locate(stamp('2026-08-24T11:00:00'));const beforeMissing=requests.length;
  await page.mouse.wheel(0,-100);
  await page.locator('.chart-band .status-line').filter({hasText:'没有对应本地行情'}).waitFor({timeout:120000});
  assert((await page.locator('.chart-status strong').innerText()).includes('30m'));
  // The response was real 5m history, but the rendered chart must still be the old 30m data.
  const missingPayload=payload;
  const stored30=await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].series.find(x=>x.method==='addCandlestickSeries').rows);
  assert(stored30.some(x=>x.time===Date.parse('2026-08-24T11:00:00Z')/1000));
  assert.equal(missingPayload.period,'minute5');
  for(let i=0;i<3;i++){await page.waitForTimeout(400);await page.mouse.wheel(0,-100);await page.waitForTimeout(100);}
  assert.equal(requests.length-beforeMissing,1);
  stages.push({stage:'missing-5m-keeps-30m',message:await page.locator('.chart-band .status-line').innerText()});
  // An HTTP failure similarly leaves the current chart and path untouched.
  await viewport(stamp('2026-08-25T10:00:00'),stamp('2026-08-25T11:30:00'));await page.waitForTimeout(400);
  await page.route('**/api/stocks/*/chart?*',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'轮缩放错误验证'})}));
  await locate(stamp('2026-08-25T11:00:00'));await page.mouse.wheel(0,-100);
  await page.locator('.chart-band .status-line').filter({hasText:'周期切换失败，已保留原图'}).waitFor();
  assert((await page.locator('.chart-status strong').innerText()).includes('30m'));
  assert.deepEqual(await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].series.find(x=>x.method==='addCandlestickSeries').rows),stored30);
  await page.unroute('**/api/stocks/*/chart?*');stages.push({stage:'failed-request-keeps-30m'});

  // Smallest and largest supported periods retain normal wheel zoom without requests.
  await page.locator('.period-control').getByRole('button',{name:'1m',exact:true}).click();await ready('1m');
  await page.getByLabel('开始日期',{exact:true}).fill('2026-08-27');
  await page.getByLabel('结束日期',{exact:true}).fill('2026-08-28');
  await page.getByRole('button',{name:'查询',exact:true}).click();await ready('1m');await verify('real-1m-boundary');
  await viewport(stamp('2026-08-27T11:00:00'),stamp('2026-08-27T11:05:00'));await page.waitForTimeout(400);
  await locate(stamp('2026-08-27T11:03:00'));const finestRequests=requests.length;
  await page.mouse.wheel(0,-100);await page.locator('.status-line').filter({hasText:'已到最细的1m周期'}).waitFor();
  assert.equal(requests.length,finestRequests);stages.push({stage:'finest-boundary-no-request'});
  await page.locator('.period-control').getByRole('button',{name:'月K',exact:true}).click();await ready('月K');
  await page.evaluate(()=>window.__charts.filter(x=>!x.removed)[0].chart.timeScale().setVisibleLogicalRange({from:-100,to:200}));await page.waitForTimeout(400);
  await locate(payload.klines.at(-5).time);const coarsestRequests=requests.length;
  await page.mouse.wheel(0,120);await page.locator('.status-line').filter({hasText:'已到最大的月K周期'}).waitFor();
  assert.equal(requests.length,coarsestRequests);stages.push({stage:'coarsest-boundary-no-request'});
  await page.locator('.chart-status').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(outputDir,'wheel-navigation.png')});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(outputDir,'wheel-results.json'),JSON.stringify({stages,errors,requests},null,2));
  await browser.close();
})().catch(async e=>{console.error(e); if(browser) await browser.close(); process.exitCode=1;});
