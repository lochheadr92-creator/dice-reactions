import React from "react";
import { Alert } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import PlayScreen from "../app/play/[id]";
import { ApiError } from "../src/api-error";
import type { Turn } from "../src/api";
import {
  ACTION_MISMATCH_MESSAGE,
  ACTION_NOT_SENT_MESSAGE,
  ACTION_RATE_LIMIT_TITLE,
  ACTION_RECOVERED_MESSAGE,
} from "../src/errors";
import { buildPendingAction, savePendingAction } from "../src/pending-action";

const mockReplace = jest.fn();
const mockGetSession = jest.fn();
const mockSendAction = jest.fn();
const mockGetActionRequestStatus = jest.fn();
const mockGetDeviceId = jest.fn();
const mockGetSettings = jest.fn();
const mockSyncAfterActionConflict = jest.fn();
let mockSessionId = "sess-1";

jest.mock("expo-router", () => {
  const React = require("react");
  return {
    useRouter: () => ({ replace: mockReplace }),
    useLocalSearchParams: () => ({ id: mockSessionId }),
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
  sendAction: (...args: unknown[]) => mockSendAction(...args),
  getActionRequestStatus: (...args: unknown[]) => mockGetActionRequestStatus(...args),
  deleteSession: jest.fn(),
  exportSession: jest.fn(),
  resetSession: jest.fn(),
  setSessionMode: jest.fn(),
}));

jest.mock("../src/action-conflict-sync", () => ({
  syncAfterActionConflict: (...args: unknown[]) => mockSyncAfterActionConflict(...args),
}));

jest.mock("../src/action-status-sync", () => {
  const actual = jest.requireActual("../src/action-status-sync");
  return {
    ...actual,
    // No real delays in tests; polling logic itself is covered in pending-action.test.ts.
    resolvePendingActionStatus: (deps: Record<string, unknown>) =>
      actual.resolvePendingActionStatus({ ...deps, sleep: async () => {}, maxAttempts: 1 }),
  };
});

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

const secondTurn = baseTurn({
  id: "turn-2",
  turn_number: 2,
  player_action: "wait",
  narrative: "You wait.",
  paragraphs: ["You wait."],
  choices: [],
});

async function renderPlay() {
  render(<PlayScreen />);
  await waitFor(() => {
    expect(screen.getByTestId("play-screen")).toBeTruthy();
  });
}

function sentRequestIds(): string[] {
  return mockSendAction.mock.calls.map((call) => call[0].action_request_id as string);
}

async function typeAndSend(text: string) {
  fireEvent.changeText(screen.getByTestId("custom-action-input"), text);
  await waitFor(() => {
    expect(screen.getByTestId("send-action-btn").props.accessibilityState?.disabled).toBe(false);
  });
  fireEvent.press(screen.getByTestId("send-action-btn"));
}

