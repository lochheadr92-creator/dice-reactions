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
import {
  getSetupCapabilities,
  newStory,
  SAFE_SETUP_CAPABILITIES,
} from "../src/api";
import type {
  CustomWorldSetup,
  MatureContentPreferences,
  NewStoryPayload,
} from "../src/api";
import { friendlyError } from "../src/errors";
import {
  AdvancedBuilder,
  buildAdvancedStartRequest,
  createDefaultAdvancedSetup,
} from "../src/newstory/AdvancedBuilder";
import {
  QuickStart,
  buildQuickStartRequest,
  type QuickStartGenre,
} from "../src/newstory/QuickStart";
import {
  GuidedStart,
  buildGuidedStartRequest,
} from "../src/newstory/GuidedStart";
import type { GuidedStartSelections } from "../src/newstory/types";

type CreationFlow = "quick" | "guided" | "advanced";
type ScreenMode = "select" | CreationFlow;

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

const SELECTION_CARDS: {
  flow: CreationFlow;
  title: string;
  body: string;
  expectation: string;
  cta: string;
  testId: string;
}[] = [
  {
    flow: "quick",
    title: "Quick Start",
    body: "Choose a world and begin immediately.",
    expectation: "Instant",
    cta: "Choose a world",
    testId: "selection-card-quick",
  },
  {
    flow: "guided",
    title: "Guided Start",
    body: "Answer a few simple questions to shape your world, character and starting pressure.",
    expectation: "About 1 minute",
    cta: "Start guided setup",
    testId: "selection-card-guided",
  },
  {
    flow: "advanced",
    title: "Advanced Builder",
    body: "Define your world, character, relationships and experience in greater detail.",
    expectation: "Full control",
    cta: "Open builder",
    testId: "selection-card-advanced",
  },
];

