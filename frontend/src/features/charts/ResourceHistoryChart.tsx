import { useMemo } from 'react';
import { TimeSeriesChart } from './TimeSeriesChart';
import type { ChartPoint, DataProvenance } from './types';

export interface ResourceHistoryChartProps {
  resource: string;
  points: ChartPoint[];
  unit: string;
  timeRangeLabel: string;
  description?: string;
  sourceLabel?: string;
  emptyMessage?: string;
  className?: string;
}

function seriesProvenance(points: ChartPoint[]): DataProvenance | 'MIXED' | undefined {
  const modes = new Set(points.map((point) => point.provenance).filter(Boolean));
  if (modes.size === 0) return undefined;
  if (modes.size > 1) return 'MIXED';
  return [...modes][0] as DataProvenance;
}

export function ResourceHistoryChart({
  resource,
  points,
  unit,
  timeRangeLabel,
  description,
  sourceLabel,
  emptyMessage,
  className = '',
}: ResourceHistoryChartProps) {
  const series = useMemo(() => [{
    id: `history-${resource.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
    label: sourceLabel || resource,
    points,
    provenance: seriesProvenance(points),
  }], [points, resource, sourceLabel]);

  return <TimeSeriesChart
    title={`${resource} history`}
    description={description || 'Observed readings over time; missing values remain visible as gaps.'}
    unit={unit}
    timeRangeLabel={timeRangeLabel}
    series={series}
    emptyMessage={emptyMessage}
    className={className}
  />;
}
