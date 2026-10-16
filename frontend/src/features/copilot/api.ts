const API_BASE = ((import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env?.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    const message = body.length > 300 ? `${body.slice(0, 300)}…` : body;
    throw new Error(`Request failed (${response.status})${message ? `: ${message}` : ''}`);
  }
  return response.json() as Promise<T>;
}

export function downloadUrl(path: string): string {
  return `${API_BASE}${path}`;
}
