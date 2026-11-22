import React, { useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../theme";
import type {
  CustomWorldSetup,
  DistributionCapabilities,
  MatureContentPreferences,
} from "../api";
import {
  HOOK_FEAR,
  HOOK_FLAW,
  HOOK_GHOST,
  HOOK_LINE,
  HOOK_TALENT,
  HOOK_WANT,
  HOOK_WHO_MATTERS,
  HARSHNESS_LABELS,
  STORY_DIFFICULTIES,
} from "./options";

type SetupOption = { value: string; label: string; explanation?: string; consequence?: string };

type AdvancedBuilderProps = {
  loading: boolean;
  fontScale: number;
  customSetup: CustomWorldSetup;
  matureContent: MatureContentPreferences;
  capabilities: DistributionCapabilities;
  onSetSetupField: (patch: Partial<CustomWorldSetup>) => void;
  onSetMatureContent: (patch: Partial<MatureContentPreferences>) => void;
  onStart: () => void;
  onChangePath: () => void;
};

export type AdvancedStartRequest = {
  genre: string;
  role: string;
  tone: string;
  difficulty: "soft" | "standard" | "hard" | "brutal";
  mode: "advanced";
  custom_premise?: string;
  custom_world_setup: CustomWorldSetup;
};

const WORLD_GENRES: SetupOption[] = [
  { value: "fantasy", label: "Fantasy", explanation: "An invented realm before machines, where magic exists.", consequence: "Expect: oaths, shortages and rival factions." },
  { value: "horror", label: "Horror", explanation: "A cut-off place with a threat you do not understand yet.", consequence: "Expect: isolation, dread and safety you cannot rely on." },
  { value: "science fiction", label: "Science fiction", explanation: "The near or far future with advanced technology. It is not forced to be cyberpunk.", consequence: "Expect: large systems, shortages and people with authority over you." },
  { value: "post-apocalyptic", label: "Post-apocalyptic", explanation: "After a collapse. People live in scattered settlements on what they salvage.", consequence: "Expect: shortages, violence and trust being tested." },
  { value: "detective", label: "Mystery or crime", explanation: "A place with something to investigate, in the present or an earlier period.", consequence: "Expect: secrets, violence and authority in your way." },
  { value: "modern", label: "Modern", explanation: "The present day, kept realistic.", consequence: "Expect: social pressure, shortages and trouble with authority." },
  { value: "custom", label: "Custom", explanation: "Type your own kind of world in a few words, such as haunted oil rig.", consequence: "Expect: the setting is built from your words. Put the story idea itself in the premise box." },
];

const TIME_PERIOD_OPTIONS: SetupOption[] = [
  { value: "world_decides", label: "Let the world type decide", explanation: "No fixed time. The kind of world sets it.", consequence: "Expect: with a custom world, the story picks the period for you." },
  { value: "present_day", label: "Present day", explanation: "Now. Phones, cars, cities as you know them.", consequence: "Expect: modern streets, jobs and technology." },
  { value: "past", label: "The past", explanation: "An earlier period of history.", consequence: "Expect: older tools, travel and customs." },
  { value: "future", label: "The future", explanation: "A time that has not happened yet.", consequence: "Expect: technology and ways of living beyond today." },
];

const LOCATION_OPTIONS: SetupOption[] = [
  { value: "small_settlement", label: "Small settlement", explanation: "A close community where shortages are hard to ignore.", consequence: "Expect: everyone knows you and there are few places to hide." },
  { value: "crowded_city", label: "Crowded city", explanation: "Many people, routes, and competing needs nearby.", consequence: "Expect: strangers, crowds and more than one way out." },
  { value: "remote_wilderness", label: "Remote wilderness", explanation: "Distance and limited support shape the opening.", consequence: "Expect: weather, travel and supplies to matter." },
  { value: "isolated_location", label: "Isolated location", explanation: "Cut off from ordinary help.", consequence: "Expect: a small group and no one coming to assist." },
  { value: "travelling_group", label: "Travelling group", explanation: "Already moving between places.", consequence: "Expect: the people you travel with to be your whole world at first." },
  { value: "custom_location", label: "Custom location", explanation: "Type where the story opens.", consequence: "Expect: the opening scene is set there." },
];

const CONDITION_OPTIONS: SetupOption[] = [
  { value: "stable", label: "Stable", explanation: "Daily life works. Trouble is local and personal.", consequence: "Expect: steady people and services that still function." },
  { value: "uneasy", label: "Uneasy", explanation: "Things still work, but people are on edge.", consequence: "Expect: suspicion, and small problems that spread." },
  { value: "divided", label: "Fracturing", explanation: "The community is splitting into sides.", consequence: "Expect: pressure to pick a side." },
  { value: "collapsing", label: "Collapsing", explanation: "Order is failing right now.", consequence: "Expect: shortages, desperate people and little help." },
];

const CHANGE_OPTIONS_FIXED: SetupOption[] = [
  { value: "nothing_major", label: "Nothing major", explanation: "Nothing big has happened lately.", consequence: "Expect: the story picks the opening problem on its own." },
  { value: "someone_disappeared", label: "A leader disappeared", explanation: "Someone people relied on is gone.", consequence: "Expect: an opening about a witness, a message, a demand from authority or a suspected betrayal." },
  { value: "resources_became_scarce", label: "An important resource became scarce", explanation: "Something people need has run short.", consequence: "Expect: an opening about a shortage, a debt or a last chance." },
  { value: "conflict_intensified", label: "Violence increased", explanation: "Fights and threats have become more common.", consequence: "Expect: an opening about an injury, an unwelcome visitor, a demand from authority or being trapped." },
  { value: "disaster_occurred", label: "A route or supply line failed", explanation: "A road, route or supply line has been cut.", consequence: "Expect: an opening about being stuck, a shortage, worsening conditions or a blocked departure." },
  { value: "important_discovery", label: "Something unexplained occurred", explanation: "Something happened that nobody can account for.", consequence: "Expect: an opening about a message, a watcher or a visitor tied to it." },
  { value: "custom_event", label: "Custom", explanation: "Type what changed.", consequence: "Expect: the story picks the opening problem and must fit it to your words." },
];

const GROUNDEDNESS_OPTIONS: SetupOption[] = [
  { value: "realistic", label: "Realistic", explanation: "Only things that could happen in real life.", consequence: "Expect: supernatural causes are rejected, unless you list them under what belongs in this world." },
  { value: "mostly_grounded", label: "Mostly grounded", explanation: "Real-world rules, with room for a small number of strange things.", consequence: "Expect: the strange stays rare." },
  { value: "openly_speculative", label: "Speculative", explanation: "Strange or impossible things are a normal part of this world.", consequence: "Expect: the unusual shows up openly." },
];

const ROLE_OPTIONS: SetupOption[] = [
  { value: "local_resident", label: "Local resident", explanation: "You live here and people know you.", consequence: "Expect: existing ties and a reputation." },
  { value: "outsider", label: "Outsider", explanation: "You are new here.", consequence: "Expect: suspicion, and nobody owing you anything." },
  { value: "worker_or_specialist", label: "Worker or specialist", explanation: "You have a trade or skill people need.", consequence: "Expect: people wanting your work, and blame when it fails." },
  { value: "leader", label: "Leader", explanation: "People look to you for decisions.", consequence: "Expect: responsibility for others and challenges to your position." },
  { value: "prisoner_or_captive", label: "Prisoner or captive", explanation: "Someone else holds you.", consequence: "Expect: limited movement, and people who control what you get." },
  { value: "traveller", label: "Traveller", explanation: "You are passing through.", consequence: "Expect: few ties and an easy exit, until something stops you." },
  { value: "custom_role", label: "Custom role", explanation: "Type who you are in a few words.", consequence: "Expect: your words become your position in the story." },
];

const KNOWLEDGE_OPTIONS: SetupOption[] = [
  { value: "very_little", label: "Very little", explanation: "Most facts must be learned in play.", consequence: "Expect: people and places introduced as new to you." },
  { value: "basic_local_knowledge", label: "Basic local knowledge", explanation: "Ordinary public places and risks.", consequence: "Expect: you know your way around, and nothing private." },
  { value: "well_connected", label: "Well connected", explanation: "Useful contacts—not hidden truth.", consequence: "Expect: people you can ask, who may want something back." },
  { value: "deeply_involved", label: "Deeply involved", explanation: "You already know disputes you have lived.", consequence: "Expect: history with the people around you." },
];

const STORY_FEEL: SetupOption[] = [
  { value: "hopeful", label: "Hopeful", explanation: "Warm writing. People can be reached and things can improve.", consequence: "Expect: a change of mood only. Harshness is the next question." },
  { value: "grounded", label: "Grounded", explanation: "Plain, realistic writing.", consequence: "Expect: a change of mood only. Harshness is the next question." },
  { value: "grim", label: "Dark", explanation: "Cold, uncertain writing. Wins cost something.", consequence: "Expect: a change of mood only. Harshness is the next question." },
  { value: "bleak", label: "Bleak", explanation: "Little comfort anywhere in the writing.", consequence: "Expect: a change of mood only. Harshness is the next question." },
];

/** Advanced answer → engine difficulty. One set of words everywhere (HARSHNESS_LABELS). */
const SEVERITY_TO_DIFFICULTY = {
  forgiving: "soft",
  balanced: "standard",
  severe: "hard",
  brutal: "brutal",
} as const;

const SEVERITY: SetupOption[] = (
  Object.entries(SEVERITY_TO_DIFFICULTY) as [string, keyof typeof HARSHNESS_LABELS][]
).map(([value, difficulty]) => {
  const copy = STORY_DIFFICULTIES.find((d) => d.value === difficulty);
  return {
    value,
    label: HARSHNESS_LABELS[difficulty],
    explanation: copy?.explanation,
    consequence: copy?.consequence,
  };
});

/** Closed-catalog hook copy from options.ts, with both description lines kept. */
function withCopy(options: readonly { value: string; label: string; explanation: string; consequence: string }[]): SetupOption[] {
  return options.map((o) => ({
    value: o.value,
    label: o.label,
    explanation: o.explanation,
    consequence: o.consequence,
  }));
}

type StepDef = {
  key: string;
  section: string;
  question: string;
  helper: string;
  optional?: boolean;
  options?: SetupOption[];
  freeText?: boolean;
  placeholder?: string;
  setupKey?: keyof CustomWorldSetup;
};

const STEPS: StepDef[] = [
  { key: "worldGenre", section: "World", question: "What kind of world is this?", helper: "The kind of setting. Pick one, or choose Custom and type your own in a few words.", options: WORLD_GENRES, setupKey: "worldGenre" },
  { key: "premise", section: "World", question: "What is this story about?", helper: "Optional. One or two sentences on what makes this world or your character different. The story is built around it and it stays true.", optional: true, freeText: true, placeholder: "Example: I am the only person who can read minds, and nobody knows.", setupKey: "premise" },
  { key: "timePeriod", section: "World", question: "When is this set?", helper: "The time period. This matters most for a custom world, which has no period of its own.", options: TIME_PERIOD_OPTIONS, setupKey: "timePeriod" },
  { key: "startingLocation", section: "World", question: "Where does this begin?", helper: "The kind of place the story opens in.", options: LOCATION_OPTIONS, setupKey: "startingLocation" },
  { key: "worldCondition", section: "World", question: "How strained is the world?", helper: "The lasting state of daily life before the story starts. The next question covers one recent event.", options: CONDITION_OPTIONS, setupKey: "worldCondition" },
  { key: "recentChange", section: "World", question: "What recently shifted?", helper: "One thing that already happened before the story starts. The opening grows out of it.", options: CHANGE_OPTIONS_FIXED, setupKey: "recentChange" },
  { key: "settingGroundedness", section: "World", question: "How real or strange is the setting?", helper: "How far this world may go beyond real life.", options: GROUNDEDNESS_OPTIONS, setupKey: "settingGroundedness" },
  { key: "worldElements", section: "World", question: "What belongs in this world?", helper: "Optional. Things you want to exist here, such as trains or a ruling church.", optional: true, freeText: true, placeholder: "Optional…", setupKey: "worldElements" },
  { key: "worldExclusions", section: "World", question: "What must not appear?", helper: "Optional. Things that must never show up, such as guns or magic.", optional: true, freeText: true, placeholder: "Optional…", setupKey: "worldExclusions" },
  { key: "startingRole", section: "Character", question: "Who are you at the start?", helper: "Your place among the people around you when the story opens.", options: ROLE_OPTIONS, setupKey: "startingRole" },
  { key: "characterKnowledge", section: "Character", question: "How much do you already know?", helper: "What your character already knows about this place. Secrets still have to be found in play.", options: KNOWLEDGE_OPTIONS, setupKey: "characterKnowledge" },
  { key: "want", section: "Character", question: "What do you want most?", helper: "What drives your character. The story keeps putting it within reach and at risk.", options: withCopy(HOOK_WANT), setupKey: "want" },
  { key: "fear", section: "Character", question: "What are you most afraid of?", helper: "What your character dreads. The story will test it.", options: withCopy(HOOK_FEAR), setupKey: "fear" },
  { key: "whoMatters", section: "Relationships", question: "Who matters most to you?", helper: "The kind of person you care about most. They get no name until they appear in play.", options: withCopy(HOOK_WHO_MATTERS), setupKey: "whoMatters" },
  { key: "ghost", section: "Optional depth", question: "What past still presses?", helper: "Optional. Something from your past that comes back.", optional: true, options: withCopy(HOOK_GHOST), setupKey: "ghost" },
  { key: "talent", section: "Optional depth", question: "What are you unusually good at?", helper: "Optional. One thing you do better than most people.", optional: true, options: withCopy(HOOK_TALENT), setupKey: "talent" },
  { key: "flaw", section: "Optional depth", question: "What gets you into trouble?", helper: "Optional. The habit that causes you problems.", optional: true, options: withCopy(HOOK_FLAW), setupKey: "flaw" },
  { key: "line", section: "Optional depth", question: "What won’t you do?", helper: "Optional. The thing you refuse to do. The story will tempt you to do it.", optional: true, options: withCopy(HOOK_LINE), setupKey: "line" },
  { key: "storyFeel", section: "Experience", question: "What should this feel like?", helper: "The mood of the writing only. It does not make the game easier or harder.", options: STORY_FEEL, setupKey: "storyFeel" },
  { key: "consequenceSeverity", section: "Experience", question: "How harsh are consequences?", helper: "How much mistakes cost and how fast you recover. The same four words are used everywhere in the game.", options: SEVERITY, setupKey: "consequenceSeverity" },
];

/** The builder shows one page per group of questions, then the review. */
const PAGES: { key: string; title: string; sections: string[] }[] = [
  { key: "world", title: "World", sections: ["World"] },
  { key: "character", title: "Character", sections: ["Character"] },
  { key: "depth", title: "People and past", sections: ["Relationships", "Optional depth"] },
  { key: "experience", title: "Experience", sections: ["Experience"] },
];

function stepsForPage(pageIndex: number): StepDef[] {
  const page = PAGES[pageIndex];
  return page ? STEPS.filter((s) => page.sections.includes(s.section)) : [];
}

function pageIndexForStep(step: StepDef): number {
  return PAGES.findIndex((p) => p.sections.includes(step.section));
}

const DEFAULT_SETUP: CustomWorldSetup = {
  worldGenre: "modern",
  timePeriod: "world_decides",
  startingLocation: "small_settlement",
  startingRole: "local_resident",
  worldCondition: "uneasy",
  recentChange: "nothing_major",
  characterKnowledge: "basic_local_knowledge",
  consequenceSeverity: "balanced",
  settingGroundedness: "mostly_grounded",
  storyFeel: "grounded",
  want: "safety",
  fear: "failure",
  whoMatters: "nobody", // No one yet — no relationship floor
  worldElements: "",
  worldExclusions: "",
};

export function createDefaultAdvancedSetup(): CustomWorldSetup {
  return { ...DEFAULT_SETUP };
}

function optionLabel(options: SetupOption[] | undefined, value?: string) {
  return options?.find((o) => o.value === value)?.label || value || "Not set";
}

function resolvedSetup(setup: CustomWorldSetup): CustomWorldSetup {
  return { ...DEFAULT_SETUP, ...setup };
}

function omitEmptySetup(setup: CustomWorldSetup): CustomWorldSetup {
  const out: CustomWorldSetup = {};
  // Top-level mapped fields + dead controls that have no persistence consumer.
  const skipTop = new Set([
    "worldGenre",
    "customGenre",
    "storyFeel",
    "worldPace",
    "storyFocus",
    "secret",
  ]);
  for (const [key, value] of Object.entries(setup)) {
    if (skipTop.has(key)) continue;
    if (value === undefined || value === null) continue;
    if (typeof value === "string" && !value.trim()) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    (out as Record<string, unknown>)[key] = value;
  }
  // Never send secret / dead controls.
  delete out.secret;
  delete out.worldPace;
  delete (out as Record<string, unknown>).storyFocus;
  // "Let the world type decide" is the absence of a time period, so nothing is sent.
  if (out.timePeriod === "world_decides") delete out.timePeriod;
  out.creationFlow = "advanced";
  return out;
}

export function buildAdvancedStartRequest(setup: CustomWorldSetup): AdvancedStartRequest {
  const value = resolvedSetup(setup);
  const role =
    value.startingRole === "custom_role"
      ? value.customRole?.trim() || "local resident"
      : optionLabel(ROLE_OPTIONS, value.startingRole).toLowerCase();

  const genre =
    value.worldGenre === "custom"
      ? value.customGenre?.trim() || "custom world"
      : value.worldGenre || "modern";

  const tone = value.storyFeel || "grounded";

  const difficulty =
    SEVERITY_TO_DIFFICULTY[value.consequenceSeverity as keyof typeof SEVERITY_TO_DIFFICULTY] ||
    "standard";

  const recentChange =
    value.recentChange === "custom_event"
      ? value.customRecentChange?.trim()
      : optionLabel(CHANGE_OPTIONS_FIXED, value.recentChange);

  const seed = omitEmptySetup(value);

  return {
    genre,
    role,
    tone,
    difficulty,
    mode: "advanced",
    custom_premise:
      value.recentChange === "nothing_major" || !recentChange
        ? undefined
        : `The opening begins after this recent change: ${recentChange}.`,
    custom_world_setup: seed,
  };
}

type MatureKey =
  | "violence_level"
  | "horror_level"
  | "sexual_content_level"
  | "consent_boundary"
  | "player_involvement"
  | "language_level"
  | "substance_content_level";

/**
 * Plain-language copy for the 18+ rows. Each level is the most the story may
 * show. A level never forces content to appear.
 */
const MATURE_COPY: Record<MatureKey, { help: string; levels: Record<string, string> }> = {
  violence_level: {
    help: "The most detail the story may use for fights and injuries.",
    levels: {
      mild: "Fights and injuries happen and are described briefly.",
      realistic: "Injuries are described as they would really look and feel.",
      graphic: "Wounds and violence are described in detail.",
      extreme_gore: "No limit on bloody detail.",
    },
  },
  horror_level: {
    help: "How far frightening scenes may go.",
    levels: {
      atmospheric: "Unease and tension. Little is shown directly.",
      disturbing: "Upsetting scenes are shown directly.",
      graphic: "Horror is described in detail.",
      extreme_psychological_or_body_horror: "Severe psychological horror and body horror are allowed.",
    },
  },
  sexual_content_level: {
    help: "The most sexual content the story may show.",
    levels: {
      off: "No sexual content.",
      romance_only: "Romance and affection. Nothing sexual.",
      suggestive: "Sex may be implied and is never shown.",
      fade_to_black: "A scene may begin, then the story cuts away.",
      explicit: "Sexual scenes are shown.",
      graphic: "Sexual scenes are shown in full detail.",
    },
  },
  consent_boundary: {
    help: "Whether sexual content without consent may exist in the story, and how much of it is shown.",
    levels: {
      consensual_only: "Only consensual sexual content between adults.",
      coercion_referenced: "Coercion may be mentioned as something that happened. It is not shown.",
      nonconsensual_implied: "Non-consensual acts may be implied. They are not shown.",
      nonconsensual_on_screen: "Non-consensual acts may be shown.",
      graphic_nonconsensual: "Non-consensual acts may be shown in detail.",
    },
  },
  player_involvement: {
    help: "Who sexual content may involve.",
    levels: {
      npcs_only: "Other characters only. Never your character.",
      player_character: "Your character may be involved.",
      either: "Your character or other characters.",
    },
  },
  language_level: {
    help: "How strong the swearing may get.",
    levels: {
      mild: "Light swearing only.",
      strong: "Strong swearing where it fits the character.",
      unrestricted: "No limit on language.",
    },
  },
  substance_content_level: {
    help: "How drugs and alcohol may appear.",
    levels: {
      mentioned: "They exist in the background.",
      present: "Characters use them on the page.",
      graphic_and_consequential: "Use, addiction and their effects are shown in detail.",
    },
  },
};

const MATURE_ROWS: { key: MatureKey; label: string; choices: { value: string; label: string }[] }[] = [
  {
    key: "violence_level",
    label: "Violence and injury",
    choices: [
      { value: "mild", label: "Mild" },
      { value: "realistic", label: "Realistic" },
      { value: "graphic", label: "Graphic" },
      { value: "extreme_gore", label: "Extreme gore" },
    ],
  },
  {
    key: "horror_level",
    label: "Horror",
    choices: [
      { value: "atmospheric", label: "Atmospheric" },
      { value: "disturbing", label: "Disturbing" },
      { value: "graphic", label: "Graphic" },
      { value: "extreme_psychological_or_body_horror", label: "Extreme" },
    ],
  },
  {
    key: "sexual_content_level",
    label: "Sexual content",
    choices: [
      { value: "off", label: "Off" },
      { value: "romance_only", label: "Romance only" },
      { value: "suggestive", label: "Suggestive" },
      { value: "fade_to_black", label: "Fade to black" },
      { value: "explicit", label: "Explicit" },
      { value: "graphic", label: "Graphic" },
    ],
  },
  {
    key: "consent_boundary",
    label: "Consent boundaries",
    choices: [
      { value: "consensual_only", label: "Consensual only" },
      { value: "coercion_referenced", label: "Coercion may be referenced" },
      { value: "nonconsensual_implied", label: "Non-consensual may be implied" },
      { value: "nonconsensual_on_screen", label: "Non-consensual on-screen" },
      { value: "graphic_nonconsensual", label: "Graphic non-consensual" },
    ],
  },
  {
    key: "player_involvement",
    label: "Player involvement",
    choices: [
      { value: "npcs_only", label: "NPCs only" },
      { value: "player_character", label: "Player character may be involved" },
      { value: "either", label: "Either" },
    ],
  },
  {
    key: "language_level",
    label: "Strong language",
    choices: [
      { value: "mild", label: "Mild" },
      { value: "strong", label: "Strong" },
      { value: "unrestricted", label: "Unrestricted" },
    ],
  },
  {
    key: "substance_content_level",
    label: "Drug and alcohol content",
    choices: [
      { value: "mentioned", label: "Mentioned" },
      { value: "present", label: "Present" },
      { value: "graphic_and_consequential", label: "Graphic and consequential" },
    ],
  },
];

export function AdvancedBuilder({
  loading,
  fontScale,
  customSetup,
  matureContent,
  capabilities,
  onSetSetupField,
  onSetMatureContent,
  onStart,
  onChangePath,
}: AdvancedBuilderProps) {
  const [pageIndex, setPageIndex] = useState(0);
  // Answers the player set in this visit. Anything else still holds its preset value.
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set());
  const [matureExpanded, setMatureExpanded] = useState(false);
  const [hardLimitDraft, setHardLimitDraft] = useState("");
  const reviewVisible = pageIndex >= PAGES.length;
  const pageSteps = stepsForPage(Math.min(pageIndex, PAGES.length - 1));
  const setup = resolvedSetup(customSetup);
  const safeFontScale = fontScale > 0 ? fontScale : 1;
  const canStart =
    (!matureContent.adult_mode_enabled || matureContent.adult_age_confirmed) && !loading;

  const setField = (patch: Partial<CustomWorldSetup>) => {
    setTouched((prev) => new Set([...prev, ...Object.keys(patch)]));
    onSetSetupField(patch);
  };

  const isUntouchedDefault = (step: StepDef) => {
    const key = step.setupKey as keyof CustomWorldSetup;
    const preset = DEFAULT_SETUP[key];
    return Boolean(step.options && preset && !touched.has(String(key)) && setup[key] === preset);
  };

  const isStepReady = (step: StepDef) => {
    if (step.optional) return true;
    const value = String(setup[step.setupKey as keyof CustomWorldSetup] ?? "");
    if (!value) return false;
    if (step.key === "worldGenre" && value === "custom") return Boolean(setup.customGenre?.trim());
    if (step.key === "startingLocation" && value === "custom_location") {
      return Boolean(setup.customLocation?.trim());
    }
    if (step.key === "startingRole" && value === "custom_role") return Boolean(setup.customRole?.trim());
    if (step.key === "recentChange" && value === "custom_event") {
      return Boolean(setup.customRecentChange?.trim());
    }
    return true;
  };

  const pageReady = pageSteps.every(isStepReady);

  const reviewRows = STEPS.filter((s) => {
      if (!s.optional) return true;
      const v = setup[s.setupKey as keyof CustomWorldSetup];
      return Boolean(v && String(v).trim());
    }).map((s, index) => {
      let value = optionLabel(s.options, String(setup[s.setupKey as keyof CustomWorldSetup] || ""));
      if (s.key === "worldGenre" && setup.worldGenre === "custom") value = setup.customGenre || "Custom";
      if (s.key === "startingLocation" && setup.startingLocation === "custom_location") {
        value = setup.customLocation || "Custom location";
      }
      if (s.key === "startingRole" && setup.startingRole === "custom_role") {
        value = setup.customRole || "Custom role";
      }
      if (s.key === "recentChange" && setup.recentChange === "custom_event") {
        value = setup.customRecentChange || "Custom event";
      }
      if ((s.key === "worldElements" || s.key === "worldExclusions") && !String(value).trim()) {
        value = "None";
      }
      return { step: s, index: pageIndexForStep(s), value, preset: isUntouchedDefault(s) };
    });

  const addHardLimit = () => {
    const value = hardLimitDraft.trim();
    if (!value) return;
    const exists = matureContent.hard_limits.some(
      (item) => item.toLowerCase() === value.toLowerCase()
    );
    if (!exists) onSetMatureContent({ hard_limits: [...matureContent.hard_limits, value] });
    setHardLimitDraft("");
  };

  const visibleMatureRows = MATURE_ROWS.filter((row) => {
    if (["sexual_content_level", "consent_boundary", "player_involvement"].includes(row.key)) {
      return capabilities.sexual_content_available;
    }
    return true;
  });

  const choicesFor = (row: (typeof MATURE_ROWS)[number]) =>
    row.choices.filter((choice) => {
      if (row.key === "sexual_content_level" && choice.value === "graphic") {
        return capabilities.graphic_sexual_content_available;
      }
      if (row.key === "consent_boundary" && choice.value !== "consensual_only") {
        if (!capabilities.nonconsensual_content_available) return false;
        if (choice.value === "graphic_nonconsensual") {
          return capabilities.graphic_sexual_content_available;
        }
      }
      return true;
    });

  return (
    <View testID="advanced-builder-panel">
      <Text style={styles.pathLink} onPress={onChangePath} testID="advanced-change-path">
        ← Change path
      </Text>
      <Text style={styles.label}>ADVANCED BUILDER</Text>
      <Text style={[styles.heading, { fontSize: Math.round(28 * safeFontScale) }]}>
        Define starting conditions in detail.
      </Text>
      <Text style={styles.help}>
        These answers set what is already true. What happens next still emerges from people, pressure, and consequence.
      </Text>

      <View style={styles.progressWrap} testID="advanced-progress">
        <Text style={styles.progressText} testID="advanced-progress-text">
          {reviewVisible ? "Review" : `Page ${pageIndex + 1} of ${PAGES.length}`}
        </Text>
        <View style={styles.progressTrack}>
          <View
            style={[
              styles.progressFill,
              { width: `${reviewVisible ? 100 : ((pageIndex + 1) / PAGES.length) * 100}%` },
            ]}
          />
        </View>
      </View>

      {!reviewVisible ? (
        <View testID={`advanced-step-${pageIndex + 1}`}>
          <Text style={styles.sectionTag}>{PAGES[pageIndex].title.toUpperCase()}</Text>
          {pageSteps.map((step) => {
            const setupKey = step.setupKey as keyof CustomWorldSetup;
            const selectedValue = String(setup[setupKey] ?? "");
            return (
              <View key={step.key} style={styles.questionBlock} testID={`advanced-question-${step.key}`}>
                <Text style={styles.question}>{step.question}</Text>
                <Text style={styles.questionHelp}>{step.helper}</Text>
                {step.optional ? <Text style={styles.optionalText}>OPTIONAL</Text> : null}
                {isUntouchedDefault(step) ? (
                  <Text style={styles.defaultText} testID={`advanced-default-${step.key}`}>
                    PRESET. YOU HAVE NOT CHOSEN THIS YET.
                  </Text>
                ) : null}

                {step.freeText ? (
                  <TextInput
                    value={selectedValue}
                    onChangeText={(v) => setField({ [setupKey]: v })}
                    placeholder={step.placeholder}
                    placeholderTextColor={COLORS.textMuted}
                    multiline
                    style={styles.textArea}
                    testID={`advanced-input-${step.key}`}
                  />
                ) : (
                  <View style={styles.optionList}>
                    {step.options?.map((option) => {
                      const selected = selectedValue === option.value;
                      return (
                        <TouchableOpacity
                          key={`${step.key}-${option.value}-${option.label}`}
                          style={[styles.optionCard, selected && styles.optionCardSelected]}
                          onPress={() => setField({ [setupKey]: option.value })}
                          disabled={loading}
                          accessibilityState={{ selected, disabled: loading }}
                          testID={`advanced-option-${step.key}-${option.value}`}
                        >
                          <Text style={[styles.optionTitle, selected && styles.optionTitleSelected]}>
                            {option.label}
                          </Text>
                          {option.explanation ? (
                            <Text style={styles.optionExplanation}>{option.explanation}</Text>
                          ) : null}
                          {option.consequence ? (
                            <Text style={styles.optionConsequence}>{option.consequence}</Text>
                          ) : null}
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                )}

                {step.key === "worldGenre" && selectedValue === "custom" ? (
                  <>
                    <TextInput
                      value={setup.customGenre || ""}
                      onChangeText={(v) => setField({ customGenre: v })}
                      placeholder="A few words, such as haunted oil rig"
                      placeholderTextColor={COLORS.textMuted}
                      style={styles.input}
                      testID="advanced-custom-genre"
                    />
                    <Text style={styles.inputHelp}>
                      Keep this to a few words. It also becomes the story title. Put the story idea in the next box.
                    </Text>
                  </>
                ) : null}
                {step.key === "startingLocation" && selectedValue === "custom_location" ? (
                  <TextInput
                    value={setup.customLocation || ""}
                    onChangeText={(v) => setField({ customLocation: v })}
                    placeholder="Describe the starting location"
                    placeholderTextColor={COLORS.textMuted}
                    style={styles.input}
                    testID="advanced-custom-location"
                  />
                ) : null}
                {step.key === "startingRole" && selectedValue === "custom_role" ? (
                  <TextInput
                    value={setup.customRole || ""}
                    onChangeText={(v) => setField({ customRole: v })}
                    placeholder="Describe the starting role"
                    placeholderTextColor={COLORS.textMuted}
                    style={styles.input}
                    testID="advanced-custom-role"
                  />
                ) : null}
                {step.key === "recentChange" && selectedValue === "custom_event" ? (
                  <TextInput
                    value={setup.customRecentChange || ""}
                    onChangeText={(v) => setField({ customRecentChange: v })}
                    placeholder="Describe what recently changed"
                    placeholderTextColor={COLORS.textMuted}
                    style={styles.input}
                    testID="advanced-custom-event"
                  />
                ) : null}
              </View>
            );
          })}

          <View style={styles.navRow}>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={() => {
                if (pageIndex === 0) onChangePath();
                else setPageIndex((v) => Math.max(0, v - 1));
              }}
              disabled={loading}
              testID="advanced-back-button"
            >
              <Text style={styles.secondaryText}>BACK</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, !pageReady && styles.disabledButton]}
              onPress={() => pageReady && setPageIndex((v) => Math.min(PAGES.length, v + 1))}
              disabled={!pageReady || loading}
              testID="advanced-next-button"
            >
              <Text style={styles.primaryText}>
                {pageIndex === PAGES.length - 1 ? "REVIEW" : "CONTINUE"}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <View testID="advanced-review-step">
          <Text style={styles.question}>Review starting conditions.</Text>
          <Text style={styles.questionHelp}>Change any answer before creating the chronicle.</Text>
          <View style={styles.reviewList}>
            {reviewRows.map(({ step: item, index, value, preset }) => (
              <View key={item.key} style={styles.reviewRow}>
                <View style={styles.reviewBody}>
                  <Text style={styles.reviewLabel}>{item.question}</Text>
                  <Text style={styles.reviewValue} testID={`advanced-review-${item.key}`}>
                    {value}
                  </Text>
                  {preset ? (
                    <Text style={styles.defaultText} testID={`advanced-review-default-${item.key}`}>
                      PRESET. YOU DID NOT CHOOSE THIS.
                    </Text>
                  ) : null}
                </View>
                <TouchableOpacity
                  onPress={() => setPageIndex(index)}
                  disabled={loading}
                  testID={`advanced-change-${item.key}`}
                >
                  <Text style={styles.changeText}>CHANGE</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>

          {capabilities.adult_mode_available ? (
            <View style={styles.matureBox} testID="mature-content-section">
              <TouchableOpacity
                style={styles.matureHeader}
                onPress={() => setMatureExpanded((v) => !v)}
                disabled={loading}
                testID="mature-content-expand"
              >
                <View style={styles.matureHeaderText}>
                  <Text style={styles.matureTitle}>Mature Content — 18+</Text>
                  <Text style={styles.matureHelp}>
                    Optional permissions. They do not force content.
                  </Text>
                  {!capabilities.mature_renderer_configured ? (
                    <Text style={styles.matureHelp} testID="mature-renderer-unavailable">
                      Mature prose rendering is unavailable in this release. Permissions are
                      saved with the chronicle; the standard narrative is shown.
                    </Text>
                  ) : null}
                </View>
                <Ionicons
                  name={matureExpanded ? "chevron-up" : "chevron-down"}
                  size={20}
                  color={COLORS.primary}
                />
              </TouchableOpacity>

              {matureExpanded ? (
                <View testID="mature-content-controls">
                  <TouchableOpacity
                    style={styles.checkboxRow}
                    onPress={() =>
                      onSetMatureContent({
                        adult_mode_enabled: !matureContent.adult_mode_enabled,
                        adult_age_confirmed: matureContent.adult_mode_enabled
                          ? false
                          : matureContent.adult_age_confirmed,
                      })
                    }
                    testID="mature-content-enable"
                  >
                    <View
                      style={[
                        styles.checkbox,
                        matureContent.adult_mode_enabled && styles.checkboxChecked,
                      ]}
                    >
                      {matureContent.adult_mode_enabled ? (
                        <Ionicons name="checkmark" size={15} color={COLORS.background} />
                      ) : null}
                    </View>
                    <Text style={styles.checkboxLabel}>
                      Enable mature-content permissions for this chronicle
                    </Text>
                  </TouchableOpacity>

                  {matureContent.adult_mode_enabled ? (
                    <>
                      <TouchableOpacity
                        style={styles.ageConfirm}
                        onPress={() =>
                          onSetMatureContent({
                            adult_age_confirmed: !matureContent.adult_age_confirmed,
                          })
                        }
                        testID="mature-age-confirmation"
                      >
                        <View
                          style={[
                            styles.checkbox,
                            matureContent.adult_age_confirmed && styles.checkboxChecked,
                          ]}
                        >
                          {matureContent.adult_age_confirmed ? (
                            <Ionicons name="checkmark" size={15} color={COLORS.background} />
                          ) : null}
                        </View>
                        <Text style={styles.ageText}>
                          I confirm that I am at least 18 years old.
                        </Text>
                      </TouchableOpacity>
                      {!matureContent.adult_age_confirmed ? (
                        <Text style={styles.warningText}>
                          Age confirmation is required before creation.
                        </Text>
                      ) : null}

                      {visibleMatureRows.map((row) => (
                        <View key={row.key} style={styles.matureRow}>
                          <Text style={styles.matureRowLabel}>{row.label}</Text>
                          <Text style={styles.matureRowHelp}>{MATURE_COPY[row.key].help}</Text>
                          <View style={styles.chipWrap}>
                            {choicesFor(row).map((choice) => {
                              const selected = matureContent[row.key] === choice.value;
                              return (
                                <TouchableOpacity
                                  key={choice.value}
                                  style={[styles.chip, selected && styles.chipSelected]}
                                  onPress={() =>
                                    onSetMatureContent({
                                      [row.key]: choice.value,
                                    } as Partial<MatureContentPreferences>)
                                  }
                                  testID={`mature-${row.key}-${choice.value}`}
                                >
                                  <Text
                                    style={[styles.chipText, selected && styles.chipTextSelected]}
                                  >
                                    {choice.label}
                                  </Text>
                                </TouchableOpacity>
                              );
                            })}
                          </View>
                          {choicesFor(row).map((choice) => (
                            <Text
                              key={`${choice.value}-copy`}
                              style={[
                                styles.matureLevelCopy,
                                matureContent[row.key] === choice.value && styles.matureLevelCopySelected,
                              ]}
                              testID={`mature-copy-${row.key}-${choice.value}`}
                            >
                              {choice.label}: {MATURE_COPY[row.key].levels[choice.value]}
                            </Text>
                          ))}
                        </View>
                      ))}

                      <View style={styles.matureRow}>
                        <Text style={styles.matureRowLabel}>Hard limits</Text>
                        <Text style={styles.matureRowHelp}>
                          Things the story must never include, whatever the levels above say.
                        </Text>
                        <View style={styles.limitInputRow}>
                          <TextInput
                            value={hardLimitDraft}
                            onChangeText={setHardLimitDraft}
                            onSubmitEditing={addHardLimit}
                            placeholder="Add an exclusion"
                            placeholderTextColor={COLORS.textMuted}
                            style={[styles.input, styles.limitInput]}
                            testID="mature-hard-limit-input"
                          />
                          <TouchableOpacity
                            style={styles.addLimitButton}
                            onPress={addHardLimit}
                            testID="mature-hard-limit-add"
                          >
                            <Text style={styles.addLimitText}>ADD</Text>
                          </TouchableOpacity>
                        </View>
                        <View style={styles.chipWrap}>
                          {matureContent.hard_limits.map((limit, index) => (
                            <TouchableOpacity
                              key={`${limit}-${index}`}
                              style={styles.limitTag}
                              onPress={() =>
                                onSetMatureContent({
                                  hard_limits: matureContent.hard_limits.filter(
                                    (_, i) => i !== index
                                  ),
                                })
                              }
                              testID={`mature-hard-limit-${index}`}
                            >
                              <Text style={styles.limitTagText}>{limit}</Text>
                              <Ionicons name="close" size={14} color={COLORS.primary} />
                            </TouchableOpacity>
                          ))}
                        </View>
                      </View>
                    </>
                  ) : null}
                </View>
              ) : null}
            </View>
          ) : null}

          <View style={styles.navRow}>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={() => setPageIndex(PAGES.length - 1)}
              disabled={loading}
              testID="advanced-review-back"
            >
              <Text style={styles.secondaryText}>BACK</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, !canStart && styles.disabledButton]}
              onPress={onStart}
              disabled={!canStart}
              testID="begin-story-btn"
            >
              {loading ? (
                <ActivityIndicator color={COLORS.background} testID="advanced-loading-state" />
              ) : (
                <Text style={styles.primaryText}>CREATE & START</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  pathLink: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 12,
    letterSpacing: 1,
    marginBottom: 14,
  },
  label: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 3,
    marginBottom: 8,
  },
  heading: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    lineHeight: 34,
  },
  help: {
    marginTop: 10,
    marginBottom: 20,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 15,
    lineHeight: 22,
  },
  progressWrap: { marginBottom: 20 },
  progressText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 1.5,
    marginBottom: 8,
  },
  progressTrack: { height: 3, backgroundColor: COLORS.border },
  progressFill: { height: 3, backgroundColor: COLORS.primary },
  sectionTag: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 2,
    marginBottom: 8,
  },
  question: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 24,
    lineHeight: 30,
  },
  questionHelp: {
    marginTop: 8,
    marginBottom: 16,
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    fontSize: 15,
    lineHeight: 22,
  },
  optionalText: {
    alignSelf: "flex-start",
    marginBottom: 12,
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 1.5,
  },
  optionList: { gap: 10 },
  optionCard: {
    minHeight: 56,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    padding: 14,
  },
  optionCardSelected: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  optionTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 18,
  },
  optionTitleSelected: { color: COLORS.primary },
  optionExplanation: {
    marginTop: 6,
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    fontSize: 14,
    lineHeight: 19,
  },
  optionConsequence: {
    marginTop: 4,
    fontFamily: FONTS.body,
    color: COLORS.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  questionBlock: { marginBottom: 34 },
  defaultText: {
    alignSelf: "flex-start",
    marginBottom: 12,
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 10,
    letterSpacing: 1.2,
  },
  inputHelp: {
    marginTop: 6,
    fontFamily: FONTS.body,
    color: COLORS.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  input: {
    minHeight: 50,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
    color: COLORS.textPrimary,
    fontFamily: FONTS.body,
    fontSize: 15,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginTop: 12,
  },
  textArea: {
    minHeight: 120,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
    color: COLORS.textPrimary,
    fontFamily: FONTS.body,
    fontSize: 15,
    padding: 14,
    textAlignVertical: "top",
  },
  navRow: { marginTop: 22, flexDirection: "row", gap: 12 },
  secondaryButton: {
    flex: 1,
    minHeight: 52,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
    alignItems: "center",
    justifyContent: "center",
  },
  secondaryText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    letterSpacing: 1.4,
  },
  primaryButton: {
    flex: 1.4,
    minHeight: 52,
    backgroundColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 12,
  },
  disabledButton: { opacity: 0.42 },
  primaryText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.background,
    letterSpacing: 1.4,
  },
  reviewList: { gap: 9 },
  reviewRow: {
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    padding: 13,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  reviewBody: { flex: 1 },
  reviewLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 1,
    marginBottom: 4,
  },
  reviewValue: {
    fontFamily: FONTS.bodyMed,
    color: COLORS.textPrimary,
    fontSize: 15,
    lineHeight: 20,
  },
  changeText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 10,
    letterSpacing: 1,
  },
  matureBox: {
    marginTop: 20,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
    padding: 14,
  },
  matureHeader: { flexDirection: "row", alignItems: "center", gap: 12 },
  matureHeaderText: { flex: 1 },
  matureTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 19,
  },
  matureHelp: {
    marginTop: 4,
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    fontSize: 13,
    lineHeight: 18,
  },
  checkboxRow: { marginTop: 18, flexDirection: "row", alignItems: "center", gap: 11 },
  checkbox: {
    width: 24,
    height: 24,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxChecked: { borderColor: COLORS.primary, backgroundColor: COLORS.primary },
  checkboxLabel: {
    flex: 1,
    fontFamily: FONTS.bodyMed,
    color: COLORS.textPrimary,
    fontSize: 14,
    lineHeight: 19,
  },
  ageConfirm: {
    marginTop: 14,
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    padding: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  ageText: {
    flex: 1,
    fontFamily: FONTS.bodyMed,
    color: COLORS.textPrimary,
    fontSize: 14,
  },
  warningText: {
    marginTop: 8,
    fontFamily: FONTS.bodyMed,
    color: COLORS.primary,
    fontSize: 13,
  },
  matureRow: { marginTop: 20 },
  matureRowLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textPrimary,
    fontSize: 11,
    letterSpacing: 1.2,
    marginBottom: 9,
  },
  matureRowHelp: {
    marginBottom: 9,
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    fontSize: 13,
    lineHeight: 18,
  },
  matureLevelCopy: {
    marginTop: 6,
    fontFamily: FONTS.body,
    color: COLORS.textMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  matureLevelCopySelected: { color: COLORS.textPrimary },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    minHeight: 40,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingHorizontal: 11,
    paddingVertical: 9,
    justifyContent: "center",
  },
  chipSelected: { borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft },
  chipText: { fontFamily: FONTS.bodyMed, color: COLORS.textSecondary, fontSize: 13 },
  chipTextSelected: { color: COLORS.primary },
  limitInputRow: { flexDirection: "row", alignItems: "stretch", gap: 8 },
  limitInput: { flex: 1, marginTop: 10 },
  addLimitButton: {
    marginTop: 10,
    minWidth: 62,
    backgroundColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  addLimitText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.background,
    fontSize: 11,
    letterSpacing: 1,
  },
  limitTag: {
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    paddingHorizontal: 10,
    paddingVertical: 7,
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
  },
  limitTagText: { fontFamily: FONTS.bodyMed, color: COLORS.primary, fontSize: 12 },
});
