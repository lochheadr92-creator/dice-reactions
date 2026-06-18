import { useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../theme";
import type { CustomWorldSetup } from "../api";
import {
  GUIDED_WORLDS,
  GUIDED_QUESTIONS,
  QUICK_CHARACTERS,
  QUICK_TONES,
  HOOK_WANT,
  HOOK_FEAR,
  HOOK_WHO_MATTERS,
  STORY_DIFFICULTIES,
  type GuidedWorldValue,
  type QuickCharacterValue,
  type QuickToneValue,
  type WantValue,
  type FearValue,
  type WhoMattersValue,
  type StoryDifficultyValue,
  type GuidedQuestion,
} from "./options";

type GuidedOption = {
  value: string;
  label: string;
  explanation: string;
  consequence: string;
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

type GuidedStartRequest = {
  genre: string;
  role?: string;
  tone: string;
  difficulty: StoryDifficultyValue;
  mode: "advanced";
  custom_premise?: string;
  custom_world_setup: CustomWorldSetup;
};

type GuidedStartProps = {
  selections: GuidedStartSelections;
  loading: boolean;
  fontScale: number;
  onChange: (patch: Partial<GuidedStartSelections>) => void;
  onStart: () => void;
};

type GuidedStepKey =
  | "world"
  | "worldDetail"
  | "character"
  | "tone"
  | "want"
  | "fear"
  | "whoMatters"
  | "difficulty";

type GuidedStepDefinition = {
  key: GuidedStepKey;
  label: string;
  question: string;
  helper: string;
  options: readonly GuidedOption[];
};

const BASE_STEPS: GuidedStepDefinition[] = [
  {
    key: "world",
    label: "World",
    question: "What kind of story world are you stepping into?",
    helper: "Pick the setting first. Guided Start will shape the opening around it.",
    options: GUIDED_WORLDS,
  },
  {
    key: "character",
    label: "Character",
    question: "Who do you begin as?",
    helper: "Choose the role you want to carry into the first scene.",
    options: QUICK_CHARACTERS,
  },
  {
    key: "tone",
    label: "Tone",
    question: "What kind of emotional atmosphere do you want?",
    helper: "This sets how harsh, hopeful, or grim the opening feels.",
    options: QUICK_TONES,
  },
  {
    key: "want",
    label: "Want",
    question: "What is pulling you forward?",
    helper: "Choose the thing your character wants badly enough to chase.",
    options: HOOK_WANT,
  },
  {
    key: "fear",
    label: "Fear",
    question: "What could break you if it came true?",
    helper: "Fear shapes what every scene can threaten.",
    options: HOOK_FEAR,
  },
  {
    key: "whoMatters",
    label: "Who matters most",
    question: "Who keeps this personal?",
    helper: "Pick the person who gives the stakes a human centre.",
    options: HOOK_WHO_MATTERS,
  },
  {
    key: "difficulty",
    label: "Intensity",
    question: "How unforgiving should this chronicle feel?",
    helper: "Choose how much mercy the world gives you.",
    options: STORY_DIFFICULTIES,
  },
] as const;

const REVIEW_ORDER: GuidedStepKey[] = [
  "world",
  "worldDetail",
  "character",
  "tone",
  "want",
  "fear",
  "whoMatters",
  "difficulty",
];

function getOption(options: readonly GuidedOption[], value?: string) {
  return options.find((option) => option.value === value) ?? null;
}

function getWorldOption(value?: GuidedWorldValue) {
  return GUIDED_WORLDS.find((option) => option.value === value) ?? null;
}

function getCharacterOption(value?: QuickCharacterValue) {
  return QUICK_CHARACTERS.find((option) => option.value === value) ?? null;
}

function getToneOption(value?: QuickToneValue) {
  return QUICK_TONES.find((option) => option.value === value) ?? null;
}

function getWorldDetailQuestion(world?: GuidedWorldValue): GuidedQuestion | null {
  if (!world) return null;
  return GUIDED_QUESTIONS[world] ?? null;
}

function toLowerPhrase(label?: string | null) {
  if (!label) return "";
  return label.charAt(0).toLowerCase() + label.slice(1);
}

function buildGuidedSteps(selections: GuidedStartSelections): GuidedStepDefinition[] {
  const detailQuestion = getWorldDetailQuestion(selections.world);
  const detailStep = detailQuestion
    ? {
        key: "worldDetail" as const,
        label: "World turning point",
        question: detailQuestion.question,
        helper: "This choice gives your opening a sharper source of pressure.",
        options: detailQuestion.options,
      }
    : null;

  return detailStep ? [BASE_STEPS[0], detailStep, ...BASE_STEPS.slice(1)] : [...BASE_STEPS];
}

function isValueSelected(stepKey: GuidedStepKey, selections: GuidedStartSelections) {
  return Boolean(selections[stepKey]);
}

export function isGuidedStartComplete(selections: GuidedStartSelections) {
  return REVIEW_ORDER.every((key) => isValueSelected(key, selections));
}

function buildGuidedPremise(selections: GuidedStartSelections) {
  const world = getWorldOption(selections.world);
  const detailQuestion = getWorldDetailQuestion(selections.world);
  const detail = detailQuestion
    ? getOption(detailQuestion.options, selections.worldDetail)
    : null;

  if (!world || !detailQuestion || !detail) return undefined;

  return `${world.label}: ${detail.label}. ${detail.explanation}`;
}

export function buildGuidedStartSummary(selections: GuidedStartSelections) {
  if (!isGuidedStartComplete(selections)) return "";

  const world = getWorldOption(selections.world);
  const detail = getOption(getWorldDetailQuestion(selections.world)?.options || [], selections.worldDetail);
  const character = getCharacterOption(selections.character);
  const tone = getToneOption(selections.tone);
  const want = getOption(HOOK_WANT, selections.want);
  const fear = getOption(HOOK_FEAR, selections.fear);
  const whoMatters = getOption(HOOK_WHO_MATTERS, selections.whoMatters);
  const difficulty = getOption(STORY_DIFFICULTIES, selections.difficulty);

  if (!world || !detail || !character || !tone || !want || !fear || !whoMatters || !difficulty) {
    return "";
  }

  const whoLine =
    whoMatters.value === "nobody"
      ? "with no one left to lean on"
      : `with your ${toLowerPhrase(whoMatters.label)} bound up in what happens next`;

  return `${character.label} in a ${toLowerPhrase(world.label)} chronicle where ${toLowerPhrase(
    detail.label
  )}, carrying a ${toLowerPhrase(tone.label)} mood, chasing ${toLowerPhrase(
    want.label
  )}, dreading ${toLowerPhrase(fear.label)}, ${whoLine}. The world will feel ${toLowerPhrase(
    difficulty.label
  )}.`;
}

export function buildGuidedStartRequest(
  selections: GuidedStartSelections
): GuidedStartRequest | null {
  if (!isGuidedStartComplete(selections)) return null;

  const world = getWorldOption(selections.world);
  const character = getCharacterOption(selections.character);
  const tone = getToneOption(selections.tone);

  if (!world || !character || !tone || !selections.difficulty) return null;

  return {
    genre: world.genre,
    role: character.role || undefined,
    tone: tone.tone,
    difficulty: selections.difficulty,
    mode: "advanced",
    custom_premise: buildGuidedPremise(selections),
    custom_world_setup: {
      want: selections.want,
      fear: selections.fear,
      whoMatters: selections.whoMatters,
    },
  };
}

export function GuidedStart({
  selections,
  loading,
  fontScale,
  onChange,
  onStart,
}: GuidedStartProps) {
  const [stepIndex, setStepIndex] = useState(0);

  const safeFontScale = fontScale > 0 ? fontScale : 1;
  const steps = useMemo(() => buildGuidedSteps(selections), [selections]);
  const boundedStepIndex = Math.min(stepIndex, steps.length - 1);
  const currentStep = steps[boundedStepIndex];
  const currentValue = selections[currentStep.key];
  const reviewVisible = stepIndex >= steps.length;
  const progressStep = reviewVisible ? steps.length : stepIndex + 1;
  const summary = useMemo(() => buildGuidedStartSummary(selections), [selections]);

  const titleSize = Math.round(30 * safeFontScale);
  const bodySize = Math.round(16 * safeFontScale);
  const helperSize = Math.round(14 * safeFontScale);
  const optionTitleSize = Math.round(20 * safeFontScale);
  const optionTextSize = Math.round(14 * safeFontScale);

  const goBack = () => {
    if (reviewVisible) {
      setStepIndex(steps.length - 1);
      return;
    }
    setStepIndex((prev) => Math.max(0, prev - 1));
  };

  const goForward = () => {
    if (!currentValue) return;
    setStepIndex((prev) => Math.min(steps.length, prev + 1));
  };

  const selectOption = (step: GuidedStepDefinition, value: string) => {
    onChange({ [step.key]: value } as Partial<GuidedStartSelections>);
  };

  return (
    <View testID="guided-start-panel">
      <Text
        style={[styles.storyLabel, { fontSize: Math.max(11, Math.round(11 * safeFontScale)) }]}
        testID="guided-start-story-label"
      >
        GUIDED START
      </Text>
      <Text style={[styles.heading, { fontSize: titleSize }]} testID="guided-start-heading">
        Shape a richer opening, one clear choice at a time.
      </Text>
      <Text style={[styles.subheading, { fontSize: helperSize }]} testID="guided-start-subheading">
        Guided Start keeps everything curated, but lets you define the pressure more precisely.
      </Text>

      <View style={styles.progressWrap} testID="guided-start-progress">
        <Text
          style={[styles.progressText, { fontSize: Math.max(12, Math.round(12 * safeFontScale)) }]}
          testID="guided-start-progress-text"
        >
          {progressStep} of {steps.length}
        </Text>
        <View style={styles.progressMarks}>
          {steps.map((step, index) => {
            const active = index < progressStep;
            return (
              <View
                key={step.key}
                style={[styles.progressMark, active && styles.progressMarkActive]}
                testID={`guided-start-progress-mark-${index + 1}`}
              />
            );
          })}
        </View>
      </View>

      {!reviewVisible ? (
        <View testID={`guided-start-step-${boundedStepIndex + 1}`}>
          <Text
            style={[styles.stepText, { fontSize: Math.max(12, Math.round(12 * safeFontScale)) }]}
            testID="guided-start-step-label"
          >
            {currentStep.label}
          </Text>
          <Text
            style={[styles.stepQuestion, { fontSize: Math.round(24 * safeFontScale) }]}
            testID="guided-start-step-question"
          >
            {currentStep.question}
          </Text>
          <Text
            style={[styles.stepHelper, { fontSize: helperSize }]}
            testID="guided-start-step-helper"
          >
            {currentStep.helper}
          </Text>

          <View style={styles.optionList}>
            {currentStep.options.map((option) => {
              const active = currentValue === option.value;
              return (
                <TouchableOpacity
                  key={option.value}
                  style={[
                    styles.optionCard,
                    active && styles.optionCardActive,
                    { minHeight: Math.max(120, Math.round(120 * safeFontScale)) },
                  ]}
                  activeOpacity={0.85}
                  onPress={() => selectOption(currentStep, option.value)}
                  accessibilityRole="button"
                  accessibilityLabel={`${currentStep.label}: ${option.label}`}
                  accessibilityState={{ selected: active, disabled: loading }}
                  disabled={loading}
                  testID={`guided-start-option-${currentStep.key}-${option.value}`}
                >
                  <View style={styles.optionHeader}>
                    <Text style={[styles.optionTitle, { fontSize: optionTitleSize }]}>
                      {option.label}
                    </Text>
                    {active ? (
                      <View
                        style={styles.selectedBadge}
                        testID={`guided-start-option-selected-${currentStep.key}-${option.value}`}
                      >
                        <Ionicons name="checkmark-circle" size={16} color={COLORS.primary} />
                        <Text
                          style={[
                            styles.selectedBadgeText,
                            { fontSize: Math.max(12, Math.round(12 * safeFontScale)) },
                          ]}
                        >
                          Selected
                        </Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={[styles.optionBody, { fontSize: optionTextSize }]}>{option.explanation}</Text>
                  <Text
                    style={[
                      styles.optionConsequence,
                      { fontSize: Math.max(13, Math.round(13 * safeFontScale)) },
                    ]}
                  >
                    {option.consequence}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <View style={styles.navRow}>
            <TouchableOpacity
              style={[styles.secondaryButton, stepIndex === 0 && styles.secondaryButtonHidden]}
              onPress={goBack}
              disabled={stepIndex === 0 || loading}
              testID="guided-start-back-button"
            >
              <Text style={[styles.secondaryButtonText, { fontSize: bodySize }]}>Back</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, !currentValue && styles.primaryButtonDisabled]}
              onPress={goForward}
              disabled={!currentValue || loading}
              accessibilityState={{ disabled: !currentValue || loading }}
              testID="guided-start-next-button"
            >
              <Text style={[styles.primaryButtonText, { fontSize: bodySize }]}>Continue</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <View testID="guided-start-review-step">
          <Text
            style={[styles.stepText, { fontSize: Math.max(12, Math.round(12 * safeFontScale)) }]}
            testID="guided-start-review-label"
          >
            Review
          </Text>
          <Text style={[styles.stepQuestion, { fontSize: Math.round(24 * safeFontScale) }]}>
            Here’s the chronicle you’ve set in motion.
          </Text>
          <Text
            style={[styles.reviewSummary, { fontSize: Math.max(18, Math.round(18 * safeFontScale)) }]}
            testID="guided-start-review-summary"
          >
            {summary}
          </Text>

          <View style={styles.reviewList}>
            {steps.map((step, index) => {
              const selected = getOption(step.options, selections[step.key]);
              return (
                <View key={step.key} style={styles.reviewRow} testID={`guided-start-review-row-${step.key}`}>
                  <View style={styles.reviewTextWrap}>
                    <Text
                      style={[styles.reviewLabel, { fontSize: Math.max(12, Math.round(12 * safeFontScale)) }]}
                    >
                      {step.label}
                    </Text>
                    <Text
                      style={[styles.reviewValue, { fontSize: Math.round(17 * safeFontScale) }]}
                      testID={`guided-start-review-value-${step.key}`}
                    >
                      {selected?.label}
                    </Text>
                  </View>
                  <TouchableOpacity
                    style={styles.reviewChangeButton}
                    onPress={() => setStepIndex(index)}
                    testID={`guided-start-change-${step.key}`}
                  >
                    <Text
                      style={[
                        styles.reviewChangeText,
                        { fontSize: Math.max(12, Math.round(12 * safeFontScale)) },
                      ]}
                    >
                      Change
                    </Text>
                  </TouchableOpacity>
                </View>
              );
            })}
          </View>

          <View style={styles.navRow}>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={goBack}
              disabled={loading}
              testID="guided-start-review-back-button"
            >
              <Text style={[styles.secondaryButtonText, { fontSize: bodySize }]}>Back</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, loading && styles.primaryButtonDisabled]}
              onPress={onStart}
              disabled={loading}
              accessibilityRole="button"
              accessibilityState={{ disabled: loading, busy: loading }}
              accessibilityLabel={loading ? "Starting your chronicle" : "Start chronicle"}
              testID="guided-start-start-button"
            >
              {loading ? (
                <View style={styles.loadingRow} testID="guided-start-loading-state">
                  <ActivityIndicator color={COLORS.background} />
                  <Text
                    style={[
                      styles.primaryButtonText,
                      { fontSize: bodySize, color: COLORS.background },
                    ]}
                  >
                    Starting your chronicle…
                  </Text>
                </View>
              ) : (
                <Text style={[styles.primaryButtonText, { fontSize: bodySize }]}>Start chronicle</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  storyLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    letterSpacing: 3,
    marginBottom: 10,
  },
  heading: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    lineHeight: 34,
  },
  subheading: {
    marginTop: 8,
    marginBottom: 24,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    lineHeight: 22,
  },
  progressWrap: {
    marginBottom: 22,
    gap: 10,
  },
  progressText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    letterSpacing: 2,
  },
  progressMarks: {
    flexDirection: "row",
    gap: 8,
  },
  progressMark: {
    flex: 1,
    height: 6,
    borderRadius: 999,
    backgroundColor: COLORS.borderDim,
  },
  progressMarkActive: {
    backgroundColor: COLORS.primary,
  },
  stepText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    letterSpacing: 2,
    marginBottom: 8,
  },
  stepQuestion: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    lineHeight: 30,
  },
  stepHelper: {
    marginTop: 8,
    marginBottom: 18,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    lineHeight: 20,
  },
  optionList: {
    gap: 12,
  },
  optionCard: {
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    padding: 16,
  },
  optionCardActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  optionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  optionTitle: {
    flex: 1,
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
  },
  selectedBadge: {
    minHeight: 28,
    paddingHorizontal: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: COLORS.primary,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  selectedBadgeText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    letterSpacing: 1,
  },
  optionBody: {
    marginTop: 10,
    fontFamily: FONTS.bodyMed,
    color: COLORS.textProse,
    lineHeight: 20,
  },
  optionConsequence: {
    marginTop: 12,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    lineHeight: 20,
  },
  navRow: {
    marginTop: 22,
    flexDirection: "row",
    gap: 12,
  },
  secondaryButton: {
    flex: 1,
    minHeight: 54,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 12,
  },
  secondaryButtonHidden: {
    opacity: 0.25,
  },
  secondaryButtonText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    letterSpacing: 1.5,
  },
  primaryButton: {
    flex: 1.4,
    minHeight: 54,
    backgroundColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 12,
  },
  primaryButtonDisabled: {
    opacity: 0.45,
  },
  primaryButtonText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.background,
    letterSpacing: 1.5,
  },
  reviewSummary: {
    marginTop: 8,
    marginBottom: 22,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textProse,
    lineHeight: 26,
  },
  reviewList: {
    gap: 12,
  },
  reviewRow: {
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  reviewTextWrap: {
    flex: 1,
  },
  reviewLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    letterSpacing: 1.5,
    marginBottom: 4,
  },
  reviewValue: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
  },
  reviewChangeButton: {
    minWidth: 74,
    minHeight: 44,
    borderWidth: 1,
    borderColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 10,
  },
  reviewChangeText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    letterSpacing: 1.2,
  },
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
});