/**
 * Pending player-action bookkeeping for action idempotency.
 *
 * One deliberate action keeps ONE request id until its outcome is known.
 * The same id + text are retried while the outcome is uncertain (lost
 * response, 502/503, lease conflict). A deliberate new action (different
 * text or debug flag) gets a fresh id. The pending record is persisted per
 * session so a reload can query the request status instead of resending.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

export type PendingAction = {
  requestId: string;
  text: string;
  debugMode: boolean;
  createdAt: string;
};

const PENDING_KEY_PREFIX = "dice_pending_action:";

export function createActionRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === "function") {
    return `action:${cryptoApi.randomUUID()}`;
  }
  if (typeof cryptoApi?.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    cryptoApi.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `action:${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return `action:${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function pendingActionKey(sessionId: string): string {
  return `${PENDING_KEY_PREFIX}${sessionId}`;
}

/**
 * Reuse the pending id only when the meaningful contents are identical;
 * otherwise this is a deliberate new action and needs a new id.
 */
export function resolveRequestId(
  pending: PendingAction | null,
  text: string,
  debugMode: boolean
): string {
  if (pending && pending.text === text.trim() && pending.debugMode === debugMode) {
    return pending.requestId;
  }
  return createActionRequestId();
}

export function buildPendingAction(requestId: string, text: string, debugMode: boolean): PendingAction {
  return { requestId, text: text.trim(), debugMode, createdAt: new Date().toISOString() };
}

function isPendingAction(value: unknown): value is PendingAction {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.requestId === "string" &&
    v.requestId.length > 0 &&
    typeof v.text === "string" &&
    typeof v.debugMode === "boolean"
  );
}

export async function loadPendingAction(sessionId: string): Promise<PendingAction | null> {
  try {
    const raw = await AsyncStorage.getItem(pendingActionKey(sessionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return isPendingAction(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export async function savePendingAction(sessionId: string, pending: PendingAction): Promise<void> {
  try {
    await AsyncStorage.setItem(pendingActionKey(sessionId), JSON.stringify(pending));
  } catch {
    // Persistence is best-effort; the in-memory copy still guards this session.
  }
}

export async function clearPendingAction(sessionId: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(pendingActionKey(sessionId));
  } catch {
    // Ignore storage failures on clear.
  }
}
