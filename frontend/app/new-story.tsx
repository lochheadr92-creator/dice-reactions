import { useState } from "react";
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
import { newStory } from "../src/api";
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

  const resolvedGenre = genre === "custom" ? customGenre.trim() : genre;
  const canStart = !!resolvedGenre && !loading;

  const handleStart = async () => {
    if (!canStart) return;
    setLoading(true);
    try {
      const device_id = await getDeviceId();
      const settings = await getSettings();
      const res = await newStory({
        device_id,
        genre: resolvedGenre,
        role: role.trim() || undefined,
        tone,
        difficulty,
        debug_mode: debugMode || settings.debugDefault,
        custom_premise: premise.trim() || undefined,
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
          <Text style={styles.stepLabel}>01 · SELECT · WORLD</Text>
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
                  {active && <View style={[styles.genreActiveRing, { pointerEvents: "none" }]} />}
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
            <View style={styles.customInputWrap}>
              <Text style={styles.inlineLabel}>Name this world</Text>
              <TextInput
                value={customGenre}
                onChangeText={setCustomGenre}
                placeholder="e.g. dieselpunk espionage, undersea cult, solarpunk heist"
                placeholderTextColor={COLORS.textMuted}
                style={styles.input}
                testID="custom-genre-input"
              />
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
            {difficulty === "soft" && "+3 to every roll · brake fires early · NPCs lean helpful."}
            {difficulty === "standard" && "No modifier · standard brake · no early death."}
            {difficulty === "hard" && "−3 to every roll · brake only at critical · death possible."}
            {difficulty === "brutal" && "−6 to every roll · NO brake · NO death guard · wounds compound · resources halve · NPCs hostile by default."}
          </Text>

          <Text style={[styles.stepLabel, { marginTop: 28 }]}>05 · OPENING · HOOK  (optional)</Text>
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
});
