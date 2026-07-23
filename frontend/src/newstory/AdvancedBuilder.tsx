import React, { useMemo, useState } from "react";
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
} from "./options";

type SetupOption = { value: string; label: string; explanation?: string };

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
  { value: "fantasy", label: "Fantasy" },
  { value: "horror", label: "Horror" },
  { value: "science fiction", label: "Science fiction" },
  { value: "post-apocalyptic", label: "Post-apocalyptic" },
  { value: "detective", label: "Mystery or crime" },
  { value: "modern", label: "Modern" },
  { value: "custom", label: "Custom" },
];

const LOCATION_OPTIONS: SetupOption[] = [
  { value: "small_settlement", label: "Small settlement", explanation: "A close community where shortages are hard to ignore." },
  { value: "crowded_city", label: "Crowded city", explanation: "Many people, routes, and competing needs nearby." },
  { value: "remote_wilderness", label: "Remote wilderness", explanation: "Distance and limited support shape the opening." },
  { value: "isolated_location", label: "Isolated location", explanation: "Cut off from ordinary help." },
  { value: "travelling_group", label: "Travelling group", explanation: "Already moving between places." },
  { value: "custom_location", label: "Custom location" },
];

const CONDITION_OPTIONS: SetupOption[] = [
  { value: "stable", label: "Stable" },
  { value: "uneasy", label: "Uneasy" },
  { value: "divided", label: "Fracturing" },
  { value: "collapsing", label: "Collapsing" },
];

const CHANGE_OPTIONS_FIXED: SetupOption[] = [
  { value: "nothing_major", label: "Nothing major" },
  { value: "someone_disappeared", label: "A leader disappeared" },
  { value: "resources_became_scarce", label: "An important resource became scarce" },
  { value: "conflict_intensified", label: "Violence increased" },
  { value: "disaster_occurred", label: "A route or supply line failed" },
  { value: "important_discovery", label: "Something unexplained occurred" },
  { value: "custom_event", label: "Custom" },
];

const GROUNDEDNESS_OPTIONS: SetupOption[] = [
  { value: "realistic", label: "Realistic" },
  { value: "mostly_grounded", label: "Mostly grounded" },
  { value: "openly_speculative", label: "Speculative" },
];

const ROLE_OPTIONS: SetupOption[] = [
  { value: "local_resident", label: "Local resident" },
  { value: "outsider", label: "Outsider" },
  { value: "worker_or_specialist", label: "Worker or specialist" },
  { value: "leader", label: "Leader" },
  { value: "prisoner_or_captive", label: "Prisoner or captive" },
  { value: "traveller", label: "Traveller" },
  { value: "custom_role", label: "Custom role" },
];

const KNOWLEDGE_OPTIONS: SetupOption[] = [
  { value: "very_little", label: "Very little", explanation: "Most facts must be learned in play." },
  { value: "basic_local_knowledge", label: "Basic local knowledge", explanation: "Ordinary public places and risks." },
  { value: "well_connected", label: "Well connected", explanation: "Useful contacts—not hidden truth." },
  { value: "deeply_involved", label: "Deeply involved", explanation: "You already know disputes you have lived." },
];

const STORY_FEEL: SetupOption[] = [
  { value: "hopeful", label: "Hopeful" },
  { value: "grounded", label: "Grounded" },
  { value: "grim", label: "Dark" },
  { value: "bleak", label: "Bleak" },
];

