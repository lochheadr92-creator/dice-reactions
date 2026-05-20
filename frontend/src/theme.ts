export const COLORS = {
  background: "#050505",
  surface: "#121214",
  surfaceDeep: "#0A0A0A",
  border: "#27272A",
  borderDim: "#18181B",
  primary: "#F59E0B",
  primaryDim: "rgba(245, 158, 11, 0.15)",
  primarySoft: "rgba(245, 158, 11, 0.08)",
  textPrimary: "#F3F4F6",
  textSecondary: "#A1A1AA",
  textProse: "#D4D4D8",
  textMuted: "#71717A",
  health: "#EF4444",
  stress: "#8B5CF6",
  objective: "#10B981",
  danger: "#DC2626",
};

export const FONTS = {
  heading: "CormorantGaramond_600SemiBold",
  headingBold: "CormorantGaramond_700Bold",
  body: "EBGaramond_400Regular",
  bodyItalic: "EBGaramond_400Regular_Italic",
  bodyMed: "EBGaramond_500Medium",
  mono: "JetBrainsMono_400Regular",
  monoBold: "JetBrainsMono_700Bold",
  monoMed: "JetBrainsMono_500Medium",
};

export const BACKEND_URL =
  process.env.EXPO_PUBLIC_BACKEND_URL || "";

export const API = `${BACKEND_URL}/api`;
