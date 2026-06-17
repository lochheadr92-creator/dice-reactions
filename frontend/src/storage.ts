import AsyncStorage from "@react-native-async-storage/async-storage";

const DEVICE_ID_KEY = "dice_device_id";
const SETTINGS_KEY = "dice_settings";

function generateDeviceId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  if (typeof globalThis.crypto?.getRandomValues !== "function") {
    throw new Error(
      "Secure random number generation is unavailable; cannot create a device identity."
    );
  }
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function getDeviceId(): Promise<string> {
  let id = await AsyncStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = generateDeviceId();
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

const ALLOWED_FONT_SCALES = [0.9, 1, 1.1, 1.25];

function sanitizeSettings(raw: any): { settings: AppSettings; repaired: boolean } {
  let repaired = false;
  const source = raw && typeof raw === "object" ? raw : {};
  if (!raw || typeof raw !== "object") repaired = true;

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
    const fresh = { ...DEFAULT_SETTINGS };
    try {
      await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(fresh));
    } catch {}
    return fresh;
  }
  const { settings, repaired } = sanitizeSettings(parsed);
  if (repaired) {
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