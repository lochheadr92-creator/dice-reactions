import { useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../src/theme";
import { getDeviceId, getSettings } from "../src/storage";
import { newStory, listScenarios } from "../src/api";
import type { Scenario, CustomWorldSetup, NewStoryPayload } from "../src/api";
import { friendlyError } from "../src/errors";
import { clampIndex } from "../src/sanitize";
import { AdvancedBuilder } from "../src/newstory/AdvancedBuilder";
import {
  QuickStart,
  buildQuickStartRequest,
} from "../src/newstory/QuickStart";
import {
  GuidedStart,
  buildGuidedStartRequest,
} from "../src/newstory/GuidedStart";
import type {
  AdvancedDifficulty,
  QuickStartSelections,
  GuidedStartSelections,
} from "../src/newstory/types";

function createCreationRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === "function") {
    return `story-create:${cryptoApi.randomUUID()}`;
  }
  if (typeof cryptoApi?.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    cryptoApi.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `story-create:${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return `story-create:${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function NewStoryScreen() {
  const router = useRouter();
  const submitLockRef = useRef(false);
  const creationRequestRef = useRef<{ fingerprint: string; id: string } | null>(null);
  const [creationFlow, setCreationFlow] = useState<"quick" | "guided" | "advanced">("quick");
  const [genre, setGenre] = useState<string>("");
  const [customGenre, setCustomGenre] = useState("");
  const [role, setRole] = useState("");
  const [tone, setTone] = useState("cinematic");
  const [difficulty, setDifficulty] = useState<AdvancedDifficulty>("standard");
  const [debugMode, setDebugMode] = useState(false);
  const [premise, setPremise] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [fontScale, setFontScale] = useState(1);
  const [developerUnlocked, setDeveloperUnlocked] = useState(false);
  const [mode, setMode] = useState<"basic" | "advanced">("advanced");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [quickSelections, setQuickSelections] = useState<QuickStartSelections>({});
  const [guidedSelections, setGuidedSelections] = useState<GuidedStartSelections>({});
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
    let active = true;
    listScenarios().then((r) => {
      if (active) setScenarios(r.scenarios);
    }).catch(() => {});
    getSettings().then((settings) => {
      if (active) {
        setFontScale(settings.fontScale || 1);
        setDeveloperUnlocked(!!settings.developerUnlocked);
      }
    }).catch(() => {});
    return () => {
      active = false;
    };
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
    const safeIndex = clampIndex(index, answers.length, 0);
    answers[safeIndex] = value;
    setSetupField({ seedAnswers: answers });
  };

  const testKey = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  const clearError = () => setSubmitError(null);

  const setQuickSelection = (patch: Partial<QuickStartSelections>) => {
    setQuickSelections((prev) => {
      const next = { ...prev, ...patch };
      if (patch.world === "random") {
        const randomWorlds = ["fantasy", "horror", "post-apocalyptic", "modern", "detective", "cyberpunk"];
        const randomGenre = randomWorlds[Math.floor(Math.random() * randomWorlds.length)] || "modern";
        next.resolvedWorldGenre = randomGenre;
      }
      if (patch.world && patch.world !== "random") {
        next.resolvedWorldGenre = undefined;
      }
      return next;
    });
    clearError();
  };

  const setGuidedSelection = (patch: Partial<GuidedStartSelections>) => {
    setGuidedSelections((prev) => {
      const next = { ...prev, ...patch };
      if (patch.world && patch.world !== prev.world) {
        next.worldDetail = undefined;
      }
      return next;
    });
    clearError();
  };

  const beginSubmit = () => {
    if (submitLockRef.current || loading) return false;
    submitLockRef.current = true;
    setLoading(true);
    clearError();
    return true;
  };

  const releaseSubmit = () => {
    submitLockRef.current = false;
    setLoading(false);
  };

  const withCreationRequestId = (payload: NewStoryPayload): NewStoryPayload => {
    const fingerprintPayload = { ...payload, creation_request_id: undefined };
    const fingerprint = JSON.stringify(fingerprintPayload);
    let creationRequest = creationRequestRef.current;
    if (!creationRequest || creationRequest.fingerprint !== fingerprint) {
      creationRequest = { fingerprint, id: createCreationRequestId() };
      creationRequestRef.current = creationRequest;
    }
    return { ...payload, creation_request_id: creationRequest.id };
  };

  const creationFailure = (error: unknown) => {
    const { message } = friendlyError(error);
    setSubmitError(message);
    releaseSubmit();
  };

  const switchFlow = (nextFlow: "quick" | "guided" | "advanced") => {
    if (loading) return;
    setCreationFlow(nextFlow);
    clearError();
  };

  const resolvedGenre = genre === "custom"
    ? (customGenre.trim() || customSetup.worldConcept?.trim() || "custom world")
    : genre;
  const customReady = genre !== "custom" || !!(customSetup.worldConcept?.trim() || customGenre.trim());
  const canStartAdvanced = (!!resolvedGenre || !!scenarioId) && customReady && !loading;

  const handleAdvancedStart = async () => {
    if (!canStartAdvanced || !beginSubmit()) return;
    try {
      const device_id = await getDeviceId();
      const settings = await getSettings();
      const requestPayload: NewStoryPayload = {
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
      };
      const res = await newStory(withCreationRequestId(requestPayload));
      if (!res?.session_id) {
        creationFailure(new Error("invalid-session"));
        return;
      }
      router.replace(`/play/${res.session_id}`);
    } catch (e: any) {
      creationFailure(e);
    }
  };

  const handleQuickStart = async () => {
    if (!beginSubmit()) return;

    const settings = await getSettings().catch(() => ({ debugDefault: false, fontScale: 1, developerUnlocked: false }));
    const payload = buildQuickStartRequest(quickSelections);
    if (!payload) {
      creationFailure(new Error("incomplete-quick-start"));
      return;
    }

    try {
      const device_id = await getDeviceId();
      const requestPayload: NewStoryPayload = {
        device_id,
        genre: payload.genre,
        role: payload.role,
        tone: payload.tone,
        difficulty: payload.difficulty,
        debug_mode: settings.debugDefault,
        mode: payload.mode,
        custom_world_setup: payload.custom_world_setup,
      };
      const res = await newStory(withCreationRequestId(requestPayload));
      if (!res?.session_id) {
        creationFailure(new Error("invalid-session"));
        return;
      }
      router.replace(`/play/${res.session_id}`);
    } catch (error) {
      creationFailure(error);
    }
  };

  const handleGuidedStart = async () => {
    if (!beginSubmit()) return;

    const settings = await getSettings().catch(() => ({
      debugDefault: false,
      fontScale: 1,
      developerUnlocked: false,
    }));
    const payload = buildGuidedStartRequest(guidedSelections);
    if (!payload) {
      creationFailure(new Error("incomplete-guided-start"));
      return;
    }

    try {
      const device_id = await getDeviceId();
      const requestPayload: NewStoryPayload = {
        device_id,
        genre: payload.genre,
        role: payload.role,
        tone: payload.tone,
        difficulty: payload.difficulty,
        debug_mode: settings.debugDefault,
        custom_premise: payload.custom_premise,
        mode: payload.mode,
        custom_world_setup: payload.custom_world_setup,
      };
      const res = await newStory(withCreationRequestId(requestPayload));
      if (!res?.session_id) {
        creationFailure(new Error("invalid-session"));
        return;
      }
      router.replace(`/play/${res.session_id}`);
    } catch (error) {
      creationFailure(error);
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
          <Text style={styles.pageLabel} testID="new-story-page-label">NEW CHRONICLE</Text>
          <Text style={styles.pageTitle} testID="new-story-page-title">Choose how your story begins.</Text>
          <Text style={styles.pageHelp} testID="new-story-page-help">
            Quick Start is fastest. Guided Start gives you more curated control. Advanced Builder keeps the full manual setup.
          </Text>

          <View style={styles.creationFlowRow} testID="creation-flow-switcher">
            <TouchableOpacity
              style={[styles.creationFlowButton, creationFlow === "quick" && styles.creationFlowButtonActive]}
              onPress={() => switchFlow("quick")}
              disabled={loading}
              accessibilityState={{ selected: creationFlow === "quick", disabled: loading }}
              testID="creation-flow-quick"
            >
              <Text style={[styles.creationFlowText, creationFlow === "quick" && styles.creationFlowTextActive]}>Quick Start</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.creationFlowButton, creationFlow === "guided" && styles.creationFlowButtonActive]}
              onPress={() => switchFlow("guided")}
              disabled={loading}
              accessibilityState={{ selected: creationFlow === "guided", disabled: loading }}
              testID="creation-flow-guided"
            >
              <Text style={[styles.creationFlowText, creationFlow === "guided" && styles.creationFlowTextActive]}>Guided Start</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.creationFlowButton, creationFlow === "advanced" && styles.creationFlowButtonActive]}
              onPress={() => switchFlow("advanced")}
              disabled={loading}
              accessibilityState={{ selected: creationFlow === "advanced", disabled: loading }}
              testID="creation-flow-advanced"
            >
              <Text style={[styles.creationFlowText, creationFlow === "advanced" && styles.creationFlowTextActive]}>Advanced Builder</Text>
            </TouchableOpacity>
          </View>

          {submitError ? (
            <View style={styles.errorBanner} testID="new-story-error-banner">
              <Ionicons name="alert-circle-outline" size={18} color={COLORS.primary} />
              <Text style={styles.errorBannerText}>{submitError}</Text>
            </View>
          ) : null}

          {creationFlow === "quick" ? (
            <QuickStart
              selections={quickSelections}
              loading={loading}
              fontScale={fontScale}
              onChange={setQuickSelection}
              onStart={handleQuickStart}
            />
          ) : creationFlow === "guided" ? (
            <GuidedStart
              selections={guidedSelections}
              loading={loading}
              fontScale={fontScale}
              onChange={setGuidedSelection}
              onStart={handleGuidedStart}
            />
          ) : (
            <AdvancedBuilder
              loading={loading}
              developerUnlocked={developerUnlocked}
              genre={genre}
              customGenre={customGenre}
              role={role}
              tone={tone}
              difficulty={difficulty}
              debugMode={debugMode}
              premise={premise}
              mode={mode}
              scenarios={scenarios}
              scenarioId={scenarioId}
              customSetup={customSetup}
              onSelectScenario={(scenario) => {
                clearError();
                selectScenario(scenario);
              }}
              onSetGenre={(nextGenre) => {
                clearError();
                setGenre(nextGenre);
              }}
              onSetCustomGenre={(value) => {
                clearError();
                setCustomGenre(value);
              }}
              onSetRole={(value) => {
                clearError();
                setRole(value);
              }}
              onSetTone={(value) => {
                clearError();
                setTone(value);
              }}
              onSetDifficulty={(value) => {
                clearError();
                setDifficulty(value);
              }}
              onSetMode={(value) => {
                clearError();
                setMode(value);
              }}
              onSetPremise={(value) => {
                clearError();
                setPremise(value);
              }}
              onToggleDebug={() => {
                clearError();
                setDebugMode((v) => !v);
              }}
              onSetSetupField={(patch) => {
                clearError();
                setSetupField(patch);
              }}
              onToggleSetupList={(key, value) => {
                clearError();
                toggleSetupList(key, value);
              }}
              onSetContentSetting={(key, value) => {
                clearError();
                setContentSetting(key, value);
              }}
              onUpdateSeedAnswer={(index, value) => {
                clearError();
                updateSeedAnswer(index, value);
              }}
              onStart={handleAdvancedStart}
              canStart={canStartAdvanced}
              testKey={testKey}
            />
          )}

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
  pageLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 3,
    marginBottom: 8,
  },
  pageTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 30,
    lineHeight: 34,
  },
  pageHelp: {
    marginTop: 10,
    marginBottom: 20,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 15,
    lineHeight: 22,
  },
  creationFlowRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 18,
  },
  creationFlowButton: {
    flex: 1,
    minHeight: 48,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 12,
  },
  creationFlowButtonActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  creationFlowText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 12,
    letterSpacing: 1.5,
  },
  creationFlowTextActive: {
    color: COLORS.primary,
  },
  errorBanner: {
    marginBottom: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
  },
  errorBannerText: {
    flex: 1,
    fontFamily: FONTS.bodyMed,
    color: COLORS.textPrimary,
    fontSize: 15,
    lineHeight: 20,
  },
});
