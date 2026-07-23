import { API } from "./theme";
import { ApiError } from "./api-error";

export { ApiError } from "./api-error";
import type {
  WantValue,
  FearValue,
  WhoMattersValue,
  GhostValue,
  TalentValue,
  FlawValue,
  LineValue,
} from "./newstory/options";

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
  debug?: Record<string, string>;
  created_at: string;
};

export type SessionSummary = {
  id: string;
  genre: string;
  role: string | null;
  tone: string | null;
  difficulty: string;
  debug_mode: boolean;
  title: string;
  turn_count: number;
  last_narrative_snippet: string;
  last_state: Record<string, string>;
  mode?: string;
  scenario_id?: string | null;
  mature_content?: MatureContentPreferences;
  distribution_capabilities?: DistributionCapabilities;
  rendering_policy?: RenderingPolicy;
  created_at: string;
  updated_at: string;
};

export type Scenario = {
  id: string;
  title: string;
  pitch: string;
  quick_description?: string;
  icon?: string;
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
  /** Provenance: which New Chronicle flow produced this setup. */
  creationFlow?: "guided" | "advanced" | "quick";
  // --- Advanced Builder starting conditions ---
  /** Maps to top-level genre at submit; stripped from seed bag if needed. */
  worldGenre?: string;
  customGenre?: string;
  /** Maps to top-level tone at submit. */
  storyFeel?: string;
  startingLocation?: string;
  customLocation?: string;
  startingRole?: string;
  customRole?: string;
  worldCondition?: string;
  recentChange?: string;
  customRecentChange?: string;
  characterKnowledge?: string;
  worldPace?: string;
  consequenceSeverity?: string;
  settingGroundedness?: string;
  worldElements?: string;
  worldExclusions?: string;

  // --- Advanced / custom free-text inputs (unchanged) ---
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

  // --- Quick Start story hooks (closed catalogs — see newstory/options.ts) ---
  want?: WantValue;
  fear?: FearValue;
  whoMatters?: WhoMattersValue;

  // --- Advanced optional narrative hook pool (closed catalogs) ---
  ghost?: GhostValue;
  talent?: TalentValue;
  flaw?: FlawValue;
  line?: LineValue;

  // --- Advanced optional free-text (kept hidden until reveal — see Phase 1 Blocker A) ---
  secret?: string;
};

export type MatureContentPreferences = {
  adult_mode_enabled: boolean;
  adult_age_confirmed: boolean;
  violence_level: "mild" | "realistic" | "graphic" | "extreme_gore";
  horror_level: "atmospheric" | "disturbing" | "graphic" | "extreme_psychological_or_body_horror";
  sexual_content_level: "off" | "romance_only" | "suggestive" | "fade_to_black" | "explicit" | "graphic";
  consent_boundary: "consensual_only" | "coercion_referenced" | "nonconsensual_implied" | "nonconsensual_on_screen" | "graphic_nonconsensual";
  player_involvement: "npcs_only" | "player_character" | "either";
  language_level: "mild" | "strong" | "unrestricted";
  substance_content_level: "mentioned" | "present" | "graphic_and_consequential";
  hard_limits: string[];
};

export type DistributionCapabilities = {
  channel: string;
  adult_mode_available: boolean;
  sexual_content_available: boolean;
  nonconsensual_content_available: boolean;
  graphic_sexual_content_available: boolean;
  mature_renderer_configured: boolean;
};

export type RenderingPolicy = {
  route: "standard" | "mature_pinned";
  failure_mode: "safe_standard";
  sexual_age_boundary: "explicit_18_plus_only";
  last_status?: string;
  last_renderer?: string;
};

export type SetupCapabilitiesResponse = {
  distribution_capabilities: DistributionCapabilities;
  mature_content_defaults: MatureContentPreferences;
};

export const SAFE_SETUP_CAPABILITIES: SetupCapabilitiesResponse = {
  distribution_capabilities: {
    channel: "store",
    adult_mode_available: false,
    sexual_content_available: false,
    nonconsensual_content_available: false,
    graphic_sexual_content_available: false,
    mature_renderer_configured: false,
  },
  mature_content_defaults: {
    adult_mode_enabled: false,
    adult_age_confirmed: false,
    violence_level: "mild",
    horror_level: "atmospheric",
    sexual_content_level: "off",
    consent_boundary: "consensual_only",
    player_involvement: "npcs_only",
    language_level: "mild",
    substance_content_level: "mentioned",
    hard_limits: [],
  },
};

const DEVICE_ID_HEADER = "X-Device-Id";
const ADMIN_API_KEY_HEADER = "X-Admin-Api-Key";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw await ApiError.fromResponse(res);
  }
  return res.json() as Promise<T>;
}

