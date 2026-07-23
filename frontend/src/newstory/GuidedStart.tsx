import { useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from "react-native";
import { COLORS, FONTS } from "../theme";
import type { CustomWorldSetup } from "../api";
import { ReviewSummary } from "./ReviewSummary";
import { HOOK_FEAR } from "./options";
import type {
  GuidedDesireValue,
  GuidedExperienceValue,
  GuidedPressureValue,
  GuidedRoleValue,
  GuidedStartSelections,
  GuidedWhoMattersValue,
  GuidedWorldValue,
} from "./types";

type GuidedOption = {
  value: string;
  label: string;
  explanation?: string;
};

type GuidedStartRequest = {
  genre: string;
  role: string;
  tone: string;
  difficulty: string;
  mode: "advanced";
  custom_world_setup: CustomWorldSetup;
};

type GuidedStartProps = {
  selections: GuidedStartSelections;
  loading: boolean;
  fontScale: number;
  onChange: (patch: Partial<GuidedStartSelections>) => void;
  onStart: () => void;
  onChangePath: () => void;
};

type GuidedStepKey =
  | "world"
  | "role"
  | "pressure"
  | "want"
  | "fear"
  | "whoMatters"
  | "experience";

const GUIDED_WORLDS: { value: GuidedWorldValue; label: string; genre: string }[] = [
  { value: "fantasy", label: "Fantasy", genre: "fantasy" },
  { value: "horror", label: "Horror", genre: "horror" },
  { value: "science-fiction", label: "Science fiction", genre: "science fiction" },
  { value: "post-apocalyptic", label: "Post-apocalyptic", genre: "post-apocalyptic" },
  { value: "mystery-crime", label: "Mystery or crime", genre: "detective" },
  { value: "modern", label: "Modern and grounded", genre: "modern" },
  { value: "surprise", label: "Surprise me", genre: "" },
];

const CONCRETE_GENRES = GUIDED_WORLDS.filter((w) => w.value !== "surprise").map((w) => w.genre);

const GUIDED_ROLES: { value: GuidedRoleValue; label: string; role: string }[] = [
  { value: "survivor", label: "Survivor", role: "a hardened survivor" },
  { value: "wanderer", label: "Wanderer", role: "a rootless wanderer" },
  { value: "investigator", label: "Investigator", role: "an investigator" },
  { value: "soldier", label: "Soldier", role: "a soldier" },
  { value: "outcast", label: "Outcast", role: "an outcast" },
  { value: "scholar", label: "Scholar", role: "a scholar" },
  { value: "worker", label: "Worker", role: "a practical worker" },
  { value: "local", label: "Local resident", role: "a local resident" },
];

const GUIDED_PRESSURES: { value: GuidedPressureValue; label: string }[] = [
  { value: "scarcity", label: "Scarcity" },
  { value: "violence", label: "Violence" },
  { value: "isolation", label: "Isolation" },
  { value: "betrayal", label: "Betrayal" },
  { value: "illness", label: "Illness or injury" },
  { value: "authority", label: "Authority tightening" },
  { value: "unknown", label: "The unknown closing in" },
];

const GUIDED_DESIRES: { value: GuidedDesireValue; label: string }[] = [
  { value: "safety", label: "Safety" },
  { value: "freedom", label: "Freedom" },
  { value: "redemption", label: "Redemption" },
  { value: "knowledge", label: "Knowledge" },
  { value: "revenge", label: "Revenge" },
  { value: "justice", label: "Justice" },
];

const GUIDED_WHO: { value: GuidedWhoMattersValue; label: string }[] = [
  { value: "family-member", label: "A family member" },
  { value: "friend", label: "A close friend" },
  { value: "partner", label: "A partner" },
  { value: "mentor", label: "A mentor" },
  { value: "someone-depending", label: "Someone depending on me" },
  { value: "someone-failed", label: "Someone I failed" },
  { value: "nobody", label: "No one yet" },
];

const GUIDED_EXPERIENCE: {
  value: GuidedExperienceValue;
  label: string;
  tone: string;
  difficulty: string;
  explanation: string;
}[] = [
  { value: "hopeful", label: "Hopeful", tone: "hopeful", difficulty: "soft", explanation: "More room to recover." },
  { value: "balanced", label: "Balanced", tone: "grounded", difficulty: "standard", explanation: "Fair pressure and cost." },
  { value: "dark", label: "Dark", tone: "grim", difficulty: "hard", explanation: "Colder world, sharper setbacks." },
  { value: "brutal", label: "Brutal", tone: "bleak", difficulty: "brutal", explanation: "Little mercy; damage lasts." },
];

const STEPS: {
  key: GuidedStepKey;
  label: string;
  question: string;
  helper: string;
  options: GuidedOption[];
}[] = [
  {
    key: "world",
    label: "World",
    question: "What kind of world is this?",
    helper: "Choose the broad setting. Local details and people emerge during play.",
    options: GUIDED_WORLDS.map((o) => ({ value: o.value, label: o.label })),
  },
  {
    key: "role",
    label: "Role",
    question: "Who are you in this world?",
    helper: "Your practical position when the story begins, not a promised destiny.",
    options: GUIDED_ROLES.map((o) => ({ value: o.value, label: o.label })),
  },
  {
    key: "pressure",
    label: "Pressure",
    question: "What pressure is closest to you?",
    helper: "Instability already near you. This establishes a condition, not a guaranteed scene.",
    options: GUIDED_PRESSURES.map((o) => ({ value: o.value, label: o.label })),
  },
  {
    key: "want",
    label: "Desire",
    question: "What do you want most right now?",
    helper: "What you are willing to spend effort, safety or trust to gain.",
    options: GUIDED_DESIRES.map((o) => ({ value: o.value, label: o.label })),
  },
  {
    key: "fear",
    label: "Fear",
    question: "What are you most afraid of?",
    helper: "What the world can use against you.",
    options: HOOK_FEAR.map((o) => ({ value: o.value, label: o.label, explanation: o.explanation })),
  },
  {
    key: "whoMatters",
    label: "Relationship",
    question: "Who matters most to you?",
    helper: "A kind of bond—or no one yet. The story will name people only when you meet them.",
    options: GUIDED_WHO.map((o) => ({ value: o.value, label: o.label })),
  },
  {
    key: "experience",
    label: "Experience",
    question: "What kind of experience do you want?",
    helper: "How merciful the world is, and how it feels.",
    options: GUIDED_EXPERIENCE.map((o) => ({
      value: o.value,
      label: o.label,
      explanation: o.explanation,
    })),
  },
];

function labelFor(key: GuidedStepKey, value?: string): string {
  const step = STEPS.find((s) => s.key === key);
  return step?.options.find((o) => o.value === value)?.label || value || "Not set";
}

function resolveGenre(selections: GuidedStartSelections): string | undefined {
  if (selections.resolvedGenre) return selections.resolvedGenre;
  if (!selections.world) return undefined;
  if (selections.world === "surprise") return undefined;
  return GUIDED_WORLDS.find((w) => w.value === selections.world)?.genre;
}

/** Resolve Surprise me once; returns patch to merge into draft. */
export function resolveGuidedWorldSelection(
  selections: GuidedStartSelections,
  world: GuidedWorldValue,
  randomIndex?: number
): Partial<GuidedStartSelections> {
  if (world !== "surprise") {
    const genre = GUIDED_WORLDS.find((w) => w.value === world)?.genre;
    return { world, resolvedGenre: genre };
  }
  // Keep existing resolution if surprise already resolved for this draft.
  if (selections.world === "surprise" && selections.resolvedGenre) {
    return { world: "surprise", resolvedGenre: selections.resolvedGenre };
  }
  const idx =
    typeof randomIndex === "number" && Number.isFinite(randomIndex)
      ? Math.abs(Math.floor(randomIndex)) % CONCRETE_GENRES.length
      : Math.floor(Math.random() * CONCRETE_GENRES.length);
  return { world: "surprise", resolvedGenre: CONCRETE_GENRES[idx] };
}

export function isGuidedStartComplete(selections: GuidedStartSelections): boolean {
  const genre = resolveGenre(selections);
  return Boolean(
    selections.world &&
      genre &&
      selections.role &&
      selections.pressure &&
      selections.want &&
      selections.fear &&
      selections.whoMatters &&
      selections.experience
  );
}

export function buildGuidedStartSummary(selections: GuidedStartSelections): string {
  if (!isGuidedStartComplete(selections)) return "";
  const worldLabel =
    selections.world === "surprise"
      ? `Surprise (${labelForGenre(selections.resolvedGenre)})`
      : labelFor("world", selections.world);
  const who =
    selections.whoMatters === "nobody"
      ? "no one yet binding the stakes"
      : labelFor("whoMatters", selections.whoMatters).toLowerCase();
  return `${labelFor("role", selections.role)} in a ${worldLabel.toLowerCase()} world, under ${labelFor(
    "pressure",
    selections.pressure
  ).toLowerCase()} pressure, chasing ${labelFor("want", selections.want).toLowerCase()}, fearing ${labelFor(
    "fear",
    selections.fear
  ).toLowerCase()}, with ${who}. Experience: ${labelFor("experience", selections.experience)}.`;
}

function labelForGenre(genre?: string): string {
  if (!genre) return "Unknown";
  const hit = GUIDED_WORLDS.find((w) => w.genre === genre);
  return hit?.label || genre;
}

export function buildGuidedStartRequest(
  selections: GuidedStartSelections
): GuidedStartRequest | null {
  if (!isGuidedStartComplete(selections)) return null;
  const genre = resolveGenre(selections);
  const roleRow = GUIDED_ROLES.find((r) => r.value === selections.role);
  const exp = GUIDED_EXPERIENCE.find((e) => e.value === selections.experience);
  if (!genre || !roleRow || !exp || !selections.pressure || !selections.want || !selections.fear || !selections.whoMatters) {
    return null;
  }

  const setup: CustomWorldSetup = {
    creationFlow: "guided",
    want: selections.want,
    fear: selections.fear,
    whoMatters: selections.whoMatters,
    // Exactly one selected pressure — seeds pressure_graph on the backend.
    pressures: [selections.pressure],
  };

  return {
    // Concrete genre (Surprise me is frozen in resolvedGenre before submit).
    genre,
    role: roleRow.role,
    // Experience splits into presentation (tone) vs consequence policy (difficulty).
    tone: exp.tone,
    difficulty: exp.difficulty,
    mode: "advanced",
    custom_world_setup: setup,
  };
}

export function GuidedStart({
  selections,
  loading,
  fontScale,
  onChange,
  onStart,
  onChangePath,
}: GuidedStartProps) {
  const [stepIndex, setStepIndex] = useState(0);
  const safeFontScale = fontScale > 0 ? fontScale : 1;
  const reviewVisible = stepIndex >= STEPS.length;
  const bounded = Math.min(stepIndex, STEPS.length - 1);
  const current = STEPS[bounded];
  const currentValue = selections[current.key];
  const titleSize = Math.round(28 * safeFontScale);
  const bodySize = Math.round(15 * safeFontScale);

  const summary = useMemo(() => buildGuidedStartSummary(selections), [selections]);

  const reviewRows = useMemo(() => {
    const genre = resolveGenre(selections);
    const worldDisplay =
      selections.world === "surprise"
        ? `Surprise me → ${labelForGenre(genre)}`
        : labelFor("world", selections.world);
    return [
      { key: "world", label: "World", value: worldDisplay, step: 0 },
      { key: "role", label: "Role", value: labelFor("role", selections.role), step: 1 },
      { key: "pressure", label: "Pressure", value: labelFor("pressure", selections.pressure), step: 2 },
      { key: "want", label: "Desire", value: labelFor("want", selections.want), step: 3 },
      { key: "fear", label: "Fear", value: labelFor("fear", selections.fear), step: 4 },
      { key: "whoMatters", label: "Who matters", value: labelFor("whoMatters", selections.whoMatters), step: 5 },
      { key: "experience", label: "Experience", value: labelFor("experience", selections.experience), step: 6 },
    ];
  }, [selections]);

  const selectOption = (stepKey: GuidedStepKey, value: string) => {
    if (stepKey === "world") {
      onChange(resolveGuidedWorldSelection(selections, value as GuidedWorldValue));
      return;
    }
    onChange({ [stepKey]: value } as Partial<GuidedStartSelections>);
  };

  const canContinue = Boolean(currentValue) && (current.key !== "world" || resolveGenre(selections));

  if (reviewVisible) {
    return (
      <View testID="guided-start-panel">
        <Text style={styles.pathLink} onPress={onChangePath} testID="guided-change-path">
          ← Change path
        </Text>
        <ReviewSummary
          testIdPrefix="guided-start"
          heading="Review your chronicle."
          summary={summary}
          fontScale={fontScale}
          loading={loading}
          onBack={() => setStepIndex(STEPS.length - 1)}
          onStart={onStart}
          startLabel="Begin Chronicle"
          rows={reviewRows.map((row) => ({
            key: row.key,
            label: row.label,
            value: row.value,
            onChange: () => setStepIndex(row.step),
          }))}
        />
      </View>
    );
  }

  return (
    <View testID="guided-start-panel">
      <Text style={styles.pathLink} onPress={onChangePath} testID="guided-change-path">
        ← Change path
      </Text>
      <Text style={[styles.label, { fontSize: Math.max(11, Math.round(11 * safeFontScale)) }]}>
        GUIDED START
      </Text>
      <Text style={[styles.heading, { fontSize: titleSize }]} testID="guided-start-heading">
        Shape a clear opening, one choice at a time.
      </Text>

      <View style={styles.progressWrap} testID="guided-start-progress">
        <Text style={styles.progressText} testID="guided-start-progress-text">
          {stepIndex + 1} of {STEPS.length}
        </Text>
        <View style={styles.progressTrack}>
          <View
            style={[styles.progressFill, { width: `${((stepIndex + 1) / STEPS.length) * 100}%` }]}
          />
        </View>
      </View>

      <View testID={`guided-start-step-${stepIndex + 1}`}>
        <Text style={styles.stepLabel} testID="guided-start-step-label">
          {current.label}
        </Text>
        <Text
          style={[styles.question, { fontSize: Math.round(24 * safeFontScale) }]}
          testID="guided-start-step-question"
        >
          {current.question}
        </Text>
        <Text style={[styles.helper, { fontSize: bodySize }]} testID="guided-start-step-helper">
          {current.helper}
        </Text>

        <View style={styles.optionList}>
          {current.options.map((option) => {
            const selected = currentValue === option.value;
            return (
              <TouchableOpacity
                key={option.value}
                style={[styles.optionCard, selected && styles.optionCardSelected]}
                onPress={() => selectOption(current.key, option.value)}
                disabled={loading}
                accessibilityRole="button"
                accessibilityState={{ selected, disabled: loading }}
                testID={
                  selected
                    ? `guided-start-option-selected-${current.key}-${option.value}`
                    : `guided-start-option-${current.key}-${option.value}`
                }
              >
                <Text style={[styles.optionTitle, selected && styles.optionTitleSelected]}>
                  {option.label}
                </Text>
                {option.explanation ? (
                  <Text style={styles.optionHelp}>{option.explanation}</Text>
                ) : null}
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={styles.navRow}>
          <TouchableOpacity
            style={styles.secondaryButton}
            onPress={() => {
              if (stepIndex === 0) onChangePath();
              else setStepIndex((v) => Math.max(0, v - 1));
            }}
            disabled={loading}
            testID="guided-start-back-button"
          >
            <Text style={styles.secondaryText}>BACK</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.primaryButton, !canContinue && styles.disabledButton]}
            onPress={() => canContinue && setStepIndex((v) => Math.min(STEPS.length, v + 1))}
            disabled={!canContinue || loading}
            testID="guided-start-next-button"
          >
            <Text style={styles.primaryText}>
              {stepIndex === STEPS.length - 1 ? "REVIEW" : "CONTINUE"}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
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
    letterSpacing: 3,
    marginBottom: 8,
  },
  heading: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    lineHeight: 34,
    marginBottom: 16,
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
  stepLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 11,
    letterSpacing: 2,
    marginBottom: 8,
  },
  question: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    lineHeight: 30,
  },
  helper: {
    marginTop: 8,
    marginBottom: 16,
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    lineHeight: 22,
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
  optionHelp: {
    marginTop: 6,
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    fontSize: 14,
    lineHeight: 19,
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
  },
  disabledButton: { opacity: 0.42 },
  primaryText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.background,
    letterSpacing: 1.4,
  },
});
