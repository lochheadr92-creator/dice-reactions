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
