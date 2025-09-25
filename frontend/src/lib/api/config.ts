const rawBase = import.meta.env.VITE_API_BASE_URL?.trim();

export const API_BASE_URL = rawBase ? rawBase.replace(/\/$/, '') : '';

export function resolveApiPath(path: string): string {
  if (!path.startsWith('/')) {
    return `${API_BASE_URL}/${path}`;
  }
  return `${API_BASE_URL}${path}`;
}
