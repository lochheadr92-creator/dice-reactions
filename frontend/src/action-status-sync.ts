import type { ActionRequestStatus } from "./api";
import { ApiError } from "./api-error";

export const DEFAULT_STATUS_POLL_ATTEMPTS = 4;
export const DEFAULT_STATUS_POLL_DELAY_MS = 1500;

export type StatusSyncSignal = { cancelled: boolean };

export type StatusSyncDeps = {
  getActionRequestStatus: (
    sessionId: string,
    requestId: string,
    deviceId: string
  ) => Promise<ActionRequestStatus>;
  sessionId: string;
  requestId: string;
  deviceId: string;
  maxAttempts?: number;
  delayMs?: number;
  sleep?: (ms: number) => Promise<void>;
  signal?: StatusSyncSignal;
};

const defaultSleep = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

/**
 * Resolve the outcome of an action whose response was lost or which was
 * still in progress. Polls the read-only status endpoint (never resends the
 * action) until the backend reports a final state or attempts run out.
 *
 * Returned ``status``:
 *   completed   — the committed turn is included; the client must not resend.
 *   failed      — no transition happened; safe to resend with the SAME id.
 *   in_progress — still resolving after the bounded poll; keep the id and text.
 *   unknown     — the backend has no record (legacy or never received); keep text.
 */
export async function resolvePendingActionStatus(
  deps: StatusSyncDeps
): Promise<ActionRequestStatus> {
  const maxAttempts = deps.maxAttempts ?? DEFAULT_STATUS_POLL_ATTEMPTS;
  const delayMs = deps.delayMs ?? DEFAULT_STATUS_POLL_DELAY_MS;
  const sleep = deps.sleep ?? defaultSleep;
  let latest: ActionRequestStatus = { status: "unknown" };

  for (let attempt = 0; attempt <= maxAttempts; attempt += 1) {
    if (deps.signal?.cancelled) break;
    let reachedBackend = false;
    try {
      latest = await deps.getActionRequestStatus(deps.sessionId, deps.requestId, deps.deviceId);
      reachedBackend = true;
    } catch (error) {
      if (ApiError.isNotFound(error)) {
        // Session (or ownership) gone: nothing to wait for.
        return { status: "unknown" };
      }
      latest = { status: "unknown" };
      // Network still down: keep polling within the bounded attempts.
    }
    // Only in_progress can change by waiting. A backend-reported unknown means
    // the id was never recorded (nothing can complete under it without a send).
    if (reachedBackend && latest.status !== "in_progress") {
      return latest;
    }
    if (attempt < maxAttempts) {
      await sleep(delayMs);
    }
  }
  return latest;
}
