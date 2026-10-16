import { routes } from './routes';
import type {
  ApiErrorShape,
  CampusAction,
  CampusEvent,
  CampusSettings,
  CopilotResponse,
  DashboardOverview,
  ScenarioRequest,
  ScenarioResponse,
  WhatIfRequest,
  WhatIfResponse,
} from '../types';

const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export class ApiError extends Error {
  status: number;
  code?: string;
  requestId?: string;
  constructor(message: string, status: number, code?: string, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError('The CampusTwin API is unreachable. Check that the backend is running and the URL is correct.', 0, 'API_UNREACHABLE');
  }

  const contentType = response.headers.get('content-type') || '';
  const body: unknown = contentType.includes('application/json') ? await response.json().catch(() => null) : await response.text().catch(() => '');
  if (!response.ok) {
    const shape = (body && typeof body === 'object' ? body : {}) as ApiErrorShape;
    const message = shape.error?.message || shape.message || `Request failed (${response.status}).`;
    throw new ApiError(message, response.status, shape.error?.code, shape.error?.request_id);
  }
  return body as T;
}

const queryString = (values: Record<string, string | undefined>) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) params.set(key, value);
  const result = params.toString();
  return result ? `?${result}` : '';
};

export const api = {
  baseUrl: apiBase,
  getOverview: () => request<DashboardOverview>(routes.overview),
  getEvents: (filters: { search?: string; status?: string; severity?: string; resource?: string } = {}) =>
    request<{ items: CampusEvent[]; total?: number } | CampusEvent[]>(`${routes.events}${queryString(filters)}`).then((result) => Array.isArray(result) ? result : result.items),
  getActions: () => request<{ items: CampusAction[]; total?: number } | CampusAction[]>(routes.actions).then((result) => Array.isArray(result) ? result : result.items),
  sendFeedback: (id: string, feedback: 'FALSE_ALARM' | 'CONFIRMED') =>
    request<{ ok: boolean }>(routes.eventFeedback(id), { method: 'POST', body: JSON.stringify({ feedback }) }),
  approveAction: (id: string) => request<CampusAction>(routes.approveAction(id), { method: 'POST', headers: { 'Idempotency-Key': `ui-approve-${id}-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}` } }),
  rejectAction: (id: string, reason: string) => request<CampusAction>(routes.rejectAction(id), { method: 'POST', headers: { 'Idempotency-Key': `ui-reject-${id}-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}` }, body: JSON.stringify({ reason }) }),
  runScenario: (body: ScenarioRequest) => request<ScenarioResponse>(routes.runScenario, { method: 'POST', body: JSON.stringify(body) }),
  resetDemo: () => request<{ ok: boolean; message?: string }>(routes.resetDemo, { method: 'POST', body: JSON.stringify({}) }),
  askCopilot: async (question: string, context?: { eventId?: string }) => {
    const result = await request<{ answer: string; mode: 'LLM' | 'CACHED' | 'TEMPLATE'; source_ids: string[]; recommendations: Array<{ label: string; action_type: string }>; warnings: string[]; generated_at: string }>(routes.copilot, {
      method: 'POST', body: JSON.stringify({ question, event_ids: context?.eventId ? [context.eventId] : [], request_mode: 'AUTO' }),
    });
    return { answer: result.answer, mode: result.mode, groundedIn: result.source_ids || [], suggestions: (result.recommendations || []).map((item) => item.label), limitations: result.warnings || [], createdAt: result.generated_at } satisfies CopilotResponse;
  },
  runWhatIf: (body: WhatIfRequest) => request<WhatIfResponse>(routes.whatIf, { method: 'POST', body: JSON.stringify(body) }),
  getSettings: () => request<CampusSettings>(routes.settings),
  saveSettings: (body: CampusSettings) => request<CampusSettings>(routes.settings, { method: 'PATCH', body: JSON.stringify(body) }),
  getReports: () => request<{ items: import('../types').ReportRecord[] } | import('../types').ReportRecord[]>(routes.reports).then((result) => Array.isArray(result) ? result : result.items),
  exportReport: (format: 'json' | 'csv') => request<unknown>(`${routes.exportReport}${queryString({ format })}`),
  getPreflight: () => request<unknown>(routes.preflight),
};
