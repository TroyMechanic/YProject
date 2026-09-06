export type FractalType = 'TOP' | 'BOTTOM';
export type BiDirection = 'UP' | 'DOWN';
export type SegmentBreakType = 'NO_GAP' | 'GAP_CONFIRMED' | 'UNCONFIRMED';
export type CentralZoneStatus = 'EXTENDING' | 'LEFT_UP' | 'LEFT_DOWN';
export type KlinePeriod = 'daily' | 'weekly' | 'monthly' | 'hour4' | 'minute60' | 'minute30' | 'minute1';

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

export interface ChartResponse {
  symbol: string;
  name: string;
  period: KlinePeriod;
  klines: Kline[];
  fractals: Fractal[];
  bis: Bi[];
  segments: Segment[];
  centralZones: CentralZone[];
}
