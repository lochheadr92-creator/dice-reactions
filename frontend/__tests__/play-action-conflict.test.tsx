import React from "react";
import { Alert } from "react-native";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import PlayScreen from "../app/play/[id]";
import { ApiError } from "../src/api-error";
import type { Turn } from "../src/api";
import { ACTION_CONFLICT_EXHAUSTION_MESSAGE } from "../src/errors";

const mockReplace = jest.fn();
const mockGetSession = jest.fn();
const mockSendAction = jest.fn();
const mockGetDeviceId = jest.fn();
const mockGetSettings = jest.fn();
const mockSyncAfterActionConflict = jest.fn();
let mockSessionId = "sess-1";
let runFocusEffect: (() => void) | null = null;

jest.mock("expo-router", () => {
  const React = require("react");
  return {
    useRouter: () => ({ replace: mockReplace }),
    useLocalSearchParams: () => ({ id: mockSessionId }),
    useFocusEffect: (cb: () => void | (() => void)) => {
      React.useEffect(() => {
        runFocusEffect = () => {
          cb();
        };
        const cleanup = cb();
        return typeof cleanup === "function" ? cleanup : undefined;
      }, []);
    },
  };
});

jest.mock("../src/api", () => ({
  ApiError: require("../src/api-error").ApiError,
  getSession: (...args: unknown[]) => mockGetSession(...args),
  sendAction: (...args: unknown[]) => mockSendAction(...args),
  deleteSession: jest.fn(),
  exportSession: jest.fn(),
  resetSession: jest.fn(),
  setSessionMode: jest.fn(),
}));

