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
import { HARSHNESS_LABELS, HOOK_FEAR, HOOK_WANT, HOOK_WHO_MATTERS } from "./options";
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

/** Both description lines from the shared hook copy, as one sentence pair. */
function hookCopy(
  catalog: readonly { value: string; explanation: string; consequence: string }[],
  value: string
): string | undefined {
  const hit = catalog.find((o) => o.value === value);
  return hit ? `${hit.explanation} ${hit.consequence}` : undefined;
}

const WORLD_COPY: Record<GuidedWorldValue, string> = {
  fantasy: "An invented realm before machines, where magic exists. Expect: oaths, shortages and rival factions.",
  horror: "A cut-off place with a threat you do not understand yet. Expect: isolation and dread.",
  "science-fiction": "The near or far future with advanced technology. Expect: large systems and people with authority over you.",
  "post-apocalyptic": "After a collapse, living on what can be salvaged. Expect: shortages, violence and trust being tested.",
  "mystery-crime": "A place with something to investigate. Expect: secrets and people who want them kept.",
  modern: "The present day, kept realistic. Expect: social pressure and trouble with authority.",
  surprise: "The game picks one of the six worlds above for you, once.",
};

const ROLE_COPY: Record<GuidedRoleValue, string> = {
  survivor: "You have already lived through the worst. Expect: hard instincts and old scars.",
  wanderer: "You have no fixed home. Expect: few ties and outsider status.",
  investigator: "You find out what is hidden. Expect: leads, and danger for following them.",
  soldier: "You are trained for violence and orders. Expect: discipline, enemies and commands that cost.",
  outcast: "Your own people pushed you out. Expect: distrust and freedom.",
  scholar: "You rely on knowledge over force. Expect: insight and physical risk.",
  worker: "You do practical work people need. Expect: people wanting your labour.",
  local: "You live here and people know you. Expect: existing ties and a reputation.",
};

const PRESSURE_COPY: Record<GuidedPressureValue, string> = {
  scarcity: "Something people need is running short. Expect: an opening about a shortage, a debt or a last chance.",
  violence: "Fights and threats are close. Expect: an opening about an injury, an unwelcome visitor or a demand from authority.",
  isolation: "You are cut off from help. Expect: an opening about being stuck, worsening conditions or a blocked departure.",
  betrayal: "Someone may have turned on you. Expect: an opening about broken trust, a witness or a debt.",
  illness: "Sickness or injury is pressing. Expect: an opening about a wound or a missing supply.",
  authority: "People in power are tightening their grip. Expect: an opening about a demand, a deadline or a watcher.",
  unknown: "Something unexplained is closing in. Expect: an opening about a message or a visitor tied to it.",
};

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
    helper: "The kind of setting. Places and people are filled in as you play.",
    options: GUIDED_WORLDS.map((o) => ({ value: o.value, label: o.label, explanation: WORLD_COPY[o.value] })),
  },
  {
    key: "role",
    label: "Role",
    question: "Who are you in this world?",
    helper: "Who you are when the story opens. What you become is decided in play.",
    options: GUIDED_ROLES.map((o) => ({ value: o.value, label: o.label, explanation: ROLE_COPY[o.value] })),
  },
  {
    key: "pressure",
    label: "Pressure",
    question: "What pressure is closest to you?",
    helper: "The trouble already near you when the story opens. The opening grows out of it.",
    options: GUIDED_PRESSURES.map((o) => ({ value: o.value, label: o.label, explanation: PRESSURE_COPY[o.value] })),
  },
  {
    key: "want",
    label: "Desire",
    question: "What do you want most right now?",
    helper: "What drives your character. The story keeps putting it within reach and at risk.",
    options: GUIDED_DESIRES.map((o) => ({ value: o.value, label: o.label, explanation: hookCopy(HOOK_WANT, o.value) })),
  },
  {
    key: "fear",
    label: "Fear",
    question: "What are you most afraid of?",
    helper: "What your character dreads. The story will test it.",
    options: HOOK_FEAR.map((o) => ({ value: o.value, label: o.label, explanation: `${o.explanation} ${o.consequence}` })),
  },
  {
    key: "whoMatters",
    label: "Relationship",
    question: "Who matters most to you?",
    helper: "The kind of person you care about most. They get no name until they appear in play.",
    options: GUIDED_WHO.map((o) => ({ value: o.value, label: o.label, explanation: hookCopy(HOOK_WHO_MATTERS, o.value) })),
  },
  {
    key: "experience",
    label: "Experience",
    question: "What kind of experience do you want?",
    helper: "One choice sets two things: the mood of the writing, and how harsh consequences are.",
    options: GUIDED_EXPERIENCE.map((o) => ({
      value: o.value,
      label: o.label,
      explanation: `Mood: ${o.tone}. Consequences: ${HARSHNESS_LABELS[o.difficulty as keyof typeof HARSHNESS_LABELS]}. ${o.explanation}`,
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
