import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ResourceHistoryChart } from './ResourceHistoryChart';
import { ScenarioComparisonChart } from './ScenarioComparisonChart';
import { buildChartModel, splitIntoSegments } from './chartMath';
import type { ChartPoint } from './types';

const points: ChartPoint[] = [
  { timestamp: '2026-10-15T10:00:00Z', value: 800, provenance: 'SIMULATED', status: 'available' },
  { timestamp: '2026-10-15T10:05:00Z', value: null, provenance: 'SIMULATED', status: 'unavailable' },
  { timestamp: '2026-10-15T10:10:00Z', value: 420, provenance: 'SIMULATED', status: 'available' },
];

describe('data-driven charts', () => {
  it('shows a no-data state rather than drawing invented values', () => {
    render(<ResourceHistoryChart resource="Energy" points={[]} unit="W" timeRangeLabel="Last hour" />);
    expect(screen.getByText('No chart data')).toBeTruthy();
  });

  it('marks simulated history and renders API-provided values', () => {
    render(<ResourceHistoryChart resource="Energy" points={points} unit="W" timeRangeLabel="10:00–10:10" />);
    expect(screen.getByText('Simulated data')).toBeTruthy();
    expect(screen.getByRole('img', { name: /Energy history.*ranging from 420 to 800/i })).toBeTruthy();
  });

  it('displays backend verification failure and unavailable values honestly', () => {
    render(<ScenarioComparisonChart
      unit="W"
      timeRangeLabel="Scenario window"
      baseline={{ label: 'Baseline', points }}
      postAction={{ label: 'Post-action', points: [] }}
      verification={{ outcome: 'VERIFICATION_FAILED', requiredDrop: 250, observedDrop: null, unit: 'W', sourceIds: ['reading-a'], provenance: 'SIMULATED' }}
    />);
    expect(screen.getByText('Verification failed')).toBeTruthy();
    expect(screen.getByText('250 W')).toBeTruthy();
    expect(screen.getByText('Unavailable')).toBeTruthy();
    expect(screen.getByText(/No verified savings should be recorded/)).toBeTruthy();
  });

  it('keeps gaps between unavailable points instead of connecting across them', () => {
    const model = buildChartModel([{ id: 'energy', label: 'Energy', points }]);
    expect(model).not.toBeNull();
    expect(splitIntoSegments(model!.series[0].points).map((segment) => segment.length)).toEqual([1, 1]);
  });
});
