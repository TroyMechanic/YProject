# 缠论规则 5.1.0

## 1. K 线口径

图上展示的是原始 K 线数据。

分型和笔的计算基于处理包含关系后的标准 K 线。

每根标准 K 线会记录：

```text
time              标准 K 线日期，永远向右归属
high              标准 K 线高点
low               标准 K 线低点
original_index    右侧原始 K 线序号，用于图上定位
source_times      由哪些原始 K 线合并而来
high_source_time  标准 K 线高点来自哪一天
low_source_time   标准 K 线低点来自哪一天
```

“永远向右合并”的含义：

```text
两根或多根 K 线发生包含合并后，合并出的标准 K 线日期和序号使用最右侧原始 K 线。
价格高低点可以来自被合并的任意一根原始 K 线。
```

因此可能出现：

```text
标准 K 线日期是 2026-06-25
标准 K 线高点来自 2026-06-24
图上 hover 2026-06-25 原始 K 线时，高点不同于标准 K 线高点
```

这是包含关系合并后的正常结果。

## 2. 包含关系

两根 K 线存在包含关系的条件：

```text
A.high >= B.high 且 A.low <= B.low
或
A.high <= B.high 且 A.low >= B.low
```

如果没有包含关系，右侧 K 线直接作为新的标准 K 线加入序列。

如果存在包含关系，则把上一根标准 K 线 `last` 和当前原始 K 线 `current` 合并，合并后的标准 K 线替换 `last`。

## 3. 合并方向

合并方向由最近两根标准 K 线判断：

```text
如果 last.high > prev.high 且 last.low > prev.low，则为上涨方向
如果 last.high < prev.high 且 last.low < prev.low，则为下跌方向
其他情况默认按上涨方向
```

标准 K 线不足两根时，也默认按上涨方向。

## 4. 包含合并取值

上涨方向合并：

```text
high = max(last.high, current.high)
low  = max(last.low, current.low)
```

下跌方向合并：

```text
high = min(last.high, current.high)
low  = min(last.low, current.low)
```

同时记录 `high_source_time` 和 `low_source_time`，用于解释标准 K 线高低点来源。

## 5. 顶分型

在标准 K 线序列中，连续三根标准 K 线：

```text
left, middle, right
```

如果中间标准 K 线同时满足：

```text
middle.high > left.high
middle.high > right.high
middle.low  > left.low
middle.low  > right.low
```

则 `middle` 是顶分型。

顶分型价格：

```text
price = middle.high
```

顶分型还会记录三元素范围：

```text
elementHigh = max(left.high, middle.high, right.high)
elementLow  = min(left.low, middle.low, right.low)
```

顶分型解释会展示：

```text
由哪三根标准 K 线形成
每根标准 K 线由哪些原始 K 线合并而来
标准 K 线高低点及来源日期
为什么 middle 高点、低点均高于左右两侧
三元素最高和最低
```

## 6. 底分型

在标准 K 线序列中，连续三根标准 K 线：

```text
left, middle, right
```

如果中间标准 K 线同时满足：

```text
middle.low  < left.low
middle.low  < right.low
middle.high < left.high
middle.high < right.high
```

则 `middle` 是底分型。

底分型价格：

```text
price = middle.low
```

底分型还会记录三元素范围：

```text
elementHigh = max(left.high, middle.high, right.high)
elementLow  = min(left.low, middle.low, right.low)
```

底分型解释会展示：

```text
由哪三根标准 K 线形成
每根标准 K 线由哪些原始 K 线合并而来
标准 K 线高低点及来源日期
为什么 middle 低点、高点均低于左右两侧
三元素最高和最低
```

## 7. 连续同类分型过滤

如果连续出现同性质分型，则只保留更极端的那个。

连续顶分型：

```text
如果后一个顶分型 price > 前一个顶分型 price，则替换为后一个。
否则保留前一个。
```

连续底分型：

```text
如果后一个底分型 price < 前一个底分型 price，则替换为后一个。
否则保留前一个。
```

