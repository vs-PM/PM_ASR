export function fmtTime(msOrSec: number | null | undefined): string {
  if (msOrSec == null) return '—';
  // приходят секунды (float) → мм:сс.мс
  const totalMs = Math.round((msOrSec as number) * 1000);
  const mm = Math.floor(totalMs / 60000);
  const ss = Math.floor((totalMs % 60000) / 1000);
  const ms = totalMs % 1000;
  const pad = (n: number, w: number) => String(n).padStart(w, '0');
  return `${pad(mm, 2)}:${pad(ss, 2)}.${pad(ms, 3)}`;
}

/** Ключ для списка митингов */
export function meetingsKey(page: number, pageSize: number) {
  return ['meetings', page, pageSize] as const;
}
