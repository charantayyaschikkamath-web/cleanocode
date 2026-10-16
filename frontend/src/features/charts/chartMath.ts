import type { ChartPoint, ChartSeriesInput } from './types';

export interface NormalizedPoint extends ChartPoint {
  epoch: number;
  x: number;
  y: number;
}

export interface ChartModel {
  plot: { left: number; top: number; width: number; height: number };
  minEpoch: number;
  maxEpoch: number;
  minValue: number;
  maxValue: number;
  yTicks: number[];
  xTicks: number[];
  series: Array<ChartSeriesInput & { points: NormalizedPoint[]; validCount: number }>;
}

export const CHART_WIDTH = 740;
export const CHART_HEIGHT = 282;
const PLOT = { left: 62, top: 20, width: 650, height: 202 };

export function sortChartPoints(points: ChartPoint[]): ChartPoint[] {
  return [...points].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
}

function finitePoints(series: ChartSeriesInput[]) {
  return series.flatMap((item) => item.points
    .filter((point) => point.status !== 'unavailable' && Number.isFinite(Date.parse(point.timestamp)) && point.value !== null && Number.isFinite(point.value))
    .map((point) => ({ epoch: Date.parse(point.timestamp), value: point.value as number })));
}

function niceTicks(min: number, max: number, count = 5): number[] {
  if (min === max) return [min];
  return Array.from({ length: count }, (_, index) => max - ((max - min) * index) / (count - 1));
}

function xTicks(minEpoch: number, maxEpoch: number): number[] {
  if (minEpoch === maxEpoch) return [minEpoch];
  return [minEpoch, minEpoch + (maxEpoch - minEpoch) / 2, maxEpoch];
}

export function buildChartModel(series: ChartSeriesInput[]): ChartModel | null {
  const valid = finitePoints(series);
  if (valid.length === 0) return null;

  const minEpoch = Math.min(...valid.map((point) => point.epoch));
  const maxEpoch = Math.max(...valid.map((point) => point.epoch));
  const rawMin = Math.min(...valid.map((point) => point.value));
  const rawMax = Math.max(...valid.map((point) => point.value));
  const rawRange = rawMax - rawMin;
  const padding = rawRange === 0 ? Math.max(Math.abs(rawMax) * 0.12, 1) : rawRange * 0.08;
  const minValue = rawMin - padding;
  const maxValue = rawMax + padding;
  const xFor = (epoch: number) => maxEpoch === minEpoch ? PLOT.left + PLOT.width / 2 : PLOT.left + ((epoch - minEpoch) / (maxEpoch - minEpoch)) * PLOT.width;
  const yFor = (value: number) => PLOT.top + ((maxValue - value) / (maxValue - minValue)) * PLOT.height;

  return {
    plot: PLOT,
    minEpoch,
    maxEpoch,
    minValue,
    maxValue,
    yTicks: niceTicks(minValue, maxValue),
    xTicks: xTicks(minEpoch, maxEpoch),
    series: series.map((item) => {
      const points = sortChartPoints(item.points).map((point) => {
        const epoch = Date.parse(point.timestamp);
        const validPoint = Number.isFinite(epoch) && point.value !== null && Number.isFinite(point.value) && point.status !== 'unavailable';
        return {
          ...point,
          epoch,
          x: Number.isFinite(epoch) ? xFor(epoch) : Number.NaN,
          y: validPoint ? yFor(point.value as number) : Number.NaN,
        };
      });
      return { ...item, points, validCount: points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y)).length };
    }),
  };
}

export function splitIntoSegments<T extends { x: number; y: number }>(points: T[]): T[][] {
  const segments: T[][] = [];
  let current: T[] = [];
  for (const point of points) {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {
      if (current.length) segments.push(current);
      current = [];
      continue;
    }
    current.push(point);
  }
  if (current.length) segments.push(current);
  return segments;
}

export function formatChartValue(value: number, maximumFractionDigits = 2): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);
}

export function formatChartTime(epoch: number, includeDate = true): string {
  if (!Number.isFinite(epoch)) return 'Time unavailable';
  return new Intl.DateTimeFormat(undefined, includeDate
    ? { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { hour: '2-digit', minute: '2-digit' }).format(new Date(epoch));
}
