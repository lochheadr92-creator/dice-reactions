import React from "react";
import { Alert } from "react-native";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import NewStoryScreen from "../app/new-story";

const mockReplace = jest.fn();
const mockBack = jest.fn();
const mockListScenarios = jest.fn();
const mockNewStory = jest.fn();
const mockGetDeviceId = jest.fn();
const mockGetSettings = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({
    replace: mockReplace,
    back: mockBack,
  }),
}));

jest.mock("../src/api", () => ({
  listScenarios: (...args: unknown[]) => mockListScenarios(...args),
  newStory: (...args: unknown[]) => mockNewStory(...args),
}));

jest.mock("../src/storage", () => ({
  getDeviceId: (...args: unknown[]) => mockGetDeviceId(...args),
  getSettings: (...args: unknown[]) => mockGetSettings(...args),
}));

jest.mock("../src/errors", () => ({
  friendlyError: () => ({
    title: "Story creation failed",
    message: "We couldn't start that chronicle. Please try again.",
  }),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function renderScreen(fontScale = 1) {
  mockGetSettings.mockResolvedValue({ debugDefault: false, fontScale, developerUnlocked: false });
  render(<NewStoryScreen />);
  await waitFor(() => {
    expect(screen.getByTestId("quick-start-step-1")).toBeTruthy();
  });
}

async function completeQuickStart() {
  fireEvent.press(screen.getByTestId("quick-start-option-world-fantasy"));
  fireEvent.press(screen.getByTestId("quick-start-next-button"));
  fireEvent.press(screen.getByTestId("quick-start-option-character-survivor"));
  fireEvent.press(screen.getByTestId("quick-start-next-button"));
  fireEvent.press(screen.getByTestId("quick-start-option-tone-hopeful"));
  fireEvent.press(screen.getByTestId("quick-start-next-button"));
  fireEvent.press(screen.getByTestId("quick-start-option-want-justice"));
  fireEvent.press(screen.getByTestId("quick-start-next-button"));
  fireEvent.press(screen.getByTestId("quick-start-option-fear-failure"));
  fireEvent.press(screen.getByTestId("quick-start-next-button"));
  fireEvent.press(screen.getByTestId("quick-start-option-whoMatters-friend"));
  fireEvent.press(screen.getByTestId("quick-start-next-button"));
  await screen.findByTestId("quick-start-review-step");
}

describe("NewStoryScreen Quick Start", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockListScenarios.mockResolvedValue({
      scenarios: [
        {
          id: "modern-mystery",
          title: "The Last Witness",
          pitch: "A witness disappears before dawn.",
          genre: "detective",
          role: "investigator",
          tone: "grim",
          difficulty: "standard",
          mode: "advanced",
          starting_location: "A rain-slick apartment block",
          starting_pressure: "Someone is already cleaning the scene",
          key_npcs: [{ name: "Mara", role: "sister", stance: "wary" }],
          starting_inventory: "phone; notebook",
          hidden_threat: "The wrong suspect is bait",
        },
      ],
    });
    mockGetDeviceId.mockResolvedValue("device-123");
    mockNewStory.mockResolvedValue({
      session_id: "session-123",
      turn: { id: "turn-1" },
      session: { id: "session-123" },
    });
    jest.spyOn(Alert, "alert").mockImplementation(jest.fn());
  });

  it("shows Quick Start by default and renders step 1", async () => {
    await renderScreen();

    expect(screen.getByTestId("creation-flow-quick")).toBeTruthy();
    expect(screen.getByTestId("quick-start-step-1")).toBeTruthy();
    expect(screen.getByTestId("quick-start-step-question").props.children).toBe(
      "Where does this story begin?"
    );
  });

  it("allows one selection and advances progress", async () => {
    await renderScreen();

    fireEvent.press(screen.getByTestId("quick-start-option-world-fantasy"));
    expect(screen.getByTestId("quick-start-option-selected-world-fantasy")).toBeTruthy();

    fireEvent.press(screen.getByTestId("quick-start-next-button"));
    expect(screen.getByTestId("quick-start-progress-text").props.children.join("")).toContain("2 of 6");
    expect(screen.getByTestId("quick-start-step-2")).toBeTruthy();
  });

  it("preserves previous selections when going back", async () => {
    await renderScreen();

    fireEvent.press(screen.getByTestId("quick-start-option-world-fantasy"));
    fireEvent.press(screen.getByTestId("quick-start-next-button"));
    fireEvent.press(screen.getByTestId("quick-start-back-button"));

    expect(screen.getByTestId("quick-start-step-1")).toBeTruthy();
    expect(screen.getByTestId("quick-start-option-selected-world-fantasy")).toBeTruthy();
  });

  it("completes all six steps without typing and shows player-facing review labels", async () => {
    await renderScreen();

    await completeQuickStart();

    expect(screen.getByTestId("quick-start-review-value-world").props.children).toBe("Fantasy");
    expect(screen.getByTestId("quick-start-review-value-character").props.children).toBe("Survivor");
    expect(screen.getByTestId("quick-start-review-value-tone").props.children).toBe("Hopeful");
    expect(screen.getByTestId("quick-start-review-value-want").props.children).toBe("Justice");
    expect(screen.getByTestId("quick-start-review-value-fear").props.children).toBe("Failure");
    expect(screen.getByTestId("quick-start-review-value-whoMatters").props.children).toBe("Friend");
    expect(screen.getByTestId("quick-start-review-summary").props.children).toContain("fantasy");
    expect(String(screen.getByTestId("quick-start-review-summary").props.children)).not.toContain("whoMatters");
    expect(String(screen.getByTestId("quick-start-review-summary").props.children)).not.toContain("losing-control");
  });

  it("updates the review after changing a previous choice", async () => {
    await renderScreen();
    await completeQuickStart();

    fireEvent.press(screen.getByTestId("quick-start-change-tone"));
    expect(screen.getByTestId("quick-start-step-3")).toBeTruthy();
    fireEvent.press(screen.getByTestId("quick-start-option-tone-brutal"));
    fireEvent.press(screen.getByTestId("quick-start-next-button"));
    fireEvent.press(screen.getByTestId("quick-start-next-button"));
    fireEvent.press(screen.getByTestId("quick-start-next-button"));
    fireEvent.press(screen.getByTestId("quick-start-next-button"));

    expect(screen.getByTestId("quick-start-review-value-tone").props.children).toBe("Brutal");
    expect(String(screen.getByTestId("quick-start-review-summary").props.children)).toContain("brutal");
  });

  it("submits the correct typed payload, disables while pending, and blocks duplicates", async () => {
    const pending = deferred<any>();
    mockNewStory.mockReturnValueOnce(pending.promise);
    await renderScreen();

    await completeQuickStart();
    fireEvent.press(screen.getByTestId("quick-start-start-button"));
    fireEvent.press(screen.getByTestId("quick-start-start-button"));

    await waitFor(() => {
      expect(mockNewStory).toHaveBeenCalledTimes(1);
      expect(mockNewStory).toHaveBeenCalledWith({
        device_id: "device-123",
        genre: "fantasy",
        role: "a hardened survivor",
        tone: "hopeful",
        difficulty: "standard",
        debug_mode: false,
        mode: "advanced",
        custom_world_setup: {
          want: "justice",
          fear: "failure",
          whoMatters: "friend",
        },
      });
    });
    expect(screen.getByTestId("quick-start-loading-state")).toBeTruthy();

    await act(async () => {
      pending.resolve({
        session_id: "session-quick",
        turn: { id: "turn-quick" },
        session: { id: "session-quick" },
      });
      await pending.promise;
    });

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/play/session-quick");
    });
  });

  it("preserves selections after a recoverable failure and allows retry", async () => {
    mockNewStory
      .mockRejectedValueOnce(new Error("500: backend trace"))
      .mockResolvedValueOnce({ session_id: "session-retry", turn: {}, session: {} });
    await renderScreen();

    await completeQuickStart();
    fireEvent.press(screen.getByTestId("quick-start-start-button"));

    await waitFor(() => {
      expect(screen.getByTestId("new-story-error-banner")).toBeTruthy();
    });
    expect(screen.getByTestId("quick-start-review-value-world").props.children).toBe("Fantasy");
    expect(String(screen.getByTestId("new-story-error-banner").props.children)).not.toContain("backend trace");
    expect(String(screen.getByTestId("new-story-error-banner").props.children)).not.toContain("OpenAI");

    fireEvent.press(screen.getByTestId("quick-start-start-button"));
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/play/session-retry");
    });
    expect(mockNewStory).toHaveBeenCalledTimes(2);
  });

  it("shows no admin controls, no secret fields, and no raw rolling state", async () => {
    await renderScreen();

    expect(screen.queryByText(/ADMIN/i)).toBeNull();
    expect(screen.queryByText(/^Secret$/i)).toBeNull();
    expect(screen.queryByText(/rolling_state/i)).toBeNull();
    expect(screen.queryByText(/ENGINE MODE/i)).toBeNull();
  });

  it("keeps the existing Advanced Builder available where accessed", async () => {
    await renderScreen();

    fireEvent.press(screen.getByTestId("creation-flow-advanced"));
    await waitFor(() => {
      expect(screen.getByTestId("scenario-modern-mystery")).toBeTruthy();
    });

    expect(screen.getByTestId("advanced-builder-panel")).toBeTruthy();
    expect(screen.getByTestId("scenario-modern-mystery")).toBeTruthy();
    expect(screen.getByTestId("role-input")).toBeTruthy();
    expect(screen.getByTestId("mode-advanced")).toBeTruthy();
    expect(screen.getByTestId("begin-story-btn")).toBeTruthy();
  });

  it("still renders and advances at large font scale", async () => {
    await renderScreen(1.25);

    await waitFor(() => {
      expect(screen.getByTestId("quick-start-heading").props.style).toEqual(
        expect.arrayContaining([expect.objectContaining({ fontSize: 38 })])
      );
    });

    fireEvent.press(screen.getByTestId("quick-start-option-world-fantasy"));
    fireEvent.press(screen.getByTestId("quick-start-next-button"));

    expect(screen.getByTestId("quick-start-step-2")).toBeTruthy();
  });
});