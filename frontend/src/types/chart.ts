export type FractalType = 'TOP' | 'BOTTOM';
export type BiDirection = 'UP' | 'DOWN';
export type SegmentBreakType = 'PIVOT_BREAK' | 'NO_GAP' | 'GAP_CONFIRMED' | 'UNCONFIRMED';
export type KlinePeriod = 'daily' | 'weekly' | 'monthly' | 'hour4' | 'minute60' | 'minute30' | 'minute1' | 'minute5';
export type RuleProfile = 'legacy' | 'separated';
export interface RuleCatalog {
  version: string;
  defaultProfile: RuleProfile;
  recommendedProfile: RuleProfile;
  profiles: Array<{ id: RuleProfile; label: string; minimumCenterGap: number; description: string }>;
  principles: Array<{ id: string; text: string }>;
  defaults: { ruleProfile: RuleProfile; minKlineGap: number };
}

export interface AnalysisMetadata {
  runId: string;
  generatedAt: string;
  ruleVersion: string;
  settings: { ruleProfile: RuleProfile; minKlineGap: number };
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
}

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
}

export interface ChartResponse {
  macd: { time: string; dif: number; dea: number; histogram: number }[];
  symbol: string;
  name: string;
  period: KlinePeriod;
  klines: Kline[];
  fractals: Fractal[];
  bis: Bi[];
  segments: Segment[];
  analysis: AnalysisMetadata | null;
}
