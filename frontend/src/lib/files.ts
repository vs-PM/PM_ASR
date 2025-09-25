import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import { apiUrl } from './api';

export type FileItem = {
  id: number;
  filename: string;
  size_bytes: number;
  mimetype: string | null;
  created_at: string; // ISO
};

export type FileList = {
  items: FileItem[];
  total: number;
};

export const PAGE_SIZE = 20;

export function filesKey(page: number, pageSize = PAGE_SIZE) {
  return ['files', page, pageSize] as const;
}

export async function fetchFiles(page: number, pageSize = PAGE_SIZE): Promise<FileList> {
  const offset = (page - 1) * pageSize;
  const url = `/api/v1/files/?limit=${pageSize}&offset=${offset}`;
  return api<FileList>(url);
}

export function useFiles(page: number, pageSize = PAGE_SIZE) {
  // важно: даём дженерики FileList/ Error → data становится типизированной
  return useQuery<FileList, Error>({
    queryKey: filesKey(page, pageSize),
    queryFn: () => fetchFiles(page, pageSize),
    staleTime: 10_000,
    // если хочешь эффект "сохранять предыдущие данные", в v5 можно так:
    // placeholderData: (prev) => prev as FileList | undefined,
  });
}

export function useInvalidateFiles() {
  const qc = useQueryClient();
  return (page?: number, pageSize = PAGE_SIZE) =>
    qc.invalidateQueries({ queryKey: page ? filesKey(page, pageSize) : ['files'] });
}

// utils
export function formatBytes(n: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0; let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString();
}

export function audioUrlById(id: number): string {
  return apiUrl(`/api/v1/files/${id}/raw`);
}
