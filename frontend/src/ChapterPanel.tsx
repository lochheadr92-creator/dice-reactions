import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "./theme";
import {
  confirmHandover,
  getHandoverCandidates,
  HandoverCandidate,
  HandoverCandidates,
  HandoverResponse,
} from "./api";
import { friendlyError } from "./errors";

type Props = {
  visible: boolean;
  sessionId: string;
  deviceId: string;
  /** Turn count the player is looking at; the server refuses if the story moved on. */
  turnCount: number;
  currentName: string | null;
  onClose: () => void;
  /** Called once the handover is committed and the player has read who they are now. */
  onDone: (res: HandoverResponse) => void;
};

function newRequestId(): string {
  return `ho-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export default function ChapterPanel({
  visible,
  sessionId,
  deviceId,
  turnCount,
  currentName,
  onClose,
  onDone,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [listing, setListing] = useState<HandoverCandidates | null>(null);
  const [picked, setPicked] = useState<HandoverCandidate | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HandoverResponse | null>(null);
  // One id per confirmation attempt: a double tap or a retry cannot hand over twice.
  const requestIdRef = useRef(newRequestId());

  const load = useCallback(async () => {
    if (!sessionId || !deviceId) return;
    setLoading(true);
    setError(null);
    try {
      setListing(await getHandoverCandidates(sessionId, deviceId));
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, deviceId]);

  useEffect(() => {
    if (visible) {
      setPicked(null);
      setResult(null);
      requestIdRef.current = newRequestId();
      void load();
    }
  }, [visible, load]);

  const confirm = async () => {
    if (!picked || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await confirmHandover(sessionId, deviceId, {
        request_id: requestIdRef.current,
        successor_id: picked.id,
        expected_turn_count: turnCount,
      });
      setResult(res);
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setSubmitting(false);
    }
  };

  const former = currentName || "your current character";

  const renderResult = (res: HandoverResponse) => (
    <View testID="handover-result">
      <Text style={styles.eyebrow}>YOU ARE NOW</Text>
      <Text style={styles.bigName} testID="handover-new-name">
        {res.session.protagonist?.name || picked?.name}
      </Text>
      {res.session.protagonist?.role ? <Text style={styles.role}>{res.session.protagonist.role}</Text> : null}
      {(res.turn?.paragraphs || []).map((p, i) => (
        <Text key={i} style={styles.para} testID={`handover-para-${i}`}>
          {p}
        </Text>
      ))}
      <TouchableOpacity style={styles.primaryBtn} onPress={() => onDone(res)} testID="handover-continue-btn">
        <Text style={styles.primaryBtnText}>CONTINUE AS {String(picked?.name || "").toUpperCase()}</Text>
      </TouchableOpacity>
    </View>
  );

  const renderConfirm = (who: HandoverCandidate) => (
    <View testID="handover-confirm">
      <Text style={styles.eyebrow}>CONFIRM</Text>
      <Text style={styles.para}>
        Close this chapter and continue as {who.name}? {former} stays in the world and acts on their own from
        here. Your earlier turns stay as they are. You can do this once per story.
      </Text>
      <View style={styles.btnRow}>
        <TouchableOpacity
          style={[styles.primaryBtn, submitting && { opacity: 0.5 }]}
          onPress={confirm}
          disabled={submitting}
          testID="handover-confirm-btn"
        >
          <Text style={styles.primaryBtnText}>{submitting ? "CHANGING HANDS…" : `BECOME ${who.name.toUpperCase()}`}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.linkBtn} onPress={() => setPicked(null)} disabled={submitting} testID="handover-back-btn">
          <Text style={styles.linkText}>BACK</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const renderList = (data: HandoverCandidates) => {
    if (data.reason === "already_done") {
      return (
        <Text style={styles.para} testID="handover-already-done">
          This story has already changed hands once.
        </Text>
      );
    }
    if (!data.can_end_chapter) {
      return (
        <Text style={styles.para} testID="handover-nobody">
          Nobody you have met can take over yet. Spend more time with the people around you, then come back.
        </Text>
      );
    }
    return (
      <View>
        <Text style={styles.para}>
          Pick someone you have met and are still alive. You continue the same story through their eyes.
        </Text>
        {data.candidates.map((c) => (
          <TouchableOpacity key={c.id} style={styles.card} onPress={() => setPicked(c)} testID={`handover-pick-${c.id}`}>
            <Text style={styles.cardTitle}>{c.name}</Text>
            <Text style={styles.cardMeta}>
              {c.relation.toUpperCase()}
              {c.last_seen ? ` · LAST SEEN ${c.last_seen.toUpperCase()}` : ""}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    );
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <View style={styles.sheet} testID="chapter-modal">
          <View style={styles.head}>
            <Text style={styles.title}>· END THIS CHAPTER ·</Text>
            <TouchableOpacity onPress={onClose} hitSlop={12} testID="close-chapter-btn" disabled={submitting}>
              <Ionicons name="close" size={22} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>
          {error ? (
            <Text style={styles.error} testID="chapter-error">
              {error}
            </Text>
          ) : null}
          <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
            {loading && !listing ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginTop: 24 }} />
            ) : result ? (
              renderResult(result)
            ) : picked ? (
              renderConfirm(picked)
            ) : listing ? (
              renderList(listing)
            ) : null}
            <View style={{ height: 32 }} />
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: COLORS.surface,
    borderTopWidth: 1,
    borderColor: COLORS.border,
    maxHeight: "92%",
    minHeight: "45%",
    width: "100%",
    maxWidth: 640,
    alignSelf: "center",
  },
  head: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  title: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 3 },
  body: { padding: 16 },
  eyebrow: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 10, letterSpacing: 2, marginBottom: 8 },
  bigName: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 28, marginBottom: 2 },
  role: { fontFamily: FONTS.bodyItalic, color: COLORS.textSecondary, fontSize: 15, marginBottom: 14 },
  para: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 16, lineHeight: 24, marginBottom: 12 },
  error: { fontFamily: FONTS.body, color: COLORS.danger, fontSize: 13, paddingHorizontal: 16, paddingTop: 10 },
  card: { borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 10, backgroundColor: COLORS.background, minHeight: 56 },
  cardTitle: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 18, marginBottom: 4 },
  cardMeta: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 10, letterSpacing: 1.5 },
  btnRow: { flexDirection: "row", flexWrap: "wrap", gap: 12, alignItems: "center", marginTop: 6 },
  primaryBtn: {
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    paddingVertical: 14,
    paddingHorizontal: 18,
    alignItems: "center",
    marginTop: 6,
  },
  primaryBtnText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 2 },
  linkBtn: { paddingVertical: 12, paddingHorizontal: 8 },
  linkText: { fontFamily: FONTS.monoBold, color: COLORS.textSecondary, fontSize: 11, letterSpacing: 2 },
});
