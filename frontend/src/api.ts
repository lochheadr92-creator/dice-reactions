import { API } from "./theme";
import { ApiError } from "./api-error";
import type {
  WantValue,
  FearValue,
  WhoMattersValue,
  GhostValue,
  TalentValue,
  FlawValue,
  LineValue,
} from "./newstory/options";

export { ApiError } from "./api-error";

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
  /** Whom the player controlled on this turn. Present once a handover has happened. */
  character?: { name: string | null; role: string | null };
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
  /** Set on a branch: "Branch 1", "Branch 1.2". */
  branch_label?: string;
  branch_root_title?: string;
  branched_from?: { session_id: string; title: string; turn_number: number };
  /** Who the player controls now, after a chapter handover. */
  protagonist?: { name: string | null; role: string | null };
  handover_done?: boolean;
  /** Standing instructions the player left: their words, what she understood, a result once seen. */
  orders_given?: OrderGiven[];
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
  /** The player's own idea for the story. Stays true for the whole chronicle. */
  premise?: string;
  /** present_day | past | future. Absent = the world type decides. */
  timePeriod?: string;
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
  /** Narration length: brief / standard / story / cinematic (the S/M/L/XL setting). */
  prose_mode?: string;
  /** Writing style: plain / balanced / rich. */
  prose_style?: string;
  /** How long the model thinks before writing: low / medium / high. */
  thinking_effort?: string;
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

export type SessionPlaySettings = {
  prose_mode?: string;
  prose_style?: string;
  thinking_effort?: string;
};

/** Turn length, writing style and speed for an existing story. The next turn uses them. */
export async function setSessionPlaySettings(
  sessionId: string,
  deviceId: string,
  settings: SessionPlaySettings
): Promise<SessionPlaySettings> {
  const res = await fetch(`${API}/story/session/${sessionId}/play-settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify(settings),
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

export type SendActionResponse = {
  turn: Turn;
  /** True when the backend returned the saved result of an already-completed request id. */
  replayed?: boolean;
};

export type Disclosure = { recipient: string; claim: string; aloud: boolean };

export type TellTargets = { turn_count: number; people: { name: string }[] };

export async function getTellTargets(sessionId: string, deviceId: string): Promise<TellTargets> {
  const res = await fetch(`${API}/story/session/${sessionId}/tell-targets`, {
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export type OrderPreview = {
  recipient: string;
  understood: { condition: string; action: string; even_if_away: boolean } | null;
  issues: string[];
  notes: string[];
  can_commit: boolean;
};

export type OrderGiven = { id: string; turn: number; to: string; text: string; understood: string; result?: string };

export async function previewOrder(
  sessionId: string,
  deviceId: string,
  body: { recipient: string; text: string }
): Promise<OrderPreview> {
  const res = await fetch(`${API}/story/session/${sessionId}/orders/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify(body),
  });
  return handle(res);
}

export function orderActionText(o: { recipient: string; text: string }): string {
  return `You leave instructions with ${o.recipient.trim()}: "${o.text.trim()}"`;
}

export function disclosureActionText(d: Disclosure): string {
  const claim = d.claim.trim();
  return d.aloud
    ? `You say aloud to ${d.recipient}: "${claim}"`
    : `You quietly tell ${d.recipient}: "${claim}"`;
}

export async function sendAction(payload: {
  session_id: string;
  device_id: string;
  action_text: string;
  debug_mode: boolean;
  /** Client idempotency key: one id ⇒ at most one committed turn. */
  action_request_id?: string;
  /** Turn count on screen. A mismatch means the choices are stale; the server refuses (409). */
  expected_turn_count?: number;
  /** Structured "tell someone": the engine records exactly this wording, speaker and witnesses. */
  disclosure?: Disclosure;
  /** Standing instructions for one person here. The server re-parses; a preview is never trusted. */
  order?: { recipient: string; text: string };
  /** One of the seven player moves. The server checks it against the saved story and decides the outcome. */
  move?: MoveRequest;
}): Promise<SendActionResponse> {
  const { device_id, ...body } = payload;
  const res = await fetch(`${API}/story/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(device_id) },
    body: JSON.stringify(body),
  });
  return handle(res);
}


// ---- Player moves (challenge, bargain, route, regard, build, signal, teach) ----

export type MoveKind = "challenge" | "bargain" | "route" | "regard" | "build" | "signal" | "teach";
export type MoveRequest = { kind: MoveKind; op?: string; args: Record<string, unknown> };
export type PassageRef = { turn: number; paragraph: number; quote: string; speaker?: string };
export type MoveOptions = { kind: MoveKind; available: boolean; reason: string | null } & Record<string, any>;
export type MoveOffer = { kind: MoveKind; label: string; prefill: Record<string, string[]> };
export type MovesResponse = { turn_count: number; moves: Record<MoveKind, MoveOptions>; offers: MoveOffer[] };

export type MovePreview = { kind: MoveKind; can_commit: boolean; issues: string[]; terms?: string; notes?: string[]; shown?: unknown };

export async function getMoves(sessionId: string, deviceId: string): Promise<MovesResponse> {
  const res = await fetch(`${API}/story/session/${sessionId}/moves`, { headers: deviceHeaders(deviceId) });
  return handle(res);
}

export async function previewMove(sessionId: string, deviceId: string, move: MoveRequest): Promise<MovePreview> {
  const res = await fetch(`${API}/story/session/${sessionId}/moves/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify(move),
  });
  return handle(res);
}

