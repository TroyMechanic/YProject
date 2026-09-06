# Chan Stock

React + FastAPI + CSV 的缠论日 K 分析 MVP。

## 功能

- 按股票代码同步日 K 数据到本地 CSV
- 支持按 `1m、30m、60m、4H、日 K、周 K、月 K` 顺序切换周期
- 自动识别顶分型、底分型
- 按顶底交替和最小 K 线间隔生成笔
- 按严格特征序列规则识别线段
- 按连续已确认线段的严格价格重叠识别中枢
- 前端展示 K 线、分型标记、笔线、线段和中枢区域
- 支持点击分型、笔、线段和中枢查看判定依据

## 规则文档

当前缠论分型、包含关系和成笔规则见：

```text
docs/chan-rules.md
```

修改规则相关代码时，必须同步更新该文档。

## 功能文档

当前项目功能、使用方式和功能边界见：

```text
docs/features.md
```

## TODO 清单

后续计划但尚未实现的功能见：

```text
docs/todo.md
```

## Review 机制

定期项目审查的范围、触发方式和报告格式见：

```text
docs/review-process.md
```

## 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问：

```text
http://localhost:5173
```

## 常用股票代码

```text
DEMO
AAPL
MSFT
000001.SZ
600519.SH
```

`DEMO` 是内置演示数据，适合在外部行情源限流或没有网络时验证完整图表链路。
后端会把 `600519.SH` 自动转换为 Yahoo Finance 使用的 `600519.SS` 数据源代码。

## CSV 文件

K 线数据：

```text
backend/app/data/raw/{SYMBOL}_{PERIOD}.csv
```

分析结果：

```text
backend/app/data/analyzed/{SYMBOL}_fractals.csv
backend/app/data/analyzed/{SYMBOL}_bis.csv
backend/app/data/analyzed/{SYMBOL}_weekly_fractals.csv
backend/app/data/analyzed/{SYMBOL}_weekly_bis.csv
backend/app/data/analyzed/{SYMBOL}_monthly_fractals.csv
backend/app/data/analyzed/{SYMBOL}_monthly_bis.csv
backend/app/data/analyzed/{SYMBOL}_segments.csv
backend/app/data/analyzed/{SYMBOL}_weekly_segments.csv
backend/app/data/analyzed/{SYMBOL}_monthly_segments.csv
backend/app/data/analyzed/{SYMBOL}_central_zones.csv
backend/app/data/analyzed/{SYMBOL}_weekly_central_zones.csv
backend/app/data/analyzed/{SYMBOL}_monthly_central_zones.csv
```

## API

同步数据：

```http
POST /api/stocks/{symbol}/sync
```

请求体：

```json
{
  "startDate": "2023-01-01",
  "endDate": "2024-12-31",
  "period": "daily"
}
```

获取图表数据：

```http
GET /api/stocks/{symbol}/chart?period=daily&startDate=2023-01-01&endDate=2024-12-31
```

重算缠论结构：

```http
POST /api/stocks/{symbol}/chan/recalculate
```

请求体：

```json
{
  "startDate": "2023-01-01",
  "endDate": "2024-12-31",
  "period": "daily",
  "minKlineGap": 1
}
```

周期取值：

```text
daily
weekly
monthly
hour4
minute60
minute30
minute1
```

日内周期当前仅支持 A 股。4H 默认查看近 120 个自然日，通常可聚合约 70 至 80 根；60m、30m、1m 默认查看近 10 个自然日。免费行情源的 1m 数据最多返回最近约 320 根 K 线。

## 测试

```bash
cd backend
PYTHONPATH=. pytest
```

```bash
cd frontend
npm run build
```
