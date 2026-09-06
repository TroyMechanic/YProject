# 缠论规则说明

本文档记录当前项目中缠论分析规则的代码口径。凡是修改 `backend/app/services/chan_analyzer.py`、相关 schema、CSV 字段或前端解释展示时，必须同步更新本文档，保证规则说明和代码一致。

当前规则入口：

```text
原始 K 线
-> 包含关系合并，生成标准 K 线
-> 识别顶分型 / 底分型
-> 过滤连续同类分型
-> 按规则生成笔
-> 基于笔构建标准特征序列
-> 按特征序列分型和破坏规则生成线段
-> 基于已确认线段的严格价格重叠识别中枢
```

核心实现文件：

```text
backend/app/services/chan_analyzer.py
backend/app/services/segment_analyzer.py
backend/app/services/central_zone_analyzer.py
backend/app/models/schemas.py
backend/app/services/csv_store.py
frontend/src/components/KLineChart.tsx
```

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

这套规则在两个阶段生效：

```text
filter_fractals 阶段：对识别出的分型序列做过滤
build_bis 阶段：构笔过程中如果再次遇到同类分型，也按相同口径更新候选端点
```

## 8. 成笔基础规则

一笔由两个相邻有效分型组成，必须顶底交替。

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

默认值：

```text
minKlineGap = 1
```

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

## 13. 线段输入

线段识别以当前有效笔序列为输入。

线段必须满足：

```text
至少由连续三笔组成
第一笔和第三笔方向相同
前三笔存在严格有效的公共价格重叠区间
```

前三笔公共重叠区间：

```text
overlapLow  = max(三笔各自的最低价格)
overlapHigh = min(三笔各自的最高价格)
```

必须满足：

```text
overlapLow < overlapHigh
```

仅在一个价格点相等不视为有效重叠。

## 14. 线段方向与特征序列

线段方向由起始笔方向确定：

```text
从向上笔开始：向上线段
从向下笔开始：向下线段
```

特征序列由与线段方向相反的笔组成：

```text
向上线段：取其中的向下笔
向下线段：取其中的向上笔
```

特征序列元素记录：

```text
high / low
来源笔序号
包含合并前的全部来源笔
高点来源笔
低点来源笔
与前一元素是否存在缺口
```

## 15. 特征序列包含处理

相邻特征序列元素存在包含关系时，按当前线段方向合并。

向上线段的特征序列：

```text
high = max(left.high, right.high)
low  = max(left.low, right.low)
```

向下线段的特征序列：

```text
high = min(left.high, right.high)
low  = min(left.low, right.low)
```

合并后的元素保留全部来源笔，并分别记录高点、低点来自哪一笔。

特征序列必须按笔的时间顺序增量处理。每加入一根新的特征笔，就更新当前标准特征序列并检查分型；一旦最早的合法线段终点完成确认，立即锁定该终点。终点之后的未来特征元素不得再反向合并并改写已经确认的历史线段。

## 16. 特征序列分型

向上线段寻找标准特征序列顶分型：

```text
middle.high > left.high
middle.high > right.high
middle.low  > left.low
middle.low  > right.low
```

线段候选终点取中间特征元素最高点的来源笔起点。

向下线段寻找标准特征序列底分型：

```text
middle.low  < left.low
middle.low  < right.low
middle.high < left.high
middle.high < right.high
```

线段候选终点取中间特征元素最低点的来源笔起点。

用于确认分型的三个特征元素，其全部来源笔必须已经确认。

## 17. 线段破坏与确认

确认旧线段结束前，候选终点之后必须已经存在反向线段的前三笔重叠结构。这保证线段由反向线段破坏，而不是由单独一笔直接破坏。

### 无缺口

向上线段的特征序列向上缺口：

```text
middle.low > left.high
```

向下线段的特征序列向下缺口：

```text
middle.high < left.low
```

不满足对应缺口条件时属于无缺口。

如果特征序列分型第一、第二元素之间无缺口，并且反向线段前三笔结构成立，则原线段在特征分型极值处确认结束：

```text
breakType = NO_GAP
confirmed = true
```

### 有缺口

如果特征序列分型第一、第二元素之间存在缺口，不能立即确认原线段结束。

从候选终点开始构造反向线段的标准特征序列：

```text
原向上线段：反向向下候选段需要形成特征序列底分型
原向下线段：反向向上候选段需要形成特征序列顶分型
```

反向特征序列形成对应分型，且相关来源笔均已确认后，原线段完成二次确认：

```text
breakType = GAP_CONFIRMED
confirmed = true
```

## 18. 未确认线段

如果已经满足前三笔重叠，但尚未出现满足严格特征序列规则的破坏，则生成当前候选线段：

```text
breakType = UNCONFIRMED
confirmed = false
```

候选向上线段终点取剩余同向笔终点中的最高点。

候选向下线段终点取剩余同向笔终点中的最低点。

后续新增的笔可能延伸候选线段，或确认新的反向线段。

