import { API } from "./theme";

export type TurnChoice = { label: string; text: string };

export type Turn = {
  id: string;
  session_id: string;
  turn_number: number;
  player_action: string | null;
  narrative: string;
  paragraphs: string[];
  choices: TurnChoice[];
  state: Record<string, string>;
  ledger: Record<string, string>;
  debug: Record<string, string> | null;
  created_at: string;
};

export type SessionSummary = {
  id: string;
  device_id: string;
  genre: string;
  role: string | null;
  tone: string | null;
  difficulty: string;
  debug_mode: boolean;
  title: string;
  turn_count: number;
  last_narrative_snippet: string;
  last_state: Record<string, string>;
  created_at: string;
  updated_at: string;
};

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function newStory(payload: {
  device_id: string;
  genre: string;
  role?: string;
  tone?: string;
  difficulty: string;
  debug_mode: boolean;
  custom_premise?: string;
}): Promise<{ session_id: string; turn: Turn; session: SessionSummary }> {
  const res = await fetch(`${API}/story/new`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

export async function sendAction(payload: {
  session_id: string;
  action_text: string;
  debug_mode: boolean;
}): Promise<{ turn: Turn }> {
  const res = await fetch(`${API}/story/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

export async function listSessions(device_id: string): Promise<{ sessions: SessionSummary[] }> {
  const res = await fetch(`${API}/story/sessions?device_id=${encodeURIComponent(device_id)}`);
  return handle(res);
}

export async function getSession(id: string): Promise<{ session: SessionSummary; turns: Turn[] }> {
  const res = await fetch(`${API}/story/session/${id}`);
  return handle(res);
}

export async function getLatestTurn(id: string): Promise<{ turn: Turn }> {
  const res = await fetch(`${API}/story/session/${id}/latest`);
  return handle(res);
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`${API}/story/session/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status}`);
}

// ---------------------------------------------------------------------------
// Admin · AI settings
// ---------------------------------------------------------------------------
export type ModelOption = {
  id: string;
  label: string;
  context: number;
  note?: string;
};

export type AISettings = {
  model: string;
  temperature: number;
  max_tokens: number;
  history_window: number;
};

export type AdminSettingsBundle = {
  settings: AISettings;
  models: ModelOption[];
  limits: {
    temperature: { min: number; max: number; step: number };
    max_tokens: { min: number; max: number; step: number };
    history_window: { min: number; max: number; step: number };
  };
  defaults: AISettings;
  provider_configured: boolean;
};

export async function getAdminSettings(): Promise<AdminSettingsBundle> {
  const res = await fetch(`${API}/admin/settings`);
  return handle(res);
}

export async function saveAdminSettings(
  patch: Partial<AISettings>
): Promise<{ settings: AISettings }> {
  const res = await fetch(`${API}/admin/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return handle(res);
}

export type HealthResponse = {
  status: string;
  llm_configured: boolean;
  provider: string;
  model: string;
  temperature: number;
  max_tokens: number;
  history_window: number;
};

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API}/health`);
  return handle(res);
}
