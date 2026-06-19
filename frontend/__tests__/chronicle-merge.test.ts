import type { Turn } from "../src/api";
import { mergeChronicleTurns, maxTurnNumber } from "../src/chronicle-merge";
import { syncAfterActionConflict } from "../src/action-conflict-sync";

function turn(id: string, turnNumber: number, narrative = "text"): Turn {
  return {
    id,
    session_id: "sess-1",
    turn_number: turnNumber,
    player_action: null,
    narrative,
    paragraphs: [narrative],
    choices: [],
    state: {},
    ledger: {},
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("mergeChronicleTurns", () => {
  it("deduplicates by turn id and sorts by turn_number", () => {
    const merged = mergeChronicleTurns(
      [turn("a", 1), turn("b", 2, "local")],
      [turn("b", 2, "server"), turn("c", 3)]
    );
    expect(merged.map((t) => t.id)).toEqual(["a", "b", "c"]);
    expect(merged.find((t) => t.id === "b")?.narrative).toBe("server");
  });

  it("does not duplicate after repeated refresh", () => {
    const first = mergeChronicleTurns([turn("a", 1)], [turn("a", 1), turn("b", 2)]);
    const second = mergeChronicleTurns(first, [turn("a", 1), turn("b", 2)]);
    expect(second).toHaveLength(2);
  });

  it("does not mutate input arrays", () => {
    const current = [turn("a", 1)];
    const incoming = [turn("b", 2, "server")];
    const currentSnapshot = [...current];
    const incomingSnapshot = [...incoming];
    mergeChronicleTurns(current, incoming);
    expect(current).toEqual(currentSnapshot);
    expect(incoming).toEqual(incomingSnapshot);
  });

  it("keeps both turns when different ids share the same turn_number", () => {
    const merged = mergeChronicleTurns(
      [turn("z-legacy", 2, "legacy")],
      [turn("a-server", 2, "server")]
    );
    expect(merged).toHaveLength(2);
    expect(merged.map((t) => t.id)).toEqual(["a-server", "z-legacy"]);
    expect(merged.find((t) => t.id === "a-server")?.narrative).toBe("server");
  });
});

describe("syncAfterActionConflict", () => {
  const session = {
    id: "sess-1",
    genre: "fantasy",
    role: null,
    tone: null,
    difficulty: "standard",
    debug_mode: false,
    title: "Test",
    turn_count: 1,
    last_narrative_snippet: "",
    last_state: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };

  it("polls read-only until a newer turn appears", async () => {
    const sleeps: number[] = [];
    let calls = 0;
    const getSession = jest.fn(async () => {
      calls += 1;
      if (calls < 3) {
        return { session: { ...session, turn_count: 1 }, turns: [turn("t1", 1)] };
      }
      return { session: { ...session, turn_count: 2 }, turns: [turn("t1", 1), turn("t2", 2)] };
    });

    const result = await syncAfterActionConflict({
      getSession,
      sessionId: "sess-1",
      deviceId: "dev-1",
      baselineMaxTurnNumber: maxTurnNumber([turn("t1", 1)]),
      maxAttempts: 3,
      delayMs: 100,
      sleep: async (ms) => {
        sleeps.push(ms);
      },
    });

    expect(result.foundNewerTurn).toBe(true);
    expect(getSession).toHaveBeenCalledTimes(3);
    expect(sleeps).toEqual([100, 100]);
  });

  it("stops when signal is cancelled", async () => {
    const signal = { cancelled: false };
    const getSession = jest.fn(async () => ({
      session,
      turns: [turn("t1", 1)],
    }));

    const promise = syncAfterActionConflict({
      getSession,
      sessionId: "sess-1",
      deviceId: "dev-1",
      baselineMaxTurnNumber: 1,
      maxAttempts: 3,
      delayMs: 1000,
      sleep: async () => {
        signal.cancelled = true;
      },
      signal,
    });

    const result = await promise;
    expect(result.foundNewerTurn).toBe(false);
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  afterEach(() => {
    jest.useRealTimers();
  });
});