## 19. 线段字段和解释

线段字段包括：

```text
startTime / endTime
startPrice / endPrice
direction
startBiIndex / endBiIndex
biCount
confirmed
breakType
featureSequence
reasons
```

前端点击线段时展示：

```text
线段方向
起止时间和价格
组成笔数量
确认状态
无缺口确认 / 缺口二次确认 / 等待确认
标准特征序列各元素
特征元素来源笔
缺口状态
完整判定原因
```

## 20. 线段级中枢

当前中枢按线段级别识别，输入只使用已确认线段。

初始中枢至少由连续三条已确认线段构成。设每条线段的价格区间为：

```text
segmentLow  = min(startPrice, endPrice)
segmentHigh = max(startPrice, endPrice)
```

前三条线段的共同重叠区间为：

```text
ZD = max(三条线段的 segmentLow)
ZG = min(三条线段的 segmentHigh)
```

必须严格满足：

```text
ZD < ZG
```

如果 `ZD == ZG`，只有价格点接触，不构成中枢。

## 21. 中枢延伸与离开

初始三段形成中枢后，`ZD` 和 `ZG` 锁定，后续延伸不会改写核心区间。

后续已确认线段满足以下条件时纳入当前中枢：

```text
segmentLow < ZG
且
segmentHigh > ZD
```

这表示该线段与中枢核心区间存在严格价格重叠。

整个中枢全部组成线段的价格范围记录为：

```text
DD = min(全部组成线段的 segmentLow)
GG = max(全部组成线段的 segmentHigh)
```

第一条不再与核心区间重叠的已确认线段用于判断离开方向，但不计入当前中枢：

```text
segmentLow >= ZG   -> LEFT_UP，向上离开
segmentHigh <= ZD  -> LEFT_DOWN，向下离开
```

如果尚无已确认线段完全离开，则：

```text
status = EXTENDING
```

未确认线段不能建立、延伸或确认中枢离开。

## 22. 中枢字段和解释

中枢字段包括：

```text
startTime / endTime
zd / zg
dd / gg
startSegmentIndex / endSegmentIndex
segmentCount
status
sourceSegmentIndices
reasons
```

前端中枢区域只绘制核心区间 `[ZD, ZG]`，横向覆盖第一条至最后一条组成线段。延伸中的中枢使用虚线边框，已向上或向下离开的中枢使用实线边框。

点击中枢区域时展示：

```text
起止时间
ZD / ZG / DD / GG
组成线段数量与序号
延伸或离开状态
完整判定依据
```

## 23. 中枢扫描边界

识别器从左到右扫描线段。找到一个中枢后，当前中枢延伸到最后一条仍与核心区间严格重叠的已确认线段；下一次扫描从该中枢之后开始。

因此当前实现不会把同一条线段重复归入两个中枢。

## 24. 数据周期

当前支持：

```text
daily     日 K
weekly    周 K
monthly   月 K
hour4     4 小时 K
minute60  60 分钟 K
minute30  30 分钟 K
minute1   1 分钟 K
```

不同周期分别抓取、存储、计算分型、笔、线段和中枢。

日 K、周 K、月 K 使用日期作为时间字段。

4h、60min、30min、1min 使用完整日期时间作为时间字段，分型、笔、线段、中枢和解释信息均保留到秒，不能只按日期定位。

A 股日内周期使用腾讯分钟 K 线数据：

```text
1min   直接使用 m1
30min  直接使用 m30
60min  直接使用 m60
4h     使用同一交易日内的 60min K 线聚合
```

4h 聚合口径：

```text
open   = 当日第一根 60min K 线开盘价
high   = 当日全部 60min K 线最高价
low    = 当日全部 60min K 线最低价
close  = 当日最后一根 60min K 线收盘价
volume = 当日全部 60min K 线成交量之和
time   = 当日最后一根 60min K 线时间
```

A 股完整交易日共 4 个交易小时，因此当前 `hour4` 实际对应一个 A 股交易日的四小时交易时段。交易日尚未结束时，最后一根 4h K 线属于当日未完成 K 线。

同一交易日重复同步 4h 数据时按交易日覆盖，收盘后的完整 4h K 线会替换盘中的未完成 K 线，不保留同日重复记录。

前端切换日内周期时，4h 默认查询近 120 个自然日，60min、30min、1min 默认查询近 10 个自然日。免费行情源的实际历史长度有限：

```text
4h 由最多约 320 根 60min K 线聚合，通常可得到约 70 至 80 根
1min 最多返回最近约 320 根 K 线
30min / 60min 在近 10 个自然日范围内按实际可得数据返回
```

系统不补造行情源未返回的历史分钟数据。

## 25. 当前未实现的规则

以下规则当前没有实现：

```text
买卖点
走势类型
笔破坏后的复杂重构
严格区分老笔 / 新笔 / 严格笔等不同流派
分型左右元素是否允许复用的额外限制
```

如需实现这些规则，必须先明确口径，再修改代码和本文档。
