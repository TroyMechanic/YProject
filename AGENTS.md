# AI Collaboration Guide

This file is for AI coding assistants working in this repository.

## Project Overview

This project is a Chan theory stock chart MVP:

```text
frontend: React + TypeScript + Vite
backend: FastAPI
storage: CSV files
chart: lightweight-charts
```

The app fetches stock K-line data, detects top/bottom fractals, builds strokes, and displays them on a frontend chart.

## Important Files

Chan rule implementation:

```text
backend/app/services/chan_analyzer.py
backend/app/services/segment_analyzer.py
backend/app/services/central_zone_analyzer.py
```

Rule documentation:

```text
docs/chan-rules.md
```

Feature documentation:

```text
docs/features.md
```

TODO list:

```text
docs/todo.md
```

Review process:

```text
docs/review-process.md
```

API and service layer:

```text
backend/app/api/routes.py
backend/app/services/chart_service.py
backend/app/services/csv_store.py
backend/app/models/schemas.py
```

Frontend chart:

```text
frontend/src/components/KLineChart.tsx
frontend/src/pages/StockChartPage.tsx
frontend/src/types/chart.ts
```

## Mandatory Rule Sync

Any change involving the following must update `docs/chan-rules.md` in the same task:

```text
K-line inclusion / merge rules
fractal detection rules
same-type fractal filtering
stroke-building rules
minKlineGap semantics
price range validation
explanation fields
frontend rule explanation display
central-zone construction, extension, and departure rules
```

Do not change rule behavior without updating the Markdown documentation.

## Mandatory Feature Doc Sync

Any user-visible feature change should update `docs/features.md` in the same task when it changes:

```text
supported workflows
frontend behavior
API capabilities
data sync behavior
supported symbols or periods
current feature boundaries
```

## Mandatory TODO Sync

Only add an item to `docs/todo.md` when the user explicitly says they want or plan to build it. Do not add inferred, suggested, adjacent, or generally useful features. AI suggestions remain outside the TODO list until the user explicitly accepts them.

When a TODO item is implemented, mark it complete or remove it and update `docs/features.md` if the feature is user-visible.

## Project Review

Follow `docs/review-process.md` when the user requests a project review. Separate confirmed rule defects from Chan-theory suggestions. Suggestions must not change code, rules, or TODO items without explicit user confirmation.

## Current Chan Rule Highlights

The full source of truth is `docs/chan-rules.md`. Current high-level rules:

```text
Raw K lines are displayed on the chart.
Fractals and strokes are calculated from merged standard K lines.
Inclusion merging always assigns the merged standard K line to the rightmost raw K line.
Upward merge: high=max, low=max.
Downward merge: high=min, low=min.
Top fractal: middle standard K line high and low are both higher than left/right.
Bottom fractal: middle standard K line high and low are both lower than left/right.
Same-type TOP keeps the later one only if it is strictly higher.
Same-type BOTTOM keeps the later one only if it is strictly lower.
Stroke min gap uses mergedIndex, not raw klineIndex.
Default minKlineGap is 1.
Stroke price validation is strict: top.price > bottom.elementHigh and bottom.price < top.elementLow.
The latest stroke is marked unconfirmed.
Segments use the strict feature-sequence approach, including feature inclusion handling, no-gap confirmation, gap secondary confirmation, and an unconfirmed current segment.
Central zones use at least three consecutive confirmed segments with strict overlap: ZD=max(segment lows), ZG=min(segment highs), and ZD < ZG. Extension keeps the initial ZD/ZG fixed; DD/GG cover all member segments.
Supported periods are daily, weekly, monthly, A-share 4h, 60min, 30min, and 1min. Intraday records must preserve full datetime values throughout CSV, API, chart, fractal, stroke, segment, and central-zone processing.
The default 4h lookback is 120 calendar days; 60min, 30min, and 1min keep the 10-day default.
```

## Data And Symbols

CSV data lives under:

```text
backend/app/data/raw
backend/app/data/analyzed
```

For unspecified 6-digit stock codes, treat them as A-share codes by default:

```text
002475 -> 002475.SZ
600519 -> 600519.SH
```

## Verification

Before considering backend rule changes complete, run:

```bash
cd backend
PYTHONPATH=. pytest
```

Before considering frontend changes complete, run:

```bash
cd frontend
npm run build
```

If stock analysis CSVs need to reflect changed rules, recalculate affected symbols and periods after the code change.

## Versioned Rules And Regression Guard

Follow `docs/development.md` for changes. Executable profiles and principle IDs live in `backend/app/services/rule_policy.py`. Guarded algorithm/schema/storage/service or chart explanation changes must update `docs/chan-rules.md`, a decision under `docs/decisions/`, and `RULE_VERSION`; run `python3 scripts/check_rule_change.py HEAD` before delivery.

Never auto-regenerate golden expectations merely to pass tests. Explain accepted differences with fixed input snapshots. Current central zones are segment-overlap approximations, not recursive completed-movement zones or trading signals. Date windows only crop display: recalculate full local history. Preserve saved settings on sync. API results must come from one committed snapshot; CSVs are readable exports. Historical confirmed geometry is stable only when existing input and rules remain unchanged.

Recursive structure rules live in recursive_analyzer.py and hierarchy_service.py. Keep display period, base period and structural layer distinct. L0 uses feature-sequence segment seeds; parents require child zones and explicitly confirmed reverse departure/retest. Never silently fall back to the legacy model when base history is insufficient. Compound snapshots retain full base inputs and source metadata. Synchronize principles R01/R02/R03 and docs/decisions/0003-recursive-structure.md for changes.

5m source uses Sina (up to 1023 bars, share volume without Tencent x100 conversion); other intraday periods retain Tencent. Segment boundary inclusion has the explicit reverse-triplet branch documented in rules section 31; do not merge the pre-boundary feature with the first reverse stroke in that branch.

Initial segment seeding additionally requires the third stroke to strictly advance beyond the first stroke's endpoint in the same direction. This cold-start condition applies only to initial-start selection; reverse candidates with a contained third stroke retain the wait-for-break rule. See rules section 32.

Stroke construction consumes all detected fractals with finalized right standard candles (right.klineIndex < last standard originalIndex); do not pre-filter away historical same-type confirmation evidence. Display filtering is separate. A new included raw candle does not finalize the right standard candle. See F04 and rules section 33.