export default function NewStoryScreen() {
  const router = useRouter();
  const submitLockRef = useRef(false);
  const creationRequestRef = useRef<{ fingerprint: string; id: string } | null>(null);
  /** Sticky Quick Start attempt: same card retry keeps seed → same scenario_id. */
  const quickAttemptRef = useRef<{
    key: string;
    seed: string;
  } | null>(null);
  const [screen, setScreen] = useState<ScreenMode>("select");
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [fontScale, setFontScale] = useState(1);
  const [launchingGenreKey, setLaunchingGenreKey] = useState<string | null>(null);
  const [guidedSelections, setGuidedSelections] = useState<GuidedStartSelections>({});
  const [customSetup, setCustomSetup] = useState<CustomWorldSetup>(createDefaultAdvancedSetup);
  const [matureContent, setMatureContent] = useState<MatureContentPreferences>(
    SAFE_SETUP_CAPABILITIES.mature_content_defaults
  );
  const [setupCapabilities, setSetupCapabilities] = useState(
    SAFE_SETUP_CAPABILITIES.distribution_capabilities
  );

  useEffect(() => {
    let active = true;
    getSetupCapabilities()
      .then((response) => {
        if (!active) return;
        setSetupCapabilities(response.distribution_capabilities);
        setMatureContent(response.mature_content_defaults);
      })
      .catch(() => {
        if (!active) return;
        setSetupCapabilities(SAFE_SETUP_CAPABILITIES.distribution_capabilities);
        setMatureContent(SAFE_SETUP_CAPABILITIES.mature_content_defaults);
      });
    getSettings()
      .then((settings) => {
        if (active) setFontScale(settings.fontScale || 1);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const setSetupField = (patch: Partial<CustomWorldSetup>) => {
    setCustomSetup((prev) => ({ ...prev, ...patch }));
  };

  const clearError = () => setSubmitError(null);

  const setGuidedSelection = (patch: Partial<GuidedStartSelections>) => {
    setGuidedSelections((prev) => ({ ...prev, ...patch }));
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
    setLaunchingGenreKey(null);
  };

  const withCreationRequestId = (payload: NewStoryPayload): NewStoryPayload => {
    const fingerprintPayload = { ...payload, creation_request_id: undefined };
    const fingerprint = JSON.stringify(fingerprintPayload);
    let creationRequest = creationRequestRef.current;
    // Honour an explicit sticky id (Quick Start) when fingerprint is new or matches.
    const explicitId = payload.creation_request_id?.trim() || null;
    if (!creationRequest || creationRequest.fingerprint !== fingerprint) {
      creationRequest = {
        fingerprint,
        id: explicitId || createCreationRequestId(),
      };
      creationRequestRef.current = creationRequest;
    }
    return { ...payload, creation_request_id: creationRequest.id };
  };

  const creationFailure = (error: unknown) => {
    const { message } = friendlyError(error);
    setSubmitError(message);
    releaseSubmit();
  };

  const enterFlow = (flow: CreationFlow) => {
    if (loading) return;
    clearError();
    setScreen(flow);
  };

  const returnToSelection = () => {
    if (loading) return;
    clearError();
    setScreen("select");
  };

  const handleBack = () => {
    if (screen === "select") {
      router.back();
      return;
    }
    returnToSelection();
  };

  const canStartAdvanced =
    (!matureContent.adult_mode_enabled || matureContent.adult_age_confirmed) && !loading;

  const handleAdvancedStart = async () => {
    if (!canStartAdvanced || !beginSubmit()) return;
    try {
      const device_id = await getDeviceId();
      const settings = await getSettings();
      const payload = buildAdvancedStartRequest(customSetup);
      const requestPayload: NewStoryPayload = {
        device_id,
        ...payload,
        debug_mode: settings.debugDefault,
        mature_content: matureContent,
      };
      const res = await newStory(withCreationRequestId(requestPayload));
      if (!res?.session_id) {
        creationFailure(new Error("invalid-session"));
        return;
      }
      router.replace(`/play/${res.session_id}`);
    } catch (e: unknown) {
      creationFailure(e);
    }
  };

  const handleQuickStart = async (option: QuickStartGenre) => {
    if (!beginSubmit()) return;
    setLaunchingGenreKey(option.key);
    try {
      const settings = await getSettings().catch(() => ({
        debugDefault: false,
        fontScale: 1,
        developerUnlocked: false,
      }));
      const device_id = await getDeviceId();
      // Sticky creation_request_id per card so retries keep the same backend scenario pick.
      let attempt = quickAttemptRef.current;
      if (!attempt || attempt.key !== option.key) {
        attempt = { key: option.key, seed: createCreationRequestId() };
        quickAttemptRef.current = attempt;
      }
      const payload = buildQuickStartRequest(option);
      // Quick Start isolation: genre/tone/difficulty/mode + quick_start_key + role.
      // Backend alone selects scenario_id. Never send Guided/Advanced custom fields.
      const requestPayload: NewStoryPayload = {
        device_id,
        genre: payload.genre,
        tone: payload.tone,
        difficulty: payload.difficulty,
        debug_mode: settings.debugDefault,
        mode: payload.mode,
        role: payload.role,
        quick_start_key: payload.quick_start_key,
        creation_request_id: attempt.seed,
      };
      // Fingerprint excludes creation_request_id; sticky seed reused when payload matches.
      const res = await newStory(withCreationRequestId(requestPayload));
      if (!res?.session_id) {
        creationFailure(new Error("invalid-session"));
        return;
      }
      quickAttemptRef.current = null;
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
          <TouchableOpacity onPress={handleBack} hitSlop={12} testID="back-btn">
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
          {submitError ? (
            <View style={styles.errorBanner} testID="new-story-error-banner">
              <Ionicons name="alert-circle-outline" size={18} color={COLORS.primary} />
              <Text style={styles.errorBannerText}>{submitError}</Text>
            </View>
          ) : null}

          {screen === "select" ? (
            <View testID="creation-selection-screen">
              <Text style={styles.pageLabel} testID="new-story-page-label">
                NEW CHRONICLE
              </Text>
              <Text style={styles.pageTitle} testID="new-story-page-title">
                Choose How to Begin
              </Text>
              <Text style={styles.pageHelp} testID="new-story-page-help">
                Three ways into a world that remembers. Your answers set real starting conditions, not a
                scripted plot.
              </Text>

              <View style={styles.selectionList} testID="creation-selection-cards">
                {SELECTION_CARDS.map((card) => (
                  <TouchableOpacity
                    key={card.flow}
                    style={styles.selectionCard}
                    onPress={() => enterFlow(card.flow)}
                    disabled={loading}
                    activeOpacity={0.82}
                    accessibilityRole="button"
                    accessibilityLabel={`${card.title}. ${card.body} Expectation: ${card.expectation}. ${card.cta}.`}
                    accessibilityState={{ disabled: loading }}
                    testID={card.testId}
                  >
                    <Text style={styles.selectionTitle}>{card.title}</Text>
                    <Text style={styles.selectionBody}>{card.body}</Text>
                    <View style={styles.selectionMeta}>
                      <Text style={styles.selectionExpectation}>{card.expectation}</Text>
                      <View style={styles.selectionCta}>
                        <Text style={styles.selectionCtaText}>{card.cta}</Text>
                        <Ionicons name="arrow-forward" size={16} color={COLORS.background} />
                      </View>
                    </View>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          ) : null}

          {screen === "quick" ? (
            <QuickStart
              creationLoading={loading}
              launchingGenreKey={launchingGenreKey}
              fontScale={fontScale}
              onStart={handleQuickStart}
            />
          ) : null}

          {screen === "guided" ? (
            <GuidedStart
              selections={guidedSelections}
              loading={loading}
              fontScale={fontScale}
              onChange={setGuidedSelection}
              onStart={handleGuidedStart}
              onChangePath={returnToSelection}
            />
          ) : null}

          {screen === "advanced" ? (
            <AdvancedBuilder
              loading={loading}
              fontScale={fontScale}
              customSetup={customSetup}
              matureContent={matureContent}
              capabilities={setupCapabilities}
              onSetSetupField={(patch) => {
                clearError();
                setSetupField(patch);
              }}
              onSetMatureContent={(patch) => {
                clearError();
                setMatureContent((current) => ({ ...current, ...patch }));
              }}
              onStart={handleAdvancedStart}
              onChangePath={returnToSelection}
            />
          ) : null}

          {screen === "quick" ? (
            <TouchableOpacity
              style={styles.changePathBtn}
              onPress={returnToSelection}
              disabled={loading}
              testID="quick-change-path"
            >
              <Text style={styles.changePathText}>← Change path</Text>
            </TouchableOpacity>
          ) : null}

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
  container: {
    padding: 20,
    maxWidth: 720,
    width: "100%",
    alignSelf: "center",
  },
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
    fontSize: 32,
    lineHeight: 38,
  },
  pageHelp: {
    marginTop: 12,
    marginBottom: 24,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 16,
    lineHeight: 24,
  },
  selectionList: { gap: 14 },
  selectionCard: {
    minHeight: 148,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    padding: 18,
  },
  selectionTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 24,
    marginBottom: 8,
  },
  selectionBody: {
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    fontSize: 15,
    lineHeight: 22,
    marginBottom: 16,
  },
  selectionMeta: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  selectionExpectation: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 11,
    letterSpacing: 1.5,
  },
  selectionCta: {
    minHeight: 44,
    paddingHorizontal: 14,
    backgroundColor: COLORS.primary,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  selectionCtaText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.background,
    fontSize: 12,
    letterSpacing: 1.2,
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
  changePathBtn: { marginTop: 18 },
  changePathText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 12,
    letterSpacing: 1,
  },
});
