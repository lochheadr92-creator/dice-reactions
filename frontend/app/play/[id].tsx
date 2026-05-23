import { useEffect, useState, useRef, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Modal,
  Alert,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeIn, FadeInDown } from "react-native-reanimated";
import { COLORS, FONTS } from "../../src/theme";
import { getSession, sendAction, deleteSession, exportSession, resetSession, setSessionMode, Turn, SessionSummary } from "../../src/api";
import { getSettings as getAppSettings } from "../../src/storage";
import { friendlyError } from "../../src/errors";
import { Share } from "react-native";

const HEALTH_COLOR_MAP: Record<string, string> = {
  stable: COLORS.objective,
  bruised: "#FBBF24",
  wounded: "#F97316",
  "badly wounded": COLORS.health,
  critical: COLORS.danger,
};

const STRESS_COLOR_MAP: Record<string, string> = {
  clear: COLORS.objective,
  tense: "#FBBF24",
  overloaded: "#F97316",
  distorted: COLORS.stress,
  breaking: COLORS.danger,
};

function chip(state: Record<string, string>, key: string, label: string, colorMap?: Record<string, string>) {
  const v = state[key];
  if (!v) return null;
  const color = colorMap?.[v.toLowerCase()] || COLORS.textSecondary;
  return { label, value: v, color };
}

