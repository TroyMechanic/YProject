# Chan Stock

React + FastAPI + CSV 的多周期缠论分析 MVP，支持版本化规则方案与完整计算溯源。

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


## 规则可追溯与防退化

规则 v4.0.0：保留兼容方案 `legacy`；推荐研究对照使用 `separated`（三元素不共用且中间至少留一根标准 K 线，中心差至少4）。当前中枢是线段重叠模型，不是完整递归走势中枢。

详细决策见 [规则决策记录](docs/decisions/0001-versioned-rules.md)，持续修改方法见 [开发与回归检查](docs/development.md)。前端从 `GET /api/chan/rules` 获取目录，并展示每批结果实际采用的版本、参数和指纹。

API 图表从原子 JSON 快照读取，CSV 是可读导出。重算使用该股票该周期全部本地历史；日期范围只裁剪显示。同步不传规则参数时保留原设置。算法或行情变化会在查询时自动重建；完整旧批次保存在 `backend/app/data/analyzed/runs/`。

本地检查（已有依赖环境）：

```bash
(cd backend && PYTHONPATH=. .venv/bin/python -m pytest)
(cd frontend && npm run build)
python3 scripts/check_rule_change.py HEAD
```

启动后端使用单 worker。CI 执行规则版本/文档检查、后端回归和前端构建；前端依赖固定版本，并使用 `npm ci` 安装。

新增分型强弱、笔/线段MACD动能、趋势/盘整背驰及三类买卖点研究模型。图上默认按最早确认时间标点，候选可变化，参数可调整。具体定义与边界见 [缠论规则](docs/chan-rules.md) 和 [研究信号决策](docs/decisions/0002-chan-signals.md)。

默认结构递归：展示与基础周期独立，从L0线段种子逐层构造走势/中枢，各层点保留来源及分钟观察时间。父子依赖可展开追溯；原单周期模型保留作对照。5m源已接入，历史不足不补造。定义见规则文档第30节及决策0003。

5m现使用新浪最近最多1023根真实分钟行情，默认30日请求窗口；其他分钟周期仍使用腾讯接口。v4.0.1修复转折边界包含及线段方向极值，首次确认时间由原始K线前缀回放记录，详见规则31及决策0004。
