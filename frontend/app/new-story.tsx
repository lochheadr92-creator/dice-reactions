import { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Image,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../src/theme";
import { getDeviceId, getSettings } from "../src/storage";
import { newStory, listScenarios, Scenario, CustomWorldSetup } from "../src/api";
import { friendlyError } from "../src/errors";

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

const TONES = ["cinematic", "grim", "hopeful", "bleak", "mythic", "grounded"];
const DIFFICULTIES = ["soft", "standard", "hard", "brutal"] as const;
const PRESSURE_OPTIONS = ["starvation", "infection", "war", "predators", "political collapse", "insanity", "extreme weather", "AI surveillance", "supernatural corruption", "scarcity", "civil unrest"];
const FOCUS_OPTIONS = ["survival", "horror", "mystery", "exploration", "warfare", "leadership", "revenge", "escape", "settlement building", "romance", "political manipulation", "emotional drama"];
const CONTENT_ROWS = [
  { key: "gore", label: "Gore", values: ["none", "low", "medium", "high"] },
  { key: "psychological_horror", label: "Psych horror", values: ["none", "low", "medium", "high"] },
  { key: "scarcity", label: "Scarcity", values: ["soft", "standard", "harsh", "brutal"] },
  { key: "cruelty", label: "Cruelty", values: ["none", "low", "medium", "high"] },
  { key: "moral_ambiguity", label: "Moral ambiguity", values: ["low", "medium", "high"] },
  { key: "relationships", label: "Relationships", values: ["none", "light romance", "mature bonds", "dark dynamics", "seduction/manipulation", "adult world simulation"] },
];

export default function NewStoryScreen() {
  const router = useRouter();
  const [genre, setGenre] = useState<string>("");
  const [customGenre, setCustomGenre] = useState("");
  const [role, setRole] = useState("");
  const [tone, setTone] = useState("cinematic");
  const [difficulty, setDifficulty] = useState<(typeof DIFFICULTIES)[number]>("standard");
  const [debugMode, setDebugMode] = useState(false);
  const [premise, setPremise] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"basic" | "advanced">("advanced");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [customSetup, setCustomSetup] = useState<CustomWorldSetup>({
    pressures: [],
    storyFocus: [],
    contentSettings: {
      gore: "low",
      psychological_horror: "medium",
      scarcity: "standard",
      cruelty: "low",
      moral_ambiguity: "medium",
      relationships: "none",
    },
    seedAnswers: ["", "", ""],
  });

  useEffect(() => {
    listScenarios().then((r) => setScenarios(r.scenarios)).catch(() => {});
  }, []);

  const selectScenario = (s: Scenario | null) => {
    if (!s) {
      setScenarioId(null);
      return;
    }
    setScenarioId(s.id);
    setGenre(s.genre);
    setRole(s.role);
    setTone(s.tone);
    setDifficulty(s.difficulty as any);
    setMode((s.mode as any) || "advanced");
  };

  const setSetupField = (patch: Partial<CustomWorldSetup>) => {
    setCustomSetup((prev) => ({ ...prev, ...patch }));
  };

  const toggleSetupList = (key: "pressures" | "storyFocus", value: string) => {
    setCustomSetup((prev) => {
      const current = prev[key] || [];
      const next = current.includes(value)
        ? current.filter((x) => x !== value)
        : [...current, value];
      return { ...prev, [key]: next };
    });
  };

  const setContentSetting = (key: string, value: string) => {
    setCustomSetup((prev) => ({
      ...prev,
      contentSettings: { ...(prev.contentSettings || {}), [key]: value },
    }));
  };

  const updateSeedAnswer = (index: number, value: string) => {
    const answers = [...(customSetup.seedAnswers || ["", "", ""] )];
    answers[index] = value;
    setSetupField({ seedAnswers: answers });
  };

  const testKey = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  const resolvedGenre = genre === "custom"
    ? (customGenre.trim() || customSetup.worldConcept?.trim() || "custom world")
    : genre;
  const customReady = genre !== "custom" || !!(customSetup.worldConcept?.trim() || customGenre.trim());
  const canStart = (!!resolvedGenre || !!scenarioId) && customReady && !loading;

  const handleStart = async () => {
    if (!canStart) return;
    setLoading(true);
    try {
      const device_id = await getDeviceId();
      const settings = await getSettings();
      const res = await newStory({
        device_id,
        genre: resolvedGenre || (scenarios.find((s) => s.id === scenarioId)?.genre ?? ""),
        role: role.trim() || customSetup.origin?.trim() || undefined,
        tone,
        difficulty,
        debug_mode: debugMode || settings.debugDefault,
        custom_premise: premise.trim() || undefined,
        mode,
        scenario_id: scenarioId || undefined,
        custom_world_setup: genre === "custom" ? customSetup : undefined,
      });
      router.replace(`/play/${res.session_id}`);
    } catch (e: any) {
      console.log("new story failed", e);
      const { title, message } = friendlyError(e);
      if (Platform.OS === "web") {
        alert(`${title}\n\n${message}`);
      } else {
        Alert.alert(title, message);
      }
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} testID="new-story-screen">
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={styles.topBar}>
          <TouchableOpacity onPress={() => router.back()} hitSlop={12} testID="back-btn">
            <Ionicons name="chevron-back" size={22} color={COLORS.textSecondary} />
          </TouchableOpacity>
          <Text style={styles.topTitle}>NEW · CHRONICLE</Text>
          <View style={{ width: 22 }} />
        </View>

        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
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
                  onPress={() => selectScenario(active ? null : s)}
                  activeOpacity={0.85}
                  testID={`scenario-${s.id}`}
                >
                  <View style={styles.scenarioHeader}>
                    <Text style={[styles.scenarioTitle, active && styles.scenarioTitleActive]}>
                      {s.title}
                    </Text>
                    {active && (
                      <Ionicons name="checkmark-circle" size={18} color={COLORS.primary} />
                    )}
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
                onPress={() => selectScenario(null)}
                testID="scenario-clear"
              >
                <Text style={styles.scenarioClearText}>CLEAR SCENARIO · build manually</Text>
              </TouchableOpacity>
            )}
          </View>

          <Text style={[styles.stepLabel, { marginTop: 28 }]}>01 · SELECT · WORLD</Text>
          <Text style={styles.stepHelp}>Each world unlocks its own systems, pressures, and textures.</Text>

          <View style={styles.grid}>
            {GENRES.map((g) => {
              const active = genre === g.key;
              return (
                <TouchableOpacity
                  key={g.key}
                  style={[styles.genreCard, active && styles.genreCardActive]}
                  onPress={() => setGenre(g.key)}
                  activeOpacity={0.8}
                  testID={`genre-${g.key}`}
                >
                  <Image source={{ uri: g.image }} style={styles.genreImage} />
                  <View style={styles.genreOverlay} />
                  {active && <View style={styles.genreActiveRing} />}
                  <View style={styles.genreTextWrap}>
                    <Text style={styles.genreTitle}>{g.label}</Text>
                    <Text style={styles.genreTag} numberOfLines={2}>{g.tagline}</Text>
                  </View>
                </TouchableOpacity>
              );
            })}
            <TouchableOpacity
              style={[styles.genreCard, genre === "custom" && styles.genreCardActive, styles.customCard]}
              onPress={() => setGenre("custom")}
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
                    setCustomGenre(v);
                    setSetupField({ worldConcept: v });
                  }}
                  placeholder="flooded cyberpunk city, plague kingdom, collapsing colony…"
                  placeholderTextColor={COLORS.textMuted}
                  style={styles.input}
                  testID="custom-world-concept-input"
                />
                <TextInput
                  value={customSetup.worldTone || ""}
                  onChangeText={(v) => setSetupField({ worldTone: v })}
                  placeholder="Tone: intimate dread, brutal realism, strange wonder…"
                  placeholderTextColor={COLORS.textMuted}
                  style={styles.input}
                  testID="custom-world-tone-input"
                />
                <TextInput
                  value={customSetup.danger || ""}
                  onChangeText={(v) => setSetupField({ danger: v })}
                  placeholder="What feels wrong or dangerous here?"
                  placeholderTextColor={COLORS.textMuted}
                  style={[styles.input, styles.inputMultiSmall]}
                  multiline
                  testID="custom-world-danger-input"
                />
              </View>

              <View style={styles.setupStep} testID="custom-step-player-origin">
                <Text style={styles.inlineLabel}>02 · PLAYER ORIGIN</Text>
                <TextInput value={customSetup.origin || ""} onChangeText={(v) => setSetupField({ origin: v })} placeholder="Who are you?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-origin-input" />
                <TextInput value={customSetup.formerLife || ""} onChangeText={(v) => setSetupField({ formerLife: v })} placeholder="What were you before this began?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-former-life-input" />
                <TextInput value={customSetup.strengths || ""} onChangeText={(v) => setSetupField({ strengths: v })} placeholder="What are you good at?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-strengths-input" />
                <TextInput value={customSetup.weakness || ""} onChangeText={(v) => setSetupField({ weakness: v })} placeholder="What weakness follows you?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-weakness-input" />
                <TextInput value={customSetup.carried || ""} onChangeText={(v) => setSetupField({ carried: v })} placeholder="What do you currently carry?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-carried-input" />
                <TextInput value={customSetup.desire || ""} onChangeText={(v) => setSetupField({ desire: v })} placeholder="What do you want most right now?" placeholderTextColor={COLORS.textMuted} style={styles.input} testID="custom-desire-input" />
              </View>

              <View style={styles.setupStep} testID="custom-step-active-pressures">
                <Text style={styles.inlineLabel}>03 · ACTIVE PRESSURES</Text>
                <View style={styles.chipRow}>
                  {PRESSURE_OPTIONS.map((p) => {
                    const active = (customSetup.pressures || []).includes(p);
                    return (
                      <TouchableOpacity key={p} style={[styles.chip, active && styles.chipActive]} onPress={() => toggleSetupList("pressures", p)} testID={`custom-pressure-${testKey(p)}`}>
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
                      <TouchableOpacity key={f} style={[styles.chip, active && styles.chipActive]} onPress={() => toggleSetupList("storyFocus", f)} testID={`custom-focus-${testKey(f)}`}>
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
                          <TouchableOpacity key={v} style={[styles.smallChip, active && styles.chipActive]} onPress={() => setContentSetting(row.key, v)} testID={`custom-content-${row.key}-${testKey(v)}`}>
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
                    onChangeText={(v) => updateSeedAnswer(idx, v)}
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
            onChangeText={setRole}
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
                onPress={() => setTone(t)}
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
                onPress={() => setDifficulty(d)}
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

          <Text style={[styles.stepLabel, { marginTop: 28 }]}>05 · ENGINE · MODE</Text>
          <View style={styles.chipRow}>
            {(["basic", "advanced"] as const).map((m) => (
              <TouchableOpacity
                key={m}
                style={[styles.chip, mode === m && styles.chipActive]}
                onPress={() => setMode(m)}
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

          <Text style={[styles.stepLabel, { marginTop: 28 }]}>06 · OPENING · HOOK  (optional)</Text>
          <TextInput
            value={premise}
            onChangeText={setPremise}
            placeholder="A custom premise, opening situation, or constraint the engine should honour."
            placeholderTextColor={COLORS.textMuted}
            style={[styles.input, styles.inputMulti]}
            multiline
            testID="premise-input"
          />

          <TouchableOpacity
            style={styles.debugRow}
            onPress={() => setDebugMode((v) => !v)}
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

          <TouchableOpacity
            style={[styles.startBtn, !canStart && styles.startBtnDisabled]}
            onPress={handleStart}
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

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  topTitle: {
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 3,
  },
  container: { padding: 20 },
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
  customInputWrap: {
    marginTop: 14,
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

  // Scenario picker
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
