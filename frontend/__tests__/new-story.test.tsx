import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import NewStoryScreen from "../app/new-story";
import {
  AdvancedBuilder,
  buildAdvancedStartRequest,
  createDefaultAdvancedSetup,
} from "../src/newstory/AdvancedBuilder";
import {
  QUICK_START_GENRES,
  assertQuickStartPoolsHealthy,
  buildQuickStartRequest,
} from "../src/newstory/QuickStart";
import {
  buildGuidedStartRequest,
  isGuidedStartComplete,
  resolveGuidedWorldSelection,
} from "../src/newstory/GuidedStart";
import type { GuidedStartSelections } from "../src/newstory/types";

jest.setTimeout(25000);

const mockReplace = jest.fn();
const mockBack = jest.fn();
const mockGetSetupCapabilities = jest.fn();
const mockNewStory = jest.fn();
const mockGetDeviceId = jest.fn();
const mockGetSettings = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ replace: mockReplace, back: mockBack }),
}));

jest.mock("../src/api", () => {
  const actual = jest.requireActual("../src/api");
  return {
    ...actual,
    getSetupCapabilities: (...args: unknown[]) => mockGetSetupCapabilities(...args),
    newStory: (...args: unknown[]) => mockNewStory(...args),
  };
});

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

const MATURE_DEFAULTS = {
  adult_mode_enabled: false,
  adult_age_confirmed: false,
  violence_level: "mild",
  horror_level: "atmospheric",
  sexual_content_level: "off",
  consent_boundary: "consensual_only",
  player_involvement: "npcs_only",
  language_level: "mild",
  substance_content_level: "mentioned",
  hard_limits: [],
};

const ADULT_CAPABILITIES = {
  channel: "development",
  adult_mode_available: true,
  sexual_content_available: true,
  nonconsensual_content_available: true,
  graphic_sexual_content_available: true,
  mature_renderer_configured: true,
};

async function renderScreen(fontScale = 1) {
  mockGetSettings.mockResolvedValue({
    debugDefault: false,
    fontScale,
    developerUnlocked: false,
  });
  render(<NewStoryScreen />);
  await waitFor(() => {
    expect(screen.getByTestId("creation-selection-screen")).toBeTruthy();
  });
}

async function openQuick() {
  fireEvent.press(screen.getByTestId("selection-card-quick"));
  await waitFor(() => expect(screen.getByTestId("quick-start-genre-fantasy")).toBeTruthy());
}

async function openGuided() {
  fireEvent.press(screen.getByTestId("selection-card-guided"));
  await waitFor(() => expect(screen.getByTestId("guided-start-step-1")).toBeTruthy());
}

async function openAdvanced() {
  fireEvent.press(screen.getByTestId("selection-card-advanced"));
  await waitFor(() => expect(screen.getByTestId("advanced-step-1")).toBeTruthy());
}

