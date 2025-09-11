'use client';
import { Badge } from '@/components/ui/badge';

export function StatusBadge({ status }: { status?: string }) {
  const map: Record<string, { label: string; className: string }> = {
    ok:        { label: 'OK',        className: 'bg-green-600 text-white' },
    alive:     { label: 'Alive',     className: 'bg-green-600 text-white' },
    degraded:  { label: 'Degraded',  className: 'bg-yellow-500 text-black' }, // MFG: жёлтый акцент
    error:     { label: 'Error',     className: 'bg-red-600 text-white' },
    unknown:   { label: 'Unknown',   className: 'bg-gray-400 text-black' },
  };
  const v = map[status || 'unknown'] ?? map.unknown;
  return <Badge className={v.className}>{v.label}</Badge>;
}
