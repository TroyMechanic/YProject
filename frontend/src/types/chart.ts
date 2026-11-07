export type FractalType = 'TOP' | 'BOTTOM';
export type BiDirection = 'UP' | 'DOWN';
export type SegmentBreakType = 'NO_GAP' | 'GAP_CONFIRMED' | 'UNCONFIRMED';
export type CentralZoneStatus = 'EXTENDING' | 'LEFT_UP' | 'LEFT_DOWN';
export type KlinePeriod = 'daily' | 'weekly' | 'monthly' | 'hour4' | 'minute60' | 'minute30' | 'minute1' | 'minute5';
export type RuleProfile = 'legacy' | 'separated';
export type SignalLevel = 'bi' | 'segment';
export interface ResearchOptions {
  signalLevel: SignalLevel;
  divergenceRatio: number;
  zeroAxisTolerance: number;
  macdFast: number;
  macdSlow: number;
  macdSignal: number;
}

export interface RuleCatalog {
  version: string;
  defaultProfile: RuleProfile;
  recommendedProfile: RuleProfile;
  profiles: Array<{ id: RuleProfile; label: string; minimumCenterGap: number; description: string }>;
  principles: Array<{ id: string; text: string }>;
  signalLevels: Array<{ id: SignalLevel; label: string }>;
  defaults: ResearchOptions & { ruleProfile: RuleProfile; minKlineGap: number };
}

export interface AnalysisMetadata {
  runId: string;
  generatedAt: string;
  ruleVersion: string;
  settings: ResearchOptions & { ruleProfile: RuleProfile; minKlineGap: number };
  effectiveMinKlineGap: number;
  inputHash: string;
  engineHash: string;
  ruleHash: string;
  resultHash: string;
  sourceCount: number;
  sourceStart: string | null;
  sourceEnd: string | null;
  principleIds: string[];
  ruleCatalog: RuleCatalog;
}

export interface Kline {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

export interface Fractal {
  time: string;
  type: FractalType;
  price: number;
  klineIndex: number;
  mergedIndex: number;
  elementHigh?: number | null;
  elementLow?: number | null;
  elements: FractalElement[];
  reasons: string[];
  strength: { grade: string; reasons: string[] } | null;
}

export interface FractalElement {
  time: string;
  klineIndex: number;
  high: number;
  low: number;
  sourceTimes: string[];
  highSourceTime?: string | null;
  lowSourceTime?: string | null;
}

export interface Bi {
  startTime: string;
  endTime: string;
  startPrice: number;
  endPrice: number;
  direction: BiDirection;
  startIndex: number;
  endIndex: number;
  confirmed: boolean;
  reasons: string[];
  confirmedAt: string | null;
  momentum: Momentum | null;
}

export interface Momentum {
  barCount: number;
  amplitudePercent: number;
  velocity: number;
  macdArea: number;
  macdPeak: number;
  volumeSum: number;
  warmupComplete: boolean;
  relativeArea: number | null;
  grade: string;
}

export interface IndicatorPoint { time: string; dif: number; dea: number; histogram: number; ready: boolean }
export interface SignalZone {
  id: string; level: SignalLevel; startUnitIndex: number; endUnitIndex: number;
  startTime: string; endTime: string; formedAt: string; zd: number; zg: number;
  closedAt: string | null; departureUnitIndex: number | null;
  dd: number; gg: number; memberIndices: number[]; status: CentralZoneStatus;
}
export interface ZoneRelation { previousZoneId: string; currentZoneId: string; type: string; observedAt: string; reasons: string[] }
export interface Divergence {
  id: string; level: SignalLevel; direction: BiDirection; type: string; time: string;
  observedAt: string; confirmed: boolean; previousUnitIndex: number; currentUnitIndex: number;
  previousArea: number; currentArea: number; ratio: number; zoneIds: string[]; reasons: string[];
}
export interface TradingPoint {
  structuralLevel: number | null; sourcePeriod: KlinePeriod | null; unitId: string | null;
  displayTime: string | null; displayEndpointTime: string | null;
  id: string; type: string; side: 'BUY' | 'SELL'; level: SignalLevel; time: string;
  price: number; observedAt: string; confirmed: boolean; unitIndex: number; zoneIds: string[];
  divergenceId: string | null; parentId: string | null; invalidationPrice: number; reasons: string[];
}
export interface TrendSummary { level: SignalLevel; type: string; zoneIds: string[]; reasons: string[] }

export interface FeatureSequenceElement {
  high: number;
  low: number;
  startBiIndex: number;
  endBiIndex: number;
  sourceBiIndices: number[];
  highSourceBiIndex: number;
  lowSourceBiIndex: number;
  gapFromPrevious: boolean;
}

export interface Segment {
  startTime: string;
  endTime: string;
  startPrice: number;
  endPrice: number;
  direction: BiDirection;
  startBiIndex: number;
  endBiIndex: number;
  biCount: number;
  confirmed: boolean;
  breakType: SegmentBreakType;
  featureSequence: FeatureSequenceElement[];
  reasons: string[];
  confirmedAt: string | null;
  confirmationBiIndex: number | null;
  momentum: Momentum | null;
}

export interface CentralZone {
  startTime: string;
  endTime: string;
  zd: number;
  zg: number;
  dd: number;
  gg: number;
  startSegmentIndex: number;
  endSegmentIndex: number;
  segmentCount: number;
  status: CentralZoneStatus;
  sourceSegmentIndices: number[];
  reasons: string[];
}

export interface Movement {
  id: string; level: number; kind: string; direction: BiDirection; startTime: string; endTime: string;
  startPrice: number; endPrice: number; high: number; low: number; confirmed: boolean; observedAt: string;
  childIds: string[]; confirmationIds: string[]; zoneIds: string[]; childZones: SignalZone[]; momentum: Momentum; reasons: string[];
}
export interface StructureLayer { level: number; movements: Movement[]; zones: SignalZone[]; divergences: Divergence[]; tradingPoints: TradingPoint[] }
export interface HierarchyAnalysis {
  basePeriod: KlinePeriod; maxLevel: number; baseAnalysis: AnalysisMetadata;
  baseKlines: Kline[]; baseFractals: Fractal[]; baseBis: Bi[]; baseSegments: Segment[]; layers: StructureLayer[]; warnings: string[];
  baseTradingPoints: TradingPoint[]; baseSignalZones: SignalZone[]; baseDivergences: Divergence[];
}
export interface ChartResponse {
  hierarchy: HierarchyAnalysis | null;
  symbol: string;
  name: string;
  period: KlinePeriod;
  klines: Kline[];
  fractals: Fractal[];
  bis: Bi[];
  segments: Segment[];
  centralZones: CentralZone[];
  analysis: AnalysisMetadata | null;
  indicators: IndicatorPoint[];
  signalZones: SignalZone[];
  zoneRelations: ZoneRelation[];
  divergences: Divergence[];
  tradingPoints: TradingPoint[];
  trend: TrendSummary;
}
