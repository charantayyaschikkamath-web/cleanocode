import { useMemo } from 'react';
import { TimeSeriesChart } from './TimeSeriesChart';
import { VerificationOutcomePanel } from './VerificationOutcomePanel';
import type { ChartSeriesInput, VerificationSummary } from './types';

export interface ScenarioComparisonChartProps {
  title?: string;
  unit: string;
  timeRangeLabel: string;
  baseline: Omit<ChartSeriesInput, 'id'> & { id?: string };
  postAction: Omit<ChartSeriesInput, 'id'> & { id?: string };
  verification?: VerificationSummary | null;
  description?: string;
  className?: string;
}

export function ScenarioComparisonChart({
  title = 'Baseline vs. post-action',
  unit,
  timeRangeLabel,
  baseline,
  postAction,
  verification,
  description = 'Compare the source series supplied by the backend. A downward line alone is not treated as verified success.',
  className = '',
}: ScenarioComparisonChartProps) {
  const series = useMemo(() => [
    { ...baseline, id: baseline.id || 'baseline', label: baseline.label || 'Baseline' },
    { ...postAction, id: postAction.id || 'post-action', label: postAction.label || 'Post-action' },
  ], [baseline, postAction]);

  return (
    <div className={`ct-scenario-comparison ${className}`}>
      <TimeSeriesChart
        title={title}
        description={description}
        unit={unit}
        timeRangeLabel={timeRangeLabel}
        series={series}
        emptyMessage="The API did not return enough readings to draw this comparison. Verification numbers are not generated from the chart."
      />
      <VerificationOutcomePanel verification={verification} />
    </div>
  );
}