const SEVERITY: SetupOption[] = [
  { value: "forgiving", label: "Forgiving" },
  { value: "balanced", label: "Balanced" },
  { value: "severe", label: "Severe" },
  { value: "brutal", label: "Brutal" },
];

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
  { key: "worldGenre", section: "World", question: "What kind of world is this?", helper: "Compact world type—not a scenario card.", options: WORLD_GENRES, setupKey: "worldGenre" },
  { key: "startingLocation", section: "World", question: "Where does this begin?", helper: "Place and access to help.", options: LOCATION_OPTIONS, setupKey: "startingLocation" },
  { key: "worldCondition", section: "World", question: "How strained is the world?", helper: "Baseline stability—not the next cutscene.", options: CONDITION_OPTIONS, setupKey: "worldCondition" },
  { key: "recentChange", section: "World", question: "What recently shifted?", helper: "Existing disruption, not a promised event.", options: CHANGE_OPTIONS_FIXED, setupKey: "recentChange" },
  { key: "settingGroundedness", section: "World", question: "How real or strange is the setting?", helper: "Ordinary limits of this world.", options: GROUNDEDNESS_OPTIONS, setupKey: "settingGroundedness" },
  { key: "worldElements", section: "World", question: "What belongs in this world?", helper: "Optional themes or elements.", optional: true, freeText: true, placeholder: "Optional…", setupKey: "worldElements" },
  { key: "worldExclusions", section: "World", question: "What must not appear?", helper: "Optional boundaries.", optional: true, freeText: true, placeholder: "Optional…", setupKey: "worldExclusions" },
  { key: "startingRole", section: "Character", question: "Who are you at the start?", helper: "Social position when the chronicle opens.", options: ROLE_OPTIONS, setupKey: "startingRole" },
  { key: "characterKnowledge", section: "Character", question: "How much do you already know?", helper: "Only what your character knows—not hidden people or secrets.", options: KNOWLEDGE_OPTIONS, setupKey: "characterKnowledge" },
  { key: "want", section: "Character", question: "What do you want most?", helper: "Core desire.", options: HOOK_WANT.map((o) => ({ value: o.value, label: o.label })), setupKey: "want" },
  { key: "fear", section: "Character", question: "What are you most afraid of?", helper: "Core fear.", options: HOOK_FEAR.map((o) => ({ value: o.value, label: o.label })), setupKey: "fear" },
  { key: "whoMatters", section: "Relationships", question: "Who matters most to you?", helper: "An archetype only—no names.", options: HOOK_WHO_MATTERS.map((o) => ({ value: o.value, label: o.label })), setupKey: "whoMatters" },
  { key: "ghost", section: "Optional depth", question: "What past still presses?", helper: "Optional.", optional: true, options: HOOK_GHOST.map((o) => ({ value: o.value, label: o.label })), setupKey: "ghost" },
  { key: "talent", section: "Optional depth", question: "What are you unusually good at?", helper: "Optional.", optional: true, options: HOOK_TALENT.map((o) => ({ value: o.value, label: o.label })), setupKey: "talent" },
  { key: "flaw", section: "Optional depth", question: "What gets you into trouble?", helper: "Optional.", optional: true, options: HOOK_FLAW.map((o) => ({ value: o.value, label: o.label })), setupKey: "flaw" },
  { key: "line", section: "Optional depth", question: "What won’t you do?", helper: "Optional.", optional: true, options: HOOK_LINE.map((o) => ({ value: o.value, label: o.label })), setupKey: "line" },
  { key: "storyFeel", section: "Experience", question: "What should this feel like?", helper: "Tone only.", options: STORY_FEEL, setupKey: "storyFeel" },
  { key: "consequenceSeverity", section: "Experience", question: "How harsh are consequences?", helper: "Cost and recovery room.", options: SEVERITY, setupKey: "consequenceSeverity" },
];

