import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "./theme";
import {
  createTheory,
  deleteTheory,
  getNotebook,
  getTurnByNumber,
  Notebook,
  NotebookPin,
  NotebookTheory,
  removePin,
  Turn,
  updateTheory,
} from "./api";
import { friendlyError } from "./errors";

type Props = {
  visible: boolean;
  sessionId: string;
  deviceId: string;
  /** Bumped by the play screen whenever a pin is added so the list reloads. */
  refreshKey: number;
  onClose: () => void;
};

type Editing = { id: string | null; title: string; body: string; pinIds: string[] };
type Passage = { pin: NotebookPin; turn: Turn };

export default function NotebookPanel({ visible, sessionId, deviceId, refreshKey, onClose }: Props) {
  const [notebook, setNotebook] = useState<Notebook>({ pins: [], theories: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);

  const load = useCallback(async () => {
    if (!sessionId || !deviceId) return;
    setLoading(true);
    setError(null);
    try {
      setNotebook(await getNotebook(sessionId, deviceId));
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, deviceId]);

  useEffect(() => {
    if (visible) void load();
  }, [visible, refreshKey, load]);

  const run = async (fn: () => Promise<void>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(friendlyError(e).message);
    }
  };

  const openPassage = async (pin: NotebookPin) => {
    setError(null);
    try {
      const res = await getTurnByNumber(sessionId, deviceId, pin.turn_number);
      setPassage({ pin, turn: res.turn });
    } catch (e) {
      setError(friendlyError(e).message);
    }
  };

  const saveTheory = () =>
    run(async () => {
      if (!editing) return;
      const title = editing.title.trim();
      if (!title) throw new Error("Give the theory a title.");
      if (editing.id) {
        await updateTheory(sessionId, deviceId, editing.id, {
          title,
          body: editing.body,
          pin_ids: editing.pinIds,
        });
      } else {
        await createTheory(sessionId, deviceId, { title, body: editing.body, pin_ids: editing.pinIds });
      }
      setEditing(null);
    });

  const togglePin = (pinId: string) =>
    setEditing((cur) =>
      cur
        ? {
            ...cur,
            pinIds: cur.pinIds.includes(pinId) ? cur.pinIds.filter((p) => p !== pinId) : [...cur.pinIds, pinId],
          }
        : cur
    );

  const pinById = (id: string) => notebook.pins.find((p) => p.id === id);

  const renderPassage = (view: Passage) => {
    const { pin, turn } = view;
    return (
      <View testID="notebook-passage">
        <TouchableOpacity onPress={() => setPassage(null)} style={styles.backRow} testID="notebook-passage-back">
          <Ionicons name="chevron-back" size={16} color={COLORS.textSecondary} />
          <Text style={styles.backText}>Back to notebook</Text>
        </TouchableOpacity>
        <Text style={styles.eyebrow}>TURN {turn.turn_number}</Text>
        {turn.paragraphs.map((para, idx) => {
          const pinned = idx === pin.paragraph_index;
          return (
            <Text
              key={idx}
              style={[styles.passagePara, pinned && styles.passageParaPinned]}
              testID={pinned ? "notebook-passage-pinned" : `notebook-passage-${idx}`}
            >
              {pinned ? (
                <>
                  {Array.from(para).slice(0, pin.start).join("")}
                  <Text style={styles.passageMark}>{Array.from(para).slice(pin.start, pin.end).join("")}</Text>
                  {Array.from(para).slice(pin.end).join("")}
                </>
              ) : (
                para
              )}
            </Text>
          );
        })}
      </View>
    );
  };

  const renderEditor = (ed: Editing) => (
    <View testID="theory-editor">
      <TouchableOpacity onPress={() => setEditing(null)} style={styles.backRow} testID="theory-cancel-btn">
        <Ionicons name="chevron-back" size={16} color={COLORS.textSecondary} />
        <Text style={styles.backText}>Back to notebook</Text>
      </TouchableOpacity>
      <Text style={styles.eyebrow}>{ed.id ? "EDIT THEORY" : "NEW THEORY"}</Text>
      <TextInput
        value={ed.title}
        onChangeText={(t) => setEditing({ ...ed, title: t })}
        placeholder="What do you suspect?"
        placeholderTextColor={COLORS.textMuted}
        style={styles.input}
        maxLength={120}
        testID="theory-title-input"
      />
      <TextInput
        value={ed.body}
        onChangeText={(t) => setEditing({ ...ed, body: t })}
        placeholder="Why do you think so?"
        placeholderTextColor={COLORS.textMuted}
        style={[styles.input, styles.inputBody]}
        multiline
        maxLength={4000}
        testID="theory-body-input"
      />
      <Text style={styles.eyebrow}>EVIDENCE · {ed.pinIds.length} ATTACHED</Text>
      {notebook.pins.length === 0 ? (
        <Text style={styles.empty}>Pin a passage from the story first, then attach it here.</Text>
      ) : (
        notebook.pins.map((pin) => {
          const on = ed.pinIds.includes(pin.id);
          return (
            <TouchableOpacity
              key={pin.id}
              onPress={() => togglePin(pin.id)}
              style={[styles.pinPick, on && styles.pinPickOn]}
              testID={`theory-attach-${pin.id}`}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: on }}
            >
              <Ionicons
                name={on ? "checkbox" : "square-outline"}
                size={18}
                color={on ? COLORS.primary : COLORS.textSecondary}
              />
              <Text style={styles.pinPickText} numberOfLines={3}>
                T{pin.turn_number} · {pin.text}
              </Text>
            </TouchableOpacity>
          );
        })
      )}
      <View style={styles.btnRow}>
        <TouchableOpacity style={styles.primaryBtn} onPress={saveTheory} testID="theory-save-btn">
          <Text style={styles.primaryBtnText}>SAVE THEORY</Text>
        </TouchableOpacity>
        {ed.id ? (
          <TouchableOpacity
            style={styles.dangerBtn}
            onPress={() =>
              run(async () => {
                await deleteTheory(sessionId, deviceId, ed.id as string);
                setEditing(null);
              })
            }
            testID="theory-delete-btn"
          >
            <Text style={styles.dangerBtnText}>DELETE</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </View>
  );

  const renderList = () => (
    <View>
      <Text style={styles.privacy}>
        Private to you and to this save. Nothing here is told to any character or to the narrator.
      </Text>
      <Text style={styles.eyebrow}>PINNED PASSAGES · {notebook.pins.length}</Text>
      {notebook.pins.length === 0 ? (
        <Text style={styles.empty} testID="notebook-no-pins">
          Nothing pinned yet. Tap the pin beside a paragraph while you read.
        </Text>
      ) : (
        notebook.pins.map((pin) => (
          <View key={pin.id} style={styles.card} testID={`pin-${pin.id}`}>
            <Text style={styles.cardMeta}>TURN {pin.turn_number}</Text>
            <Text style={styles.cardText}>{pin.text}</Text>
            {pin.note ? <Text style={styles.cardNote}>{pin.note}</Text> : null}
            <View style={styles.btnRow}>
              <TouchableOpacity onPress={() => openPassage(pin)} style={styles.linkBtn} testID={`pin-open-${pin.id}`}>
                <Text style={styles.linkBtnText}>OPEN IN STORY</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => run(() => removePin(sessionId, deviceId, pin.id))}
                style={styles.linkBtn}
                testID={`pin-remove-${pin.id}`}
              >
                <Text style={styles.linkBtnDanger}>REMOVE</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))
      )}
      <Text style={[styles.eyebrow, { marginTop: 20 }]}>THEORIES · {notebook.theories.length}</Text>
      {notebook.theories.map((t: NotebookTheory) => (
        <TouchableOpacity
          key={t.id}
          style={styles.card}
          onPress={() => setEditing({ id: t.id, title: t.title, body: t.body, pinIds: t.pin_ids })}
          testID={`theory-${t.id}`}
        >
          <Text style={styles.cardTitle}>{t.title}</Text>
          {t.body ? (
            <Text style={styles.cardText} numberOfLines={3}>
              {t.body}
            </Text>
          ) : null}
          <Text style={styles.cardMeta}>
            {t.pin_ids.filter((id) => pinById(id)).length} PINS ATTACHED
          </Text>
        </TouchableOpacity>
      ))}
      <TouchableOpacity
        style={styles.primaryBtn}
        onPress={() => setEditing({ id: null, title: "", body: "", pinIds: [] })}
        testID="new-theory-btn"
      >
        <Text style={styles.primaryBtnText}>+ NEW THEORY</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <View style={styles.sheet} testID="notebook-modal">
          <View style={styles.head}>
            <Text style={styles.title}>· NOTEBOOK ·</Text>
            <TouchableOpacity onPress={onClose} hitSlop={12} testID="close-notebook-btn">
              <Ionicons name="close" size={22} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>
          {error ? (
            <Text style={styles.error} testID="notebook-error">
              {error}
            </Text>
          ) : null}
          {loading && notebook.pins.length === 0 && notebook.theories.length === 0 ? (
            <ActivityIndicator color={COLORS.primary} style={{ marginTop: 24 }} />
          ) : (
            <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
              {passage ? renderPassage(passage) : editing ? renderEditor(editing) : renderList()}
              <View style={{ height: 32 }} />
            </ScrollView>
          )}
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
    minHeight: "55%",
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
  privacy: { fontFamily: FONTS.bodyItalic, color: COLORS.textSecondary, fontSize: 14, lineHeight: 20, marginBottom: 14 },
  eyebrow: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 10, letterSpacing: 2, marginBottom: 8, marginTop: 4 },
  empty: { fontFamily: FONTS.bodyItalic, color: COLORS.textMuted, fontSize: 14, marginBottom: 10 },
  error: { fontFamily: FONTS.body, color: COLORS.danger, fontSize: 13, paddingHorizontal: 16, paddingTop: 10 },
  card: { borderWidth: 1, borderColor: COLORS.border, padding: 12, marginBottom: 10, backgroundColor: COLORS.background },
  cardMeta: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 10, letterSpacing: 2, marginTop: 4 },
  cardTitle: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 17, marginBottom: 4 },
  cardText: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 15, lineHeight: 21 },
  cardNote: { fontFamily: FONTS.bodyItalic, color: COLORS.textSecondary, fontSize: 13, marginTop: 4 },
  btnRow: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 10, alignItems: "center" },
  linkBtn: { paddingVertical: 8, paddingHorizontal: 4, minHeight: 36, justifyContent: "center" },
  linkBtnText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 11, letterSpacing: 2 },
  linkBtnDanger: { fontFamily: FONTS.monoBold, color: COLORS.danger, fontSize: 11, letterSpacing: 2 },
  primaryBtn: {
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    paddingVertical: 12,
    paddingHorizontal: 18,
    alignItems: "center",
    marginTop: 10,
  },
  primaryBtnText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 3 },
  dangerBtn: { borderWidth: 1, borderColor: COLORS.danger, paddingVertical: 12, paddingHorizontal: 18, marginTop: 10 },
  dangerBtnText: { fontFamily: FONTS.monoBold, color: COLORS.danger, fontSize: 12, letterSpacing: 3 },
  input: {
    borderWidth: 1,
    borderColor: COLORS.border,
    color: COLORS.textPrimary,
    fontFamily: FONTS.body,
    fontSize: 16,
    padding: 10,
    marginBottom: 10,
    backgroundColor: COLORS.background,
  },
  inputBody: { minHeight: 110, textAlignVertical: "top" },
  pinPick: { flexDirection: "row", gap: 10, padding: 10, borderWidth: 1, borderColor: COLORS.borderDim, marginBottom: 8, alignItems: "flex-start" },
  pinPickOn: { borderColor: COLORS.primary },
  pinPickText: { flex: 1, fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 14, lineHeight: 20 },
  backRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: 12, minHeight: 36 },
  backText: { fontFamily: FONTS.mono, color: COLORS.textSecondary, fontSize: 11, letterSpacing: 1 },
  passagePara: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 16, lineHeight: 24, marginBottom: 12 },
  passageParaPinned: { borderLeftWidth: 2, borderLeftColor: COLORS.primary, paddingLeft: 10 },
  passageMark: { backgroundColor: COLORS.primarySoft, color: COLORS.textPrimary },
});