export type ActionRequestStatus = {
  status: "completed" | "in_progress" | "failed" | "unknown";
  turn?: Turn;
  error_kind?: string;
};

export async function getActionRequestStatus(
  sessionId: string,
  requestId: string,
  deviceId: string
): Promise<ActionRequestStatus> {
  const res = await fetch(
    `${API}/story/session/${sessionId}/action/${encodeURIComponent(requestId)}`,
    { headers: deviceHeaders(deviceId) }
  );
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


// ---------------------------------------------------------------------------
// Branching, private notebook, chapter handover
// ---------------------------------------------------------------------------
export type BranchResponse = {
  session: SessionSummary;
  replayed: boolean;
  source_turn_count: number;
};

export async function branchSession(
  sessionId: string,
  deviceId: string,
  requestId: string,
  expectedTurnCount: number
): Promise<BranchResponse> {
  const res = await fetch(`${API}/story/session/${sessionId}/branch`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify({ request_id: requestId, expected_turn_count: expectedTurnCount }),
  });
  return handle(res);
}

export type NotebookPin = {
  id: string;
  kind: "pin";
  turn_number: number;
  turn_id?: string;
  paragraph_index: number;
  start: number;
  end: number;
  text: string;
  note: string;
  created_at: string;
};

export type NotebookTheory = {
  id: string;
  kind: "theory";
  title: string;
  body: string;
  pin_ids: string[];
  created_at: string;
  updated_at: string;
};

export type Notebook = { pins: NotebookPin[]; theories: NotebookTheory[] };

