import React from "react";
import { Alert } from "react-native";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import SettingsScreen from "../app/settings";

const mockBack = jest.fn();
const mockGetSettings = jest.fn();
const mockSaveSettings = jest.fn();
const mockGetAdminSettings = jest.fn();
const mockUpdateAdminSettings = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({
    back: mockBack,
  }),
}));

jest.mock("../src/storage", () => ({
  getSettings: (...args: unknown[]) => mockGetSettings(...args),
  saveSettings: (...args: unknown[]) => mockSaveSettings(...args),
}));

jest.mock("../src/api", () => ({
  getAdminSettings: (...args: unknown[]) => mockGetAdminSettings(...args),
  updateAdminSettings: (...args: unknown[]) => mockUpdateAdminSettings(...args),
}));

const sonnet = "anthropic/claude-sonnet-4.5";
const deepseek = "deepseek/deepseek-chat-v3-0324";

describe("Settings admin AI engine", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSaveSettings.mockResolvedValue(undefined);
    jest.spyOn(Alert, "alert").mockImplementation(jest.fn());
  });

  it("keeps S/M/L/XL wired to local prose font scale", async () => {
    mockGetSettings.mockResolvedValue({
      debugDefault: false,
      fontScale: 1,
      developerUnlocked: false,
    });

    render(<SettingsScreen />);
    await waitFor(() => expect(screen.getByTestId("font-scale-1.25")).toBeTruthy());

    fireEvent.press(screen.getByTestId("font-scale-1.25"));

    await waitFor(() => {
      expect(mockSaveSettings).toHaveBeenCalledWith(
        expect.objectContaining({ fontScale: 1.25 })
      );
    });
    expect(screen.queryByTestId("admin-ai-engine")).toBeNull();
  });

  it("developer unlock reveals admin controls", async () => {
    mockGetSettings.mockResolvedValue({
      debugDefault: false,
      fontScale: 1,
      developerUnlocked: false,
    });

    render(<SettingsScreen />);
    await waitFor(() => expect(screen.getByTestId("version-tap")).toBeTruthy());

    for (let i = 0; i < 7; i += 1) {
      fireEvent.press(screen.getByTestId("version-tap"));
    }

    await waitFor(() => {
      expect(screen.getByTestId("admin-ai-engine")).toBeTruthy();
      expect(mockSaveSettings).toHaveBeenCalledWith(
        expect.objectContaining({ developerUnlocked: true })
      );
    });
  });

  it("loads active model and posts manual model selection", async () => {
    mockGetSettings.mockResolvedValue({
      debugDefault: false,
      fontScale: 1,
      developerUnlocked: true,
    });
    mockGetAdminSettings.mockResolvedValue({
      settings: { model: sonnet, fallback_models: [sonnet, deepseek] },
      models: [
        { id: sonnet, label: "Claude Sonnet 4.5", note: "Default" },
        { id: deepseek, label: "DeepSeek V3", note: "Fallback" },
      ],
    });
    mockUpdateAdminSettings.mockResolvedValue({
      settings: { model: deepseek, fallback_models: [sonnet, deepseek] },
    });

    render(<SettingsScreen />);
    await waitFor(() => expect(screen.getByTestId("admin-key-input")).toBeTruthy());

    fireEvent.changeText(screen.getByTestId("admin-key-input"), "admin-key");
    fireEvent.press(screen.getByTestId("admin-load-settings"));

    await waitFor(() => {
      expect(mockGetAdminSettings).toHaveBeenCalledWith("admin-key");
      expect(screen.getByTestId("active-model-value").props.children).toBe("Claude Sonnet 4.5");
    });

    fireEvent.press(screen.getByTestId(`model-select-${deepseek}`));

    await waitFor(() => {
      expect(mockUpdateAdminSettings).toHaveBeenCalledWith("admin-key", { model: deepseek });
      expect(screen.getByTestId("active-model-value").props.children).toBe("DeepSeek V3");
    });
  });
});
