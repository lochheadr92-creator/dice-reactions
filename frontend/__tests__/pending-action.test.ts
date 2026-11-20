import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  buildPendingAction,
  clearPendingAction,
  createActionRequestId,
  loadPendingAction,
  resolveRequestId,
  savePendingAction,
} from "../src/pending-action";
import { resolvePendingActionStatus } from "../src/action-status-sync";
import type { ActionRequestStatus, Turn } from "../src/api";

const turn: Turn = {
  id: "turn-9",
  session_id: "s",
  turn_number: 9,
  player_action: "wait",
  narrative: "done",
  paragraphs: ["done"],
  choices: [],
  state: {},
  ledger: {},
  created_at: "2026-01-01T00:00:00Z",
};

describe("pending action request ids", () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it("creates distinct ids with the action prefix", () => {
    const a = createActionRequestId();
    const b = createActionRequestId();
    expect(a).toMatch(/^action:/);
    expect(a).not.toBe(b);
  });

  it("reuses the pending id only for identical text and debug flag", () => {
    const pending = buildPendingAction("action:1", "  open the door ", false);
    expect(pending.text).toBe("open the door");
    expect(resolveRequestId(pending, "open the door", false)).toBe("action:1");
    expect(resolveRequestId(pending, "open the door ", false)).toBe("action:1");
    expect(resolveRequestId(pending, "run", false)).not.toBe("action:1");
    expect(resolveRequestId(pending, "open the door", true)).not.toBe("action:1");
    expect(resolveRequestId(null, "open the door", false)).not.toBe("action:1");
  });

  it("persists, restores, and clears per session", async () => {
    const pending = buildPendingAction("action:2", "wait", true);
    await savePendingAction("sess-a", pending);
    expect(await loadPendingAction("sess-a")).toEqual(pending);
    expect(await loadPendingAction("sess-b")).toBeNull();
    await clearPendingAction("sess-a");
    expect(await loadPendingAction("sess-a")).toBeNull();
  });

  it("ignores malformed stored records", async () => {
    await AsyncStorage.setItem("dice_pending_action:sess-x", JSON.stringify({ requestId: "" }));
    expect(await loadPendingAction("sess-x")).toBeNull();
    await AsyncStorage.setItem("dice_pending_action:sess-y", "not json");
    expect(await loadPendingAction("sess-y")).toBeNull();
  });
});

describe("resolvePendingActionStatus", () => {
  const noSleep = async () => {};

  it("returns the completed turn without resending", async () => {
    const getStatus = jest.fn(async (): Promise<ActionRequestStatus> => ({ status: "completed", turn }));
    const result = await resolvePendingActionStatus({
      getActionRequestStatus: getStatus,
      sessionId: "s",
      requestId: "action:1",
      deviceId: "d",
      sleep: noSleep,
    });
    expect(result.status).toBe("completed");
    expect(result.turn?.id).toBe("turn-9");
    expect(getStatus).toHaveBeenCalledTimes(1);
  });

  it("keeps polling while in_progress, up to the bounded attempts", async () => {
    const getStatus = jest
      .fn<Promise<ActionRequestStatus>, [string, string, string]>()
      .mockResolvedValueOnce({ status: "in_progress" })
      .mockResolvedValueOnce({ status: "in_progress" })
      .mockResolvedValueOnce({ status: "failed", error_kind: "provider_unavailable" });
    const result = await resolvePendingActionStatus({
      getActionRequestStatus: getStatus,
      sessionId: "s",
      requestId: "action:1",
      deviceId: "d",
      maxAttempts: 4,
      sleep: noSleep,
    });
    expect(result.status).toBe("failed");
    expect(getStatus).toHaveBeenCalledTimes(3);
  });

  it("reports in_progress after exhausting attempts", async () => {
    const getStatus = jest.fn(async (): Promise<ActionRequestStatus> => ({ status: "in_progress" }));
    const result = await resolvePendingActionStatus({
      getActionRequestStatus: getStatus,
      sessionId: "s",
      requestId: "action:1",
      deviceId: "d",
      maxAttempts: 2,
      sleep: noSleep,
    });
    expect(result.status).toBe("in_progress");
    expect(getStatus).toHaveBeenCalledTimes(3);
  });

  it("stops immediately on a backend-reported unknown but retries transport errors", async () => {
    const unknown = jest.fn(async (): Promise<ActionRequestStatus> => ({ status: "unknown" }));
    const first = await resolvePendingActionStatus({
      getActionRequestStatus: unknown,
      sessionId: "s",
      requestId: "action:1",
      deviceId: "d",
      maxAttempts: 3,
      sleep: noSleep,
    });
    expect(first.status).toBe("unknown");
    expect(unknown).toHaveBeenCalledTimes(1);

    const flaky = jest
      .fn<Promise<ActionRequestStatus>, [string, string, string]>()
      .mockRejectedValueOnce(new Error("Network request failed"))
      .mockResolvedValueOnce({ status: "completed", turn });
    const second = await resolvePendingActionStatus({
      getActionRequestStatus: flaky,
      sessionId: "s",
      requestId: "action:1",
      deviceId: "d",
      maxAttempts: 3,
      sleep: noSleep,
    });
    expect(second.status).toBe("completed");
    expect(flaky).toHaveBeenCalledTimes(2);
  });
});
