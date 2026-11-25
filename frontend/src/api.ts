// Thin typed client. Same-origin paths: nginx (Docker) or Vite (dev) forwards them to the API.

export type Health = { status: string; version: string; database: string; llm_mode: string; runs: Record<string, number> };
export type Agent = { kind: string; title: string; job: string; built: boolean };
export type Doc = { id: string; kind: string; filename: string; size_bytes: number; created_at: string };
export type Run = {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  document_id: string | null;
  progress: number;
  message: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  finished_at: string | null;
};
export type GoalSeek = { value: number | null; achieved: number | null; iterations: number; converged: boolean; elapsed_ms: number; message: string };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => call<Health>("/health"),
  agents: () => call<Agent[]>("/api/agents"),
  documents: () => call<Doc[]>("/api/documents"),
  runs: () => call<Run[]>("/api/runs?limit=30"),
  goalSeek: (docId: string, variable: string, target: string, targetValue: number) =>
    call<GoalSeek>(`/api/workbooks/${docId}/goal-seek`, {
      method: "POST",
      body: JSON.stringify({ variable, target, target_value: targetValue }),
    }),
  upload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/documents", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
    return res.json();
  },
};
