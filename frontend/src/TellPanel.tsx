import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "./theme";
import { Disclosure, getTellTargets } from "./api";
import { friendlyError } from "./errors";

type Props = {
  visible: boolean;
  sessionId: string;
  deviceId: string;
  busy: boolean;
  onClose: () => void;
  /** The play screen sends this as a normal story action, so it costs one action like any other. */
  onSend: (d: Disclosure) => void;
};

const MAX_CLAIM = 280;

export default function TellPanel({ visible, sessionId, deviceId, busy, onClose, onSend }: Props) {
  const [loading, setLoading] = useState(false);
  const [people, setPeople] = useState<string[] | null>(null);
  const [who, setWho] = useState<string | null>(null);
  const [claim, setClaim] = useState("");
  const [aloud, setAloud] = useState(false);
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
      setClaim("");
      setAloud(false);
      void load();
    }
  }, [visible, load]);

  const ready = !!who && claim.trim().length > 0 && !busy;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <View style={styles.sheet} testID="tell-modal">
          <View style={styles.head}>
            <Text style={styles.title}>· TELL SOMEONE ·</Text>
            <TouchableOpacity onPress={onClose} hitSlop={12} testID="close-tell-btn">
              <Ionicons name="close" size={22} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>
          {error ? (
            <Text style={styles.error} testID="tell-error">
              {error}
            </Text>
          ) : null}
          <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
            {loading && !people ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginTop: 24 }} />
            ) : people && people.length === 0 ? (
              <Text style={styles.para} testID="tell-nobody">
                Nobody here you can speak to yet.
              </Text>
            ) : people ? (
              <View>
                <Text style={styles.eyebrow}>WHO</Text>
                {people.map((name) => (
                  <TouchableOpacity
                    key={name}
                    style={[styles.card, who === name && styles.cardOn]}
                    onPress={() => setWho(name)}
                    testID={`tell-who-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
                  >
                    <Text style={styles.cardTitle}>{name}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={[styles.eyebrow, { marginTop: 8 }]}>WHAT YOU TELL THEM</Text>
                <TextInput
                  style={styles.input}
                  value={claim}
                  onChangeText={(t) => setClaim(t.slice(0, MAX_CLAIM))}
                  placeholder="The missing passenger is at the mill"
                  placeholderTextColor={COLORS.textMuted}
                  multiline
                  testID="tell-claim-input"
                />
                <TouchableOpacity style={styles.toggle} onPress={() => setAloud((v) => !v)} testID="tell-aloud-toggle">
                  <Ionicons name={aloud ? "checkbox" : "square-outline"} size={20} color={COLORS.textSecondary} />
                  <Text style={styles.toggleText}>
                    {aloud ? "Say it aloud, anyone here can hear" : "Say it quietly, only they hear"}
                  </Text>
                </TouchableOpacity>
                <Text style={styles.note}>
                  This costs one action. They will remember exactly what you said. Whether it travels is up to them.
                </Text>
                <TouchableOpacity
                  style={[styles.primaryBtn, !ready && { opacity: 0.4 }]}
                  disabled={!ready}
                  onPress={() => who && onSend({ recipient: who, claim: claim.trim(), aloud })}
                  testID="tell-send-btn"
                >
                  <Text style={styles.primaryBtnText}>{busy ? "SENDING…" : "TELL THEM"}</Text>
                </TouchableOpacity>
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
  para: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 16, lineHeight: 24, marginBottom: 12 },
  note: { fontFamily: FONTS.body, color: COLORS.textSecondary, fontSize: 13, lineHeight: 19, marginBottom: 12 },
  error: { fontFamily: FONTS.body, color: COLORS.danger, fontSize: 13, paddingHorizontal: 16, paddingTop: 10 },
  card: { borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 10, backgroundColor: COLORS.background, minHeight: 48 },
  cardOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft },
  cardTitle: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 18 },
  input: {
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.background,
    color: COLORS.textPrimary,
    fontFamily: FONTS.body,
    fontSize: 16,
    padding: 12,
    minHeight: 72,
    textAlignVertical: "top",
    marginBottom: 12,
  },
  toggle: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 44, marginBottom: 6 },
  toggleText: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 14, flexShrink: 1 },
  primaryBtn: {
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    paddingVertical: 14,
    paddingHorizontal: 18,
    alignItems: "center",
  },
  primaryBtnText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 2 },
});
