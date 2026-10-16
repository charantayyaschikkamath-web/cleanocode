/**
 * Central endpoint map for the frontend adapter.
 * Reconcile these routes with the frozen docs/CONTRACTS.md before integration.
 * Keep any backend-specific path translation here rather than scattering it through views.
 */
export const routes = {
  overview: '/api/v1/ui/dashboard/overview',
  events: '/api/v1/ui/events',
  eventFeedback: (id: string) => `/api/v1/ui/events/${encodeURIComponent(id)}/feedback`,
  actions: '/api/v1/ui/actions',
  approveAction: (id: string) => `/api/v1/ui/actions/${encodeURIComponent(id)}/approve`,
  rejectAction: (id: string) => `/api/v1/ui/actions/${encodeURIComponent(id)}/reject`,
  runScenario: '/api/v1/ui/scenarios/run',
  resetDemo: '/api/v1/ui/demo/reset',
  copilot: '/api/v1/copilot/query',
  whatIf: '/api/v1/ui/what-if',
  settings: '/api/v1/ui/settings',
  reports: '/api/v1/ui/reports',
  exportReport: '/api/v1/ui/reports/export',
  preflight: '/api/v1/preflight',
} as const;