价格相等时保留前一个。

构笔中已有末笔时，延伸同类端点必须重新满足末笔起点与新终点的价格范围；成立后同时更新末笔终点时间、价格、原始序号和解释。不能只移动下一笔起点，造成两笔断开。

这套规则在两个阶段生效：

```text
filter_fractals 阶段：对识别出的分型序列做过滤
build_bis 阶段：构笔过程中如果再次遇到同类分型，也按相同口径更新候选端点
```

## 8. 成笔基础规则

一笔由满足间隔与价格范围的有效端点组成，必须顶底交替。反向候选不满足规则时跳过；后续同类更极端分型可延伸当前末笔，因此这里的“相邻”指构笔后接受的端点，不保证是检测序列中紧邻的两个分型。这是项目约定，不能当作对所有缠论流派的统一定义。

```text
底分型 -> 顶分型 = 向上笔
顶分型 -> 底分型 = 向下笔
```

同类分型之间不会直接成笔。

## 9. 成笔最小间隔

成笔最小间隔使用合并后的标准 K 线序号计算，不使用原始 K 线序号。

```text
gap = right.mergedIndex - left.mergedIndex
```

兼容方案默认参数：

```text
minKlineGap = 1
```

独立分型方案生效间隔为 `max(minKlineGap, 4)`：两个三元素分型不共用标准 K 线，中间至少保留一根。间隔指中心序号差，不是两分型之间的空白根数。详见第 26 节。

如果：

```text
gap < minKlineGap
```

则不能成笔。

前端输入框“标准K线最小间隔”传入的是这个参数。

## 10. 成笔价格范围规则

一笔内的顶分型和底分型必须满足严格价格关系。

设：

```text
top.price                 顶分型最高点
top.elementLow            顶分型三元素最低点
bottom.price              底分型最低点
bottom.elementHigh        底分型三元素最高点
```

必须同时满足：

```text
top.price > bottom.elementHigh
bottom.price < top.elementLow
```

业务含义：

```text
顶分型最高点必须严格高于底分型三元素最高点
底分型最低点必须严格低于顶分型三元素最低点
```

边界相等不允许成笔。

## 11. 最后一笔状态

如果已经生成了至少一笔，最后一笔会标记为未确认：

```text
confirmed = false
```

原因是后续新增 K 线可能改变最后的分型或笔。

其他笔：

```text
confirmed = true
```

## 12. 分型和笔解释字段

后端会返回解释字段给前端展示。

分型字段包括：

```text
time
type
price
klineIndex     原始 K 线序号，用于图表定位
mergedIndex    标准 K 线序号，用于计算成笔间隔
elementHigh
elementLow
elements       左、中、右三根标准 K 线明细
reasons
```

`elements` 中每个元素包括：

```text
time
klineIndex
high
low
sourceTimes
highSourceTime
lowSourceTime
```

笔字段包括：

```text
startTime
endTime
startPrice
endPrice
direction
startIndex
endIndex
confirmed
reasons
```

笔解释会展示：

```text
顶底是否交替
标准 K 线间隔是否满足 minKlineGap
方向是向上笔还是向下笔
顶分型最高点 > 底分型三元素最高点
底分型最低点 < 顶分型三元素最低点
最后一笔是否未确认
```

满足成笔或成段条件后画实线。终点尚可延伸时，在当前终点标注“笔终点待定”或“段终点待定”。虚线仅用于尚未成立的候选结构；当前图表只绘制已经成立的笔和线段。

## 13. 线段

### 怎么算一个线段

同级别的笔构成同级别的线段。按时间顺序比较相邻两个笔高点，再比较相邻两个笔低点。高点和低点都严格抬高，画向上线段；高点和低点都严格降低，画向下线段。相等只算持平。以向上为例，笔端点依次为 `10低 → 15高 → 12低 → 18高`，因 18 高于 15、12 高于 10，从 10 向 18 画一条线段。