function deviceHeaders(deviceId: string): Record<string, string> {
  return { [DEVICE_ID_HEADER]: deviceId };
}

function adminHeaders(adminKey: string): Record<string, string> {
  return { [ADMIN_API_KEY_HEADER]: adminKey };
}

export type NewStoryPayload = {
  device_id: string;
  genre: string;
  role?: string;
  tone?: string;
  difficulty: string;
  debug_mode: boolean;
  custom_premise?: string;
  mode?: string;
  scenario_id?: string;
  /** Quick Start only — backend selects scenario_id from this card's pool. */
  quick_start_key?: string;
  custom_world_setup?: CustomWorldSetup;
  mature_content?: MatureContentPreferences;
  creation_request_id?: string;
};

export async function newStory(
  payload: NewStoryPayload
): Promise<{ session_id: string; turn: Turn; session: SessionSummary }> {
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

export async function setSessionMode(
  sessionId: string,
  deviceId: string,
  mode: "basic" | "advanced"
): Promise<{ mode: string }> {
  const res = await fetch(`${API}/story/session/${sessionId}/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify({ mode }),
  });
  return handle(res);
}

export async function exportSession(sessionId: string, deviceId: string): Promise<any> {
  const res = await fetch(`${API}/story/session/${sessionId}/export`, {
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export type HistoryEvent = { kind: string; text: string };
export type HistoryTurn = { turn: number; events: HistoryEvent[] };
export type OutcomeChange = { label: string; before?: string; after: string };
export type TurnOutcome = {
  turn: number;
  events: HistoryEvent[];
  changes: OutcomeChange[];
};

export async function getSessionHistory(
  sessionId: string,
  deviceId: string
): Promise<{ history: HistoryTurn[]; latest_outcome?: TurnOutcome | null }> {
  const res = await fetch(`${API}/story/session/${sessionId}/history`, {
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export async function resetSession(sessionId: string, deviceId: string): Promise<{ reset: boolean }> {
  const res = await fetch(`${API}/story/session/${sessionId}/reset`, {
    method: "POST",
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export async function sendAction(payload: {
  session_id: string;
  device_id: string;
  action_text: string;
  debug_mode: boolean;
}): Promise<{ turn: Turn }> {
  const { device_id, ...body } = payload;
  const res = await fetch(`${API}/story/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(device_id) },
    body: JSON.stringify(body),
  });
  return handle(res);
}

export async function listSessions(device_id: string): Promise<{ sessions: SessionSummary[] }> {
  const res = await fetch(`${API}/story/sessions`, {
    headers: deviceHeaders(device_id),
  });
  return handle(res);
}

export async function getSession(
  id: string,
  deviceId: string
): Promise<{ session: SessionSummary; turns: Turn[] }> {
  const res = await fetch(`${API}/story/session/${id}`, {
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export async function getLatestTurn(id: string, deviceId: string): Promise<{ turn: Turn }> {
  const res = await fetch(`${API}/story/session/${id}/latest`, {
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export async function deleteSession(id: string, deviceId: string): Promise<void> {
  const res = await fetch(`${API}/story/session/${id}`, {
    method: "DELETE",
    headers: deviceHeaders(deviceId),
  });
  if (!res.ok) {
    throw await ApiError.fromResponse(res);
  }
}

export type HealthResponse = {
  status: string;
  llm_configured: boolean;
};

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API}/health`);
  return handle(res);
}

export async function getSetupCapabilities(): Promise<SetupCapabilitiesResponse> {
  const res = await fetch(`${API}/setup/capabilities`);
  return handle(res);
}

export type AdminModel = {
  id: string;
  label: string;
  context?: number;
  note?: string;
};

export type AdminSettings = {
  model: string;
  temperature?: number;
  max_tokens?: number;
  history_window?: number;
  fallback_models?: string[];
  developer_mode?: boolean;
  [key: string]: unknown;
};

export type AdminSettingsResponse = {
  settings: AdminSettings;
  models: AdminModel[];
};

export async function getAdminSettings(adminKey: string): Promise<AdminSettingsResponse> {
  const res = await fetch(`${API}/admin/settings`, {
    headers: adminHeaders(adminKey),
  });
  return handle(res);
}

export async function updateAdminSettings(
  adminKey: string,
  patch: Partial<AdminSettings>
): Promise<{ settings: AdminSettings }> {
  const res = await fetch(`${API}/admin/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...adminHeaders(adminKey) },
    body: JSON.stringify(patch),
  });
  return handle(res);
}
