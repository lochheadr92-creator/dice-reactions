import type { SessionSummary, Turn } from "./api";
import { hasNewerTurnThan } from "./chronicle-merge";

export const DEFAULT_CONFLICT_POLL_ATTEMPTS = 3;
export const DEFAULT_CONFLICT_POLL_DELAY_MS = 1000;

export type ConflictSyncSignal = {
  cancelled: boolean;
};

export type ConflictSyncDeps = {
  getSession: (
    sessionId: string,
    deviceId: string
  ) => Promise<{ session: SessionSummary; turns: Turn[] }>;
  sessionId: string;
  deviceId: string;
  baselineMaxTurnNumber: number;
  maxAttempts?: number;
  delayMs?: number;
  sleep?: (ms: number) => Promise<void>;
  signal?: ConflictSyncSignal;
};

export type ConflictSyncResult = {
  session: SessionSummary;
  turns: Turn[];
  foundNewerTurn: boolean;
};

const defaultSleep = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

export async function syncAfterActionConflict(
  deps: ConflictSyncDeps
): Promise<ConflictSyncResult> {
  const maxAttempts = deps.maxAttempts ?? DEFAULT_CONFLICT_POLL_ATTEMPTS;
  const delayMs = deps.delayMs ?? DEFAULT_CONFLICT_POLL_DELAY_MS;
  const sleep = deps.sleep ?? defaultSleep;

  let latestSession: SessionSummary | null = null;
  let latestTurns: Turn[] = [];

  for (let attempt = 0; attempt <= maxAttempts; attempt += 1) {
    if (deps.signal?.cancelled) {
      break;
    }
    const res = await deps.getSession(deps.sessionId, deps.deviceId);
    latestSession = res.session;
    latestTurns = res.turns;
    if (hasNewerTurnThan(deps.baselineMaxTurnNumber, latestTurns)) {
      return {
        session: latestSession,
        turns: latestTurns,
        foundNewerTurn: true,
      };
    }
    if (attempt < maxAttempts) {
      await sleep(delayMs);
    }
  }

  return {
    session: latestSession!,
    turns: latestTurns,
    foundNewerTurn: false,
  };
}