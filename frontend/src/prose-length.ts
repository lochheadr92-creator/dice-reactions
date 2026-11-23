/**
 * Two separate reading settings, each with its own S / M / L / XL control:
 * text size (how big the letters are) and turn length (how many paragraphs
 * each turn has). The paragraph ranges mirror the engine's prose modes in
 * backend/prose_modes.py.
 */
export type TurnLength = "S" | "M" | "L" | "XL";

export const TEXT_SIZES: readonly { fontScale: number; label: TurnLength }[] = [
  { fontScale: 0.9, label: "S" },
  { fontScale: 1, label: "M" },
  { fontScale: 1.1, label: "L" },
  { fontScale: 1.25, label: "XL" },
];

export const TURN_LENGTHS: readonly {
  label: TurnLength;
  proseMode: "brief" | "standard" | "story" | "cinematic";
  paragraphs: string;
}[] = [
  { label: "S", proseMode: "brief", paragraphs: "1 to 2 paragraphs" },
  { label: "M", proseMode: "standard", paragraphs: "2 to 4 paragraphs" },
  { label: "L", proseMode: "story", paragraphs: "4 to 6 paragraphs" },
  { label: "XL", proseMode: "cinematic", paragraphs: "6 to 8 paragraphs" },
];

export const DEFAULT_TURN_LENGTH: TurnLength = "M";

export function isTurnLength(value: unknown): value is TurnLength {
  return TURN_LENGTHS.some((t) => t.label === value);
}

/** Engine prose mode for a turn length. An unknown or missing value gives M. */
export function proseModeForTurnLength(value: unknown): (typeof TURN_LENGTHS)[number]["proseMode"] {
  const label = isTurnLength(value) ? value : DEFAULT_TURN_LENGTH;
  return TURN_LENGTHS.find((t) => t.label === label)!.proseMode;
}

/** Writing style. Sent to the engine as prose_style. */
export type WritingStyle = "plain" | "balanced" | "rich";

export const WRITING_STYLES: readonly { value: WritingStyle; label: string; explanation: string }[] = [
  { value: "plain", label: "Plain", explanation: "Short, direct sentences. No metaphor. Only what matters to your decision." },
  { value: "balanced", label: "Balanced", explanation: "The story's normal voice." },
  { value: "rich", label: "Rich", explanation: "More description, mood and imagery. What is at stake still has to be said plainly." },
];

export const DEFAULT_WRITING_STYLE: WritingStyle = "balanced";

/** Speed. Sent to the engine as thinking_effort: how long the model thinks before it writes. */
export type Speed = "fast" | "balanced" | "careful";

export const SPEEDS: readonly {
  value: Speed;
  label: string;
  thinkingEffort: "low" | "medium" | "high";
  explanation: string;
}[] = [
  { value: "fast", label: "Fast", thinkingEffort: "low", explanation: "Turns arrive soonest. The model thinks least, so rule slips are a little more likely." },
  { value: "balanced", label: "Balanced", thinkingEffort: "medium", explanation: "A middle setting. Slower than Fast." },
  { value: "careful", label: "Careful", thinkingEffort: "high", explanation: "The model thinks longest before writing. Slowest turns. In testing, an opening took 3 to 4 minutes." },
];

export const DEFAULT_SPEED: Speed = "fast";

/** Per-story defaults chosen in Settings. The Advanced builder starts from them. */
export type StoryDefaults = {
  storyFeel?: string;
  consequenceSeverity?: string;
  /** 18+ levels by row key. Applied when mature content is switched on for a story. */
  mature?: Record<string, string>;
};

function isOneOf<T extends string>(options: readonly { value: T }[], value: unknown): value is T {
  return options.some((o) => o.value === value);
}

export function isWritingStyle(value: unknown): value is WritingStyle {
  return isOneOf(WRITING_STYLES, value);
}

export function isSpeed(value: unknown): value is Speed {
  return isOneOf(SPEEDS, value);
}

/** The three engine fields the reading settings turn into. */
export function playSettingsFor(settings: {
  turnLength?: unknown;
  writingStyle?: unknown;
  speed?: unknown;
}): { prose_mode: string; prose_style: WritingStyle; thinking_effort: "low" | "medium" | "high" } {
  const speed = isSpeed(settings.speed) ? settings.speed : DEFAULT_SPEED;
  return {
    prose_mode: proseModeForTurnLength(settings.turnLength),
    prose_style: isWritingStyle(settings.writingStyle) ? settings.writingStyle : DEFAULT_WRITING_STYLE,
    thinking_effort: SPEEDS.find((s) => s.value === speed)!.thinkingEffort,
  };
}
