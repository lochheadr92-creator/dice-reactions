const store: Record<string, string> = {};

jest.mock("@react-native-async-storage/async-storage", () => ({
  __esModule: true,
  default: {
    getItem: jest.fn(async (key: string) => (key in store ? store[key] : null)),
    setItem: jest.fn(async (key: string, value: string) => {
      store[key] = value;
    }),
  },
}));

import { getSettings, saveSettings } from "../src/storage";

const SETTINGS_KEY = "dice_settings";

describe("turn length in saved settings", () => {
  beforeEach(() => {
    for (const key of Object.keys(store)) delete store[key];
  });

  it("gives M to settings saved before turn length existed, keeping text size", async () => {
    store[SETTINGS_KEY] = JSON.stringify({ debugDefault: false, fontScale: 1.25, developerUnlocked: false });
    const settings = await getSettings();
    expect(settings.fontScale).toBe(1.25);
    expect(settings.turnLength).toBe("M");
  });

  it("saves and reads back a chosen turn length", async () => {
    await saveSettings({ debugDefault: false, fontScale: 0.9, turnLength: "XL" });
    const settings = await getSettings();
    expect(settings).toEqual(
      expect.objectContaining({ fontScale: 0.9, turnLength: "XL" })
    );
  });

  it("replaces an unknown turn length with M", async () => {
    store[SETTINGS_KEY] = JSON.stringify({ debugDefault: false, fontScale: 1, turnLength: "huge" });
    const settings = await getSettings();
    expect(settings.turnLength).toBe("M");
    expect(JSON.parse(store[SETTINGS_KEY]).turnLength).toBe("M");
  });
});
