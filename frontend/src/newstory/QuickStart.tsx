import { useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../theme";
import type { CustomWorldSetup } from "../api";
import { ReviewSummary } from "./ReviewSummary";
import {
  QUICK_WORLDS,
  QUICK_CHARACTERS,
  QUICK_TONES,
  HOOK_WANT,
  HOOK_FEAR,
  HOOK_WHO_MATTERS,
  type QuickWorldValue,
  type QuickCharacterValue,
  type QuickToneValue,
  type WantValue,
  type FearValue,
  type WhoMattersValue,
} from "./options";
import type { QuickStartSelections } from "./types";

type QuickOption = {
  value: string;
  label: string;
  explanation: string;
  consequence: string;
};

type QuickStartRequest = {
  genre: string;
  role?: string;
  tone: string;
  difficulty: string;
  mode: "advanced";
  custom_world_setup: CustomWorldSetup;
};

type QuickStartProps = {
  selections: QuickStartSelections;
  loading: boolean;
  fontScale: number;
  onChange: (patch: Partial<QuickStartSelections>) => void;
  onStart: () => void;
};

type StepDefinition = {
  key: keyof Pick<
    QuickStartSelections,
    "world" | "character" | "tone" | "want" | "fear" | "whoMatters"
  >;
  label: string;
  question: string;
  helper: string;
  options: readonly QuickOption[];
};

const STEP_DEFINITIONS: StepDefinition[] = [
  {
    key: "world",
    label: "World",
    question: "Where does this story begin?",
    helper: "Choose the kind of world you want to step into.",
    options: QUICK_WORLDS,
  },
  {
    key: "character",
    label: "Character",
    question: "Who are you at the start?",
    helper: "Pick the kind of protagonist you want to inhabit.",
    options: QUICK_CHARACTERS,
  },
  {
    key: "tone",
    label: "Tone",
    question: "How should this opening feel?",
    helper: "This shapes the emotional pressure of the story.",
    options: QUICK_TONES,
  },
  {
    key: "want",
    label: "Want",
    question: "What do you want most?",
    helper: "A strong want gives the opening an immediate pull.",
    options: HOOK_WANT,
  },
  {
    key: "fear",
    label: "Fear",
    question: "What are you most afraid of?",
    helper: "Fear sharpens what every scene can threaten.",
    options: HOOK_FEAR,
  },
  {
    key: "whoMatters",
    label: "Who matters most",
    question: "Who is at the centre of it all?",
    helper: "This gives the opening a personal stake right away.",
    options: HOOK_WHO_MATTERS,
  },
] as const;

const REVIEW_ORDER = STEP_DEFINITIONS.map((step) => step.key);

function getOption(options: readonly QuickOption[], value?: string) {
  return options.find((option) => option.value === value) ?? null;
}

function getWorldOption(value?: QuickWorldValue) {
  return QUICK_WORLDS.find((option) => option.value === value) ?? null;
}

function getCharacterOption(value?: QuickCharacterValue) {
  return QUICK_CHARACTERS.find((option) => option.value === value) ?? null;
}

function getToneOption(value?: QuickToneValue) {
  return QUICK_TONES.find((option) => option.value === value) ?? null;
}

function toLowerPhrase(label?: string | null) {
  if (!label) return "";
  return label.charAt(0).toLowerCase() + label.slice(1);
}

export function isQuickStartComplete(selections: QuickStartSelections) {
  return REVIEW_ORDER.every((key) => Boolean(selections[key]));
}

export function buildQuickStartSummary(selections: QuickStartSelections) {
  if (!isQuickStartComplete(selections)) return "";

  const world = getWorldOption(selections.world);
  const character = getCharacterOption(selections.character);
  const tone = getToneOption(selections.tone);
  const want = getOption(HOOK_WANT, selections.want);
  const fear = getOption(HOOK_FEAR, selections.fear);
  const whoMatters = getOption(HOOK_WHO_MATTERS, selections.whoMatters);

  if (!world || !character || !tone || !want || !fear || !whoMatters) return "";

  const whoLine =
    whoMatters.value === "nobody"
      ? "with Nobody at the centre of everything but yourself"
      : `with your ${toLowerPhrase(whoMatters.label)} at the centre of everything`;

  return `${character.label} in a ${toLowerPhrase(world.label)} story with a ${toLowerPhrase(
    tone.label
  )} edge, driven by ${toLowerPhrase(want.label)}, haunted by ${toLowerPhrase(
    fear.label
  )}, ${whoLine}.`;
}

export function buildQuickStartRequest(
  selections: QuickStartSelections
): QuickStartRequest | null {
  if (!isQuickStartComplete(selections)) return null;

  const world = getWorldOption(selections.world);
  const character = getCharacterOption(selections.character);
  const tone = getToneOption(selections.tone);

  if (!world || !character || !tone) return null;

  const resolvedGenre =
    world.value === "random"
      ? selections.resolvedWorldGenre || "modern"
      : world.genre;

  return {
    genre: resolvedGenre,
    role: character.role || undefined,
    tone: tone.tone,
    difficulty: tone.difficulty,
    mode: "advanced",
    custom_world_setup: {
      want: selections.want,
      fear: selections.fear,
      whoMatters: selections.whoMatters,
    },
  };
}

export function QuickStart({
  selections,
  loading,
  fontScale,
  onChange,
  onStart,
}: QuickStartProps) {
  const [stepIndex, setStepIndex] = useState(0);

  const safeFontScale = fontScale > 0 ? fontScale : 1;
  const boundedStepIndex = Math.min(stepIndex, STEP_DEFINITIONS.length - 1);
  const currentStep = STEP_DEFINITIONS[boundedStepIndex];
  const currentValue = selections[currentStep.key];
  const reviewVisible = stepIndex >= STEP_DEFINITIONS.length;
  const progressStep = reviewVisible ? STEP_DEFINITIONS.length : stepIndex + 1;
  const summary = useMemo(() => buildQuickStartSummary(selections), [selections]);

  const titleSize = Math.round(30 * safeFontScale);
  const bodySize = Math.round(16 * safeFontScale);
  const helperSize = Math.round(14 * safeFontScale);
  const optionTitleSize = Math.round(20 * safeFontScale);
  const optionTextSize = Math.round(14 * safeFontScale);

  const goBack = () => {
    if (reviewVisible) {
      setStepIndex(STEP_DEFINITIONS.length - 1);
      return;
    }
    setStepIndex((prev) => Math.max(0, prev - 1));
  };

  const goForward = () => {
    if (!currentValue) return;
    setStepIndex((prev) => Math.min(STEP_DEFINITIONS.length, prev + 1));
  };

  const selectOption = (step: StepDefinition, value: string) => {
    onChange({ [step.key]: value } as Partial<QuickStartSelections>);
  };

  return (
    <View testID="quick-start-panel">
      <Text
        style={[styles.storyLabel, { fontSize: Math.max(11, Math.round(11 * safeFontScale)) }]}
        testID="quick-start-story-label"
      >
        QUICK START
      </Text>
      <Text style={[styles.heading, { fontSize: titleSize }]} testID="quick-start-heading">
        Start with a story, not a settings form.
      </Text>
      <Text style={[styles.subheading, { fontSize: helperSize }]} testID="quick-start-subheading">
        Choose a world, a protagonist, and the pressure that follows them.
      </Text>

      <View style={styles.progressWrap} testID="quick-start-progress">
        <Text style={[styles.progressText, { fontSize: Math.max(12, Math.round(12 * safeFontScale)) }]} testID="quick-start-progress-text">
          {progressStep} of {STEP_DEFINITIONS.length}
        </Text>
        <View style={styles.progressMarks}>
          {STEP_DEFINITIONS.map((step, index) => {
            const active = index < progressStep;
            return (
              <View
                key={step.key}
                style={[styles.progressMark, active && styles.progressMarkActive]}
                testID={`quick-start-progress-mark-${index + 1}`}
              />
            );
          })}
        </View>
      </View>

      {!reviewVisible ? (
        <View testID={`quick-start-step-${stepIndex + 1}`}>
          <Text style={[styles.stepText, { fontSize: Math.max(12, Math.round(12 * safeFontScale)) }]} testID="quick-start-step-label">
            {currentStep.label}
          </Text>
          <Text style={[styles.stepQuestion, { fontSize: Math.round(24 * safeFontScale) }]} testID="quick-start-step-question">
            {currentStep.question}
          </Text>
          <Text style={[styles.stepHelper, { fontSize: helperSize }]} testID="quick-start-step-helper">
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
                  testID={`quick-start-option-${currentStep.key}-${option.value}`}
                >
                  <View style={styles.optionHeader}>
                    <Text style={[styles.optionTitle, { fontSize: optionTitleSize }]}>
                      {option.label}
                    </Text>
                    {active ? (
                      <View style={styles.selectedBadge} testID={`quick-start-option-selected-${currentStep.key}-${option.value}`}>
                        <Ionicons name="checkmark-circle" size={16} color={COLORS.primary} />
                        <Text style={[styles.selectedBadgeText, { fontSize: Math.max(12, Math.round(12 * safeFontScale)) }]}>Selected</Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={[styles.optionBody, { fontSize: optionTextSize }]}>{option.explanation}</Text>
                  <Text style={[styles.optionConsequence, { fontSize: Math.max(13, Math.round(13 * safeFontScale)) }]}>
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
              testID="quick-start-back-button"
            >
              <Text style={[styles.secondaryButtonText, { fontSize: bodySize }]}>Back</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, !currentValue && styles.primaryButtonDisabled]}
              onPress={goForward}
              disabled={!currentValue || loading}
              accessibilityState={{ disabled: !currentValue || loading }}
              testID="quick-start-next-button"
            >
              <Text style={[styles.primaryButtonText, { fontSize: bodySize }]}>
                {stepIndex === STEP_DEFINITIONS.length - 1 ? "Review your start" : "Continue"}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <ReviewSummary
          testIdPrefix="quick-start"
          heading="Here’s the opening you’ve set up."
          summary={summary}
          rows={STEP_DEFINITIONS.map((step, index) => ({
            key: step.key,
            label: step.label,
            value: getOption(step.options, selections[step.key])?.label,
            onChange: () => setStepIndex(index),
          }))}
          fontScale={safeFontScale}
          loading={loading}
          onBack={goBack}
          onStart={onStart}
        />
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
});