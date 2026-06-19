import React from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Image,
  ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../theme";
import type { Scenario, CustomWorldSetup } from "../api";
import type { AdvancedDifficulty } from "./types";

type Genre = {
  key: string;
  label: string;
  tagline: string;
  image: string;
};

const GENRES: Genre[] = [
  {
    key: "fantasy",
    label: "Fantasy",
    tagline: "Oaths, relics, and kingdoms in slow collapse.",
    image:
      "https://static.prod-images.emergentagent.com/jobs/1f4993bf-965b-40a7-8797-1d8bc205019e/images/3faa0f0bf91c735e5727f826cce85e16076fff278b6a93a826f43d2fd235c453.png",
  },
  {
    key: "post-apocalyptic",
    label: "Post-Apocalyptic",
    tagline: "Scarcity, salvage, trust as currency.",
    image:
      "https://static.prod-images.emergentagent.com/jobs/1f4993bf-965b-40a7-8797-1d8bc205019e/images/a077cabe987d3d5beec7cd3580f9cfd394a20bd25c13cc9aaed8a7e7ca462cbb.png",
  },
  {
    key: "cosmic horror",
    label: "Cosmic Horror",
    tagline: "Doomed curiosity, perception unraveling.",
    image:
      "https://static.prod-images.emergentagent.com/jobs/1f4993bf-965b-40a7-8797-1d8bc205019e/images/1871295a9e304d75675d6744ab08139cbbe71471bb4262e6baab1ddfbba19836.png",
  },
  {
    key: "detective",
    label: "Detective / Noir",
    tagline: "Clues, lies, and a timeline that won't hold.",
    image:
      "https://images.unsplash.com/photo-1764536602389-07ee8e0b4f55?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
  },
  {
    key: "dinosaur survival",
    label: "Prehistoric Survival",
    tagline: "Tracks, scent, and the food chain.",
    image:
      "https://images.pexels.com/photos/1671324/pexels-photo-1671324.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  },
  {
    key: "horror",
    label: "Horror",
    tagline: "Isolation, dread, false safety.",
    image:
      "https://images.unsplash.com/photo-1712777691122-8a10db0a78a2?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
  },
  {
    key: "urban crime",
    label: "Urban Crime",
    tagline: "Heat, money, loyalty as leverage.",
    image:
      "https://images.unsplash.com/photo-1764536602389-07ee8e0b4f55?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
  },
  {
    key: "war survival",
    label: "War & Attrition",
    tagline: "Morale, supply lines, command pressure.",
    image:
      "https://images.unsplash.com/photo-1712777691122-8a10db0a78a2?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
  },
];

type WorldTheme = { key: string; label: string; tagline: string; image: string };

function normalizeTheme(raw: any, idx: number): WorldTheme {
  const pick = (...vals: any[]) => {
    for (const v of vals) {
      if (typeof v === "string" && v.trim()) return v.trim();
    }
    return "";
  };
  const key = pick(raw?.key, raw?.id, raw?.value, raw?.slug) || `theme-${idx}`;
  const label = pick(raw?.label, raw?.name, raw?.title, raw?.displayName) || "Untitled Theme";
  const tagline = pick(raw?.tagline, raw?.description, raw?.subtitle, raw?.tag);
  const image = pick(raw?.image, raw?.imageUrl, raw?.image_url, raw?.cover, raw?.thumbnail);
  return { key, label, tagline, image };
}

const WORLD_THEMES: WorldTheme[] = GENRES.map(normalizeTheme);
const TONES = ["cinematic", "grim", "hopeful", "bleak", "mythic", "grounded"];
const DIFFICULTIES: AdvancedDifficulty[] = ["soft", "standard", "hard", "brutal"];
const PRESSURE_OPTIONS = [
  "starvation",
  "infection",
  "war",
  "predators",
  "political collapse",
  "insanity",
  "extreme weather",
  "AI surveillance",
  "supernatural corruption",
  "scarcity",
  "civil unrest",
];
const FOCUS_OPTIONS = [
  "survival",
  "horror",
  "mystery",
  "exploration",
  "warfare",
  "leadership",
  "revenge",
  "escape",
  "settlement building",
  "romance",
  "political manipulation",
  "emotional drama",
];
const CONTENT_ROWS = [
  { key: "gore", label: "Gore", values: ["none", "low", "medium", "high"] },
  { key: "psychological_horror", label: "Psych horror", values: ["none", "low", "medium", "high"] },
  { key: "scarcity", label: "Scarcity", values: ["soft", "standard", "harsh", "brutal"] },
  { key: "cruelty", label: "Cruelty", values: ["none", "low", "medium", "high"] },
  { key: "moral_ambiguity", label: "Moral ambiguity", values: ["low", "medium", "high"] },
  { key: "relationships", label: "Relationships", values: ["none", "light romance", "mature bonds", "dark dynamics", "seduction/manipulation", "adult world simulation"] },
];

type AdvancedBuilderProps = {
  loading: boolean;
  developerUnlocked: boolean;
  genre: string;
  customGenre: string;
  role: string;
  tone: string;
  difficulty: AdvancedDifficulty;
  debugMode: boolean;
  premise: string;
  mode: "basic" | "advanced";
  scenarios: Scenario[];
  scenarioId: string | null;
  customSetup: CustomWorldSetup;
  onSelectScenario: (scenario: Scenario | null) => void;
  onSetGenre: (genre: string) => void;
  onSetCustomGenre: (value: string) => void;
  onSetRole: (value: string) => void;
  onSetTone: (value: string) => void;
  onSetDifficulty: (value: AdvancedDifficulty) => void;
  onSetMode: (value: "basic" | "advanced") => void;
  onSetPremise: (value: string) => void;
  onToggleDebug: () => void;
  onSetSetupField: (patch: Partial<CustomWorldSetup>) => void;
  onToggleSetupList: (key: "pressures" | "storyFocus", value: string) => void;
  onSetContentSetting: (key: string, value: string) => void;
  onUpdateSeedAnswer: (index: number, value: string) => void;
  onStart: () => void;
  canStart: boolean;
  testKey: (value: string) => string;
};

export function AdvancedBuilder({
  loading,
  developerUnlocked,
  genre,
  customGenre,
  role,
  tone,
  difficulty,
  debugMode,
  premise,
  mode,
  scenarios,
  scenarioId,
  customSetup,
  onSelectScenario,
  onSetGenre,
  onSetCustomGenre,
  onSetRole,
  onSetTone,
  onSetDifficulty,
  onSetMode,
  onSetPremise,
  onToggleDebug,
  onSetSetupField,
  onToggleSetupList,
  onSetContentSetting,
  onUpdateSeedAnswer,
  onStart,
  canStart,
  testKey,
}: AdvancedBuilderProps) {
  return (
    <View testID="advanced-builder-panel">
      <Text style={styles.stepLabel}>ADVANCED · WORLD · BUILDER</Text>
      <Text style={styles.stepHelp}>
        The existing builder is preserved here, including curated scenarios and manual world setup.
      </Text>

      <Text style={styles.stepLabel}>00 · QUICK · START</Text>
      <Text style={styles.stepHelp}>
        Hand-tuned scenarios with named NPCs, seeded inventory, and a hidden threat already in place. Or scroll past to build your own.
      </Text>
      <View style={styles.scenarioList}>
        {scenarios.map((s) => {
          const active = scenarioId === s.id;
          return (
            <TouchableOpacity
              key={s.id}
              style={[styles.scenarioCard, active && styles.scenarioCardActive]}
              onPress={() => onSelectScenario(active ? null : s)}
              activeOpacity={0.85}
              testID={`scenario-${s.id}`}
            >
              <View style={styles.scenarioHeader}>
                <Text style={[styles.scenarioTitle, active && styles.scenarioTitleActive]}>
                  {s.title}
                </Text>
                {active && <Ionicons name="checkmark-circle" size={18} color={COLORS.primary} />}
              </View>
              <Text style={styles.scenarioPitch}>{s.pitch}</Text>
              <View style={styles.scenarioMetaRow}>
                <Text style={styles.scenarioMeta}>{s.difficulty.toUpperCase()}</Text>
                <Text style={styles.scenarioMetaDim}>·</Text>
                <Text style={styles.scenarioMeta}>{s.mode.toUpperCase()} MODE</Text>
                <Text style={styles.scenarioMetaDim}>·</Text>
                <Text style={styles.scenarioMeta}>{s.key_npcs.length} NPCs</Text>
              </View>
            </TouchableOpacity>
          );
        })}
        {scenarioId && (
          <TouchableOpacity
            style={styles.scenarioClear}
            onPress={() => onSelectScenario(null)}
            testID="scenario-clear"
          >
            <Text style={styles.scenarioClearText}>CLEAR SCENARIO · build manually</Text>
          </TouchableOpacity>
        )}
      </View>

      <Text style={[styles.stepLabel, { marginTop: 28 }]}>01 · SELECT · WORLD</Text>
      <Text style={styles.stepHelp}>Each world unlocks its own systems, pressures, and textures.</Text>

      <View style={styles.grid}>
        {WORLD_THEMES.map((g) => {
          const active = genre === g.key;
          return (
            <TouchableOpacity
              key={g.key}
              style={[styles.genreCard, active && styles.genreCardActive]}
              onPress={() => onSetGenre(g.key)}
              activeOpacity={0.8}
              testID={`genre-${g.key}`}
            >
              {g.image ? (
                <Image source={{ uri: g.image }} style={styles.genreImage} />
              ) : (
                <View style={[styles.genreImage, styles.genreImageFallback]}>
                  <Ionicons name="planet-outline" size={30} color={COLORS.textMuted} />
                </View>
              )}
              <View style={styles.genreOverlay} />
              {active && <View style={styles.genreActiveRing} />}
              <View style={styles.genreTextWrap}>
                <Text style={styles.genreTitle} numberOfLines={1}>{g.label || "Untitled Theme"}</Text>
                {g.tagline ? <Text style={styles.genreTag} numberOfLines={2}>{g.tagline}</Text> : null}
              </View>
            </TouchableOpacity>
          );
        })}
        <TouchableOpacity
          style={[styles.genreCard, genre === "custom" && styles.genreCardActive, styles.customCard]}
          onPress={() => onSetGenre("custom")}
          activeOpacity={0.8}
          testID="genre-custom"
        >
          <View style={styles.customCardInner}>
            <Ionicons name="add" size={28} color={COLORS.primary} />
            <Text style={styles.genreTitle}>Custom</Text>
            <Text style={styles.genreTag}>Write your own world.</Text>
          </View>
        </TouchableOpacity>
      </View>

      {genre === "custom" && (
        <View style={styles.customSetupBox} testID="custom-world-setup-panel">
          <View style={styles.setupIntroRow}>
            <Ionicons name="sparkles-outline" size={18} color={COLORS.primary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.setupTitle}>CUSTOM · WORLD · IGNITION</Text>
              <Text style={styles.setupHelp}>Fast answers. Persistent consequences. Skip anything you want the engine to infer.</Text>
            </View>
          </View>

          <View style={styles.setupStep} testID="custom-step-world-concept">
            <Text style={styles.inlineLabel}>01 · WORLD CONCEPT</Text>
            <TextInput
              value={customGenre}
              onChangeText={(v) => {
                onSetCustomGenre(v);
                onSetSetupField({ worldConcept: v });
              }}
              placeholder="flooded cyberpunk city, plague kingdom, collapsing colony…"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              testID="custom-world-concept-input"
            />
            <TextInput
              value={customSetup.worldTone || ""}
              onChangeText={(v) => onSetSetupField({ worldTone: v })}
              placeholder="Tone: intimate dread, brutal realism, strange wonder…"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              testID="custom-world-tone-input"
            />
            <TextInput
              value={customSetup.danger || ""}
              onChangeText={(v) => onSetSetupField({ danger: v })}
              placeholder="What feels wrong or dangerous here?"
              placeholderTextColor={COLORS.textMuted}
              style={[styles.input, styles.inputMultiSmall]}
              multiline
              testID="custom-world-danger-input"
            />
          </View>

          <View style={styles.setupStep} testID="custom-step-player-origin">
            <Text style={styles.inlineLabel}>02 · PLAYER ORIGIN</Text>
            <TextInput value={customSetup.origin || ""} onChangeText={(v) => onSetSetupField({ origin: v })} placeholder="Who are you?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-origin-input" />
            <TextInput value={customSetup.formerLife || ""} onChangeText={(v) => onSetSetupField({ formerLife: v })} placeholder="What were you before this began?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-former-life-input" />
            <TextInput value={customSetup.strengths || ""} onChangeText={(v) => onSetSetupField({ strengths: v })} placeholder="What are you good at?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-strengths-input" />
            <TextInput value={customSetup.weakness || ""} onChangeText={(v) => onSetSetupField({ weakness: v })} placeholder="What weakness follows you?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-weakness-input" />
            <TextInput value={customSetup.carried || ""} onChangeText={(v) => onSetSetupField({ carried: v })} placeholder="What do you currently carry?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-carried-input" />
            <TextInput value={customSetup.desire || ""} onChangeText={(v) => onSetSetupField({ desire: v })} placeholder="What do you want most right now?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-desire-input" />
          </View>

          <View style={styles.setupStep} testID="custom-step-active-pressures">
            <Text style={styles.inlineLabel}>03 · ACTIVE PRESSURES</Text>
            <View style={styles.chipRow}>
              {PRESSURE_OPTIONS.map((p) => {
                const active = (customSetup.pressures || []).includes(p);
                return (
                  <TouchableOpacity key={p} style={[styles.chip, active && styles.chipActive]} onPress={() => onToggleSetupList("pressures", p)} testID={`custom-pressure-${testKey(p)}`}>
                    <Text style={[styles.chipText, active && styles.chipTextActive]}>{p}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={styles.setupStep} testID="custom-step-story-focus">
            <Text style={styles.inlineLabel}>04 · STORY FOCUS</Text>
            <Text style={styles.setupHelp}>Pick what this world should naturally produce most often.</Text>
            <View style={styles.chipRow}>
              {FOCUS_OPTIONS.map((f) => {
                const active = (customSetup.storyFocus || []).includes(f);
                return (
                  <TouchableOpacity key={f} style={[styles.chip, active && styles.chipActive]} onPress={() => onToggleSetupList("storyFocus", f)} testID={`custom-focus-${testKey(f)}`}>
                    <Text style={[styles.chipText, active && styles.chipTextActive]}>{f}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={styles.setupStep} testID="custom-step-content-settings">
            <Text style={styles.inlineLabel}>05 · INTENSITY & SOCIAL SYSTEMS</Text>
            <Text style={styles.setupHelp}>These affect NPC memory, faction reactions, stress, leverage, and delayed consequences.</Text>
            {CONTENT_ROWS.map((row) => (
              <View key={row.key} style={styles.contentRow}>
                <Text style={styles.contentLabel}>{row.label}</Text>
                <View style={styles.chipRow}>
                  {row.values.map((v) => {
                    const active = customSetup.contentSettings?.[row.key] === v;
                    return (
                      <TouchableOpacity key={v} style={[styles.smallChip, active && styles.chipActive]} onPress={() => onSetContentSetting(row.key, v)} testID={`custom-content-${row.key}-${testKey(v)}`}>
                        <Text style={[styles.smallChipText, active && styles.chipTextActive]}>{v}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            ))}
          </View>

          <View style={styles.setupStep} testID="custom-step-seed-questions">
            <Text style={styles.inlineLabel}>06 · SEED QUESTIONS</Text>
            {[
              "What are you afraid of losing?",
              "Who already wants something from you?",
              "What mistake still follows you?",
            ].map((q, idx) => (
              <TextInput
                key={q}
                value={(customSetup.seedAnswers || [])[idx] || ""}
                onChangeText={(v) => onUpdateSeedAnswer(idx, v)}
                placeholder={q}
                placeholderTextColor={COLORS.textMuted}
                style={styles.input}
                testID={`custom-seed-answer-${idx}`}
              />
            ))}
          </View>
        </View>
      )}

      <Text style={[styles.stepLabel, { marginTop: 28 }]}>02 · CHARACTER</Text>
      <TextInput
        value={role}
        onChangeText={onSetRole}
        placeholder="Role or archetype (leave blank to let the engine decide)"
        placeholderTextColor={COLORS.textMuted}
        style={styles.input}
        testID="role-input"
      />

      <Text style={[styles.stepLabel, { marginTop: 28 }]}>03 · TONE</Text>
      <View style={styles.chipRow}>
        {TONES.map((t) => (
          <TouchableOpacity
            key={t}
            style={[styles.chip, tone === t && styles.chipActive]}
            onPress={() => onSetTone(t)}
            testID={`tone-${t}`}
          >
            <Text style={[styles.chipText, tone === t && styles.chipTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={[styles.stepLabel, { marginTop: 28 }]}>04 · DIFFICULTY</Text>
      <View style={styles.chipRow}>
        {DIFFICULTIES.map((d) => (
          <TouchableOpacity
            key={d}
            style={[styles.chip, difficulty === d && styles.chipActive]}
            onPress={() => onSetDifficulty(d)}
            testID={`difficulty-${d}`}
          >
            <Text style={[styles.chipText, difficulty === d && styles.chipTextActive]}>{d}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.diffHelp}>
        {difficulty === "soft" && "The world meets you halfway. Wounds heal. People help."}
        {difficulty === "standard" && "Fair, but consequences bite. The world does not wait."}
        {difficulty === "hard" && "Scarcity, fewer safe routes, faster escalation. People are tired."}
        {difficulty === "brutal" && "Fragile survival. Mistakes compound. Death is causal and quiet."}
      </Text>

      {developerUnlocked ? (
        <>
          <Text style={[styles.stepLabel, { marginTop: 28 }]}>05 · ENGINE · MODE</Text>
          <View style={styles.chipRow}>
            {(["basic", "advanced"] as const).map((m) => (
              <TouchableOpacity
                key={m}
                style={[styles.chip, mode === m && styles.chipActive]}
                onPress={() => onSetMode(m)}
                testID={`mode-${m}`}
              >
                <Text style={[styles.chipText, mode === m && styles.chipTextActive]}>{m}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={styles.diffHelp}>
            {mode === "basic"
              ? "Lighter scenes, fewer choices. Faster, cheaper play."
              : "Deeper memory, richer characters, longer arcs. Consequences carry further."}
          </Text>
        </>
      ) : null}

      <Text style={[styles.stepLabel, { marginTop: 28 }]}> 
        {developerUnlocked ? "06 · OPENING · HOOK  (optional)" : "05 · OPENING · HOOK  (optional)"}
      </Text>
      <TextInput
        value={premise}
        onChangeText={onSetPremise}
        placeholder="A custom premise, opening situation, or constraint the engine should honour."
        placeholderTextColor={COLORS.textMuted}
        style={[styles.input, styles.inputMulti]}
        multiline
        testID="premise-input"
      />

      {developerUnlocked ? (
        <TouchableOpacity
          style={styles.debugRow}
          onPress={onToggleDebug}
          testID="debug-toggle"
          activeOpacity={0.7}
        >
          <View style={[styles.checkbox, debugMode && styles.checkboxOn]}>
            {debugMode && <Ionicons name="checkmark" size={14} color={COLORS.background} />}
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.debugTitle}>DEBUG · MODE</Text>
            <Text style={styles.debugHelp}>Surface rolls, modifiers, and active systems each turn.</Text>
          </View>
        </TouchableOpacity>
      ) : null}

      <TouchableOpacity
        style={[styles.startBtn, !canStart && styles.startBtnDisabled]}
        onPress={onStart}
        disabled={!canStart}
        testID="begin-story-btn"
        activeOpacity={0.8}
      >
        {loading ? (
          <ActivityIndicator color={COLORS.primary} />
        ) : (
          <Text style={styles.startBtnText}>[ ROLL · FOR · INITIATIVE ]</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  stepLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 11,
    letterSpacing: 3,
    marginBottom: 6,
  },
  stepHelp: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 14,
    marginBottom: 14,
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  genreCard: {
    width: "48.5%",
    aspectRatio: 0.95,
    minHeight: 160,
    borderWidth: 1,
    borderColor: COLORS.border,
    overflow: "hidden",
    backgroundColor: COLORS.surface,
    position: "relative",
  },
  genreCardActive: {
    borderColor: COLORS.primary,
  },
  genreImage: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, width: "100%", height: "100%" },
  genreImageFallback: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.surfaceDeep,
  },
  genreOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(5, 5, 5, 0.55)",
  },
  genreActiveRing: {
    position: "absolute",
    top: 6,
    left: 6,
    right: 6,
    bottom: 6,
    borderWidth: 1,
    borderColor: COLORS.primary,
  },
  genreTextWrap: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: 12,
    backgroundColor: "rgba(5, 5, 5, 0.8)",
  },
  genreTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 18,
  },
  genreTag: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 12,
    marginTop: 2,
    lineHeight: 16,
  },
  customCard: { backgroundColor: COLORS.surfaceDeep },
  customCardInner: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 12,
  },
  customSetupBox: {
    marginTop: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  setupIntroRow: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
    marginBottom: 14,
  },
  setupTitle: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 2,
  },
  setupHelp: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 13,
    marginTop: 4,
    lineHeight: 18,
  },
  setupStep: {
    paddingTop: 14,
    marginTop: 8,
    borderTopWidth: 1,
    borderTopColor: COLORS.borderDim,
  },
  inlineLabel: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 2,
    marginBottom: 6,
  },
  input: {
    borderWidth: 0,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    paddingVertical: 12,
    paddingHorizontal: 0,
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 14,
  },
  inputMulti: {
    minHeight: 80,
    textAlignVertical: "top",
  },
  inputMultiSmall: {
    minHeight: 58,
    textAlignVertical: "top",
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
  },
  chipActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  chipText: {
    fontFamily: FONTS.mono,
    color: COLORS.textSecondary,
    fontSize: 12,
    letterSpacing: 1.5,
  },
  chipTextActive: {
    color: COLORS.primary,
  },
  contentRow: {
    marginTop: 12,
    gap: 8,
  },
  contentLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 10,
    letterSpacing: 2,
  },
  smallChip: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
  },
  smallChipText: {
    fontFamily: FONTS.mono,
    color: COLORS.textSecondary,
    fontSize: 10,
    letterSpacing: 1,
  },
  diffHelp: {
    marginTop: 10,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 13,
  },
  debugRow: {
    marginTop: 28,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 14,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
  },
  checkbox: {
    width: 20,
    height: 20,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxOn: {
    backgroundColor: COLORS.primary,
    borderColor: COLORS.primary,
  },
  debugTitle: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textPrimary,
    fontSize: 11,
    letterSpacing: 3,
  },
  debugHelp: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 13,
    marginTop: 2,
  },
  startBtn: {
    marginTop: 28,
    paddingVertical: 20,
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    alignItems: "center",
  },
  startBtnDisabled: {
    opacity: 0.35,
  },
  startBtnText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 13,
    letterSpacing: 4,
  },
  scenarioList: { gap: 10, marginTop: 8 },
  scenarioCard: {
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
  },
  scenarioCardActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  scenarioHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 6,
  },
  scenarioTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 17,
  },
  scenarioTitleActive: { color: COLORS.primary },
  scenarioPitch: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textProse,
    fontSize: 13,
    lineHeight: 19,
  },
  scenarioMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 10,
  },
  scenarioMeta: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 9,
    letterSpacing: 2,
  },
  scenarioMetaDim: {
    color: COLORS.textMuted,
    fontSize: 9,
  },
  scenarioClear: {
    paddingVertical: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    borderStyle: "dashed",
    marginTop: 4,
  },
  scenarioClearText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 2,
  },
});