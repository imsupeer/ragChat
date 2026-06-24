const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    cache: 'no-store',
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;

    try {
      const data = await response.json();
      const rawDetail = data?.detail ?? data?.message;
      if (typeof rawDetail === 'string') {
        detail = rawDetail;
      } else if (rawDetail && typeof rawDetail === 'object' && 'message' in rawDetail) {
        detail = String((rawDetail as { message?: string }).message ?? detail);
      } else if (rawDetail) {
        detail = JSON.stringify(rawDetail);
      }
    } catch {
      const text = await response.text();
      if (text) detail = text;
    }

    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function getApiUrl(path: string): string {
  return `${API_URL}${path}`;
}