jest.mock("../src/action-conflict-sync", () => ({
  syncAfterActionConflict: (...args: unknown[]) => mockSyncAfterActionConflict(...args),
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

const baseSession = {
  id: "sess-1",
  genre: "horror",
  role: "scout",
  tone: "grim",
  difficulty: "standard",
  debug_mode: false,
  title: "Test Chronicle",
  turn_count: 1,
  last_narrative_snippet: "quiet",
  last_state: { Health: "stable" },
  mode: "advanced",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

async function renderPlay() {
  render(<PlayScreen />);
  await waitFor(() => {
    expect(screen.getByTestId("play-screen")).toBeTruthy();
  });
}

describe("PlayScreen action conflict recovery", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useRealTimers();
    mockSessionId = "sess-1";
    runFocusEffect = null;
    jest.spyOn(Alert, "alert").mockImplementation(() => {});
    mockGetDeviceId.mockResolvedValue("device-1");
    mockGetSettings.mockResolvedValue({ developerUnlocked: false, fontScale: 1 });
    mockGetSession.mockResolvedValue({
      session: baseSession,
      turns: [baseTurn()],
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
    mockSendAction.mockReset();
    mockGetSession.mockReset();
    mockSyncAfterActionConflict.mockReset();
  });

  it("appends one turn and clears custom input on success", async () => {
    mockSendAction.mockResolvedValueOnce({
      turn: baseTurn({
        id: "turn-2",
        turn_number: 2,
        player_action: "wait",
        narrative: "You wait.",
        paragraphs: ["You wait."],
        choices: [],
      }),
    });

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "wait");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    expect(screen.getByTestId("custom-action-input").props.value).toBe("");
    expect(mockSendAction).toHaveBeenCalledTimes(1);
  });

  it("on 409 preserves input, does not resubmit, and syncs read-only", async () => {
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"An action is already in progress for this chronicle"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockResolvedValueOnce({
      session: { ...baseSession, turn_count: 2 },
      turns: [
        baseTurn(),
        baseTurn({
          id: "turn-2",
          turn_number: 2,
          player_action: "other tab",
          narrative: "From another tab.",
          paragraphs: ["From another tab."],
          choices: [{ label: "A", text: "Continue" }],
        }),
      ],
      foundNewerTurn: true,
    });

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "my preserved action");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByText("From another tab.")).toBeTruthy();
    });

    expect(mockSendAction).toHaveBeenCalledTimes(1);
    expect(mockSyncAfterActionConflict).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("custom-action-input").props.value).toBe("my preserved action");
    expect(Alert.alert).not.toHaveBeenCalled();
  });

  it("disables controls while conflict sync runs and restores afterward", async () => {
    let resolveSync!: (value: unknown) => void;
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSync = resolve;
      })
    );

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "held");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("syncing-indicator")).toBeTruthy();
    });
    expect(screen.getByTestId("send-action-btn").props.accessibilityState?.disabled).toBe(true);

    await act(async () => {
      resolveSync({
        session: baseSession,
        turns: [baseTurn()],
        foundNewerTurn: false,
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.queryByTestId("syncing-indicator")).toBeNull();
    });
    expect(screen.getByTestId("send-action-btn").props.accessibilityState?.disabled).toBe(false);
    expect(screen.getByTestId("custom-action-input").props.value).toBe("held");
  });

  it("does not start conflict sync for non-409 failures", async () => {
    mockSendAction.mockRejectedValueOnce(new ApiError(502, "{}", "Story engine unavailable"));

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "still here");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalled();
    });
    expect(mockSyncAfterActionConflict).not.toHaveBeenCalled();
    expect(screen.getByTestId("custom-action-input").props.value).toBe("still here");
  });

  it("choice conflict does not auto-retry sendAction", async () => {
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockResolvedValueOnce({
      session: baseSession,
      turns: [baseTurn()],
      foundNewerTurn: false,
    });

    await renderPlay();
    fireEvent.press(screen.getByTestId("choice-A"));

    await waitFor(() => {
      expect(mockSyncAfterActionConflict).toHaveBeenCalledTimes(1);
    });
    expect(mockSendAction).toHaveBeenCalledTimes(1);
    expect(mockSendAction).toHaveBeenCalledWith(
      expect.objectContaining({ action_text: "Look around" })
    );
  });

  it("409 does not append a turn from the failed request", async () => {
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockResolvedValueOnce({
      session: baseSession,
      turns: [baseTurn()],
      foundNewerTurn: false,
    });

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "ghost turn");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(mockSyncAfterActionConflict).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByText("ghost turn")).toBeNull();
    expect(screen.getAllByText("The hall is quiet.")).toHaveLength(1);
  });

  it("shows guidance after bounded sync finds no newer turn", async () => {
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockResolvedValueOnce({
      session: baseSession,
      turns: [baseTurn()],
      foundNewerTurn: false,
    });

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "retry later");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("action-notice")).toBeTruthy();
    });
    const notice = screen.getByTestId("action-notice").props.children;
    const text = typeof notice === "string" ? notice : notice?.props?.children ?? "";
    expect(String(text)).toBe(ACTION_CONFLICT_EXHAUSTION_MESSAGE);
    expect(String(text).toLowerCase()).toContain("kept");
    expect(String(text).toLowerCase()).not.toContain("automatically");
    expect(String(text).toLowerCase()).not.toContain("lease");
    expect(String(text).toLowerCase()).not.toContain("token");
    expect(screen.getByTestId("custom-action-input").props.value).toBe("retry later");
  });

  it("clears action notice after a newer synced turn is merged", async () => {
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockResolvedValueOnce({
      session: { ...baseSession, turn_count: 2 },
      turns: [
        baseTurn(),
        baseTurn({
          id: "turn-2",
          turn_number: 2,
          narrative: "Fresh from server.",
          paragraphs: ["Fresh from server."],
        }),
      ],
      foundNewerTurn: true,
    });

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "held");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByText("Fresh from server.")).toBeTruthy();
    });
    expect(screen.queryByTestId("action-notice")).toBeNull();
  });

  it("does not leave stale submitting or syncing indicators", async () => {
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockResolvedValueOnce({
      session: baseSession,
      turns: [baseTurn()],
      foundNewerTurn: false,
    });

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "done");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.queryByTestId("syncing-indicator")).toBeNull();
      expect(screen.queryByTestId("thinking-indicator")).toBeNull();
    });
    expect(screen.getByTestId("send-action-btn").props.accessibilityState?.disabled).toBe(false);
  });

  it("merges a refreshed newer turn once without duplication", async () => {
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockResolvedValueOnce({
      session: { ...baseSession, turn_count: 2 },
      turns: [
        baseTurn(),
        baseTurn({
          id: "turn-2",
          turn_number: 2,
          narrative: "Synced once.",
          paragraphs: ["Synced once."],
        }),
      ],
      foundNewerTurn: true,
    });

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "blocked");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByText("Synced once.")).toBeTruthy();
    });
    expect(screen.getAllByText("Synced once.")).toHaveLength(1);
  });

  it("cancels the prior conflict-sync signal when a newer submit starts", async () => {
    let capturedSignal: { cancelled: boolean } | undefined;
    mockSendAction
      .mockRejectedValueOnce(
        new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
      )
      .mockResolvedValueOnce({
        turn: baseTurn({
          id: "turn-2",
          turn_number: 2,
          player_action: "second",
          narrative: "Second wins.",
          paragraphs: ["Second wins."],
        }),
      });
    mockSyncAfterActionConflict.mockImplementation(async (deps: { signal?: { cancelled: boolean } }) => {
      capturedSignal = deps.signal;
      return {
        session: baseSession,
        turns: [baseTurn()],
        foundNewerTurn: false,
      };
    });

    await renderPlay();
    fireEvent.changeText(screen.getByTestId("custom-action-input"), "first");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(mockSyncAfterActionConflict).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId("syncing-indicator")).toBeNull();
    });
    expect(capturedSignal?.cancelled).toBe(false);

    fireEvent.changeText(screen.getByTestId("custom-action-input"), "second");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByText("Second wins.")).toBeTruthy();
    });
    expect(capturedSignal?.cancelled).toBe(true);
    expect(mockSendAction).toHaveBeenCalledTimes(2);
  });

  it("unmount cancels pending conflict sync updates", async () => {
    let resolveSync!: (value: unknown) => void;
    let capturedSignal: { cancelled: boolean } | undefined;
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockImplementationOnce(
      (deps: { signal?: { cancelled: boolean } }) =>
        new Promise((resolve) => {
          capturedSignal = deps.signal;
          resolveSync = resolve;
        })
    );

    const { unmount } = render(<PlayScreen />);
    await waitFor(() => {
      expect(screen.getByTestId("play-screen")).toBeTruthy();
    });

    fireEvent.changeText(screen.getByTestId("custom-action-input"), "held");
    await act(async () => {
      fireEvent.press(screen.getByTestId("send-action-btn"));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId("syncing-indicator")).toBeTruthy();
    });

    unmount();

    expect(capturedSignal?.cancelled).toBe(true);

    await act(async () => {
      resolveSync({
        session: baseSession,
        turns: [
          baseTurn({
            id: "turn-late",
            turn_number: 2,
            narrative: "After unmount.",
            paragraphs: ["After unmount."],
          }),
        ],
        foundNewerTurn: true,
      });
      await Promise.resolve();
      await Promise.resolve();
    });
  });

  it("does not apply conflict sync results after navigating to another session", async () => {
    let resolveSync!: (value: unknown) => void;
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSync = resolve;
      })
    );

    const { unmount: unmountSessionA } = render(<PlayScreen key="sess-1" />);
    await waitFor(() => {
      expect(screen.getByTestId("play-screen")).toBeTruthy();
    });

    fireEvent.changeText(screen.getByTestId("custom-action-input"), "held");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("syncing-indicator")).toBeTruthy();
    });

    unmountSessionA();
    mockSessionId = "sess-2";
    mockGetSession.mockResolvedValue({
      session: { ...baseSession, id: "sess-2", title: "Chronicle B" },
      turns: [baseTurn({ session_id: "sess-2", narrative: "Session B opening." })],
    });
    render(<PlayScreen key="sess-2" />);

    await waitFor(() => {
      expect(screen.getByTestId("play-screen")).toBeTruthy();
      expect(mockGetSession).toHaveBeenCalledWith("sess-2", "device-1");
    });

    await act(async () => {
      resolveSync({
        session: { ...baseSession, title: "Stale Session A" },
        turns: [
          baseTurn({
            id: "turn-stale-a",
            turn_number: 2,
            narrative: "Stale Session A turn.",
            paragraphs: ["Stale Session A turn."],
          }),
        ],
        foundNewerTurn: true,
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.queryByText("Stale Session A turn.")).toBeNull();
    expect(screen.queryByText("Stale Session A")).toBeNull();
  });

  it("does not let a stale focus refresh overwrite a successful action", async () => {
    let resolveStaleRefresh!: (value: unknown) => void;
    const staleRefresh = new Promise((resolve) => {
      resolveStaleRefresh = resolve;
    });

    await renderPlay();

    mockGetSession.mockReturnValueOnce(staleRefresh);
    await act(async () => {
      runFocusEffect?.();
      await Promise.resolve();
    });

    mockSendAction.mockResolvedValueOnce({
      turn: baseTurn({
        id: "turn-2",
        turn_number: 2,
        player_action: "advance",
        narrative: "You advance.",
        paragraphs: ["You advance."],
      }),
    });

    fireEvent.changeText(screen.getByTestId("custom-action-input"), "advance");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByText("You advance.")).toBeTruthy();
    });

    await act(async () => {
      resolveStaleRefresh({
        session: { ...baseSession, title: "Stale title", turn_count: 1 },
        turns: [baseTurn()],
      });
      await Promise.resolve();
    });

    expect(screen.getByText("You advance.")).toBeTruthy();
    expect(screen.queryByText("Stale title")).toBeNull();
  });

  it("does not leave syncingConflict stuck after cancellation", async () => {
    let resolveSync!: (value: unknown) => void;
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSync = resolve;
      })
    );

    const { unmount: unmountSessionA } = render(<PlayScreen key="sess-1" />);
    await waitFor(() => {
      expect(screen.getByTestId("play-screen")).toBeTruthy();
    });

    fireEvent.changeText(screen.getByTestId("custom-action-input"), "probe");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("syncing-indicator")).toBeTruthy();
    });

    unmountSessionA();
    mockSessionId = "sess-2";
    mockGetSession.mockResolvedValue({
      session: { ...baseSession, id: "sess-2", title: "Next chronicle" },
      turns: [baseTurn({ session_id: "sess-2" })],
    });
    render(<PlayScreen key="sess-2" />);

    await waitFor(() => {
      expect(screen.queryByTestId("syncing-indicator")).toBeNull();
    });

    await act(async () => {
      resolveSync({
        session: baseSession,
        turns: [baseTurn()],
        foundNewerTurn: false,
      });
      await Promise.resolve();
    });

    expect(screen.queryByTestId("syncing-indicator")).toBeNull();
  });

  it("serialises repeated 409 conflict syncs without overlapping loops", async () => {
    let resolveFirst!: (value: unknown) => void;
    mockSendAction
      .mockRejectedValueOnce(
        new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
      )
      .mockRejectedValueOnce(
        new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
      );
    mockSyncAfterActionConflict
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve;
        })
      )
      .mockResolvedValueOnce({
        session: baseSession,
        turns: [baseTurn()],
        foundNewerTurn: false,
      });

    await renderPlay();

    fireEvent.changeText(screen.getByTestId("custom-action-input"), "first");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("syncing-indicator")).toBeTruthy();
    });

    await act(async () => {
      resolveFirst({
        session: baseSession,
        turns: [baseTurn()],
        foundNewerTurn: false,
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.queryByTestId("syncing-indicator")).toBeNull();
    });

    fireEvent.changeText(screen.getByTestId("custom-action-input"), "second");
    fireEvent.press(screen.getByTestId("send-action-btn"));

    await waitFor(() => {
      expect(mockSyncAfterActionConflict).toHaveBeenCalledTimes(2);
    });
    expect(mockSendAction).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId("syncing-indicator")).toBeNull();
  });
});