const DEFAULT_SETUP: CustomWorldSetup = {
  worldGenre: "modern",
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

  const difficultyBySeverity = {
    forgiving: "soft",
    balanced: "standard",
    severe: "hard",
    brutal: "brutal",
  } as const;
  const difficulty =
    difficultyBySeverity[value.consequenceSeverity as keyof typeof difficultyBySeverity] ||
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
  const [stepIndex, setStepIndex] = useState(0);
  const [matureExpanded, setMatureExpanded] = useState(false);
  const [hardLimitDraft, setHardLimitDraft] = useState("");
  const reviewVisible = stepIndex >= STEPS.length;
  const step = STEPS[Math.min(stepIndex, STEPS.length - 1)];
  const setup = resolvedSetup(customSetup);
  const safeFontScale = fontScale > 0 ? fontScale : 1;
  const canStart =
    (!matureContent.adult_mode_enabled || matureContent.adult_age_confirmed) && !loading;

  const setupKey = step.setupKey as keyof CustomWorldSetup;
  const selectedValue = String(setup[setupKey] ?? "");

  const customRequired =
    (step.key === "worldGenre" && selectedValue === "custom" && !setup.customGenre?.trim()) ||
    (step.key === "startingLocation" &&
      selectedValue === "custom_location" &&
      !setup.customLocation?.trim()) ||
    (step.key === "startingRole" && selectedValue === "custom_role" && !setup.customRole?.trim()) ||
    (step.key === "recentChange" &&
      selectedValue === "custom_event" &&
      !setup.customRecentChange?.trim());

  const stepReady = Boolean(step.optional || (selectedValue && !customRequired));

  const reviewRows = useMemo(() => {
    return STEPS.filter((s) => {
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
      return { step: s, index: STEPS.indexOf(s), value };
    });
  }, [setup]);

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
          {reviewVisible ? "Review" : `${stepIndex + 1} of ${STEPS.length}`}
        </Text>
        <View style={styles.progressTrack}>
          <View
            style={[
              styles.progressFill,
              { width: `${reviewVisible ? 100 : ((stepIndex + 1) / STEPS.length) * 100}%` },
            ]}
          />
        </View>
      </View>

      {!reviewVisible ? (
        <View testID={`advanced-step-${stepIndex + 1}`}>
          <Text style={styles.sectionTag}>{step.section.toUpperCase()}</Text>
          <Text style={styles.question}>{step.question}</Text>
          <Text style={styles.questionHelp}>{step.helper}</Text>
          {step.optional ? <Text style={styles.optionalText}>OPTIONAL</Text> : null}

          {step.freeText ? (
            <TextInput
              value={selectedValue}
              onChangeText={(v) => onSetSetupField({ [setupKey]: v })}
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
                    onPress={() => onSetSetupField({ [setupKey]: option.value })}
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
                  </TouchableOpacity>
                );
              })}
            </View>
          )}

          {step.key === "worldGenre" && selectedValue === "custom" ? (
            <TextInput
              value={setup.customGenre || ""}
              onChangeText={(v) => onSetSetupField({ customGenre: v })}
              placeholder="Describe the world type"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              testID="advanced-custom-genre"
            />
          ) : null}
          {step.key === "startingLocation" && selectedValue === "custom_location" ? (
            <TextInput
              value={setup.customLocation || ""}
              onChangeText={(v) => onSetSetupField({ customLocation: v })}
              placeholder="Describe the starting location"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              testID="advanced-custom-location"
            />
          ) : null}
          {step.key === "startingRole" && selectedValue === "custom_role" ? (
            <TextInput
              value={setup.customRole || ""}
              onChangeText={(v) => onSetSetupField({ customRole: v })}
              placeholder="Describe the starting role"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              testID="advanced-custom-role"
            />
          ) : null}
          {step.key === "recentChange" && selectedValue === "custom_event" ? (
            <TextInput
              value={setup.customRecentChange || ""}
              onChangeText={(v) => onSetSetupField({ customRecentChange: v })}
              placeholder="Describe what recently changed"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              testID="advanced-custom-event"
            />
          ) : null}

          <View style={styles.navRow}>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={() => {
                if (stepIndex === 0) onChangePath();
                else setStepIndex((v) => Math.max(0, v - 1));
              }}
              disabled={loading}
              testID="advanced-back-button"
            >
              <Text style={styles.secondaryText}>BACK</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, !stepReady && styles.disabledButton]}
              onPress={() =>
                stepReady && setStepIndex((v) => Math.min(STEPS.length, v + 1))
              }
              disabled={!stepReady || loading}
              testID="advanced-next-button"
            >
              <Text style={styles.primaryText}>
                {stepIndex === STEPS.length - 1 ? "REVIEW" : "CONTINUE"}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <View testID="advanced-review-step">
          <Text style={styles.question}>Review starting conditions.</Text>
          <Text style={styles.questionHelp}>Change any answer before creating the chronicle.</Text>
          <View style={styles.reviewList}>
            {reviewRows.map(({ step: item, index, value }) => (
              <View key={item.key} style={styles.reviewRow}>
                <View style={styles.reviewBody}>
                  <Text style={styles.reviewLabel}>{item.question}</Text>
                  <Text style={styles.reviewValue} testID={`advanced-review-${item.key}`}>
                    {value}
                  </Text>
                </View>
                <TouchableOpacity
                  onPress={() => setStepIndex(index)}
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
                        </View>
                      ))}

                      <View style={styles.matureRow}>
                        <Text style={styles.matureRowLabel}>Hard limits</Text>
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
              onPress={() => setStepIndex(STEPS.length - 1)}
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
