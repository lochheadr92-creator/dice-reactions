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
};

export async function getSettings(): Promise<AppSettings> {
  const raw = await AsyncStorage.getItem(SETTINGS_KEY);
  if (!raw) return { debugDefault: false, fontScale: 1 };
  try {
    return { debugDefault: false, fontScale: 1, ...JSON.parse(raw) };
  } catch {
    return { debugDefault: false, fontScale: 1 };
  }
}

export async function saveSettings(s: AppSettings): Promise<void> {
  await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
}
