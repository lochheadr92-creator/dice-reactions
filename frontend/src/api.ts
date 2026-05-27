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
  rolling_state: Record<string, any> | null;
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
  rolling_state?: Record<string, any> | null;
  mode?: string;
  scenario_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type Scenario = {
  id: string;
  title: string;
  pitch: string;
  genre: string;
  role: string;
  tone: string;
  difficulty: string;
  mode: string;
  starting_location: string;
  starting_pressure: string;
  key_npcs: { name: string; role: string; stance: string }[];
  starting_inventory: string;
  hidden_threat: string;
};

export type CustomWorldSetup = {
  worldConcept?: string;
  worldTone?: string;
  danger?: string;
  origin?: string;
  formerLife?: string;
  strengths?: string;
  weakness?: string;
  carried?: string;
  desire?: string;
  pressures?: string[];
  storyFocus?: string[];
  contentSettings?: Record<string, string>;
  seedAnswers?: string[];
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
  mode?: string;
  scenario_id?: string;
  custom_world_setup?: CustomWorldSetup;
}): Promise<{ session_id: string; turn: Turn; session: SessionSummary }> {
  const res = await fetch(`${API}/story/new`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

export async function listScenarios(): Promise<{ scenarios: Scenario[] }> {
  const res = await fetch(`${API}/scenarios`);
  return handle(res);
}

export async function setSessionMode(sessionId: string, mode: "basic" | "advanced"): Promise<{ mode: string }> {
  const res = await fetch(`${API}/story/session/${sessionId}/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  return handle(res);
}

export async function exportSession(sessionId: string): Promise<any> {
  const res = await fetch(`${API}/story/session/${sessionId}/export`);
  return handle(res);
}

export async function resetSession(sessionId: string): Promise<{ reset: boolean }> {
  const res = await fetch(`${API}/story/session/${sessionId}/reset`, { method: "POST" });
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
  default_mode?: string;
  compression_level?: string;
  memory_depth?: number;
  developer_mode?: boolean;
};

export type AdminSettingsBundle = {
  settings: AISettings;
  models: ModelOption[];
  modes?: string[];
  compression_levels?: string[];
  limits: {
    temperature: { min: number; max: number; step: number };
    max_tokens: { min: number; max: number; step: number };
    history_window: { min: number; max: number; step: number };
    memory_depth?: { min: number; max: number; step: number };
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