describe("PlayScreen action idempotency", () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    jest.useRealTimers();
    await AsyncStorage.clear();
    mockSessionId = "sess-1";
    jest.spyOn(Alert, "alert").mockImplementation(() => {});
    mockGetDeviceId.mockResolvedValue("device-1");
    mockGetSettings.mockResolvedValue({ developerUnlocked: false, fontScale: 1 });
    mockGetSession.mockResolvedValue({ session: baseSession, turns: [baseTurn()] });
    mockGetActionRequestStatus.mockResolvedValue({ status: "unknown" });
  });

  afterEach(() => {
    jest.restoreAllMocks();
    mockSendAction.mockReset();
    mockGetSession.mockReset();
    mockGetActionRequestStatus.mockReset();
    mockSyncAfterActionConflict.mockReset();
  });

  it("sends a request id, keeps it across a retryable failure, and renews it for a new action", async () => {
    mockSendAction
      .mockRejectedValueOnce(new ApiError(502, "{}", "Story engine unavailable"))
      .mockResolvedValueOnce({ turn: secondTurn })
      .mockResolvedValueOnce({
        turn: baseTurn({ id: "turn-3", turn_number: 3, narrative: "You listen.", paragraphs: ["You listen."], choices: [] }),
      });

    await renderPlay();
    await typeAndSend("wait");
    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalled();
    });
    // Text preserved after the 502; same id reused on retry of the same text.
    expect(screen.getByTestId("custom-action-input").props.value).toBe("wait");
    fireEvent.press(screen.getByTestId("send-action-btn"));
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    expect(screen.getByTestId("custom-action-input").props.value).toBe("");

    await typeAndSend("listen");
    await waitFor(() => {
      expect(screen.getByText("You listen.")).toBeTruthy();
    });

    const ids = sentRequestIds();
    expect(ids).toHaveLength(3);
    expect(ids[0]).toMatch(/^action:/);
    expect(ids[1]).toBe(ids[0]);
    expect(ids[2]).not.toBe(ids[0]);
    expect(mockSendAction.mock.calls[0][0]).toMatchObject({
      session_id: "sess-1",
      device_id: "device-1",
      action_text: "wait",
      debug_mode: false,
    });
  });

  it("preserves text and request id on a rate limit", async () => {
    mockSendAction
      .mockRejectedValueOnce(new ApiError(429, '{"detail":"Too many requests"}', "Too many requests"))
      .mockResolvedValueOnce({ turn: secondTurn });

    await renderPlay();
    await typeAndSend("wait");
    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith(ACTION_RATE_LIMIT_TITLE, expect.any(String));
    });
    expect(screen.getByTestId("custom-action-input").props.value).toBe("wait");
    expect(screen.getByTestId("send-action-btn").props.accessibilityState?.disabled).toBe(false);

    fireEvent.press(screen.getByTestId("send-action-btn"));
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    const ids = sentRequestIds();
    expect(ids[1]).toBe(ids[0]);
  });

  it("recovers a lost response by querying status instead of resending", async () => {
    mockSendAction.mockRejectedValueOnce(new TypeError("Network request failed"));
    mockGetActionRequestStatus.mockResolvedValue({ status: "completed", turn: secondTurn });

    await renderPlay();
    await typeAndSend("wait");
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    expect(mockSendAction).toHaveBeenCalledTimes(1);
    expect(mockGetActionRequestStatus).toHaveBeenCalledWith("sess-1", sentRequestIds()[0], "device-1");
    expect(screen.getByTestId("custom-action-input").props.value).toBe("");
    expect(screen.getAllByText("You wait.")).toHaveLength(1);
    expect(Alert.alert).not.toHaveBeenCalled();
  });

  it("keeps text and id when the lost action is reported as not received", async () => {
    mockSendAction
      .mockRejectedValueOnce(new TypeError("Network request failed"))
      .mockResolvedValueOnce({ turn: secondTurn });
    mockGetActionRequestStatus.mockResolvedValue({ status: "failed", error_kind: "interrupted" });

    await renderPlay();
    await typeAndSend("wait");
    await waitFor(() => {
      expect(screen.getByText(ACTION_NOT_SENT_MESSAGE)).toBeTruthy();
    });
    expect(screen.getByTestId("custom-action-input").props.value).toBe("wait");
    await waitFor(() => {
      expect(screen.getByTestId("send-action-btn").props.accessibilityState?.disabled).toBe(false);
    });
    fireEvent.press(screen.getByTestId("send-action-btn"));
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    const ids = sentRequestIds();
    expect(ids).toHaveLength(2);
    expect(ids[1]).toBe(ids[0]);
  });

  it("restores a pending action after reload and merges its completed turn", async () => {
    await savePendingAction("sess-1", buildPendingAction("action:pending-1", "wait", false));
    mockGetActionRequestStatus.mockResolvedValue({ status: "completed", turn: secondTurn });

    await renderPlay();
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    expect(mockGetActionRequestStatus).toHaveBeenCalledWith("sess-1", "action:pending-1", "device-1");
    expect(mockSendAction).not.toHaveBeenCalled();
    expect(screen.getByText(ACTION_RECOVERED_MESSAGE)).toBeTruthy();
    expect(screen.getByTestId("custom-action-input").props.value).toBe("");
    expect(await AsyncStorage.getItem("dice_pending_action:sess-1")).toBeNull();
  });

  it("restores pending text after reload when the action never went through", async () => {
    await savePendingAction("sess-1", buildPendingAction("action:pending-2", "open the gate", false));
    mockGetActionRequestStatus.mockResolvedValue({ status: "failed", error_kind: "interrupted" });
    mockSendAction.mockResolvedValueOnce({ turn: secondTurn });

    await renderPlay();
    await waitFor(() => {
      expect(screen.getByTestId("custom-action-input").props.value).toBe("open the gate");
    });
    await waitFor(() => {
      expect(screen.getByText(ACTION_NOT_SENT_MESSAGE)).toBeTruthy();
    });
    expect(mockSendAction).not.toHaveBeenCalled();
    fireEvent.press(screen.getByTestId("send-action-btn"));
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    expect(sentRequestIds()[0]).toBe("action:pending-2");
  });

  it("drops the id but keeps the text when the backend reports a contents mismatch", async () => {
    mockSendAction
      .mockRejectedValueOnce(
        new ApiError(
          409,
          '{"detail":"action_request_id was already used for a different action"}',
          "action_request_id was already used for a different action"
        )
      )
      .mockResolvedValueOnce({ turn: secondTurn });

    await renderPlay();
    await typeAndSend("wait");
    await waitFor(() => {
      expect(screen.getByText(ACTION_MISMATCH_MESSAGE)).toBeTruthy();
    });
    expect(mockSyncAfterActionConflict).not.toHaveBeenCalled();
    expect(screen.getByTestId("custom-action-input").props.value).toBe("wait");
    fireEvent.press(screen.getByTestId("send-action-btn"));
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    const ids = sentRequestIds();
    expect(ids[1]).not.toBe(ids[0]);
  });

  it("after a lease conflict, an own duplicate that completed is adopted without resending", async () => {
    mockSendAction.mockRejectedValueOnce(
      new ApiError(409, '{"detail":"conflict"}', "An action is already in progress for this chronicle")
    );
    mockSyncAfterActionConflict.mockResolvedValueOnce({
      session: baseSession,
      turns: [baseTurn()],
      foundNewerTurn: false,
    });
    mockGetActionRequestStatus.mockResolvedValue({ status: "completed", turn: secondTurn });

    await renderPlay();
    await typeAndSend("wait");
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    expect(mockSendAction).toHaveBeenCalledTimes(1);
    expect(mockSyncAfterActionConflict).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("custom-action-input").props.value).toBe("");
    expect(screen.queryByTestId("action-notice")).toBeNull();
  });

  it("blocks a second press while an action is in flight", async () => {
    let resolveSend!: (value: unknown) => void;
    mockSendAction.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSend = resolve;
      })
    );
    await renderPlay();
    await typeAndSend("wait");
    await waitFor(() => {
      expect(screen.getByTestId("send-action-btn").props.accessibilityState?.disabled).toBe(true);
    });
    fireEvent.press(screen.getByTestId("send-action-btn"));
    fireEvent.press(screen.getByTestId("choice-A"));
    await act(async () => {
      resolveSend({ turn: secondTurn });
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getByText("You wait.")).toBeTruthy();
    });
    expect(mockSendAction).toHaveBeenCalledTimes(1);
  });
});
