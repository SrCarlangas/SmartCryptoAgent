import type {
  ConfigOut,
  ConfigSaveResponse,
  DashboardSnapshot,
  InstructionOut,
  InstructionPreviewOut,
} from './types';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      detail = await res.text();
    }
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

export const api = {
  health: () => request<{ status: string; uptime_s: number; bot_alive: boolean; ws_connections: number }>('/api/health'),
  dashboard: () => request<DashboardSnapshot>('/api/dashboard'),
  trades: (limit = 50) => request<unknown[]>(`/api/trades?limit=${limit}`),
  decisions: (limit = 20) => request<unknown[]>(`/api/decisions?limit=${limit}`),
  logs: (lines = 200) => request<{ lines: string[]; total: number }>(`/api/logs?lines=${lines}`),

  listInstructions: () => request<InstructionOut[]>('/api/instructions'),
  previewInstruction: (text: string, complex = false) =>
    request<InstructionPreviewOut>('/api/instructions/preview', {
      method: 'POST',
      body: JSON.stringify({ text, complex }),
    }),
  createInstruction: (text: string, complex = false, expires_at?: number) =>
    request<InstructionOut>('/api/instructions', {
      method: 'POST',
      body: JSON.stringify({ text, complex, expires_at }),
    }),
  cancelInstruction: (id: string) =>
    request<InstructionOut>(`/api/instructions/${id}/cancel`, { method: 'POST' }),

  getConfig: () => request<ConfigOut>('/api/config'),
  updateConfig: (changes: Record<string, unknown>) =>
    request<ConfigSaveResponse>('/api/config', {
      method: 'PUT',
      body: JSON.stringify(changes),
    }),
};
