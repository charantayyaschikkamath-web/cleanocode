import { useMemo } from 'react';
import type { ChartSeriesInput, DataProvenance } from './types';
import './charts.css';
import {
  buildChartModel,
  CHART_HEIGHT,
  CHART_WIDTH,
  formatChartTime,
  formatChartValue,
  splitIntoSegments,
} from './chartMath';

interface TimeSeriesChartProps {
  title: string;
  description?: string;
  unit: string;
  timeRangeLabel?: string;
  series: ChartSeriesInput[];
  emptyMessage?: string;
  className?: string;
}

function provenanceName(provenance: DataProvenance | 'MIXED' | undefined): string {
  if (!provenance) return 'Provenance not supplied';
  if (provenance === 'MIXED') return 'Mixed provenance';
  return provenance === 'REAL' ? 'Real data' : provenance === 'SIMULATED' ? 'Simulated data' : 'Derived data';
}

function pointDescription(series: ChartSeriesInput): string {
  const values = series.points.flatMap((point) => point.value !== null && Number.isFinite(point.value) ? [point.value] : []);
  if (values.length === 0) return `${series.label}: no readable values.`;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return `${series.label}: ${values.length} readable point${values.length === 1 ? '' : 's'}, ranging from ${formatChartValue(min)} to ${formatChartValue(max)}.`;
}

export function TimeSeriesChart({
  title,
  description,
  unit,
  timeRangeLabel,
  series,
  emptyMessage = 'No readable measurements are available for this period.',
  className = '',
}: TimeSeriesChartProps) {
  const model = useMemo(() => buildChartModel(series), [series]);
  const summary = series.map(pointDescription).join(' ');

  return (
    <section className={`ct-chart-card ${className}`} aria-label={title}>
      <div className="ct-chart-header">
        <div><h3>{title}</h3>{description ? <p>{description}</p> : null}</div>
        {timeRangeLabel ? <span className="ct-chart-period">{timeRangeLabel}</span> : null}
      </div>

      <div className="ct-chart-legend" aria-label="Chart series">
        {series.map((item, index) => (
          <span className="ct-chart-legend-item" key={item.id}>
            <i className={`ct-chart-swatch ct-chart-swatch--${index % 4}`} aria-hidden="true" />
            <span>{item.label}</span>
            <span className={`ct-chart-provenance ct-chart-provenance--${(item.provenance || 'mixed').toLowerCase()}`}>{provenanceName(item.provenance)}</span>
          </span>
        ))}
      </div>

      {!model ? <div className="ct-chart-empty" role="status">
        <span aria-hidden="true">∿</span><strong>No chart data</strong><p>{emptyMessage}</p>
      </div> : <>
        <div className="ct-chart-canvas">
          <svg className="ct-chart-svg" viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} role="img" aria-label={`${title}. ${summary} Unit: ${unit}. ${timeRangeLabel || 'Time range not supplied'}.`}>
            <title>{title}</title>
            <desc>{summary} All values use {unit || 'an unspecified unit'}. Null and unavailable readings create gaps rather than being connected.</desc>
            {model.yTicks.map((tick, index) => {
              const y = model.plot.top + (index / Math.max(1, model.yTicks.length - 1)) * model.plot.height;
              return <g key={`y-${index}`}>
                <line x1={model.plot.left} x2={model.plot.left + model.plot.width} y1={y} y2={y} className="ct-chart-grid-line" />
                <text x={model.plot.left - 10} y={y + 4} className="ct-chart-axis-label" textAnchor="end">{formatChartValue(tick)}</text>
              </g>;
            })}
            {model.xTicks.map((tick, index) => {
              const x = model.maxEpoch === model.minEpoch
                ? model.plot.left + model.plot.width / 2
                : model.plot.left + ((tick - model.minEpoch) / (model.maxEpoch - model.minEpoch)) * model.plot.width;
              const anchor = index === 0 ? 'start' : index === model.xTicks.length - 1 ? 'end' : 'middle';
              return <g key={`x-${index}`}>
                <line x1={x} x2={x} y1={model.plot.top} y2={model.plot.top + model.plot.height} className="ct-chart-grid-line ct-chart-grid-line--vertical" />
                <text x={x} y={model.plot.top + model.plot.height + 24} textAnchor={anchor} className="ct-chart-axis-label">{formatChartTime(tick, true)}</text>
              </g>;
            })}
            <text x="16" y="14" className="ct-chart-unit-label">{unit || 'unit unavailable'}</text>
            {model.series.map((item, seriesIndex) => {
              const segments = splitIntoSegments(item.points);
              return <g key={item.id} className={`ct-chart-series ct-chart-series--${seriesIndex % 4}`}>
                {segments.map((segment, segmentIndex) => <path
                  key={`segment-${segmentIndex}`}
                  d={segment.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')}
                  className={`ct-chart-line${item.provenance === 'SIMULATED' ? ' ct-chart-line--simulated' : ''}`}
                />)}
                {item.points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y)).map((point, pointIndex) => (
                  <circle key={`${point.timestamp}-${pointIndex}`} cx={point.x} cy={point.y} r={point.status === 'stale' ? 4 : 3} className={`ct-chart-point${point.status === 'stale' ? ' ct-chart-point--stale' : ''}`}>
                    <title>{`${formatChartTime(point.epoch)} · ${formatChartValue(point.value as number)} ${unit}${point.status === 'stale' ? ' · stale reading' : ''}${point.sourceId ? ` · source ${point.sourceId}` : ''}${point.provenance ? ` · ${provenanceName(point.provenance)}` : ''}`}</title>
                  </circle>
                ))}
              </g>;
            })}
          </svg>
        </div>
        <div className="ct-chart-footnote"><span>{summary}</span><span>{model.series.reduce((sum, item) => sum + item.validCount, 0)} readable points</span></div>
      </>}
    </section>
  );
}
