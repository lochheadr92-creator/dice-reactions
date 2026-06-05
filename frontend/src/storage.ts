import AsyncStorage from "@react-native-async-storage/async-storage";

const DEVICE_ID_KEY = "dice_device_id";
const SETTINGS_KEY = "dice_settings";

function uuid(): string {
  // RFC4122-ish v4
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function getDeviceId(): Promise<string> {
  let id = await AsyncStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = uuid();
    await AsyncStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

export type AppSettings = {
  debugDefault: boolean;
  fontScale: number;
  developerUnlocked?: boolean;
};

const DEFAULT_SETTINGS: AppSettings = {
  debugDefault: false,
  fontScale: 1,
  developerUnlocked: false,
};

// The only font scales the UI can render. Anything else is corrupt/legacy and
// must be repaired so it can never feed an out-of-range index into the picker.
const ALLOWED_FONT_SCALES = [0.9, 1, 1.1, 1.25];

/**
 * Startup sanitiser for persisted settings.
 *
 * Coerces every field to a known-good value and strips any unknown/legacy keys
 * (e.g. stale array indexes saved by older builds). If anything had to be
 * repaired the cleaned object is written back to disk and the repair is logged.
 * This guarantees no malformed persisted value can ever reach a native indexed
 * component on launch.
 */
function sanitizeSettings(raw: any): { settings: AppSettings; repaired: boolean } {
  let repaired = false;
  const source = raw && typeof raw === "object" ? raw : {};
  if (!raw || typeof raw !== "object") repaired = true;

  // fontScale must be one of the allowed values.
  let fontScale = Number(source.fontScale);
  if (!ALLOWED_FONT_SCALES.includes(fontScale)) {
    repaired = true;
    fontScale = DEFAULT_SETTINGS.fontScale;
  }

  const debugDefault = source.debugDefault === true;
  if (source.debugDefault !== undefined && typeof source.debugDefault !== "boolean") repaired = true;

  const developerUnlocked = source.developerUnlocked === true;
  if (source.developerUnlocked !== undefined && typeof source.developerUnlocked !== "boolean") repaired = true;

  const cleaned: AppSettings = { debugDefault, fontScale, developerUnlocked };

  // Detect legacy / unexpected keys (older builds may have stored array
  // indexes such as a selected-model index). Dropping them is a repair.
  const allowedKeys = new Set(["debugDefault", "fontScale", "developerUnlocked"]);
  for (const k of Object.keys(source)) {
    if (!allowedKeys.has(k)) {
      repaired = true;
      break;
    }
  }

  return { settings: cleaned, repaired };
}

export async function getSettings(): Promise<AppSettings> {
  const raw = await AsyncStorage.getItem(SETTINGS_KEY);
  if (!raw) return { ...DEFAULT_SETTINGS };
  let parsed: any = null;
  try {
    parsed = JSON.parse(raw);
  } catch {
    console.log("[storage] corrupt settings JSON — resetting to defaults");
    const fresh = { ...DEFAULT_SETTINGS };
    try {
      await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(fresh));
    } catch {}
    return fresh;
  }
  const { settings, repaired } = sanitizeSettings(parsed);
  if (repaired) {
    console.log("[storage] repaired invalid persisted settings", { from: parsed, to: settings });
    try {
      await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch {}
  }
  return settings;
}

export async function saveSettings(s: AppSettings): Promise<void> {
  const { settings } = sanitizeSettings(s);
  await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}