export default function PlayScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const sessionId = String(id || "");

  const [session, setSession] = useState<SessionSummary | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [customAction, setCustomAction] = useState("");
  const [showLedger, setShowLedger] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [mode, setMode] = useState<"basic" | "advanced">("advanced");
  const scrollRef = useRef<ScrollView>(null);

  const load = useCallback(async () => {
    try {
      const res = await getSession(sessionId);
      setSession(res.session);
      setTurns(res.turns);
      setDebugMode(res.session.debug_mode);
      setMode(((res.session as any).mode as "basic" | "advanced") || "advanced");
    } catch (e) {
      console.log("load session", e);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 120);
    return () => clearTimeout(t);
  }, [turns.length]);

  const submit = async (text: string) => {
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    try {
      const res = await sendAction({
        session_id: sessionId,
        action_text: text.trim(),
        debug_mode: debugMode,
      });
      setTurns((prev) => [...prev, res.turn]);
      setCustomAction("");
    } catch (e: any) {
      const { title, message } = friendlyError(e);
      if (Platform.OS === "web") alert(`${title}\n\n${message}`);
      else Alert.alert(title, message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = () => {
    const doIt = async () => {
      try {
        await deleteSession(sessionId);
        router.replace("/");
      } catch (e) {
        console.log(e);
      }
    };
    if (Platform.OS === "web") {
      if (window.confirm("Delete this chronicle? Cannot be undone.")) doIt();
    } else {
      Alert.alert("Delete Chronicle", "This cannot be undone.", [
        { text: "Cancel", style: "cancel" },
        { text: "Delete", style: "destructive", onPress: doIt },
      ]);
    }
    setShowMenu(false);
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={COLORS.primary} />
          <Text style={styles.loadingText}>summoning the world…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!session || turns.length === 0) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loadingWrap}>
          <Text style={styles.loadingText}>chronicle not found.</Text>
          <TouchableOpacity onPress={() => router.replace("/")} style={{ marginTop: 12 }}>
            <Text style={styles.linkBack}>[ return to menu ]</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const latest = turns[turns.length - 1];
  const state = latest.state || {};
  const ledger = latest.ledger || {};

  const healthChip = chip(state, "Health", "HP", HEALTH_COLOR_MAP);
  const stressChip = chip(state, "Stress", "STR", STRESS_COLOR_MAP);
  const fatigueChip = chip(state, "Fatigue", "FTG");
  const objective = state["Objective"];

  return (
    <SafeAreaView style={styles.safe} testID="play-screen">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        {/* Top sticky state bar */}
        <View style={styles.topBar}>
          <TouchableOpacity onPress={() => router.replace("/")} hitSlop={12} testID="exit-play-btn">
            <Ionicons name="chevron-back" size={20} color={COLORS.textSecondary} />
          </TouchableOpacity>

          <View style={styles.statRow}>
            {healthChip && (
              <View style={styles.statChip} testID="state-health">
                <Text style={styles.statKey}>{healthChip.label}</Text>
                <Text style={[styles.statVal, { color: healthChip.color }]}>{healthChip.value}</Text>
              </View>
            )}
            {stressChip && (
              <View style={styles.statChip} testID="state-stress">
                <Text style={styles.statKey}>{stressChip.label}</Text>
                <Text style={[styles.statVal, { color: stressChip.color }]}>{stressChip.value}</Text>
              </View>
            )}
            {fatigueChip && (
              <View style={styles.statChip} testID="state-fatigue">
                <Text style={styles.statKey}>{fatigueChip.label}</Text>
                <Text style={[styles.statVal, { color: COLORS.textSecondary }]}>{fatigueChip.value}</Text>
              </View>
            )}
          </View>

          <View style={styles.topActions}>
            <TouchableOpacity onPress={() => setShowLedger(true)} hitSlop={10} testID="open-ledger-btn">
              <Ionicons name="briefcase-outline" size={18} color={COLORS.primary} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowMenu(true)} hitSlop={10} testID="open-menu-btn">
              <Ionicons name="ellipsis-horizontal" size={20} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>
        </View>

        {objective ? (
          <View style={styles.objectiveBar} testID="objective-bar">
            <Text style={styles.objectiveLabel}>OBJ</Text>
            <Text style={styles.objectiveText} numberOfLines={1}>{objective}</Text>
          </View>
        ) : null}

        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
          testID="story-scroll"
        >
          {turns.map((turn, i) => (
            <View key={turn.id} style={styles.turnBlock}>
              {turn.player_action ? (
                <View style={styles.playerActionRow}>
                  <Text style={styles.playerActionLabel}>›</Text>
                  <Text style={styles.playerActionText}>{turn.player_action}</Text>
                </View>
              ) : null}

              {(turn.paragraphs && turn.paragraphs.length > 0
                ? turn.paragraphs
                : [turn.narrative]
              ).map((p, idx) => (
                <Animated.Text
                  key={idx}
                  entering={i === turns.length - 1 ? FadeInDown.duration(420).delay(idx * 90) : FadeIn}
                  style={styles.proseParagraph}
                  testID={`paragraph-${turn.turn_number}-${idx}`}
                >
                  {p}
                </Animated.Text>
              ))}

              {debugMode && turn.debug && (
                <View style={styles.debugBlock} testID={`debug-block-${turn.turn_number}`}>
                  <Text style={styles.debugHeader}>· DEBUG · TURN {turn.turn_number} ·</Text>
                  {Object.entries(turn.debug).map(([k, v]) => (
                    <View key={k} style={styles.debugLine}>
                      <Text style={styles.debugKey}>{k.toUpperCase()}</Text>
                      <Text style={styles.debugVal}>{v}</Text>
                    </View>
                  ))}
                </View>
              )}

              {debugMode && turn.rolling_state && (
                <View style={styles.debugBlock} testID={`rolling-state-${turn.turn_number}`}>
                  <Text style={styles.debugHeader}>· ROLLING · STATE ·</Text>
                  {Object.entries(turn.rolling_state).map(([k, v]) => {
                    let display: string;
                    if (typeof v === "string") display = v;
                    else if (Array.isArray(v)) {
                      display = v
                        .map((x) =>
                          typeof x === "string"
                            ? x
                            : x?.name
                            ? `${x.name}${x.stance ? ` (${x.stance})` : ""}${x.note ? ` — ${x.note}` : ""}`
                            : JSON.stringify(x)
                        )
                        .join(" · ");
                    } else if (v && typeof v === "object") {
                      display = Object.entries(v as any)
                        .map(([kk, vv]) => `${kk}: ${vv}`)
                        .join(" · ");
                    } else {
                      display = String(v);
                    }
                    return (
                      <View key={k} style={styles.debugLine}>
                        <Text style={styles.debugKey}>{k.toUpperCase()}</Text>
                        <Text style={styles.debugVal}>{display}</Text>
                      </View>
                    );
                  })}
                </View>
              )}

              {i < turns.length - 1 && <View style={styles.turnDivider} />}
            </View>
          ))}

          {/* Choices for latest turn */}
          {latest.choices && latest.choices.length > 0 && (
            <View style={styles.choicesWrap} testID="choices-wrap">
              <Text style={styles.choicesHeader}>· CHOOSE ·</Text>
              {latest.choices.map((c, idx) => (
                <TouchableOpacity
                  key={c.label}
                  style={styles.choiceCard}
                  onPress={() => submit(c.text)}
                  disabled={submitting}
                  testID={`choice-${c.label}`}
                  activeOpacity={0.7}
                >
                  <Text style={styles.choiceLabel}>[{c.label}]</Text>
                  <Text style={styles.choiceText}>{c.text}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          {submitting && (
            <View style={styles.thinkingRow} testID="thinking-indicator">
              <ActivityIndicator color={COLORS.primary} size="small" />
              <Text style={styles.thinkingText}>the dice fall…</Text>
            </View>
          )}

          <View style={{ height: 24 }} />
        </ScrollView>

        {/* Custom action input */}
        <View style={styles.inputBar}>
          <Text style={styles.prompt}>{">"}</Text>
          <TextInput
            value={customAction}
            onChangeText={setCustomAction}
            placeholder="or type your own action…"
            placeholderTextColor={COLORS.textMuted}
            style={styles.actionInput}
            editable={!submitting}
            onSubmitEditing={() => submit(customAction)}
            returnKeyType="send"
            testID="custom-action-input"
          />
          <TouchableOpacity
            onPress={() => submit(customAction)}
            disabled={!customAction.trim() || submitting}
            style={[styles.sendBtn, (!customAction.trim() || submitting) && styles.sendBtnDisabled]}
            testID="send-action-btn"
          >
            <Ionicons name="arrow-forward" size={16} color={COLORS.background} />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>

      {/* Ledger Modal */}
      <Modal visible={showLedger} animationType="slide" transparent onRequestClose={() => setShowLedger(false)}>
        <View style={styles.modalRoot}>
          <View style={styles.ledgerSheet} testID="ledger-modal">
            <View style={styles.ledgerHead}>
              <Text style={styles.ledgerTitle}>· INVENTORY · LEDGER ·</Text>
              <TouchableOpacity onPress={() => setShowLedger(false)} hitSlop={12} testID="close-ledger-btn">
                <Ionicons name="close" size={22} color={COLORS.textSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ padding: 16 }} showsVerticalScrollIndicator={false}>
              {Object.keys(ledger).length === 0 ? (
                <Text style={styles.ledgerEmpty}>— no ledger yet —</Text>
              ) : (
                Object.entries(ledger).map(([k, v]) => (
                  <View key={k} style={styles.ledgerCell} testID={`ledger-${k}`}>
                    <Text style={styles.ledgerKey}>{k.toUpperCase()}</Text>
                    <Text style={styles.ledgerVal}>{String(v) || "—"}</Text>
                  </View>
                ))
              )}
              {state["Inventory Summary"] && (
                <View style={[styles.ledgerCell, styles.ledgerCellAccent]}>
                  <Text style={styles.ledgerKey}>SUMMARY</Text>
                  <Text style={styles.ledgerVal}>{state["Inventory Summary"]}</Text>
                </View>
              )}
              {state["Notable Conditions"] && (
                <View style={[styles.ledgerCell, styles.ledgerCellAccent]}>
                  <Text style={styles.ledgerKey}>CONDITIONS</Text>
                  <Text style={styles.ledgerVal}>{state["Notable Conditions"]}</Text>
                </View>
              )}
              <TouchableOpacity
                style={styles.ledgerCheckBtn}
                onPress={() => {
                  setShowLedger(false);
                  submit("I check my inventory carefully.");
                }}
                testID="ledger-check-action"
              >
                <Text style={styles.ledgerCheckText}>[ CHECK · GEAR · IN · STORY ]</Text>
              </TouchableOpacity>
              <View style={{ height: 30 }} />
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Menu Modal */}
      <Modal visible={showMenu} transparent animationType="fade" onRequestClose={() => setShowMenu(false)}>
        <TouchableOpacity style={styles.menuRoot} activeOpacity={1} onPress={() => setShowMenu(false)}>
          <View style={styles.menuSheet} testID="menu-sheet">
            <Text style={styles.menuHead}>· CHRONICLE ·</Text>
            <Text style={styles.menuMeta}>{session.genre.toUpperCase()} · {session.difficulty} · turn {session.turn_count}</Text>

            {devUnlocked && (
              <TouchableOpacity
                style={styles.menuRow}
                onPress={() => {
                  setDebugMode((v) => !v);
                }}
                testID="toggle-debug-menu"
              >
                <Ionicons name={debugMode ? "eye" : "eye-off-outline"} size={18} color={debugMode ? COLORS.primary : COLORS.textSecondary} />
                <Text style={[styles.menuText, debugMode && { color: COLORS.primary }]}>
                  {debugMode ? "Diagnostics · ON  (next turn)" : "Diagnostics · OFF"}
                </Text>
              </TouchableOpacity>
            )}

            <TouchableOpacity
              style={styles.menuRow}
              onPress={async () => {
                const next = mode === "basic" ? "advanced" : "basic";
                try {
                  await setSessionMode(sessionId, next);
                  setMode(next);
                } catch (e: any) {
                  const { title, message } = friendlyError(e);
                  if (Platform.OS === "web") alert(`${title}\n\n${message}`);
                  else Alert.alert(title, message);
                }
              }}
              testID="toggle-mode-menu"
            >
              <Ionicons name="layers-outline" size={18} color={COLORS.textSecondary} />
              <Text style={styles.menuText}>Mode · {mode.toUpperCase()}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.menuRow}
              onPress={async () => {
                try {
                  const data = await exportSession(sessionId);
                  const json = JSON.stringify(data, null, 2);
                  if (Platform.OS === "web") {
                    try {
                      await (navigator as any).clipboard?.writeText(json);
                      alert(`Session exported · ${data.summary.turn_count} turns · copied to clipboard.`);
                    } catch {
                      alert(json.slice(0, 2000) + (json.length > 2000 ? "\n…(truncated)" : ""));
                    }
                  } else {
                    await Share.share({
                      title: `${session.title} · export`,
                      message: json,
                    });
                  }
                  setShowMenu(false);
                } catch (e: any) {
                  const { title, message } = friendlyError(e);
                  Alert.alert(title, message);
                }
              }}
              testID="export-session-btn"
            >
              <Ionicons name="share-outline" size={18} color={COLORS.textSecondary} />
              <Text style={styles.menuText}>Export session state</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.menuRow}
              onPress={() => {
                const confirmAndRun = async () => {
                  try {
                    await resetSession(sessionId);
                    setShowMenu(false);
                    router.replace(`/new-story?from=reset&sessionTitle=${encodeURIComponent(session.title)}`);
                  } catch (e: any) {
                    const { title, message } = friendlyError(e);
                    Alert.alert(title, message);
                  }
                };
                if (Platform.OS === "web") {
                  if (confirm("Reset this chronicle? All turns and rolling state will be wiped.")) confirmAndRun();
                } else {
                  Alert.alert("Reset chronicle?", "All turns and rolling state will be wiped. The session shell stays.", [
                    { text: "Cancel", style: "cancel" },
                    { text: "Reset", style: "destructive", onPress: confirmAndRun },
                  ]);
                }
              }}
              testID="reset-session-btn"
            >
              <Ionicons name="refresh-outline" size={18} color={COLORS.textSecondary} />
              <Text style={styles.menuText}>Reset chronicle</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.menuRow}
              onPress={() => {
                setShowMenu(false);
                router.replace("/");
              }}
              testID="back-to-menu-btn"
            >
              <Ionicons name="home-outline" size={18} color={COLORS.textSecondary} />
              <Text style={styles.menuText}>Return to menu</Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.menuRow} onPress={handleDelete} testID="delete-chronicle-btn">
              <Ionicons name="trash-outline" size={18} color={COLORS.danger} />
              <Text style={[styles.menuText, { color: COLORS.danger }]}>Delete chronicle</Text>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  loadingWrap: { flex: 1, alignItems: "center", justifyContent: "center" },
  loadingText: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 14,
    marginTop: 14,
    letterSpacing: 1,
  },
  linkBack: {
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 12,
    letterSpacing: 2,
  },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
    backgroundColor: COLORS.background,
  },
  statRow: { flex: 1, flexDirection: "row", gap: 10, flexWrap: "wrap" },
  statChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
  },
  statKey: { fontFamily: FONTS.monoBold, color: COLORS.textMuted, fontSize: 9, letterSpacing: 1 },
  statVal: { fontFamily: FONTS.mono, fontSize: 10, letterSpacing: 0.5 },
  topActions: { flexDirection: "row", gap: 14, alignItems: "center" },
  objectiveBar: {
    flexDirection: "row",
    gap: 10,
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: COLORS.surfaceDeep,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  objectiveLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.objective,
    fontSize: 9,
    letterSpacing: 2,
  },
  objectiveText: {
    flex: 1,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textProse,
    fontSize: 14,
  },
  scroll: { paddingHorizontal: 22, paddingTop: 18 },
  turnBlock: { marginBottom: 8 },
  playerActionRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 14,
    paddingLeft: 6,
    borderLeftWidth: 2,
    borderLeftColor: COLORS.primary,
  },
  playerActionLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 14,
  },
  playerActionText: {
    flex: 1,
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 13,
    letterSpacing: 0.5,
    paddingTop: 1,
  },
  proseParagraph: {
    fontFamily: FONTS.body,
    color: COLORS.textProse,
    fontSize: 18,
    lineHeight: 28,
    marginBottom: 14,
    letterSpacing: 0.2,
  },
  turnDivider: {
    height: 1,
    backgroundColor: COLORS.borderDim,
    marginVertical: 14,
    marginHorizontal: 60,
  },
  debugBlock: {
    marginTop: 6,
    marginBottom: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
  },
  debugHeader: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 10,
    letterSpacing: 3,
    marginBottom: 8,
  },
  debugLine: { flexDirection: "row", gap: 8, marginBottom: 4 },
  debugKey: { fontFamily: FONTS.monoBold, color: COLORS.textMuted, fontSize: 10, width: 90, letterSpacing: 1 },
  debugVal: { fontFamily: FONTS.mono, color: COLORS.textProse, fontSize: 11, flex: 1 },
  choicesWrap: { marginTop: 12, marginBottom: 18 },
  choicesHeader: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 10,
    letterSpacing: 4,
    textAlign: "center",
    marginBottom: 14,
    marginTop: 8,
  },
  choiceCard: {
    flexDirection: "row",
    gap: 10,
    paddingVertical: 14,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: "transparent",
    marginBottom: 10,
  },
  choiceLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 13,
    letterSpacing: 1,
    minWidth: 26,
  },
  choiceText: {
    flex: 1,
    fontFamily: FONTS.body,
    color: COLORS.textProse,
    fontSize: 16,
    lineHeight: 22,
  },
  thinkingRow: {
    flexDirection: "row",
    gap: 10,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 18,
  },
  thinkingText: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 13,
    letterSpacing: 1,
  },
  inputBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
  },
  prompt: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 16 },
  actionInput: {
    flex: 1,
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 13,
    paddingVertical: 8,
  },
  sendBtn: {
    width: 36,
    height: 36,
    backgroundColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  sendBtnDisabled: { opacity: 0.3 },
  modalRoot: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.7)",
    justifyContent: "flex-end",
  },
  ledgerSheet: {
    maxHeight: "80%",
    backgroundColor: COLORS.background,
    borderTopWidth: 1,
    borderTopColor: COLORS.primary,
  },
  ledgerHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  ledgerTitle: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 4,
  },
  ledgerEmpty: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 14,
    textAlign: "center",
    paddingVertical: 30,
  },
  ledgerCell: {
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    padding: 12,
    marginBottom: 6,
    backgroundColor: COLORS.surfaceDeep,
  },
  ledgerCellAccent: { borderColor: COLORS.primary },
  ledgerKey: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 10,
    letterSpacing: 2,
    marginBottom: 4,
  },
  ledgerVal: {
    fontFamily: FONTS.mono,
    color: COLORS.textProse,
    fontSize: 12,
    lineHeight: 18,
  },
  ledgerCheckBtn: {
    marginTop: 14,
    paddingVertical: 14,
    borderWidth: 1,
    borderColor: COLORS.primary,
    alignItems: "center",
    backgroundColor: COLORS.primarySoft,
  },
  ledgerCheckText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 3,
  },
  menuRoot: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.7)",
    justifyContent: "center",
    alignItems: "center",
  },
  menuSheet: {
    width: "85%",
    maxWidth: 360,
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 18,
  },
  menuHead: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 4,
    textAlign: "center",
  },
  menuMeta: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 1.5,
    textAlign: "center",
    marginTop: 6,
    marginBottom: 18,
  },
  menuRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 14,
    borderTopWidth: 1,
    borderTopColor: COLORS.borderDim,
  },
  menuText: {
    fontFamily: FONTS.mono,
    color: COLORS.textPrimary,
    fontSize: 13,
    letterSpacing: 1,
  },
});
