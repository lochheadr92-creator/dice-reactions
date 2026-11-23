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
  Share,
} from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeIn, FadeInDown } from "react-native-reanimated";
import { COLORS, FONTS } from "../../src/theme";
import {
  ApiError,
  getSession,
  getSessionHistory,
  HistoryTurn,
  TurnOutcome,
  sendAction,
  deleteSession,
  exportSession,
  setSessionMode,
  setSessionPlaySettings,
  getActionRequestStatus,
  branchSession,
  pinPassage,
  HandoverResponse,
  Disclosure,
  disclosureActionText,
  MoveRequest,
  moveActionText,
  orderActionText,
  Turn,
  SessionSummary,
} from "../../src/api";
import NotebookPanel from "../../src/NotebookPanel";
import InventoryPanel from "../../src/InventoryPanel";
import ChapterPanel from "../../src/ChapterPanel";
import TellPanel from "../../src/TellPanel";
import OrderPanel from "../../src/OrderPanel";
import MovesPanel from "../../src/MovesPanel";
import { syncAfterActionConflict } from "../../src/action-conflict-sync";
import { resolvePendingActionStatus } from "../../src/action-status-sync";
import { mergeChronicleTurns, maxTurnNumber } from "../../src/chronicle-merge";
import {
  PendingAction,
  buildPendingAction,
  clearPendingAction,
  loadPendingAction,
  resolveRequestId,
  savePendingAction,
} from "../../src/pending-action";
import { getDeviceId, getSettings as getAppSettings } from "../../src/storage";
import { playSettingsFor } from "../../src/prose-length";
import {
  friendlyError,
  ACTION_CONFLICT_EXHAUSTION_MESSAGE,
  ACTION_MISMATCH_MESSAGE,
  ACTION_NOT_SENT_MESSAGE,
  ACTION_PENDING_MESSAGE,
  ACTION_RECOVERED_MESSAGE,
  ACTION_UNCERTAIN_MESSAGE,
} from "../../src/errors";
import { sanitizeParagraphs, sanitizeChoices } from "../../src/sanitize";

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

const DANGER_COLOR_MAP: Record<string, string> = {
  none: COLORS.objective,
  low: "#FBBF24",
  elevated: "#F97316",
  high: COLORS.health,
  critical: COLORS.danger,
};

const MOMENTUM_COLOR_MAP: Record<string, string> = {
  surging: COLORS.objective,
  steady: COLORS.textSecondary,
  stalling: "#FBBF24",
  declining: "#F97316",
  lost: COLORS.danger,
};

// Outcome-card event kinds (player-safe; state dumps belong in the HUD / bag).
const WHY_CHIPS: Record<string, { label: string; color: string }> = {
  opening: { label: "WORLD", color: COLORS.textSecondary },
  action: { label: "YOU", color: COLORS.primary },
  change: { label: "CONSEQUENCE", color: COLORS.objective },
  cast: { label: "CAST", color: COLORS.stress },
  seed: { label: "SET", color: COLORS.textMuted },
  return: { label: "RETURN", color: COLORS.danger },
};

// Words already covered by status chips — omit from the compact condition line.
const CONDITION_CHIP_DUPLICATES = new Set([
  "stable",
  "bruised",
  "wounded",
  "badly wounded",
  "critical",
  "clear",
  "tense",
  "overloaded",
  "distorted",
  "breaking",
  "none",
  "low",
  "elevated",
  "high",
  "surging",
  "steady",
  "stalling",
  "declining",
  "lost",
  "health",
  "stress",
  "fatigue",
  "danger",
  "momentum",
  "pressure",
]);

function chip(state: Record<string, string>, key: string, label: string, colorMap?: Record<string, string>) {
  const v = state[key];
  if (!v) return null;
  const color = colorMap?.[v.toLowerCase()] || COLORS.textSecondary;
  return { label, value: v, color };
}

/**
 * Compact current-condition summary for the HUD.
 * Presentation only — does not mutate turn state.
 */
function compactConditionLine(state: Record<string, string>): string | null {
  const raw = String(state["Conditions"] || state["Notable Conditions"] || "").trim();
  if (!raw) return null;

  const clauses = raw
    .split(/[;|]/)
    .map((part) => part.trim().replace(/\s+/g, " "))
    .filter(Boolean)
    .filter((part) => {
      const lower = part.toLowerCase();
      if (CONDITION_CHIP_DUPLICATES.has(lower)) return false;
      // Drop pure restatements of a chip value ("Health: bruised").
      if (/^(health|stress|fatigue|danger|momentum|pressure)\s*[:=]/i.test(part)) return false;
      return true;
    });

  if (clauses.length === 0) return null;

  // Prefer shorter, distinct clauses; cap to three.
  const picked: string[] = [];
  const seen = new Set<string>();
  for (const clause of clauses) {
    const key = clause.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    picked.push(clause.length > 48 ? `${clause.slice(0, 45).replace(/\s+\S*$/, "").trim()}…` : clause);
    if (picked.length >= 3) break;
  }
  if (picked.length === 0) return null;
  return picked.join(" · ");
}

