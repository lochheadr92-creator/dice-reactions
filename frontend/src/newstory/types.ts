import type {
  QuickWorldValue,
  QuickCharacterValue,
  QuickToneValue,
  WantValue,
  FearValue,
  WhoMattersValue,
  GuidedWorldValue,
  StoryDifficultyValue,
} from "./options";

export type AdvancedDifficulty = "soft" | "standard" | "hard" | "brutal";

export type QuickStartSelections = {
  world?: QuickWorldValue;
  resolvedWorldGenre?: string;
  character?: QuickCharacterValue;
  tone?: QuickToneValue;
  want?: WantValue;
  fear?: FearValue;
  whoMatters?: WhoMattersValue;
};

export type GuidedStartSelections = {
  world?: GuidedWorldValue;
  worldDetail?: string;
  character?: QuickCharacterValue;
  tone?: QuickToneValue;
  want?: WantValue;
  fear?: FearValue;
  whoMatters?: WhoMattersValue;
  difficulty?: StoryDifficultyValue;
};