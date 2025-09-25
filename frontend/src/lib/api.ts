// src/lib/api.ts
export type ApiOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  headers?: Record<string, string>;
  body?: unknown;
  signal?: AbortSignal;
};

const PUBLIC_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? '').replace(/\/+$/, '');

function buildUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/api/v1/${path}`;
  return PUBLIC_BASE ? `${PUBLIC_BASE}${p}` : p;
}

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { method = 'GET', headers = {}, body, signal } = opts;
  const url = buildUrl(path);

  const res = await fetch(url, {
    method,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body == null ? undefined : JSON.stringify(body),
    signal,
    cache: 'no-store',
  });

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const ct = res.headers.get('content-type') ?? '';
      if (ct.includes('application/json')) {
        const j = (await res.json()) as { detail?: unknown; message?: unknown };
        if (typeof j?.detail === 'string') message = j.detail;
        else if (typeof j?.message === 'string') message = j.message;
      } else {
        const t = await res.text();
        if (t) message = t;
      }
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }

  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) return (await res.json()) as T;
  return (await res.text()) as T;
}

export function apiUrl(path: string): string {
  return buildUrl(path);
}