export default function PlayScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const sessionId = String(id || "");

  const [session, setSession] = useState<SessionSummary | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [syncingConflict, setSyncingConflict] = useState(false);
  // True while the outcome of an already-sent action is being looked up
  // (lost response, reload with a pending action). Blocks resubmission.
  const [resolvingPending, setResolvingPending] = useState(false);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [customAction, setCustomAction] = useState("");
  const [showLedger, setShowLedger] = useState(false);
  const inventoryLineRef = useRef<string | null>(null);
  useEffect(() => {
    if (!showLedger) inventoryLineRef.current = null;
  }, [showLedger]);
  const [showMenu, setShowMenu] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const [showNotebook, setShowNotebook] = useState(false);
  const [notebookKey, setNotebookKey] = useState(0);
  const [showChapter, setShowChapter] = useState(false);
  const [showTell, setShowTell] = useState(false);
  const [showOrder, setShowOrder] = useState(false);
  const [showMoves, setShowMoves] = useState(false);
  const [branching, setBranching] = useState(false);
  const [pinNotice, setPinNotice] = useState<string | null>(null);
  // One request id per branch attempt: a double tap or retry returns the same branch.
  const branchRequestRef = useRef<string | null>(null);
  const [whyHistory, setWhyHistory] = useState<HistoryTurn[]>([]);
  const [latestOutcome, setLatestOutcome] = useState<TurnOutcome | null>(null);
  const [whyLoading, setWhyLoading] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [mode, setMode] = useState<"basic" | "advanced">("advanced");
  const [devUnlocked, setDevUnlocked] = useState(false);
  const [fontScale, setFontScale] = useState(1);
  const scrollRef = useRef<ScrollView>(null);
  // Scroll orchestration. After a turn is appended (or on initial load) we want
  // to land at the TOP of the newest turn — the start of the narration — not at
  // the bottom of the content and not on the choices. We record the newest
  // turn's y-offset on layout and scroll exactly once when a scroll is pending.
  const pendingScrollRef = useRef<null | boolean>(null); // null = no scroll, boolean = animated?
  const latestTurnYRef = useRef(0);
  const deviceIdRef = useRef("");
  const submitGenerationRef = useRef(0);
  const conflictSyncGenerationRef = useRef(0);
  const conflictSyncSignalRef = useRef({ cancelled: false });
  const sessionEpochRef = useRef(0);
  const focusRefreshGenerationRef = useRef(0);
  const mountedRef = useRef(true);
  // The action currently in flight / awaiting an outcome. Keeps ONE request id
  // (and the typed text) until the backend reports completion or failure.
  const pendingActionRef = useRef<PendingAction | null>(null);
  const actionBusy = submitting || syncingConflict || resolvingPending;

  const refreshCausalHistory = useCallback(async () => {
    if (!sessionId || !deviceIdRef.current) return;
    try {
      const res = await getSessionHistory(sessionId, deviceIdRef.current);
      if (!mountedRef.current) return;
      setWhyHistory(res.history || []);
      setLatestOutcome(res.latest_outcome || null);
    } catch {
      // The causal projection is supplemental; play remains usable if it fails.
    }
  }, [sessionId]);

  const refreshSessionReadOnly = useCallback(async () => {
    if (!sessionId || !deviceIdRef.current) return;
    const refreshGen = ++focusRefreshGenerationRef.current;
    const epoch = sessionEpochRef.current;
    const sid = sessionId;
    try {
      const res = await getSession(sid, deviceIdRef.current);
      if (
        !mountedRef.current ||
        refreshGen !== focusRefreshGenerationRef.current ||
        epoch !== sessionEpochRef.current ||
        sid !== sessionId
      ) {
        return;
      }
      setSession(res.session);
      setTurns((prev) => mergeChronicleTurns(prev, res.turns));
      void refreshCausalHistory();
    } catch {
      // Read-only refresh failures are non-fatal.
    }
  }, [refreshCausalHistory, sessionId]);

  // Refresh display preferences and lightly sync chronicle state on focus.
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        try {
          const s = await getAppSettings();
          if (!cancelled) {
            setDevUnlocked(!!s.developerUnlocked);
            setFontScale(s.fontScale || 1);
          }
        } catch {
          if (!cancelled) {
            setDevUnlocked(false);
            setFontScale(1);
          }
        }
        if (!cancelled && deviceIdRef.current && sessionId) {
          await refreshSessionReadOnly();
        }
        // Keep this story on the turn length, writing style and speed chosen in
        // Settings; a failure here only leaves the previous values.
        try {
          const s = await getAppSettings();
          const deviceId = deviceIdRef.current || (await getDeviceId());
          if (!cancelled && sessionId) {
            await setSessionPlaySettings(sessionId, deviceId, playSettingsFor(s));
          }
        } catch {
          // Presentation preference only.
        }
      })();
      return () => {
        cancelled = true;
      };
    }, [sessionId, refreshSessionReadOnly])
  );

  const appendCommittedTurn = useCallback(
    (turn: Turn) => {
      focusRefreshGenerationRef.current += 1;
      setTurns((prev) => mergeChronicleTurns(prev, [turn]));
      pendingScrollRef.current = true;
      void refreshCausalHistory();
    },
    [refreshCausalHistory]
  );

  const settlePendingAction = useCallback(
    async (sid: string, completedTurn?: Turn, pendingText?: string) => {
      pendingActionRef.current = null;
      await clearPendingAction(sid);
      if (completedTurn) {
        appendCommittedTurn(completedTurn);
        // Clear only the text that belonged to the completed action; keep
        // anything the player typed afterwards (e.g. after a reload).
        setCustomAction((current) =>
          pendingText === undefined || current.trim() === pendingText ? "" : current
        );
      }
    },
    [appendCommittedTurn]
  );

  /**
   * Look up the outcome of a sent action WITHOUT resending it. Completed →
   * append the saved turn; failed/unknown → keep id + text for a retry;
   * in_progress → keep id + text and tell the player it is still resolving.
   */
  const resolvePendingAction = useCallback(
    async (
      pending: PendingAction,
      generation: number,
      mode: "recovered" | "uncertain" | "after_conflict"
    ) => {
      const sid = sessionId;
      const epoch = sessionEpochRef.current;
      setResolvingPending(true);
      try {
        const deviceId = deviceIdRef.current || (await getDeviceId());
        deviceIdRef.current = deviceId;
        const result = await resolvePendingActionStatus({
          getActionRequestStatus,
          sessionId: sid,
          requestId: pending.requestId,
          deviceId,
        });
        if (
          !mountedRef.current ||
          sid !== sessionId ||
          epoch !== sessionEpochRef.current ||
          generation !== submitGenerationRef.current
        ) {
          return;
        }
        if (result.status === "completed" && result.turn) {
          await settlePendingAction(sid, result.turn, pending.text);
          setActionNotice(mode === "recovered" ? ACTION_RECOVERED_MESSAGE : null);
          return;
        }
        if (result.status === "in_progress") {
          setActionNotice(ACTION_PENDING_MESSAGE);
          return;
        }
        // failed / unknown: no transition happened; same id + text can be resent.
        // After a lease conflict the conflict guidance already says so.
        if (mode !== "after_conflict") {
          setActionNotice(ACTION_NOT_SENT_MESSAGE);
        }
      } finally {
        if (mountedRef.current) setResolvingPending(false);
      }
    },
    [sessionId, settlePendingAction]
  );

  const load = useCallback(async () => {
    const epoch = sessionEpochRef.current;
    try {
      const deviceId = await getDeviceId();
      deviceIdRef.current = deviceId;
      const res = await getSession(sessionId, deviceId);
      setSession(res.session);
      setTurns(res.turns);
      void refreshCausalHistory();
      // On initial load, land at the start of the most recent turn (no animation).
      pendingScrollRef.current = false;
      setDebugMode(res.session.debug_mode);
      setMode(((res.session as any).mode as "basic" | "advanced") || "advanced");
      // Restore an action whose outcome was never confirmed (reload mid-flight).
      const pending = await loadPendingAction(sessionId);
      if (pending && mountedRef.current && epoch === sessionEpochRef.current) {
        pendingActionRef.current = pending;
        setCustomAction((current) => current || pending.text);
        void resolvePendingAction(pending, submitGenerationRef.current, "recovered");
      }
    } catch (e) {
      console.log("load session", e);
    } finally {
      setLoading(false);
    }
  }, [refreshCausalHistory, resolvePendingAction, sessionId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      conflictSyncSignalRef.current.cancelled = true;
    };
  }, []);

  const isInitialSessionRef = useRef(true);
  useEffect(() => {
    if (isInitialSessionRef.current) {
      isInitialSessionRef.current = false;
      return;
    }
    sessionEpochRef.current += 1;
    focusRefreshGenerationRef.current += 1;
    conflictSyncSignalRef.current.cancelled = true;
    conflictSyncGenerationRef.current += 1;
    pendingActionRef.current = null;
    setResolvingPending(false);
    setSyncingConflict(false);
    setSubmitting(false);
    setActionNotice(null);
    setLoading(true);
    setTurns([]);
    setSession(null);
  }, [sessionId]);

  const runConflictSync = async (generation: number, baselineMaxTurn: number) => {
    conflictSyncSignalRef.current.cancelled = true;
    const signal = { cancelled: false };
    conflictSyncSignalRef.current = signal;
    const syncGen = ++conflictSyncGenerationRef.current;
    const sid = sessionId;
    const epoch = sessionEpochRef.current;

    const shouldApply = () =>
      mountedRef.current &&
      syncGen === conflictSyncGenerationRef.current &&
      generation === submitGenerationRef.current &&
      !signal.cancelled &&
      sid === sessionId &&
      epoch === sessionEpochRef.current;

    setSubmitting(false);
    setSyncingConflict(true);
    setActionNotice("Syncing latest turn…");

    try {
      const deviceId = deviceIdRef.current || (await getDeviceId());
      deviceIdRef.current = deviceId;
      const result = await syncAfterActionConflict({
        getSession,
        sessionId: sid,
        deviceId,
        baselineMaxTurnNumber: baselineMaxTurn,
        signal,
      });

      if (!shouldApply()) {
        return;
      }

      setSession(result.session);
      setTurns((prev) => mergeChronicleTurns(prev, result.turns));
      void refreshCausalHistory();

      if (result.foundNewerTurn) {
        pendingScrollRef.current = true;
        setActionNotice(null);
      } else {
        setActionNotice(ACTION_CONFLICT_EXHAUSTION_MESSAGE);
      }
    } catch {
      if (shouldApply()) {
        setActionNotice(
          "Could not sync the latest turn. Your text has been preserved — try again."
        );
      }
    } finally {
      if (syncGen === conflictSyncGenerationRef.current && mountedRef.current) {
        setSyncingConflict(false);
      }
    }
  };

  const showError = (e: unknown) => {
    const { title, message } = friendlyError(e);
    if (Platform.OS === "web") alert(`${title}\n\n${message}`);
    else Alert.alert(title, message);
  };

  const submit = async (
    text: string,
    extra?: { disclosure?: Disclosure; order?: { recipient: string; text: string }; move?: MoveRequest }
  ) => {
    const disclosure = extra?.disclosure;
    const move = extra?.move;
    const order = extra?.order;
    const trimmed = text.trim();
    if (!trimmed || actionBusy) return;

    const generation = submitGenerationRef.current + 1;
    submitGenerationRef.current = generation;
    conflictSyncSignalRef.current.cancelled = true;

    const baselineMaxTurn = maxTurnNumber(turns);
    const sid = sessionId;
    // Same text + flag as the unresolved action ⇒ same request id (safe retry).
    // Anything else is a deliberate new action and gets a fresh id.
    const requestId = resolveRequestId(pendingActionRef.current, trimmed, debugMode);
    const pending = buildPendingAction(requestId, trimmed, debugMode);
    pendingActionRef.current = pending;
    setSubmitting(true);
    setActionNotice(null);

    try {
      const deviceId = deviceIdRef.current || (await getDeviceId());
      deviceIdRef.current = deviceId;
      await savePendingAction(sid, pending);
      const res = await sendAction({
        session_id: sid,
        device_id: deviceId,
        action_text: trimmed,
        debug_mode: debugMode,
        action_request_id: requestId,
        expected_turn_count: baselineMaxTurn,
        ...(disclosure ? { disclosure } : {}),
        ...(order ? { order } : {}),
        ...(move ? { move } : {}),
      });

      if (generation !== submitGenerationRef.current) return;
      await settlePendingAction(sid, res.turn);
    } catch (e: unknown) {
      if (generation !== submitGenerationRef.current) return;

      if (ApiError.isRequestMismatch(e)) {
        // Our id was already bound to different contents: drop it, keep the text.
        pendingActionRef.current = null;
        await clearPendingAction(sid);
        setActionNotice(ACTION_MISMATCH_MESSAGE);
        return;
      }

      if (ApiError.isConflict(e)) {
        await runConflictSync(generation, baselineMaxTurn);
        if (generation === submitGenerationRef.current && pendingActionRef.current) {
          // The conflicting action may have been our own duplicate: ask, don't resend.
          await resolvePendingAction(pendingActionRef.current, generation, "after_conflict");
        }
        return;
      }

      if (ApiError.isValidation(e)) {
        // Rejected before any work: the id is free to reuse, the text is kept.
        pendingActionRef.current = null;
        await clearPendingAction(sid);
        showError(e);
        return;
      }

      if (e instanceof ApiError) {
        // 429 / 502 / 503: nothing committed; keep id + text for a safe retry.
        // Other statuses (e.g. 404 session gone) cannot be retried meaningfully.
        if (!ApiError.isRateLimited(e) && !ApiError.isRetryableServerError(e)) {
          pendingActionRef.current = null;
          await clearPendingAction(sid);
        }
        showError(e);
        return;
      }

      // Transport failure after sending: the outcome is uncertain. Never resend
      // blindly — look the request up by its id.
      setActionNotice(ACTION_UNCERTAIN_MESSAGE);
      await resolvePendingAction(pending, generation, "uncertain");
    } finally {
      if (generation === submitGenerationRef.current) {
        setSubmitting(false);
      }
    }
  };

  const handleBranch = () => {
    setShowMenu(false);
    if (branching || actionBusy) return;
    const turnCount = maxTurnNumber(turns);
    const doIt = async () => {
      if (!branchRequestRef.current) {
        branchRequestRef.current = `br-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
      }
      setBranching(true);
      try {
        const deviceId = deviceIdRef.current || (await getDeviceId());
        const res = await branchSession(sessionId, deviceId, branchRequestRef.current, turnCount);
        branchRequestRef.current = null;
        router.replace(`/play/${res.session.id}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          // Stale or busy: a retry needs a fresh decision, not the same id.
          branchRequestRef.current = null;
        }
        showError(e);
      } finally {
        if (mountedRef.current) setBranching(false);
      }
    };
    const message =
      "Make a copy of this story at this exact decision. You can take one choice here and the other in the new copy.";
    if (Platform.OS === "web") {
      if (window.confirm(`Branch story from here?\n\n${message}`)) void doIt();
    } else {
      Alert.alert("Branch story from here?", message, [
        { text: "Cancel", style: "cancel" },
        { text: "Branch", onPress: () => void doIt() },
      ]);
    }
  };

  const handlePin = async (turn: Turn, paragraphIndex: number) => {
    try {
      const deviceId = deviceIdRef.current || (await getDeviceId());
      const res = await pinPassage(sessionId, deviceId, {
        turn_number: turn.turn_number,
        paragraph_index: paragraphIndex,
      });
      setNotebookKey((k) => k + 1);
      setPinNotice(res.created ? "Pinned to your notebook." : "Already in your notebook.");
      setTimeout(() => {
        if (mountedRef.current) setPinNotice(null);
      }, 2500);
    } catch (e) {
      showError(e);
    }
  };

  const handleHandoverDone = async (res: HandoverResponse) => {
    setShowChapter(false);
    setSession(res.session);
    try {
      const deviceId = deviceIdRef.current || (await getDeviceId());
      const fresh = await getSession(sessionId, deviceId);
      setSession(fresh.session);
      setTurns((prev) => mergeChronicleTurns(prev, fresh.turns));
      pendingScrollRef.current = true;
      void refreshCausalHistory();
    } catch {
      if (res.turn) appendCommittedTurn(res.turn);
    }
  };

  const handleDelete = () => {
    const doIt = async () => {
      try {
        const deviceId = deviceIdRef.current || (await getDeviceId());
        await deleteSession(sessionId, deviceId);
        pendingActionRef.current = null;
        await clearPendingAction(sessionId);
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
  const visibleChoices = sanitizeChoices(latest.choices);

  const healthChip = chip(state, "Health", "Health", HEALTH_COLOR_MAP);
  const stressChip = chip(state, "Stress", "Stress", STRESS_COLOR_MAP);
  const fatigueChip = chip(state, "Fatigue", "Fatigue");
  const dangerChip = chip(state, "Danger", "Danger", DANGER_COLOR_MAP);
  const momentumChip = chip(state, "Momentum", "Momentum", MOMENTUM_COLOR_MAP);
  const pressure = state["Pressure"];
  const conditionLine = compactConditionLine(state);
  const statusChips = [healthChip, stressChip, fatigueChip, dangerChip, momentumChip].filter(
    Boolean
  ) as { label: string; value: string; color: string }[];
  // Events only — never dump latestOutcome.changes (STATE SHIFT) on the play surface.
  const outcomeEvents = (latestOutcome?.events || []).filter((ev) => ev?.text?.trim());

  return (
    <SafeAreaView style={styles.safe} testID="play-screen">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        {/* Top sticky state bar — single place for current condition */}
        <View style={styles.hudBlock} testID="play-hud">
          <View style={styles.topBar}>
            <TouchableOpacity onPress={() => router.replace("/")} hitSlop={12} testID="exit-play-btn">
              <Ionicons name="chevron-back" size={20} color={COLORS.textSecondary} />
            </TouchableOpacity>

            <View style={styles.statRow}>
              {statusChips.map((item) => (
                <View
                  key={item.label}
                  style={styles.statChip}
                  testID={`state-${item.label.toLowerCase()}`}
                  accessible
                  accessibilityLabel={`${item.label}: ${item.value}`}
                  accessibilityRole="text"
                >
                  <Text style={styles.statKey}>{item.label}</Text>
                  <Text style={styles.statDot}>·</Text>
                  <Text style={[styles.statVal, { color: item.color }]}>{item.value}</Text>
                </View>
              ))}
            </View>

            <View style={styles.topActions}>
              <TouchableOpacity
                onPress={() => setShowLedger(true)}
                hitSlop={10}
                testID="open-ledger-btn"
                accessibilityLabel="Open bag and supplies"
                accessibilityRole="button"
              >
                <Ionicons name="briefcase-outline" size={18} color={COLORS.primary} />
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setShowMoves(true)}
                disabled={actionBusy}
                hitSlop={10}
                testID="open-moves-btn"
                accessibilityLabel="Things you can do here"
                accessibilityRole="button"
              >
                <Ionicons name="hand-left-outline" size={18} color={actionBusy ? COLORS.textMuted : COLORS.primary} />
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setShowMenu(true)} hitSlop={10} testID="open-menu-btn">
                <Ionicons name="ellipsis-horizontal" size={20} color={COLORS.textSecondary} />
              </TouchableOpacity>
            </View>
          </View>

          {session.protagonist?.name || session.branch_label ? (
            <Text style={[styles.characterTag, { paddingHorizontal: 12, marginBottom: 4 }]} numberOfLines={1} testID="hud-identity">
              {[
                session.protagonist?.name ? `YOU ARE ${session.protagonist.name.toUpperCase()}` : null,
                session.branch_label ? session.branch_label.toUpperCase() : null,
              ]
                .filter(Boolean)
                .join("  ·  ")}
            </Text>
          ) : null}

          {conditionLine ? (
            <View style={styles.conditionLine} testID="hud-condition-line">
              <Text style={styles.conditionLabel}>Condition</Text>
              <Text style={styles.conditionDot}>·</Text>
              <Text style={styles.conditionText} numberOfLines={2}>
                {conditionLine}
              </Text>
            </View>
          ) : null}

          {pressure ? (
            <View style={styles.pressureBar} testID="pressure-bar">
              <Text style={styles.pressureLabel}>Pressure</Text>
              <Text style={styles.pressureText} numberOfLines={1}>{pressure}</Text>
            </View>
          ) : null}
        </View>

        {latestOutcome && outcomeEvents.length > 0 ? (
          <View style={styles.outcomeCard} testID="latest-outcome">
            <View style={styles.outcomeHeader}>
              <Text style={styles.outcomeEyebrow}>
                · TURN {String(latestOutcome.turn).padStart(2, "0")} · WHAT CHANGED
              </Text>
              <Text style={styles.outcomeHint}>RECORDED</Text>
            </View>
            {outcomeEvents.map((ev, i) => {
              const chipCfg = WHY_CHIPS[ev.kind] || {
                label: ev.kind.toUpperCase(),
                color: COLORS.textSecondary,
              };
              return (
                <View key={`outcome-event-${i}`} style={styles.outcomeRow}>
                  <Text style={[styles.outcomeChip, { color: chipCfg.color, borderColor: chipCfg.color }]}>
                    {chipCfg.label}
                  </Text>
                  <Text style={styles.outcomeText}>{ev.text}</Text>
                </View>
              );
            })}
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
          {turns.map((turn, i) => {
            const isLatest = i === turns.length - 1;
            return (
            <View
              key={turn.id}
              style={styles.turnBlock}
              onLayout={
                isLatest
                  ? (e) => {
                      const y = e.nativeEvent.layout.y;
                      latestTurnYRef.current = y;
                      if (pendingScrollRef.current !== null) {
                        const animated = pendingScrollRef.current;
                        pendingScrollRef.current = null;
                        // Land a touch above the turn's top so the first line of
                        // narration sits at the top of the viewport. rAF lets the
                        // layout settle before scrolling (works on web + Android).
                        const targetY = Math.max(0, y - 10);
                        requestAnimationFrame(() => {
                          scrollRef.current?.scrollTo({ y: targetY, animated });
                        });
                      }
                    }
                  : undefined
              }
            >
              {turn.player_action ? (
                <View style={styles.playerActionRow}>
                  <Text style={styles.playerActionLabel}>›</Text>
                  <Text style={styles.playerActionText}>{turn.player_action}</Text>
                </View>
              ) : null}

              {turn.character?.name &&
              (i === 0 || turns[i - 1].character?.name !== turn.character.name) ? (
                <Text style={styles.characterTag} testID={`character-tag-${turn.turn_number}`}>
                  · {turn.character.name.toUpperCase()}
                  {turn.character.role ? ` · ${turn.character.role.toUpperCase()}` : ""} ·
                </Text>
              ) : null}

              {(() => {
                const shown = sanitizeParagraphs(turn.paragraphs, turn.narrative);
                // A pin addresses the stored paragraph by index, so it is only offered
                // when the screen shows exactly the stored paragraphs.
                const pinnable = shown.length === (turn.paragraphs || []).length;
                return shown.map((p, idx) => (
                  <View key={idx} style={styles.paragraphRow}>
                    <Animated.Text
                      entering={i === turns.length - 1 ? FadeInDown.duration(420).delay(idx * 90) : FadeIn}
                      style={[
                        styles.proseParagraph,
                        styles.paragraphText,
                        { fontSize: Math.round(18 * fontScale), lineHeight: Math.round(28 * fontScale) },
                      ]}
                      testID={`paragraph-${turn.turn_number}-${idx}`}
                    >
                      {p}
                    </Animated.Text>
                    {pinnable ? (
                      <TouchableOpacity
                        onPress={() => handlePin(turn, idx)}
                        hitSlop={8}
                        style={styles.pinBtn}
                        testID={`pin-btn-${turn.turn_number}-${idx}`}
                        accessibilityRole="button"
                        accessibilityLabel={`Pin paragraph ${idx + 1} of turn ${turn.turn_number} to your notebook`}
                      >
                        <Ionicons name="bookmark-outline" size={16} color={COLORS.textMuted} />
                      </TouchableOpacity>
                    ) : null}
                  </View>
                ));
              })()}

              {devUnlocked && debugMode && turn.debug && Object.keys(turn.debug).length > 0 ? (
                <View style={styles.debugBlock} testID={`debug-block-${turn.turn_number}`}>
                  <Text style={styles.debugHeader}>· DEBUG · TURN {turn.turn_number} ·</Text>
                  {Object.entries(turn.debug).map(([k, v]) => (
                    <View key={k} style={styles.debugLine}>
                      <Text style={styles.debugKey}>{k.toUpperCase()}</Text>
                      <Text style={styles.debugVal}>{v}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              {i < turns.length - 1 && <View style={styles.turnDivider} />}
            </View>
            );
          })}

          {/* Choices for latest turn */}
          {visibleChoices.length > 0 && (
            <View style={styles.choicesWrap} testID="choices-wrap">
              <Text style={styles.choicesHeader}>· CHOOSE ·</Text>
              {visibleChoices.map((c) => (
                <TouchableOpacity
                  key={c.label}
                  style={styles.choiceCard}
                  onPress={() => submit(c.text)}
                  disabled={actionBusy}
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

          {syncingConflict && (
            <View style={styles.thinkingRow} testID="syncing-indicator">
              <ActivityIndicator color={COLORS.primary} size="small" />
              <Text style={styles.thinkingText}>syncing chronicle…</Text>
            </View>
          )}

          {resolvingPending && !syncingConflict && (
            <View style={styles.thinkingRow} testID="resolving-indicator">
              <ActivityIndicator color={COLORS.primary} size="small" />
              <Text style={styles.thinkingText}>checking your last action…</Text>
            </View>
          )}

          {actionNotice ? (
            <View style={styles.actionNoticeRow} testID="action-notice">
              <Text style={styles.actionNoticeText}>{actionNotice}</Text>
            </View>
          ) : null}

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
            editable={!actionBusy}
            onSubmitEditing={() => submit(customAction)}
            returnKeyType="send"
            testID="custom-action-input"
          />
          <TouchableOpacity
            onPress={() => submit(customAction)}
            disabled={!customAction.trim() || actionBusy}
            style={[styles.sendBtn, (!customAction.trim() || actionBusy) && styles.sendBtnDisabled]}
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
              <InventoryPanel
                ledger={ledger}
                summary={state["Inventory Summary"]}
                conditions={state["Notable Conditions"]}
                characterName={session.protagonist?.name}
                busy={submitting}
                onAct={(text) => {
                  // Fill the action box, do not send. A later pick swaps the sentence this panel
                  // added before, and anything the player typed stays.
                  const prev = inventoryLineRef.current;
                  let base = customAction;
                  if (prev && base.includes(prev)) base = base.replace(prev, "").replace(/\s{2,}/g, " ");
                  base = base.trim();
                  inventoryLineRef.current = text;
                  setCustomAction(base ? `${base} ${text}` : text);
                }}
                onClose={() => {
                  inventoryLineRef.current = null;
                  setShowLedger(false);
                }}
                onCheckInStory={() => {
                  setShowLedger(false);
                  submit("I check my inventory carefully.");
                }}
              />
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
            {session.branch_label ? (
              <Text style={styles.menuMeta} testID="menu-branch-label">
                {session.branch_label.toUpperCase()} · from turn {session.branched_from?.turn_number}
              </Text>
            ) : null}

            <TouchableOpacity
              style={styles.menuRow}
              onPress={handleBranch}
              disabled={branching || actionBusy}
              testID="branch-story-btn"
            >
              <Ionicons name="git-branch-outline" size={18} color={COLORS.textSecondary} />
              <Text style={styles.menuText}>Branch story from here</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.menuRow}
              onPress={() => {
                setShowMenu(false);
                setShowNotebook(true);
              }}
              testID="open-notebook-btn"
            >
              <Ionicons name="bookmarks-outline" size={18} color={COLORS.textSecondary} />
              <Text style={styles.menuText}>Notebook</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.menuRow}
              onPress={() => {
                setShowMenu(false);
                setShowTell(true);
              }}
              disabled={actionBusy}
              testID="tell-someone-btn"
            >
              <Ionicons name="chatbubble-ellipses-outline" size={18} color={COLORS.textSecondary} />
              <Text style={styles.menuText}>Tell someone</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.menuRow}
              onPress={() => {
                setShowMenu(false);
                void refreshSessionReadOnly(); // the list inside shows results once they have been seen
                setShowOrder(true);
              }}
              disabled={actionBusy}
              testID="leave-instructions-btn"
            >
              <Ionicons name="clipboard-outline" size={18} color={COLORS.textSecondary} />
              <Text style={styles.menuText}>Leave instructions</Text>
            </TouchableOpacity>

            {!session.handover_done ? (
              <TouchableOpacity
                style={styles.menuRow}
                onPress={() => {
                  setShowMenu(false);
                  setShowChapter(true);
                }}
                disabled={actionBusy}
                testID="end-chapter-btn"
              >
                <Ionicons name="swap-horizontal-outline" size={18} color={COLORS.textSecondary} />
                <Text style={styles.menuText}>End this chapter</Text>
              </TouchableOpacity>
            ) : null}

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
                  const deviceId = deviceIdRef.current || (await getDeviceId());
                  await setSessionMode(sessionId, deviceId, next);
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
                setShowMenu(false);
                setShowWhy(true);
                setWhyLoading(true);
                try {
                  const deviceId = deviceIdRef.current || (await getDeviceId());
                  const res = await getSessionHistory(sessionId, deviceId);
                  setWhyHistory(res.history || []);
                  setLatestOutcome(res.latest_outcome || null);
                } catch (e: any) {
                  const { title, message } = friendlyError(e);
                  if (Platform.OS === "web") alert(`${title}\n\n${message}`);
                  else Alert.alert(title, message);
                  setShowWhy(false);
                } finally {
                  setWhyLoading(false);
                }
              }}
              testID="why-history-btn"
            >
              <Ionicons name="git-branch-outline" size={18} color={COLORS.primary} />
              <Text style={[styles.menuText, { color: COLORS.primary }]}>Why this happened</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.menuRow}
              onPress={async () => {
                try {
                  const deviceId = deviceIdRef.current || (await getDeviceId());
                  const data = await exportSession(sessionId, deviceId);
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
                    const deviceId = deviceIdRef.current || (await getDeviceId());
                    // "Reset" starts a new story. The old chronicle is deleted
                    // rather than left behind as an empty shell (review
                    // 2026-11-20, finding 9).
                    await deleteSession(sessionId, deviceId);
                    pendingActionRef.current = null;
                    await clearPendingAction(sessionId);
                    setShowMenu(false);
                    router.replace(`/new-story?from=reset&sessionTitle=${encodeURIComponent(session.title)}`);
                  } catch (e: any) {
                    const { title, message } = friendlyError(e);
                    Alert.alert(title, message);
                  }
                };
                if (Platform.OS === "web") {
                  if (confirm("Reset this chronicle? It will be deleted and you can start a new story.")) confirmAndRun();
                } else {
                  Alert.alert("Reset chronicle?", "This chronicle will be deleted and you can start a new story.", [
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

      <NotebookPanel
        visible={showNotebook}
        sessionId={sessionId}
        deviceId={deviceIdRef.current}
        refreshKey={notebookKey}
        onClose={() => setShowNotebook(false)}
      />
      <TellPanel
        visible={showTell}
        sessionId={sessionId}
        deviceId={deviceIdRef.current}
        busy={actionBusy}
        onClose={() => setShowTell(false)}
        onSend={(d) => {
          setShowTell(false);
          void submit(disclosureActionText(d), { disclosure: d });
        }}
      />
      <OrderPanel
        visible={showOrder}
        sessionId={sessionId}
        deviceId={deviceIdRef.current}
        busy={actionBusy}
        given={session.orders_given || []}
        onClose={() => setShowOrder(false)}
        onSend={(o) => {
          setShowOrder(false);
          void submit(orderActionText(o), { order: o });
        }}
      />
      <MovesPanel
        visible={showMoves}
        sessionId={sessionId}
        deviceId={deviceIdRef.current}
        busy={actionBusy}
        onClose={() => setShowMoves(false)}
        onSend={(m) => {
          setShowMoves(false);
          void submit(moveActionText(m), { move: m });
        }}
      />
      <ChapterPanel
        visible={showChapter}
        sessionId={sessionId}
        deviceId={deviceIdRef.current}
        turnCount={maxTurnNumber(turns)}
        currentName={session.protagonist?.name || null}
        onClose={() => setShowChapter(false)}
        onDone={handleHandoverDone}
      />
      {pinNotice ? (
        <View style={styles.pinToast} testID="pin-toast" pointerEvents="none">
          <Text style={styles.pinToastText}>{pinNotice}</Text>
        </View>
      ) : null}

      {/* Why this happened — engine-recorded causal history (player-safe) */}
      <Modal visible={showWhy} animationType="slide" transparent onRequestClose={() => setShowWhy(false)}>
        <View style={styles.modalRoot}>
          <View style={styles.ledgerSheet} testID="why-history-modal">
            <View style={styles.whyHead}>
              <Text style={styles.ledgerTitle}>· WHY · THIS · HAPPENED ·</Text>
              <TouchableOpacity onPress={() => setShowWhy(false)} hitSlop={12} testID="close-why-btn">
                <Ionicons name="close" size={20} color={COLORS.textSecondary} />
              </TouchableOpacity>
            </View>
            <Text style={styles.whyIntro}>
              Every line below is recorded world state — written by the engine, not by the narrator.
            </Text>
            {whyLoading ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginTop: 28 }} />
            ) : (
              <ScrollView showsVerticalScrollIndicator={false} testID="why-history-scroll">
                {whyHistory.map((row) => (
                  <View key={row.turn} style={styles.whyTurnBlock}>
                    <Text style={styles.whyTurnHead}>TURN · {String(row.turn).padStart(2, "0")}</Text>
                    {row.events.map((ev, i) => {
                      const chipCfg = WHY_CHIPS[ev.kind] || {
                        label: ev.kind.toUpperCase(),
                        color: COLORS.textSecondary,
                      };
                      return (
                        <View key={`${row.turn}-${i}`} style={styles.whyRow}>
                          <Text style={[styles.whyChip, { color: chipCfg.color, borderColor: chipCfg.color }]}>
                            {chipCfg.label}
                          </Text>
                          <Text style={styles.whyText}>{ev.text}</Text>
                        </View>
                      );
                    })}
                  </View>
                ))}
                {whyHistory.length === 0 && (
                  <Text style={styles.whyEmpty}>— the chronicle has no recorded turns yet —</Text>
                )}
                <View style={{ height: 30 }} />
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  characterTag: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 10,
    letterSpacing: 3,
    marginBottom: 8,
  },
  paragraphRow: { flexDirection: "row", alignItems: "flex-start", gap: 6 },
  paragraphText: { flex: 1 },
  pinBtn: { paddingTop: 6, minWidth: 28, minHeight: 28, alignItems: "center" },
  pinToast: {
    position: "absolute",
    bottom: 90,
    alignSelf: "center",
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.primary,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  pinToastText: { fontFamily: FONTS.mono, color: COLORS.primary, fontSize: 11, letterSpacing: 1 },
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
  hudBlock: {
    backgroundColor: COLORS.background,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
    backgroundColor: COLORS.background,
  },
  statRow: { flex: 1, flexDirection: "row", gap: 8, flexWrap: "wrap" },
  statChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    maxWidth: "100%",
  },
  statKey: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 9,
    letterSpacing: 0.8,
  },
  statDot: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 9,
  },
  statVal: {
    fontFamily: FONTS.mono,
    fontSize: 10,
    letterSpacing: 0.3,
    textTransform: "capitalize",
  },
  topActions: { flexDirection: "row", gap: 14, alignItems: "center" },
  conditionLine: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 6,
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  conditionLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 9,
    letterSpacing: 1,
    marginTop: 2,
  },
  conditionDot: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 9,
    marginTop: 2,
  },
  conditionText: {
    flex: 1,
    fontFamily: FONTS.body,
    color: COLORS.textProse,
    fontSize: 13,
    lineHeight: 18,
  },
  pressureBar: {
    flexDirection: "row",
    gap: 10,
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: COLORS.surfaceDeep,
    borderTopWidth: 1,
    borderTopColor: COLORS.borderDim,
    borderLeftWidth: 2,
    borderLeftColor: COLORS.danger,
  },
  pressureLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.danger,
    fontSize: 9,
    letterSpacing: 1.2,
  },
  pressureText: {
    flex: 1,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textProse,
    fontSize: 14,
  },
  outcomeCard: {
    marginHorizontal: 16,
    marginTop: 10,
    marginBottom: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  outcomeHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  outcomeEyebrow: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 10,
    letterSpacing: 1.5,
  },
  outcomeHint: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 9,
    letterSpacing: 1,
  },
  outcomeRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    marginTop: 6,
  },
  outcomeChip: {
    minWidth: 72,
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderWidth: 1,
    fontFamily: FONTS.monoBold,
    fontSize: 8,
    letterSpacing: 1,
    textAlign: "center",
  },
  outcomeText: {
    flex: 1,
    fontFamily: FONTS.body,
    color: COLORS.textProse,
    fontSize: 15,
    lineHeight: 20,
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
  actionNoticeRow: {
    paddingHorizontal: 20,
    paddingBottom: 12,
  },
  actionNoticeText: {
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    fontSize: 13,
    lineHeight: 18,
    textAlign: "center",
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
  whyHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  whyIntro: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 13,
    lineHeight: 19,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 4,
  },
  whyTurnBlock: {
    paddingHorizontal: 16,
    paddingTop: 14,
  },
  whyTurnHead: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 3,
    marginBottom: 8,
  },
  whyRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
    marginBottom: 8,
  },
  whyChip: {
    fontFamily: FONTS.monoBold,
    fontSize: 9,
    letterSpacing: 1,
    borderWidth: 1,
    borderRadius: 3,
    paddingHorizontal: 5,
    paddingVertical: 2,
    marginTop: 1,
    width: 62,
    textAlign: "center",
    overflow: "hidden",
  },
  whyText: {
    fontFamily: FONTS.body,
    color: COLORS.textProse,
    fontSize: 13,
    lineHeight: 19,
    flex: 1,
  },
  whyEmpty: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 11,
    letterSpacing: 2,
    textAlign: "center",
    marginTop: 28,
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
