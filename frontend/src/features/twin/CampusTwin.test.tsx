import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CampusTwin } from './CampusTwin';
import type { TwinBuilding } from './types';

const buildings: TwinBuilding[] = [
  {
    id: 'north', name: 'North Hall', shortCode: 'NH', status: 'attention',
    rooms: [
      {
        id: 'lab-1', name: 'Lab 1', occupancy: { state: 'UNKNOWN', provenance: 'SIMULATED', observedAt: '2026-10-15T10:00:00Z' },
        readings: [{ id: 'r-1', resourceType: 'energy', value: null, unit: 'W', observedAt: '2026-10-15T10:00:00Z', provenance: 'SIMULATED', status: 'unavailable' }],
        events: [{ id: 'e-1', title: 'Power signal missing', type: 'sensor_unavailable', severity: 'medium', status: 'open', createdAt: '2026-10-15T10:00:00Z' }],
        camera: { status: 'unavailable', inferenceMode: 'unknown', lastFrameAt: null, coveragePercent: null },
      },
    ],
  },
  { id: 'library', name: 'Library', status: 'healthy', rooms: [] },
];

describe('CampusTwin', () => {
  it('renders empty state rather than fabricated campus data', () => {
    render(<CampusTwin buildings={[]} />);
    expect(screen.getByText('Campus layout unavailable')).toBeTruthy();
  });

  it('selects buildings and displays explicit unknown/unavailable states', () => {
    const onBuildingSelect = vi.fn();
    render(<CampusTwin buildings={buildings} onBuildingSelect={onBuildingSelect} now={new Date('2026-10-15T10:01:00Z')} />);
    expect(screen.getByText('Occupancy unknown')).toBeTruthy();
    expect(screen.getByText('Unavailable')).toBeTruthy();
    expect(screen.getByText('Simulated')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Library, healthy, 0 rooms, 0 open events/i }));
    expect(onBuildingSelect).toHaveBeenCalledWith('library');
    expect(screen.getByRole('heading', { name: 'Library' })).toBeTruthy();
  });

  it('exposes event navigation callbacks without pretending an action succeeded', () => {
    const onOpenEvent = vi.fn();
    render(<CampusTwin buildings={buildings} onOpenEvent={onOpenEvent} />);
    const eventPanel = screen.getByText('Power signal missing').closest('article');
    expect(eventPanel).not.toBeNull();
    fireEvent.click(within(eventPanel as HTMLElement).getByRole('button', { name: 'View event' }));
    expect(onOpenEvent).toHaveBeenCalledWith('e-1');
  });
});
