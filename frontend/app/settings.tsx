import { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Switch,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../src/theme";
import { getSettings, saveSettings, AppSettings } from "../src/storage";
import {
  getAdminSettings,
  saveAdminSettings,
  AdminSettingsBundle,
  AISettings,
} from "../src/api";

export default function SettingsScreen() {
  const router = useRouter();
  const [settings, setSettings] = useState<AppSettings>({ debugDefault: false, fontScale: 1 });

  // Admin AI
  const [adminLoading, setAdminLoading] = useState(true);
  const [adminBundle, setAdminBundle] = useState<AdminSettingsBundle | null>(null);
  const [aiDraft, setAiDraft] = useState<AISettings | null>(null);
  const [savingAi, setSavingAi] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [showAllModels, setShowAllModels] = useState(false);

  // Hidden developer unlock — 7 taps on version row
  const [devUnlocked, setDevUnlocked] = useState(false);
  const [versionTaps, setVersionTaps] = useState(0);

  useEffect(() => {
    getSettings().then((s) => {
      setSettings(s);
      setDevUnlocked(!!s.developerUnlocked);
    });
  }, []);

  const bumpVersionTap = async () => {
    const next = versionTaps + 1;
    setVersionTaps(next);
    if (next >= 7 && !devUnlocked) {
      setDevUnlocked(true);
      const updated = { ...settings, developerUnlocked: true };
      setSettings(updated);
      await saveSettings(updated);
      // Mirror to server so payload sanitiser opens up
      try {
        const res = await saveAdminSettings({ developer_mode: true } as any);
        if (adminBundle) {
          setAdminBundle({ ...adminBundle, settings: res.settings });
          setAiDraft(res.settings);
        }
      } catch {}
      Alert.alert("Developer access", "Diagnostics unlocked. Scroll to ADMIN · AI ENGINE.");
    }
    setTimeout(() => setVersionTaps(0), 2000);
  };

  const lockDeveloper = async () => {
    setDevUnlocked(false);
    const updated = { ...settings, developerUnlocked: false };
    setSettings(updated);
    await saveSettings(updated);
    // Also turn off the server-side developer_mode so payload stripping resumes
    if (adminBundle) {
      try {
        const res = await saveAdminSettings({ developer_mode: false as any });
        setAdminBundle({ ...adminBundle, settings: res.settings });
        setAiDraft(res.settings);
      } catch {}
    }
  };

  const refreshAdmin = useCallback(async () => {
    try {
      setAdminLoading(true);
      const bundle = await getAdminSettings();
      setAdminBundle(bundle);
      setAiDraft(bundle.settings);
    } catch (e: any) {
      console.warn("Failed to load admin settings", e?.message);
    } finally {
      setAdminLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshAdmin();
  }, [refreshAdmin]);

  const update = async (patch: Partial<AppSettings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    await saveSettings(next);
  };

  const aiDirty =
    !!adminBundle &&
    !!aiDraft &&
    (aiDraft.model !== adminBundle.settings.model ||
      aiDraft.temperature !== adminBundle.settings.temperature ||
      aiDraft.max_tokens !== adminBundle.settings.max_tokens ||
      aiDraft.history_window !== adminBundle.settings.history_window ||
      aiDraft.default_mode !== adminBundle.settings.default_mode ||
      aiDraft.compression_level !== adminBundle.settings.compression_level ||
      aiDraft.memory_depth !== adminBundle.settings.memory_depth);

  const onSaveAi = async () => {
    if (!aiDraft || !adminBundle) return;
    try {
      setSavingAi(true);
      const res = await saveAdminSettings({
        model: aiDraft.model,
        temperature: aiDraft.temperature,
        max_tokens: aiDraft.max_tokens,
        history_window: aiDraft.history_window,
        default_mode: aiDraft.default_mode,
        compression_level: aiDraft.compression_level,
        memory_depth: aiDraft.memory_depth,
      });
      setAdminBundle({ ...adminBundle, settings: res.settings });
      setAiDraft(res.settings);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 1600);
    } catch (e: any) {
      Alert.alert("Save failed", e?.message || "Unknown error");
    } finally {
      setSavingAi(false);
    }
  };

  const onResetAi = () => {
    if (!adminBundle) return;
    setAiDraft(adminBundle.defaults);
  };

  const adjust = (key: keyof AISettings, delta: number, clamp?: { min: number; max: number }) => {
    if (!aiDraft) return;
    let value = (aiDraft[key] as number) + delta;
    if (clamp) value = Math.max(clamp.min, Math.min(clamp.max, value));
    // Round temperature to 2 decimals
    if (key === "temperature") value = Math.round(value * 100) / 100;
    setAiDraft({ ...aiDraft, [key]: value } as AISettings);
  };

  const setField = (patch: Partial<AISettings>) => {
    if (!aiDraft) return;
    setAiDraft({ ...aiDraft, ...patch });
  };

  const currentModelMeta = adminBundle?.models.find((m) => m.id === aiDraft?.model);
  const visibleModels = showAllModels ? adminBundle?.models ?? [] : (adminBundle?.models ?? []).slice(0, 4);

  return (
    <SafeAreaView style={styles.safe} testID="settings-screen">
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} testID="back-btn">
          <Ionicons name="chevron-back" size={22} color={COLORS.textSecondary} />
        </TouchableOpacity>
        <Text style={styles.topTitle}>SETTINGS</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
        <Text style={styles.section}>· READING ·</Text>
        <Text style={styles.rowHelp}>Story prose size.</Text>
        <View style={styles.scaleRow}>
          {[0.9, 1, 1.1, 1.25].map((s) => (
            <TouchableOpacity
              key={s}
              style={[styles.scaleChip, settings.fontScale === s && styles.scaleChipActive]}
              onPress={() => update({ fontScale: s })}
              testID={`font-scale-${s}`}
            >
              <Text
                style={[
                  styles.scaleChipText,
                  settings.fontScale === s && styles.scaleChipTextActive,
                ]}
              >
                {s === 0.9 ? "S" : s === 1 ? "M" : s === 1.1 ? "L" : "XL"}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {devUnlocked && (
          <View style={[styles.row, { marginTop: 28 }]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>DEVELOPER · DIAGNOSTICS</Text>
              <Text style={styles.rowHelp}>
                Reveal hidden rolls, modifiers, and the rolling state. New chronicles will request a debug block from the engine.
              </Text>
            </View>
            <Switch
              value={settings.debugDefault}
              onValueChange={(v) => update({ debugDefault: v })}
              trackColor={{ false: COLORS.border, true: COLORS.primary }}
              thumbColor={settings.debugDefault ? COLORS.primary : COLORS.textMuted}
              testID="debug-default-switch"
            />
          </View>
        )}

        {devUnlocked && (
          <TouchableOpacity
            style={[styles.row, { marginTop: 10 }]}
            onPress={() =>
              Alert.alert(
                "Lock developer mode?",
                "Diagnostics will be hidden and the server will strip developer-facing data from responses.",
                [
                  { text: "Cancel", style: "cancel" },
                  { text: "Lock", style: "destructive", onPress: lockDeveloper },
                ]
              )
            }
            testID="lock-developer"
          >
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>LOCK · DEVELOPER · MODE</Text>
              <Text style={styles.rowHelp}>Hide diagnostics and strip developer data from API responses.</Text>
            </View>
            <Ionicons name="lock-closed-outline" size={18} color={COLORS.textSecondary} />
          </TouchableOpacity>
        )}

        {/* -------------------- ADMIN · AI ENGINE (developer-only) -------------------- */}
        {devUnlocked && (
        <>
        <Text style={[styles.section, { marginTop: 36 }]}>· ADMIN · AI ENGINE ·</Text>

        {adminLoading || !adminBundle || !aiDraft ? (
          <View style={[styles.aboutBox, { alignItems: "center" }]}>
            <ActivityIndicator color={COLORS.primary} />
            <Text style={[styles.rowHelp, { marginTop: 8 }]}>Loading engine settings…</Text>
          </View>
        ) : (
          <View style={styles.aiBox}>
            <View style={styles.providerRow}>
              <View>
                <Text style={styles.providerLabel}>PROVIDER</Text>
                <Text style={styles.providerValue}>OpenRouter</Text>
              </View>
              <View
                style={[
                  styles.statusDot,
                  {
                    backgroundColor: adminBundle.provider_configured
                      ? COLORS.objective
                      : COLORS.danger,
                  },
                ]}
              />
              <Text
                style={[
                  styles.providerStatus,
                  { color: adminBundle.provider_configured ? COLORS.objective : COLORS.danger },
                ]}
              >
                {adminBundle.provider_configured ? "CONFIGURED" : "MISSING KEY"}
              </Text>
            </View>

            <Text style={styles.subSection}>MODEL</Text>
            <View style={styles.modelList}>
              {visibleModels.map((m) => {
                const active = m.id === aiDraft.model;
                return (
                  <TouchableOpacity
                    key={m.id}
                    style={[styles.modelChip, active && styles.modelChipActive]}
                    onPress={() => setAiDraft({ ...aiDraft, model: m.id })}
                    testID={`model-${m.id}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.modelLabel, active && styles.modelLabelActive]}>
                        {m.label}
                      </Text>
                      <Text style={styles.modelMeta}>
                        {m.id} · {Math.round(m.context / 1024)}k ctx
                      </Text>
                      {m.note && <Text style={styles.modelNote}>{m.note}</Text>}
                    </View>
                    {active && (
                      <Ionicons name="checkmark-circle" size={18} color={COLORS.primary} />
                    )}
                  </TouchableOpacity>
                );
              })}
              {!showAllModels && adminBundle.models.length > 4 && (
                <TouchableOpacity
                  style={styles.moreButton}
                  onPress={() => setShowAllModels(true)}
                  testID="show-more-models"
                >
                  <Text style={styles.moreButtonText}>
                    SHOW {adminBundle.models.length - 4} MORE MODELS
                  </Text>
                </TouchableOpacity>
              )}
            </View>

            {currentModelMeta && (
              <Text style={styles.contextHint}>
                Active model context: {currentModelMeta.context.toLocaleString()} tokens
              </Text>
            )}

            <Text style={styles.subSection}>TEMPERATURE · {aiDraft.temperature.toFixed(2)}</Text>
            <View style={styles.stepperRow}>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() =>
                  adjust("temperature", -adminBundle.limits.temperature.step, adminBundle.limits.temperature)
                }
                testID="temp-down"
              >
                <Ionicons name="remove" size={18} color={COLORS.textPrimary} />
              </TouchableOpacity>

              <View style={styles.stepperTrack}>
                <View
                  style={[
                    styles.stepperFill,
                    {
                      width: `${
                        ((aiDraft.temperature - adminBundle.limits.temperature.min) /
                          (adminBundle.limits.temperature.max - adminBundle.limits.temperature.min)) *
                        100
                      }%`,
                    },
                  ]}
                />
              </View>

              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() =>
                  adjust("temperature", adminBundle.limits.temperature.step, adminBundle.limits.temperature)
                }
                testID="temp-up"
              >
                <Ionicons name="add" size={18} color={COLORS.textPrimary} />
              </TouchableOpacity>
            </View>
            <Text style={styles.rowHelp}>
              Lower = focused & predictable. Higher = wilder, more varied prose.
            </Text>

            <Text style={styles.subSection}>MAX · OUTPUT · TOKENS · {aiDraft.max_tokens}</Text>
            <View style={styles.stepperRow}>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() =>
                  adjust("max_tokens", -adminBundle.limits.max_tokens.step, adminBundle.limits.max_tokens)
                }
                testID="tokens-down"
              >
                <Ionicons name="remove" size={18} color={COLORS.textPrimary} />
              </TouchableOpacity>
              <View style={styles.stepperTrack}>
                <View
                  style={[
                    styles.stepperFill,
                    {
                      width: `${
                        ((aiDraft.max_tokens - adminBundle.limits.max_tokens.min) /
                          (adminBundle.limits.max_tokens.max - adminBundle.limits.max_tokens.min)) *
                        100
                      }%`,
                    },
                  ]}
                />
              </View>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() =>
                  adjust("max_tokens", adminBundle.limits.max_tokens.step, adminBundle.limits.max_tokens)
                }
                testID="tokens-up"
              >
                <Ionicons name="add" size={18} color={COLORS.textPrimary} />
              </TouchableOpacity>
            </View>
            <Text style={styles.rowHelp}>
              Cap per response. Higher = longer scenes ({adminBundle.limits.max_tokens.min}–
              {adminBundle.limits.max_tokens.max}).
            </Text>

            <Text style={styles.subSection}>
              CONTEXT · HISTORY · {aiDraft.history_window} TURNS
            </Text>
            <View style={styles.stepperRow}>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() =>
                  adjust(
                    "history_window",
                    -adminBundle.limits.history_window.step,
                    adminBundle.limits.history_window
                  )
                }
                testID="history-down"
              >
                <Ionicons name="remove" size={18} color={COLORS.textPrimary} />
              </TouchableOpacity>
              <View style={styles.stepperTrack}>
                <View
                  style={[
                    styles.stepperFill,
                    {
                      width: `${
                        ((aiDraft.history_window - adminBundle.limits.history_window.min) /
                          (adminBundle.limits.history_window.max - adminBundle.limits.history_window.min)) *
                        100
                      }%`,
                    },
                  ]}
                />
              </View>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() =>
                  adjust(
                    "history_window",
                    adminBundle.limits.history_window.step,
                    adminBundle.limits.history_window
                  )
                }
                testID="history-up"
              >
                <Ionicons name="add" size={18} color={COLORS.textPrimary} />
              </TouchableOpacity>
            </View>
            <Text style={styles.rowHelp}>
              Recent turns replayed each call. Higher = stronger continuity, more tokens used.
            </Text>

            <Text style={styles.subSection}>DEFAULT · ENGINE · MODE</Text>
            <View style={styles.chipRowAdmin}>
              {(["basic", "advanced"] as const).map((m) => {
                const active = (aiDraft.default_mode || "advanced") === m;
                return (
                  <TouchableOpacity
                    key={m}
                    style={[styles.chipAdmin, active && styles.chipAdminActive]}
                    onPress={() => setField({ default_mode: m })}
                    testID={`default-mode-${m}`}
                  >
                    <Text style={[styles.chipAdminText, active && styles.chipAdminTextActive]}>
                      {m.toUpperCase()}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <Text style={styles.rowHelp}>
              The mode applied to new chronicles when none is selected. Per-session mode still wins.
            </Text>

            <Text style={styles.subSection}>COMPRESSION · LEVEL</Text>
            <View style={styles.chipRowAdmin}>
              {(["light", "standard", "aggressive"] as const).map((c) => {
                const active = (aiDraft.compression_level || "standard") === c;
                return (
                  <TouchableOpacity
                    key={c}
                    style={[styles.chipAdmin, active && styles.chipAdminActive]}
                    onPress={() => setField({ compression_level: c })}
                    testID={`compression-${c}`}
                  >
                    <Text style={[styles.chipAdminText, active && styles.chipAdminTextActive]}>
                      {c.toUpperCase()}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <Text style={styles.rowHelp}>
              How aggressively the rolling state should compress older context. Standard is recommended.
            </Text>

            <Text style={styles.subSection}>
              MEMORY · DEPTH · {aiDraft.memory_depth ?? 3} TURNS
            </Text>
            <View style={styles.stepperRow}>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() =>
                  adjust(
                    "memory_depth" as any,
                    -(adminBundle.limits.memory_depth?.step || 1),
                    adminBundle.limits.memory_depth || { min: 0, max: 10 }
                  )
                }
                testID="memory-down"
              >
                <Ionicons name="remove" size={18} color={COLORS.textPrimary} />
              </TouchableOpacity>
              <View style={styles.stepperTrack}>
                <View
                  style={[
                    styles.stepperFill,
                    {
                      width: `${
                        (((aiDraft.memory_depth ?? 3) - (adminBundle.limits.memory_depth?.min || 0)) /
                          ((adminBundle.limits.memory_depth?.max || 10) - (adminBundle.limits.memory_depth?.min || 0))) *
                        100
                      }%`,
                    },
                  ]}
                />
              </View>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() =>
                  adjust(
                    "memory_depth" as any,
                    adminBundle.limits.memory_depth?.step || 1,
                    adminBundle.limits.memory_depth || { min: 0, max: 10 }
                  )
                }
                testID="memory-up"
              >
                <Ionicons name="add" size={18} color={COLORS.textPrimary} />
              </TouchableOpacity>
            </View>
            <Text style={styles.rowHelp}>
              Recent turns replayed verbatim ON TOP of the compressed rolling state. 3 is a good default.
            </Text>

            <View style={styles.actionRow}>
              <TouchableOpacity
                style={[styles.actionBtn, styles.actionBtnGhost]}
                onPress={onResetAi}
                testID="ai-reset"
              >
                <Text style={styles.actionBtnGhostText}>RESET</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[
                  styles.actionBtn,
                  styles.actionBtnPrimary,
                  (!aiDirty || savingAi) && styles.actionBtnDisabled,
                ]}
                onPress={onSaveAi}
                disabled={!aiDirty || savingAi}
                testID="ai-save"
              >
                {savingAi ? (
                  <ActivityIndicator color={COLORS.background} size="small" />
                ) : (
                  <Text style={styles.actionBtnPrimaryText}>
                    {savedFlash ? "SAVED ✓" : aiDirty ? "SAVE" : "UP TO DATE"}
                  </Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        )}
        </>
        )}

        <Text style={[styles.section, { marginTop: 36 }]}>· ABOUT ·</Text>
        <TouchableOpacity activeOpacity={1} onPress={bumpVersionTap} style={styles.aboutBox} testID="version-tap">
          <Text style={styles.aboutTitle}>Dice Reaction Story Engine</Text>
          <Text style={styles.aboutVer}>
            Master Runtime · v3.4{devUnlocked ? "  ·  DEV" : ""}
          </Text>
          <Text style={styles.aboutBody}>
            A persistent causal simulation. Every action resolved through hidden D20 logic. Failure
            redirects, success costs, and consequences carry. Powered by OpenRouter.
          </Text>
        </TouchableOpacity>
      </ScrollView>
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
  container: { padding: 20, paddingBottom: 48 },
  section: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 11,
    letterSpacing: 4,
    marginBottom: 14,
  },
  subSection: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 10,
    letterSpacing: 3,
    marginTop: 18,
    marginBottom: 8,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 16,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
    gap: 12,
  },
  rowTitle: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textPrimary,
    fontSize: 11,
    letterSpacing: 2,
  },
  rowHelp: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 13,
    marginTop: 4,
    lineHeight: 18,
  },
  scaleRow: { flexDirection: "row", gap: 8, marginTop: 12 },
  scaleChip: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
  },
  scaleChipActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  scaleChipText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 12,
    letterSpacing: 2,
  },
  scaleChipTextActive: { color: COLORS.primary },
  aboutBox: {
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
  },
  aboutTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 22,
    marginBottom: 4,
  },
  aboutVer: {
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 2,
    marginBottom: 12,
  },
  aboutBody: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textProse,
    fontSize: 14,
    lineHeight: 21,
  },

  // AI admin
  aiBox: {
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
  },
  providerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  providerLabel: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 9,
    letterSpacing: 2,
  },
  providerValue: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 18,
    marginTop: 2,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginLeft: "auto",
  },
  providerStatus: {
    fontFamily: FONTS.monoBold,
    fontSize: 10,
    letterSpacing: 2,
  },
  modelList: { gap: 8 },
  modelChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.background,
  },
  modelChipActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  modelLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textPrimary,
    fontSize: 12,
    letterSpacing: 1,
  },
  modelLabelActive: { color: COLORS.primary },
  modelMeta: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 10,
    marginTop: 2,
  },
  modelNote: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 12,
    marginTop: 4,
  },
  moreButton: {
    paddingVertical: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    borderStyle: "dashed",
  },
  moreButtonText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 10,
    letterSpacing: 2,
  },
  contextHint: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 10,
    marginTop: 8,
    letterSpacing: 1,
  },
  stepperRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  stepperBtn: {
    width: 36,
    height: 36,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.background,
  },
  stepperTrack: {
    flex: 1,
    height: 8,
    backgroundColor: COLORS.border,
    overflow: "hidden",
  },
  stepperFill: {
    height: "100%",
    backgroundColor: COLORS.primary,
  },
  actionRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 20,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
  actionBtnGhost: {
    borderColor: COLORS.border,
    backgroundColor: COLORS.background,
  },
  actionBtnGhostText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 11,
    letterSpacing: 2,
  },
  actionBtnPrimary: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primary,
  },
  actionBtnPrimaryText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.background,
    fontSize: 11,
    letterSpacing: 2,
  },
  actionBtnDisabled: {
    opacity: 0.5,
  },
  chipRowAdmin: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  chipAdmin: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.background,
  },
  chipAdminActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  chipAdminText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 10,
    letterSpacing: 2,
  },
  chipAdminTextActive: { color: COLORS.primary },
});
