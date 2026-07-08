import React from "react";
import { render, screen, waitFor } from "@testing-library/react-native";
import PlayScreen from "../app/play/[id]";
import type { Turn } from "../src/api";

const mockGetSession = jest.fn();
const mockGetDeviceId = jest.fn();
const mockGetSettings = jest.fn();

jest.mock("expo-router", () => {
  const React = require("react");
  return {
    useRouter: () => ({ replace: jest.fn() }),
    useLocalSearchParams: () => ({ id: "sess-1" }),
    useFocusEffect: (cb: () => void | (() => void)) => {
      React.useEffect(() => {
        const cleanup = cb();
        return typeof cleanup === "function" ? cleanup : undefined;
      }, []);
    },
  };
});

jest.mock("../src/api", () => ({
  ApiError: require("../src/api-error").ApiError,
  getSession: (...args: unknown[]) => mockGetSession(...args),
  sendAction: jest.fn(),
  deleteSession: jest.fn(),
  exportSession: jest.fn(),
  resetSession: jest.fn(),
  setSessionMode: jest.fn(),
  getSessionHistory: jest.fn().mockResolvedValue({ history: [] }),
}));

jest.mock("../src/action-conflict-sync", () => ({
  syncAfterActionConflict: jest.fn(),
}));

jest.mock("../src/storage", () => ({
  getDeviceId: (...args: unknown[]) => mockGetDeviceId(...args),
  getSettings: (...args: unknown[]) => mockGetSettings(...args),
}));

function baseTurn(overrides: Partial<Turn> = {}): Turn {
  return {
    id: "turn-1",
    session_id: "sess-1",
    turn_number: 1,
    player_action: null,
    narrative: "The hall is quiet.",
    paragraphs: ["The hall is quiet."],
    choices: [{ label: "A", text: "Look around" }],
    state: { Health: "stable", Pressure: "calm" },
    ledger: {},
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("PlayScreen debug panel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetDeviceId.mockResolvedValue("device-1");
    mockGetSettings.mockResolvedValue({ developerUnlocked: true, fontScale: 1 });
    mockGetSession.mockResolvedValue({
      session: {
        id: "sess-1",
        genre: "horror",
        role: "scout",
        tone: "grim",
        difficulty: "standard",
        debug_mode: true,
        title: "Test Chronicle",
        turn_count: 1,
        last_narrative_snippet: "quiet",
        last_state: { Health: "stable" },
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      turns: [
        baseTurn({
          debug: { model_used: "test-model", latency_ms: "1200" },
        }),
      ],
    });
  });

  async function renderLoadedPlay() {
    render(<PlayScreen />);
    await waitFor(
      () => {
        expect(screen.getByTestId("play-screen")).toBeTruthy();
      },
      { timeout: 5000 },
    );
  }

  it("renders per-turn debug block when dev unlocked and session debug_mode is on", async () => {
    await renderLoadedPlay();
    expect(screen.getByTestId("debug-block-1")).toBeTruthy();
    expect(screen.getByText("MODEL_USED")).toBeTruthy();
    expect(screen.getByText("test-model")).toBeTruthy();
  });

  it("hides debug block when developer unlock is off", async () => {
    mockGetSettings.mockResolvedValue({ developerUnlocked: false, fontScale: 1 });
    await renderLoadedPlay();
    expect(screen.queryByTestId("debug-block-1")).toBeNull();
  });
});