线段随同向新极值延伸。高低点只满足一个条件时，原段继续等待结束确认。

### 线段的结束判断

**确认结束（结构确认）**　向上段取向下笔为特征序列，向下段取向上笔。同一序列内按方向处理包含后，上段找顶分型，下段找底分型。分型第一、第二元素的价格区间有重叠时，在分型极值处确认旧段结束；两者有缺口时，须等反向特征序列形成对应分型，再确认同一极值为终点。新段从该终点接续。[缠中说禅第 67 课](https://chzhshch.blog/stocks/067/)

若转折后的第一笔就破坏前段，按第 71 课观察后续笔。例如上段从 20 回落至 13，已跌破前低 14，随后反弹到 19。第三笔若跌破 13，确认上段结束在 20；若第三笔仍在 13～20 内，就继续等。后续先破 13，确认在 20 转下；先破 20，上段延伸。下段按高低反转判断。记录时分别保留转折发生时间与结构得到确认的时间。[缠中说禅第 71 课](https://chzhshch.blog/stocks/071/)


## 26. 版本化规则方案与原则编号

本次版本为 **5.1.0**。可执行目录是 `backend/app/services/rule_policy.py`，接口为 `GET /api/chan/rules`。本文是解释口径，测试是验收约束，目录提供前后端共享的方案与默认值。三者必须一起修改。

| 原则 | 采用的口径 | 性质 |
| --- | --- | --- |
| K01 | 包含按方向取 max/max 或 min/min；方向不足时默认向上；时间向右、高低来源各自保留 | 包含处理参考原文；初始化和时间归属为项目约定 |
| F01 | 三标准 K 线，高低点均严格高于/低于左右才成分型；相等不成立 | 分型几何定义加严格边界约定 |
| F04 | 成笔只使用右侧支撑已冻结的分型 | 右侧标准 K 线之后已有新的原始 K 线 |
| F02 | 同类保留更极端分型；相等保留早者 | 项目确定性约定 |
| B01 | 顶底交替；间隔使用标准 K 线中心序号差 | 成笔参数的明确语义 |
| B02 | `top.price > bottom.elementHigh` 且 `bottom.price < top.elementLow` | 项目沿用的双严格范围约束 |
| B03 | 末笔可延伸，前后笔保持连接；最后一笔未确认 | 项目候选状态约定 |
| S01 | 同级别笔的高低点与线段方向 | 见第 13 节 |
| S02 | 线段的结构确认结束 | 见第 13 节 |
| D01 | 全部本地历史参与分析，日期仅裁剪展示；日内时间保留到秒 | 数据上下文一致性 |

两个已实现方案：

| 方案 ID | 默认输入间隔 | 实际间隔 | 元素共用 |
| --- | --- | --- | --- |
| `legacy` 兼容方案 | 1 | `minKlineGap` | 允许，保留原敏感口径 |
| `separated` 独立分型方案 | 1 | `max(minKlineGap, 4)` | 不允许，两个三元素之间至少留一根标准 K 线 |

例如两个分型中心序号分别为 2 和 6，元素是 `[1,2,3]` 与 `[5,6,7]`，序号 4 是中间独立 K 线。中心差 3 只有元素不共用，没有中间独立 K 线，不能满足本项目独立方案。

我的选择：研究时推荐 `separated`，减少两个端点的结构纠缠；保留 `legacy` 作为现有结果的对照。后端首次默认仍为 `legacy`，前端默认读取当前结果方案，**不会悄悄替换已有设置**。两个方案均不宣称是完整“老笔”“新笔”，也不代表概率估计；间隔更大不等于胜率更高。


## MACD 副图

MACD 副图使用当前周期完整本地收盘价历史，取 EMA(12) 减 EMA(26) 为 DIF，DIF 的 EMA(9) 为 DEA，柱值为 2 × (DIF − DEA)。按日期查询时同步裁剪行情和指标。主副图共用时间索引，正柱红色、负柱绿色。