export async function getNotebook(sessionId: string, deviceId: string): Promise<Notebook> {
  const res = await fetch(`${API}/story/session/${sessionId}/notebook`, {
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export async function pinPassage(
  sessionId: string,
  deviceId: string,
  body: { turn_number: number; paragraph_index: number; quote?: string; occurrence?: number; note?: string }
): Promise<{ pin: NotebookPin; created: boolean }> {
  const res = await fetch(`${API}/story/session/${sessionId}/notebook/pins`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify(body),
  });
  return handle(res);
}

export async function removePin(sessionId: string, deviceId: string, pinId: string): Promise<void> {
  const res = await fetch(`${API}/story/session/${sessionId}/notebook/pins/${pinId}`, {
    method: "DELETE",
    headers: deviceHeaders(deviceId),
  });
  if (!res.ok) throw await ApiError.fromResponse(res);
}

export async function createTheory(
  sessionId: string,
  deviceId: string,
  body: { title: string; body: string; pin_ids: string[] }
): Promise<{ theory: NotebookTheory }> {
  const res = await fetch(`${API}/story/session/${sessionId}/notebook/theories`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify(body),
  });
  return handle(res);
}

export async function updateTheory(
  sessionId: string,
  deviceId: string,
  theoryId: string,
  body: { title?: string; body?: string; pin_ids?: string[] }
): Promise<{ theory: NotebookTheory }> {
  const res = await fetch(`${API}/story/session/${sessionId}/notebook/theories/${theoryId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify(body),
  });
  return handle(res);
}

export async function deleteTheory(sessionId: string, deviceId: string, theoryId: string): Promise<void> {
  const res = await fetch(`${API}/story/session/${sessionId}/notebook/theories/${theoryId}`, {
    method: "DELETE",
    headers: deviceHeaders(deviceId),
  });
  if (!res.ok) throw await ApiError.fromResponse(res);
}

export async function getTurnByNumber(
  sessionId: string,
  deviceId: string,
  turnNumber: number
): Promise<{ turn: Turn }> {
  const res = await fetch(`${API}/story/session/${sessionId}/turn/${turnNumber}`, {
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export type HandoverCandidate = {
  id: string;
  name: string;
  relation: string;
  last_seen: string;
  appearances: number;
};

export type HandoverCandidates = {
  turn_count: number;
  can_end_chapter: boolean;
  reason: string | null;
  candidates: HandoverCandidate[];
};

export async function getHandoverCandidates(
  sessionId: string,
  deviceId: string
): Promise<HandoverCandidates> {
  const res = await fetch(`${API}/story/session/${sessionId}/handover`, {
    headers: deviceHeaders(deviceId),
  });
  return handle(res);
}

export type HandoverResponse = {
  session: SessionSummary;
  turn: Turn | null;
  replayed: boolean;
};

export async function confirmHandover(
  sessionId: string,
  deviceId: string,
  body: { request_id: string; successor_id: string; expected_turn_count: number }
): Promise<HandoverResponse> {
  const res = await fetch(`${API}/story/session/${sessionId}/handover`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: JSON.stringify(body),
  });
  return handle(res);
}


// ---- Two friends, opposite sides (duets) ----

export type DuetEntry = { turn: number; kind: "opening" | "you" | "observed"; text: string; action?: string };

export type DuetView = {
  id: string;
  title: string;
  status: "waiting_for_friend" | "active" | "chapter_ended";
  you: { seat: string; label: string; character: { name: string; role: string; inventory: string[]; [k: string]: any } };
  other: { seat: string; name: string; role: string; joined: boolean };
  turn_count: number;
  your_turn: boolean;
  waiting_for: string | null;
  history: DuetEntry[];
  choices: TurnChoice[];
  known: { boat: string };
  /** Signals the two lamp keepers have offered or agreed. Meanings are shown to both seats once agreed. */
  signals: { id: string; count: number; meaning: string; status: "proposed" | "agreed"; mine: boolean }[];
  /** Signals can only be settled before the first lamp is lit. */
  signal_window_open: boolean;
  chapter_ended: boolean;
};

export type DuetListItem = {
  id: string;
  title: string;
  status: DuetView["status"];
  seat: string;
  label: string;
  other_name: string;
  turn_count: number;
  your_turn: boolean;
};

export type DuetComparison = {
  ended: boolean;
  you_shared: boolean | null;
  both_shared: boolean;
  accounts: { seat: string; mine: boolean; character: { name: string; role: string }; entries: DuetEntry[] }[];
};

async function duetCall<T>(deviceId: string, method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...deviceHeaders(deviceId) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handle<T>(res);
}

export const listDuets = (d: string) => duetCall<{ duets: DuetListItem[] }>(d, "GET", "/duets");
export const createDuet = (d: string, seat: string) =>
  duetCall<{ duet: DuetView; invite_code: string }>(d, "POST", "/duets", { seat });
export const joinDuet = (d: string, code: string) => duetCall<{ duet: DuetView }>(d, "POST", "/duets/join", { code });
export const reissueDuetInvite = (d: string, id: string) =>
  duetCall<{ invite_code: string }>(d, "POST", `/duets/${id}/invite`);
export const getDuet = (d: string, id: string) => duetCall<{ duet: DuetView }>(d, "GET", `/duets/${id}`);
export const duetAction = (d: string, id: string, body: { action_text: string; action_request_id: string; expected_turn_count?: number; clarity?: "clear" | "faint" }) =>
  duetCall<{ duet: DuetView; replayed: boolean }>(d, "POST", `/duets/${id}/action`, body);
export const proposeDuetSignal = (d: string, id: string, body: { request_id: string; count: number; meaning: string }) =>
  duetCall<{ duet: DuetView }>(d, "POST", `/duets/${id}/signals`, body);
export const respondDuetSignal = (d: string, id: string, signalId: string, accept: boolean) =>
  duetCall<{ duet: DuetView }>(d, "POST", `/duets/${id}/signals/${signalId}/respond`, { accept });
export const endDuetChapter = (d: string, id: string) => duetCall<{ duet: DuetView }>(d, "POST", `/duets/${id}/end-chapter`);
export const getDuetComparison = (d: string, id: string) => duetCall<DuetComparison>(d, "GET", `/duets/${id}/comparison`);
export const shareDuetComparison = (d: string, id: string, share: boolean) =>
  duetCall<DuetComparison>(d, "POST", `/duets/${id}/comparison`, { share });