async function completeGuidedHappyPath() {
  await openGuided();
  fireEvent.press(screen.getByTestId("guided-start-option-world-fantasy"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-role-scholar"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-pressure-isolation"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-want-knowledge"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-fear-becoming-a-monster"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-whoMatters-mentor"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  fireEvent.press(screen.getByTestId("guided-start-option-experience-dark"));
  fireEvent.press(screen.getByTestId("guided-start-next-button"));
  await screen.findByTestId("guided-start-review-step");
}

const COMPLETE_GUIDED: GuidedStartSelections = {
  world: "fantasy",
  resolvedGenre: "fantasy",
  role: "scholar",
  pressure: "isolation",
  want: "knowledge",
  fear: "becoming-a-monster",
  whoMatters: "mentor",
  experience: "dark",
};

describe("new story onboarding redesign", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetSetupCapabilities.mockResolvedValue({
      distribution_capabilities: ADULT_CAPABILITIES,
      mature_content_defaults: MATURE_DEFAULTS,
    });
    mockGetDeviceId.mockResolvedValue("device-123");
    mockNewStory.mockResolvedValue({
      session_id: "session-123",
      turn: { id: "turn-1" },
      session: { id: "session-123" },
    });
  });

  it("renders selection cards without a tab switcher", async () => {
    await renderScreen();
    expect(screen.getByTestId("selection-card-quick")).toBeTruthy();
    expect(screen.getByTestId("selection-card-guided")).toBeTruthy();
    expect(screen.getByTestId("selection-card-advanced")).toBeTruthy();
    expect(screen.queryByTestId("creation-flow-switcher")).toBeNull();
    expect(screen.getByText("Choose How to Begin")).toBeTruthy();
    expect(screen.getByText("Choose a world")).toBeTruthy();
    expect(screen.getByText("Start guided setup")).toBeTruthy();
    expect(screen.getByText("Open builder")).toBeTruthy();
  });

  it("navigates into Quick Start and keeps the eight world cards one-tap", async () => {
    await renderScreen();
    await openQuick();
    expect(screen.queryByTestId("creation-selection-screen")).toBeNull();
    for (const option of QUICK_START_GENRES) {
      expect(screen.getByTestId(`quick-start-genre-${option.key}`)).toBeTruthy();
    }
    fireEvent.press(screen.getByTestId("quick-start-genre-horror"));
    await waitFor(() => {
      expect(mockNewStory).toHaveBeenCalledWith(
        expect.objectContaining({
          device_id: "device-123",
          genre: "horror",
          tone: "grim",
          difficulty: "hard",
          debug_mode: false,
          mode: "advanced",
          role: expect.any(String),
          quick_start_key: "horror",
          creation_request_id: expect.stringMatching(/^story-create:/),
        })
      );
      const body = mockNewStory.mock.calls[0][0];
      expect(body.scenario_id).toBeUndefined();
      expect(body.custom_world_setup).toBeUndefined();
      expect(body.custom_premise).toBeUndefined();
      expect(mockReplace).toHaveBeenCalledWith("/play/session-123");
    });
  });

  it("returns to selection from Quick Start without merging drafts", async () => {
    await renderScreen();
    await openQuick();
    fireEvent.press(screen.getByTestId("quick-change-path"));
    await waitFor(() => expect(screen.getByTestId("creation-selection-screen")).toBeTruthy());
  });

  it("maps every Quick Start card to a pool of at least 3 scenarios without client scenario_id", () => {
    expect(() => assertQuickStartPoolsHealthy()).not.toThrow();
    for (const option of QUICK_START_GENRES) {
      expect(option.scenario_pool.length).toBeGreaterThanOrEqual(3);
      const built = buildQuickStartRequest(option);
      expect(built.quick_start_key).toBe(option.key);
      expect(built.role).toBe(option.role);
      expect(built.genre).toBe(option.genre);
      expect((built as { scenario_id?: string }).scenario_id).toBeUndefined();
    }
  });

  it("Prehistoric Survival sends quick_start_key only — no modern containment scenario_id", async () => {
    const pre = QUICK_START_GENRES.find((g) => g.key === "dinosaur-survival");
    expect(pre).toBeTruthy();
    expect(pre!.scenario_pool).not.toContain("dinosaur-containment-breach");
    expect(pre!.scenario_pool).toEqual(
      expect.arrayContaining(["flint-band-stalked", "river-ice-calving", "tar-pit-foraging"])
    );

    await renderScreen();
    fireEvent.press(screen.getByTestId("selection-card-quick"));
    await waitFor(() => expect(screen.getByTestId("quick-start-genre-dinosaur-survival")).toBeTruthy());
    fireEvent.press(screen.getByTestId("quick-start-genre-dinosaur-survival"));
    await waitFor(() => {
      expect(mockNewStory).toHaveBeenCalledWith(
        expect.objectContaining({
          genre: "prehistoric survival",
          difficulty: "brutal",
          mode: "advanced",
          role: expect.any(String),
          quick_start_key: "dinosaur-survival",
        })
      );
    });
    const payload = mockNewStory.mock.calls[0][0];
    expect(payload.custom_world_setup).toBeUndefined();
    expect(payload.custom_premise).toBeUndefined();
    expect(payload.scenario_id).toBeUndefined();
    expect(payload.quick_start_key).toBe("dinosaur-survival");
  });

  it("builds Guided payload with pressures, hooks, tone and difficulty", () => {
    expect(isGuidedStartComplete(COMPLETE_GUIDED)).toBe(true);
    expect(buildGuidedStartRequest(COMPLETE_GUIDED)).toEqual({
      genre: "fantasy",
      role: "a scholar",
      tone: "grim",
      difficulty: "hard",
      mode: "advanced",
      custom_world_setup: {
        creationFlow: "guided",
        want: "knowledge",
        fear: "becoming-a-monster",
        whoMatters: "mentor",
        pressures: ["isolation"],
      },
    });
  });

  it("resolves Surprise me once and reuses the concrete genre", () => {
    const first = resolveGuidedWorldSelection({}, "surprise", 2);
    expect(first.world).toBe("surprise");
    expect(first.resolvedGenre).toBeTruthy();
    const second = resolveGuidedWorldSelection(first as GuidedStartSelections, "surprise", 0);
    expect(second.resolvedGenre).toBe(first.resolvedGenre);
  });

  it("maps science fiction to a general science-fiction genre", () => {
    const patch = resolveGuidedWorldSelection({}, "science-fiction");
    expect(patch.resolvedGenre).toBe("science fiction");
  });

  it("nobody relationship does not invent a named person in payload", () => {
    const payload = buildGuidedStartRequest({
      ...COMPLETE_GUIDED,
      whoMatters: "nobody",
    });
    expect(payload?.custom_world_setup.whoMatters).toBe("nobody");
    expect(JSON.stringify(payload)).not.toMatch(/Marlene|Greg|named/i);
  });

  it("preserves generic relationship meanings without parent/child mis-mapping", () => {
    const family = buildGuidedStartRequest({
      ...COMPLETE_GUIDED,
      whoMatters: "family-member",
    });
    expect(family?.custom_world_setup.whoMatters).toBe("family-member");
    expect(family?.custom_world_setup.whoMatters).not.toBe("parent");

    const dependant = buildGuidedStartRequest({
      ...COMPLETE_GUIDED,
      whoMatters: "someone-depending",
    });
    expect(dependant?.custom_world_setup.whoMatters).toBe("someone-depending");
    expect(dependant?.custom_world_setup.whoMatters).not.toBe("child");
  });

  it("walks Guided seven steps to review and submits", async () => {
    await renderScreen();
    await completeGuidedHappyPath();
    fireEvent.press(screen.getByTestId("guided-start-start-button"));
    await waitFor(() => {
      expect(mockNewStory).toHaveBeenCalledWith(
        expect.objectContaining({
          genre: "fantasy",
          role: "a scholar",
          tone: "grim",
          difficulty: "hard",
          mode: "advanced",
          custom_world_setup: {
            creationFlow: "guided",
            want: "knowledge",
            fear: "becoming-a-monster",
            whoMatters: "mentor",
            pressures: ["isolation"],
          },
        })
      );
    });
  });

  it("retains Guided draft when returning to selection and re-entering", async () => {
    await renderScreen();
    await openGuided();
    fireEvent.press(screen.getByTestId("guided-start-option-world-horror"));
    fireEvent.press(screen.getByTestId("guided-change-path"));
    await waitFor(() => expect(screen.getByTestId("creation-selection-screen")).toBeTruthy());
    await openGuided();
    expect(screen.getByTestId("guided-start-option-selected-world-horror")).toBeTruthy();
  });

  it("locks Guided duplicate submit", async () => {
    const pending = deferred<any>();
    mockNewStory.mockReturnValueOnce(pending.promise);
    await renderScreen();
    await completeGuidedHappyPath();
    fireEvent.press(screen.getByTestId("guided-start-start-button"));
    fireEvent.press(screen.getByTestId("guided-start-start-button"));
    await waitFor(() => expect(mockNewStory).toHaveBeenCalledTimes(1));
    await act(async () => {
      pending.resolve({ session_id: "g1", turn: {}, session: {} });
      await pending.promise;
    });
  });

  it("opens Advanced without Quick image grid and starts at world type", async () => {
    await renderScreen();
    await openAdvanced();
    expect(screen.queryByTestId("quick-start-genre-grid")).toBeNull();
    expect(screen.queryByTestId("genre-fantasy")).toBeNull();
    expect(screen.getByText("What kind of world is this?")).toBeTruthy();
    expect(screen.getByTestId("advanced-option-worldGenre-fantasy")).toBeTruthy();
  });

  it("maps Advanced builder including want/fear/whoMatters and omits empty optionals", () => {
    const request = buildAdvancedStartRequest({
      ...createDefaultAdvancedSetup(),
      worldGenre: "horror",
      storyFeel: "grim",
      consequenceSeverity: "brutal",
      want: "safety",
      fear: "failure",
      whoMatters: "nobody",
      ghost: undefined,
      talent: "",
      worldElements: "",
    });
    expect(request.genre).toBe("horror");
    expect(request.tone).toBe("grim");
    expect(request.difficulty).toBe("brutal");
    expect(request.custom_world_setup.want).toBe("safety");
    expect(request.custom_world_setup.whoMatters).toBe("nobody");
    expect(request.custom_world_setup.creationFlow).toBe("advanced");
    expect(request.custom_world_setup.secret).toBeUndefined();
    expect(request.custom_world_setup.worldPace).toBeUndefined();
    expect(request.custom_world_setup.ghost).toBeUndefined();
    expect(request.custom_world_setup.worldGenre).toBeUndefined();
  });

  it("Advanced defaults walk to review and create", async () => {
    await renderScreen();
    await openAdvanced();
    for (let i = 0; i < 18; i += 1) {
      fireEvent.press(screen.getByTestId("advanced-next-button"));
    }
    await screen.findByTestId("advanced-review-step");
    expect(screen.getByTestId("advanced-review-want")).toBeTruthy();
    expect(screen.getByTestId("advanced-review-whoMatters")).toBeTruthy();
    expect(screen.queryByText("Secret")).toBeNull();
    fireEvent.press(screen.getByTestId("begin-story-btn"));
    await waitFor(() => {
      expect(mockNewStory).toHaveBeenCalledWith(
        expect.objectContaining({
          genre: "modern",
          mode: "advanced",
          custom_world_setup: expect.objectContaining({
            want: "safety",
            fear: "failure",
            whoMatters: "nobody",
          }),
        })
      );
    });
  });

  it("keeps mature age gate", async () => {
    await renderScreen();
    await openAdvanced();
    for (let i = 0; i < 18; i += 1) {
      fireEvent.press(screen.getByTestId("advanced-next-button"));
    }
    await screen.findByTestId("advanced-review-step");
    fireEvent.press(screen.getByTestId("mature-content-expand"));
    fireEvent.press(screen.getByTestId("mature-content-enable"));
    fireEvent.press(screen.getByTestId("begin-story-btn"));
    expect(mockNewStory).not.toHaveBeenCalled();
    fireEvent.press(screen.getByTestId("mature-age-confirmation"));
    fireEvent.press(screen.getByTestId("begin-story-btn"));
    await waitFor(() => expect(mockNewStory).toHaveBeenCalled());
  });

  it("reuses creation_request_id on identical Quick retry", async () => {
    mockNewStory
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValueOnce({ session_id: "retry-1", turn: {}, session: {} });
    await renderScreen();
    await openQuick();
    fireEvent.press(screen.getByTestId("quick-start-genre-fantasy"));
    await screen.findByTestId("new-story-error-banner");
    const firstId = mockNewStory.mock.calls[0][0].creation_request_id;
    fireEvent.press(screen.getByTestId("quick-start-genre-fantasy"));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/play/retry-1"));
    expect(mockNewStory.mock.calls[1][0].creation_request_id).toBe(firstId);
  });

  it("exposes AdvancedBuilder as a module", () => {
    expect(typeof AdvancedBuilder).toBe("function");
  });
});
