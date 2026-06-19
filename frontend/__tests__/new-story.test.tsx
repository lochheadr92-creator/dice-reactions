import React from "react";
import { Alert } from "react-native";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import NewStoryScreen from "../app/new-story";
import { AdvancedBuilder } from "../src/newstory/AdvancedBuilder";

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

async function completeGuidedStart() {
  fireEvent.press(screen.getByTestId("creation-flow-guided"));
  await waitFor(() => {
    expect(screen.getByTestId("guided-start-step-1")).toBeTruthy();
  });
  fireEvent.press(screen.getByTestId("guided-start-option-world-fantasy"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-worldDetail-magic-is-dying"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-character-scholar"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-tone-dark"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-want-knowledge"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-fear-becoming-a-monster"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-whoMatters-mentor"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-difficulty-hard"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  await screen.findByTestId("guided-start-review-step");
}

describe("Advanced Builder extraction", () => {
  it("exposes AdvancedBuilder as a separate component module", () => {
    expect(typeof AdvancedBuilder).toBe("function");
  });
});

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
    expect(screen.getByTestId("begin-story-btn")).toBeTruthy();
    expect(screen.queryByTestId("mode-advanced")).toBeNull();
  });

  it("maps Advanced Builder payload through the unchanged newStory contract", async () => {
    mockNewStory.mockResolvedValueOnce({
      session_id: "advanced-123",
      turn: { id: "turn-advanced" },
      session: { id: "advanced-123" },
    });
    await renderScreen();

    fireEvent.press(screen.getByTestId("creation-flow-advanced"));
    await waitFor(() => {
      expect(screen.getByTestId("advanced-builder-panel")).toBeTruthy();
    });
    fireEvent.press(screen.getByTestId("scenario-modern-mystery"));
    fireEvent.changeText(screen.getByTestId("role-input"), "investigator");
    fireEvent.press(screen.getByTestId("begin-story-btn"));

    await waitFor(() => {
      expect(mockNewStory).toHaveBeenCalledWith(
        expect.objectContaining({
          device_id: "device-123",
          genre: "detective",
          role: "investigator",
          scenario_id: "modern-mystery",
          mode: "advanced",
        })
      );
    });
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

  it("shows three player-facing creation modes and switches without crashing", async () => {
    await renderScreen();

    expect(screen.getByTestId("creation-flow-quick")).toBeTruthy();
    expect(screen.getByTestId("creation-flow-guided")).toBeTruthy();
    expect(screen.getByTestId("creation-flow-advanced")).toBeTruthy();
    expect(screen.queryByText(/rolling state/i)).toBeNull();
    expect(screen.queryByText(/simulation hook/i)).toBeNull();

    fireEvent.press(screen.getByTestId("creation-flow-guided"));
    await waitFor(() => {
      expect(screen.getByTestId("guided-start-step-1")).toBeTruthy();
    });

    fireEvent.press(screen.getByTestId("creation-flow-advanced"));
    await waitFor(() => {
      expect(screen.getByTestId("advanced-builder-panel")).toBeTruthy();
    });

    fireEvent.press(screen.getByTestId("creation-flow-quick"));
    await waitFor(() => {
      expect(screen.getByTestId("quick-start-step-1")).toBeTruthy();
    });
  });

  it("Guided Start renders, advances, and preserves choices when going back", async () => {
    await renderScreen();

    fireEvent.press(screen.getByTestId("creation-flow-guided"));
    await waitFor(() => {
      expect(screen.getByTestId("guided-start-step-1")).toBeTruthy();
    });
    fireEvent.press(screen.getByTestId("guided-start-option-world-fantasy"));
    fireEvent.press(screen.getByTestId("guided-start-next-button"));
    expect(screen.getByTestId("guided-start-step-2")).toBeTruthy();
    fireEvent.press(screen.getByTestId("guided-start-option-worldDetail-magic-is-dying"));
    fireEvent.press(screen.getByTestId("guided-start-back-button"));

    expect(screen.getByTestId("guided-start-step-1")).toBeTruthy();
    expect(screen.getByTestId("guided-start-option-selected-world-fantasy")).toBeTruthy();

    fireEvent.press(screen.getByTestId("guided-start-next-button"));
    expect(screen.getByTestId("guided-start-option-selected-worldDetail-magic-is-dying")).toBeTruthy();
  });

  it("Guided Start completes without typing, shows player-facing review labels, and updates after edits", async () => {
    await renderScreen();
    await completeGuidedStart();

    expect(screen.getByTestId("guided-start-review-value-world").props.children).toBe("Fantasy");
    expect(screen.getByTestId("guided-start-review-value-worldDetail").props.children).toBe("Magic is dying");
    expect(screen.getByTestId("guided-start-review-value-character").props.children).toBe("Scholar");
    expect(screen.getByTestId("guided-start-review-value-tone").props.children).toBe("Dark");
    expect(screen.getByTestId("guided-start-review-value-want").props.children).toBe("Knowledge");
    expect(screen.getByTestId("guided-start-review-value-fear").props.children).toBe("Becoming a monster");
    expect(screen.getByTestId("guided-start-review-value-whoMatters").props.children).toBe("Mentor");
    expect(screen.getByTestId("guided-start-review-value-difficulty").props.children).toBe("Hard");
    expect(String(screen.getByTestId("guided-start-review-summary").props.children)).toContain("magic is dying");
    expect(String(screen.getByTestId("guided-start-review-summary").props.children)).not.toContain("worldDetail");
    expect(String(screen.getByTestId("guided-start-review-summary").props.children)).not.toContain("rolling_state");

    fireEvent.press(screen.getByTestId("guided-start-change-difficulty"));
    fireEvent.press(screen.getByTestId("guided-start-option-difficulty-brutal"));
    fireEvent.press(screen.getByTestId("guided-start-next-button"));

    expect(screen.getByTestId("guided-start-review-value-difficulty").props.children).toBe("Brutal");
    expect(String(screen.getByTestId("guided-start-review-summary").props.children)).toContain("brutal");
  });

  it("Guided Start maps to the existing payload and prevents duplicate submit", async () => {
    const pending = deferred<any>();
    mockNewStory.mockReturnValueOnce(pending.promise);
    await renderScreen();
    await completeGuidedStart();

    fireEvent.press(screen.getByTestId("guided-start-start-button"));
    fireEvent.press(screen.getByTestId("guided-start-start-button"));

    await waitFor(() => {
      expect(mockNewStory).toHaveBeenCalledTimes(1);
      expect(mockNewStory).toHaveBeenCalledWith({
        device_id: "device-123",
        genre: "fantasy",
        role: "a scholar",
        tone: "grim",
        difficulty: "hard",
        debug_mode: false,
        custom_premise: "Fantasy: Magic is dying. The old power is draining away.",
        mode: "advanced",
        custom_world_setup: {
          want: "knowledge",
          fear: "becoming-a-monster",
          whoMatters: "mentor",
        },
      });
    });
    expect(screen.getByTestId("guided-start-loading-state")).toBeTruthy();

    await act(async () => {
      pending.resolve({
        session_id: "guided-123",
        turn: { id: "turn-guided" },
        session: { id: "guided-123" },
      });
      await pending.promise;
    });

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/play/guided-123");
    });
  });

  it("Guided Start preserves answers after failure and retry", async () => {
    mockNewStory
      .mockRejectedValueOnce(new Error("502: trace"))
      .mockResolvedValueOnce({ session_id: "guided-retry", turn: {}, session: {} });
    await renderScreen();
    await completeGuidedStart();

    fireEvent.press(screen.getByTestId("guided-start-start-button"));

    await waitFor(() => {
      expect(screen.getByTestId("new-story-error-banner")).toBeTruthy();
    });
    expect(screen.getByTestId("guided-start-review-value-world").props.children).toBe("Fantasy");
    expect(screen.getByTestId("guided-start-review-value-difficulty").props.children).toBe("Hard");
    expect(String(screen.getByTestId("new-story-error-banner").props.children)).not.toContain("trace");

    fireEvent.press(screen.getByTestId("guided-start-start-button"));
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/play/guided-retry");
    });
    expect(mockNewStory).toHaveBeenCalledTimes(2);
  });

  it("keeps Guided Start state isolated from Quick Start and Advanced Builder", async () => {
    await renderScreen();

    fireEvent.press(screen.getByTestId("creation-flow-guided"));
    await waitFor(() => {
      expect(screen.getByTestId("guided-start-step-1")).toBeTruthy();
    });
    fireEvent.press(screen.getByTestId("guided-start-option-world-fantasy"));

    fireEvent.press(screen.getByTestId("creation-flow-quick"));
    await waitFor(() => {
      expect(screen.getByTestId("quick-start-step-1")).toBeTruthy();
    });
    expect(screen.queryByTestId("quick-start-option-selected-world-fantasy")).toBeNull();

    fireEvent.press(screen.getByTestId("creation-flow-guided"));
    await waitFor(() => {
      expect(screen.getByTestId("guided-start-step-1")).toBeTruthy();
    });
    expect(screen.getByTestId("guided-start-option-selected-world-fantasy")).toBeTruthy();

    fireEvent.press(screen.getByTestId("creation-flow-advanced"));
    await waitFor(() => {
      expect(screen.getByTestId("advanced-builder-panel")).toBeTruthy();
    });
    expect(screen.getByTestId("role-input").props.value).toBe("");
  });

  it("renders Guided Start safely at XL font scale", async () => {
    await renderScreen(1.25);

    fireEvent.press(screen.getByTestId("creation-flow-guided"));
    await waitFor(() => {
      expect(screen.getByTestId("guided-start-heading").props.style).toEqual(
        expect.arrayContaining([expect.objectContaining({ fontSize: 38 })])
      );
    });

    fireEvent.press(screen.getByTestId("guided-start-option-world-fantasy"));
    fireEvent.press(screen.getByTestId("guided-start-next-button"));
    expect(screen.getByTestId("guided-start-step-2")).toBeTruthy();
  });
});