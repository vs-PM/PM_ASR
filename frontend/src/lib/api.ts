// src/lib/api.ts
export type ApiOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  headers?: Record<string, string>;
  body?: unknown;
  signal?: AbortSignal;
};

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { method = 'GET', headers = {}, body, signal } = opts;

  const url = path.startsWith('/') ? path : `/api/v1/${path}`;
  const res = await fetch(url, {
    method,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    body: body == null ? undefined : JSON.stringify(body),
    signal,
    cache: 'no-store',
  });

  if (!res.ok) {
    // Пытаемся прочитать осмысленную ошибку
    let message = `${res.status} ${res.statusText}`;
    try {
      const ct = res.headers.get('content-type');
      if (ct && ct.includes('application/json')) {
        const j = (await res.json()) as { detail?: unknown; message?: unknown };
        message =
          typeof j?.detail === 'string'
            ? j.detail
            : typeof j?.message === 'string'
            ? j.message
            : message;
      } else {
        const t = await res.text();
        if (t) message = t;
      }
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }

  const ct = res.headers.get('content-type');
  if (ct && ct.includes('application/json')) {
    return (await res.json()) as T;
  }
  // Пустой ответ или текст
  const text = await res.text();
  return (text as unknown) as T;
}
