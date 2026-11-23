import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "./theme";
import { getTellTargets, OrderGiven, OrderPreview, previewOrder } from "./api";
import { friendlyError } from "./errors";

type Props = {
  visible: boolean;
  sessionId: string;
  deviceId: string;
  busy: boolean;
  given: OrderGiven[];
  onClose: () => void;
  /** Sent as a normal story action: one action, the same cost as anything else. */
  onSend: (o: { recipient: string; text: string }) => void;
};

const MAX_TEXT = 280;

export default function OrderPanel({ visible, sessionId, deviceId, busy, given, onClose, onSend }: Props) {
  const [loading, setLoading] = useState(false);
  const [people, setPeople] = useState<string[] | null>(null);
  const [who, setWho] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<OrderPreview | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!sessionId || !deviceId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getTellTargets(sessionId, deviceId);
      setPeople(res.people.map((p) => p.name));
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, deviceId]);

  useEffect(() => {
    if (visible) {
      setWho(null);
      setText("");
      setPreview(null);
      void load();
    }
  }, [visible, load]);

  const check = async () => {
    if (!who || !text.trim()) return;
    setChecking(true);
    setError(null);
    try {
      setPreview(await previewOrder(sessionId, deviceId, { recipient: who, text: text.trim() }));
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setChecking(false);
    }
  };

  const edit = (t: string) => {
    setText(t.slice(0, MAX_TEXT));
    setPreview(null); // what she understood belongs to these exact words
  };

  const canCheck = !!who && text.trim().length > 0 && !checking && !busy;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <View style={styles.sheet} testID="order-modal">
          <View style={styles.head}>
            <Text style={styles.title}>· LEAVE INSTRUCTIONS ·</Text>
            <TouchableOpacity onPress={onClose} hitSlop={12} testID="close-order-btn">
              <Ionicons name="close" size={22} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>
          {error ? (
            <Text style={styles.error} testID="order-error">
              {error}
            </Text>
          ) : null}
          <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
            {loading && !people ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginTop: 24 }} />
            ) : people && people.length === 0 ? (
              <Text style={styles.para} testID="order-nobody">
                Nobody here you can leave instructions with.
              </Text>
            ) : people ? (
              <View>
                <Text style={styles.eyebrow}>WHO</Text>
                {people.map((name) => (
                  <TouchableOpacity
                    key={name}
                    style={[styles.card, who === name && styles.cardOn]}
                    onPress={() => {
                      setWho(name);
                      setPreview(null);
                    }}
                    testID={`order-who-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
                  >
                    <Text style={styles.cardTitle}>{name}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={[styles.eyebrow, { marginTop: 8 }]}>WHAT SHOULD HAPPEN WHEN YOU ARE GONE</Text>
                <TextInput
                  style={styles.input}
                  value={text}
                  onChangeText={edit}
                  placeholder="If the water reaches the red mark, cut the ferry loose, even if I'm still across the river."
                  placeholderTextColor={COLORS.textMuted}
                  multiline
                  testID="order-text-input"
                />
                <TouchableOpacity
                  style={[styles.ghostBtn, !canCheck && { opacity: 0.4 }]}
                  disabled={!canCheck}
                  onPress={check}
                  testID="order-check-btn"
                >
                  <Text style={styles.ghostBtnText}>{checking ? "CHECKING…" : "SEE WHAT SHE UNDERSTANDS"}</Text>
                </TouchableOpacity>

                {preview ? (
                  <View style={styles.previewBox} testID="order-preview">
                    {preview.understood ? (
                      <Text style={styles.para} testID="order-understood">
                        {preview.recipient} understood: when {preview.understood.condition}, {preview.understood.action}.
                      </Text>
                    ) : null}
                    {preview.issues.map((m, i) => (
                      <Text key={`i${i}`} style={styles.issue} testID={`order-issue-${i}`}>
                        {m}
                      </Text>
                    ))}
                    {preview.notes.map((m, i) => (
                      <Text key={`n${i}`} style={styles.note} testID={`order-note-${i}`}>
                        {m}
                      </Text>
                    ))}
                    {!preview.can_commit ? <Text style={styles.note}>Change the wording above and check again.</Text> : null}
                  </View>
                ) : null}

                <TouchableOpacity
                  style={[styles.primaryBtn, !(preview && preview.can_commit && !busy) && { opacity: 0.4 }]}
                  disabled={!(preview && preview.can_commit && !busy && who)}
                  onPress={() => who && onSend({ recipient: who, text: text.trim() })}
                  testID="order-send-btn"
                >
                  <Text style={styles.primaryBtnText}>{busy ? "SENDING…" : "LEAVE THESE INSTRUCTIONS"}</Text>
                </TouchableOpacity>
                <Text style={styles.note}>This costs one action. She acts only on what she understood above.</Text>
              </View>
            ) : null}

            {given.length > 0 ? (
              <View style={{ marginTop: 18 }} testID="orders-given">
                <Text style={styles.eyebrow}>ALREADY LEFT</Text>
                {given.map((o) => (
                  <View key={o.id} style={styles.card}>
                    <Text style={styles.cardMeta}>
                      {o.to.toUpperCase()} · TURN {o.turn}
                    </Text>
                    <Text style={styles.para}>{o.understood}</Text>
                    {o.result ? <Text style={styles.result}>{o.result}</Text> : null}
                  </View>
                ))}
              </View>
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
  para: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 16, lineHeight: 24, marginBottom: 8 },
  note: { fontFamily: FONTS.body, color: COLORS.textSecondary, fontSize: 13, lineHeight: 19, marginBottom: 6 },
  issue: { fontFamily: FONTS.body, color: COLORS.danger, fontSize: 14, lineHeight: 20, marginBottom: 6 },
  result: { fontFamily: FONTS.bodyItalic, color: COLORS.textPrimary, fontSize: 14, lineHeight: 20 },
  error: { fontFamily: FONTS.body, color: COLORS.danger, fontSize: 13, paddingHorizontal: 16, paddingTop: 10 },
  card: { borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 10, backgroundColor: COLORS.background, minHeight: 48 },
  cardOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft },
  cardTitle: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 18 },
  cardMeta: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 10, letterSpacing: 1.5, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.background,
    color: COLORS.textPrimary,
    fontFamily: FONTS.body,
    fontSize: 16,
    padding: 12,
    minHeight: 84,
    textAlignVertical: "top",
    marginBottom: 12,
  },
  previewBox: { borderWidth: 1, borderColor: COLORS.borderDim, padding: 12, marginTop: 12, marginBottom: 12 },
  ghostBtn: { borderWidth: 1, borderColor: COLORS.border, paddingVertical: 14, alignItems: "center" },
  ghostBtnText: { fontFamily: FONTS.monoBold, color: COLORS.textSecondary, fontSize: 12, letterSpacing: 2 },
  primaryBtn: {
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    paddingVertical: 14,
    paddingHorizontal: 18,
    alignItems: "center",
    marginBottom: 8,
  },
  primaryBtnText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 2 },
});
