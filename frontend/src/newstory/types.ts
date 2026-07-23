import type {
  FearValue,
  WantValue,
} from "./options";

export type AdvancedDifficulty = "soft" | "standard" | "hard" | "brutal";

export type GuidedWorldValue =
  | "fantasy"
  | "horror"
  | "science-fiction"
  | "post-apocalyptic"
  | "mystery-crime"
  | "modern"
  | "surprise";

export type GuidedRoleValue =
  | "survivor"
  | "wanderer"
  | "investigator"
  | "soldier"
  | "outcast"
  | "scholar"
  | "worker"
  | "local";

export type GuidedPressureValue =
  | "scarcity"
  | "violence"
  | "isolation"
  | "betrayal"
  | "illness"
  | "authority"
  | "unknown";

export type GuidedWhoMattersValue =
  | "family-member"
  | "friend"
  | "partner"
  | "mentor"
  | "someone-depending"
  | "someone-failed"
  | "nobody";

export type GuidedExperienceValue = "hopeful" | "balanced" | "dark" | "brutal";

export type GuidedDesireValue =
  | "safety"
  | "freedom"
  | "redemption"
  | "knowledge"
  | "revenge"
  | "justice";

/** Draft state for Guided Start (isolated from Advanced). */
export type GuidedStartSelections = {
  world?: GuidedWorldValue;
  /** Concrete genre after Surprise me is resolved once. */
  resolvedGenre?: string;
  role?: GuidedRoleValue;
  pressure?: GuidedPressureValue;
  want?: GuidedDesireValue | WantValue;
  fear?: FearValue;
  whoMatters?: GuidedWhoMattersValue;
  experience?: GuidedExperienceValue;
};

export type QuickStartSelections = {
  // Legacy type retained for catalog compatibility; Quick Start no longer uses multi-step drafts.
  world?: string;
};
