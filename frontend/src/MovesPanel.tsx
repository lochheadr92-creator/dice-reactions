import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "./theme";
import { getMoves, MoveKind, MoveOptions, MovePreview, MoveRequest, MovesResponse, previewMove } from "./api";
import { MOVE_LABELS } from "./moves";
import { friendlyError } from "./errors";

type Props = {
  visible: boolean;
  sessionId: string;
  deviceId: string;
  busy: boolean;
  /** Sent as one normal story action; the server decides the outcome. */
  onSend: (m: MoveRequest) => void;
  onClose: () => void;
  /** Open straight into one feature (and only that one). Without it the panel lists them all. */
  initialKind?: MoveKind | null;
  /** What to pre-select, for a move the scene offered. */
  prefill?: Record<string, string[]>;
};

const KINDS: MoveKind[] = ["challenge", "bargain", "route", "regard", "build"];
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");

type Passage = { turn: number; paragraph: number; text: string; speakers?: string[] };
const ref = (p: Passage, speaker?: string) => ({ turn: p.turn, paragraph: p.paragraph, ...(speaker ? { speaker } : {}) });

function Chips({ label, options, value, onChange, multi, testPrefix }: {
  label: string;
  options: { id: string; text: string }[];
  value: string[];
  onChange: (v: string[]) => void;
  multi?: boolean;
  testPrefix: string;
}) {
  if (!options.length) return null;
  return (
    <View style={{ marginBottom: 10 }}>
      <Text style={styles.eyebrow}>{label}</Text>
      {options.map((o) => {
        const on = value.includes(o.id);
        return (
          <TouchableOpacity
            key={o.id}
            style={[styles.card, on && styles.cardOn]}
            onPress={() => onChange(multi ? (on ? value.filter((x) => x !== o.id) : [...value, o.id]) : on ? [] : [o.id])}
            testID={`${testPrefix}-${slug(o.id)}`}
          >
            <Text style={styles.cardText}>{o.text}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const names = (xs: { name: string }[] | undefined) => (xs || []).map((x) => ({ id: x.name, text: x.name }));
const strs = (xs: string[] | undefined) => (xs || []).map((x) => ({ id: x, text: x }));
const psg = (xs: Passage[] | undefined) => (xs || []).map((p) => ({ id: `${p.turn}:${p.paragraph}`, text: p.text }));
const findP = (xs: Passage[] | undefined, id: string | undefined) => (xs || []).find((p) => `${p.turn}:${p.paragraph}` === id);

/** Builds the move for one kind from what the player picked. Null means not ready yet. */
function useForm(kind: MoveKind, o: MoveOptions, prefill?: Record<string, string[]>) {
  const [pick, setPick] = useState<Record<string, string[]>>(prefill || {});
  const [text, setText] = useState<Record<string, string>>({});
  const p = (k: string) => pick[k] || [];
  const set = (k: string) => (v: string[]) => setPick((s) => ({ ...s, [k]: v }));
  const t = (k: string) => (text[k] || "").trim();
  const setT = (k: string) => (v: string) => setText((s) => ({ ...s, [k]: v }));
  let move: MoveRequest | null = null;
  const mode = p("mode")[0];
  if (kind === "challenge") {
    const subject = findP(o.statements, p("subject")[0]);
    const ev: unknown[] = [
      ...p("evidence").map((id) => findP(o.passages, id)).filter(Boolean).map((x) => ref(x as Passage)),
      ...p("items").map((item) => ({ item })),
    ];
    if (p("audience")[0] && subject && ev.length)
      move = { kind, args: { audience: p("audience")[0], subject: ref(subject, subject.speakers?.[0]), evidence: ev, aloud: p("aloud")[0] === "yes" } };
  } else if (kind === "bargain") {
    const open = (o.open || []).find((x: any) => x.id === p("open")[0]);
    if (open && mode && ["accept", "decline", "settle"].includes(mode)) move = { kind, op: mode, args: { bargain_id: open.id } };
    else if (!open && p("with")[0] && t("service") && (p("give").length || p("get").length))
      move = { kind, op: "propose", args: { with: p("with")[0], service: t("service"), give: p("give"), get: p("get") } };
  } else if (kind === "route") {
    const route = (o.routes || []).find((r: any) => r.id === p("route")[0]);
    if (route && mode === "travel") move = { kind, op: "travel", args: { route_id: route.id } };
    else if (route && (mode === "teach" || mode === "guide") && p("with")[0]) move = { kind, op: mode, args: { route_id: route.id, with: p("with")[0] } };
    else if (route && (mode === "block" || mode === "reopen")) move = { kind, op: mode, args: { route_id: route.id, note: t("note") } };
    else if (!route && p("via")[0] && p("to")[0]) {
      const via = findP(o.passages, p("via")[0]);
      if (via) move = { kind, op: "discover", args: { via: ref(via), to: p("to")[0] } };
    }
  } else if (kind === "regard") {
    if (p("op")[0] && p("a")[0] && p("b")[0] && p("a")[0] !== p("b")[0]) move = { kind, args: { op: p("op")[0], a: p("a")[0], b: p("b")[0] } };
  } else if (kind === "build") {
    const work = (o.works || []).find((w: any) => w.id === p("work")[0]);
    if (work && mode === "share" && p("with")[0]) move = { kind, op: "share", args: { work_id: work.id, with: p("with")[0] } };
    else if (!work && p("kind")[0] && p("items").length) move = { kind, op: "build", args: { kind: p("kind")[0], items: p("items"), note: t("note") } };
  }
  return { move, p, set, t, setT, reset: () => { setPick({}); setText({}); } };
}

function Field({ label, value, onChange, placeholder, testID }: { label: string; value: string; onChange: (v: string) => void; placeholder: string; testID: string }) {
  return (
    <View style={{ marginBottom: 10 }}>
      <Text style={styles.eyebrow}>{label}</Text>
      <TextInput style={styles.input} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={COLORS.textMuted} maxLength={120} testID={testID} />
    </View>
  );
}

const MODES: Record<MoveKind, { id: string; text: string }[]> = {
  challenge: [],
  bargain: [{ id: "accept", text: "Accept their counter" }, { id: "decline", text: "Decline" }, { id: "settle", text: "Settle my side" }],
  route: [{ id: "travel", text: "Take it" }, { id: "teach", text: "Tell someone" }, { id: "guide", text: "Guide someone" }, { id: "block", text: "Block it" }, { id: "reopen", text: "Reopen it" }],
  regard: [],
  build: [{ id: "share", text: "Let someone know about it" }],
};

function Form({ kind, o, busy, sessionId, deviceId, onSend, prefill }: { kind: MoveKind; o: MoveOptions; busy: boolean; sessionId: string; deviceId: string; onSend: (m: MoveRequest) => void; prefill?: Record<string, string[]> }) {
  const f = useForm(kind, o, prefill);
  const [checked, setChecked] = useState<{ key: string; value?: MovePreview; error?: string } | null>(null);

  const [checking, setChecking] = useState(false);
  const key = JSON.stringify(f.move);
  const preview = checked?.key === key ? checked.value : undefined;
  const error = checked?.key === key ? checked.error : undefined;
  useEffect(() => setChecked(null), [key]);
  const check = async () => {
    if (!f.move) return;
    setChecking(true);
    setChecked(null);
    try {
      setChecked({ key, value: await previewMove(sessionId, deviceId, f.move) });
    } catch (e) {
      setChecked({ key, error: friendlyError(e).message });
    } finally {
      setChecking(false);
    }
  };
  const { p, set } = f;
  const ready = !!f.move && !busy;
  return (
    <View testID={`move-form-${kind}`}>
      {kind === "challenge" ? (
        <>
          <Chips label="WHO YOU PUT IT TO" options={names(o.audiences)} value={p("audience")} onChange={set("audience")} testPrefix="mv-audience" />
          <Chips label="WHAT THEY SAID" options={psg(o.statements)} value={p("subject")} onChange={set("subject")} testPrefix="mv-subject" />
          <Chips label="WHAT YOU HAVE SEEN" options={psg(o.passages)} value={p("evidence")} onChange={set("evidence")} multi testPrefix="mv-evidence" />
          <Chips label="WHAT YOU HOLD" options={strs(o.items)} value={p("items")} onChange={set("items")} multi testPrefix="mv-item" />
          <Chips label="HOW" options={[{ id: "yes", text: "Say it aloud, so others hear" }]} value={p("aloud")} onChange={set("aloud")} testPrefix="mv-aloud" />
        </>
      ) : null}
      {kind === "bargain" ? (
        <>
          {(o.open || []).length ? (
            <Chips label="OPEN DEALS" options={(o.open as any[]).map((d) => ({ id: d.id, text: `${d.with}: ${d.terms}` }))} value={p("open")} onChange={set("open")} testPrefix="mv-open" />
          ) : null}
          {p("open")[0] ? (
            <Chips label="WHAT NOW" options={MODES.bargain.filter((m) => (o.open as any[]).find((d) => d.id === p("open")[0])?.can.includes(m.id))} value={p("mode")} onChange={set("mode")} testPrefix="mv-mode" />
          ) : (
            <>
              <Chips label="WITH" options={names(o.partners)} value={p("with")} onChange={set("with")} testPrefix="mv-with" />
              <Chips label="YOU GIVE" options={strs(o.items)} value={p("give")} onChange={set("give")} multi testPrefix="mv-give" />
              <Chips label="YOU ASK FOR" options={strs(((o.partners || []).find((x: any) => x.name === p("with")[0]) || {}).offers)} value={p("get")} onChange={set("get")} multi testPrefix="mv-get" />
              <Field label="WHAT YOU WANT DONE" value={f.t("service")} onChange={f.setT("service")} placeholder="Drive me to the depot" testID="mv-service" />
            </>
          )}
        </>
      ) : null}
      {kind === "route" ? (
        <>
          {(o.routes || []).length ? (
            <Chips label="WAYS YOU KNOW" options={(o.routes as any[]).map((r) => ({ id: r.id, text: `${r.a} to ${r.b}${r.status === "blocked" ? " (blocked)" : ""}${!r.can_travel && r.why_not ? `: ${r.why_not}` : ""}` }))} value={p("route")} onChange={set("route")} testPrefix="mv-route" />
          ) : null}
          {p("route")[0] ? (
            <>
              <Chips label="WHAT NOW" options={MODES.route} value={p("mode")} onChange={set("mode")} testPrefix="mv-mode" />
              {["teach", "guide"].includes(p("mode")[0]) ? <Chips label="WHO" options={names(o.people)} value={p("with")} onChange={set("with")} testPrefix="mv-with" /> : null}
            </>
          ) : (
            <>
              <Chips label="WHERE YOU SAW IT" options={psg(o.passages)} value={p("via")} onChange={set("via")} testPrefix="mv-via" />
              <Chips label="WHERE IT LEADS" options={strs(o.places)} value={p("to")} onChange={set("to")} testPrefix="mv-to" />
            </>
          )}
        </>
      ) : null}
      {kind === "regard" ? (
        <>
          <Chips label="WHAT" options={strs(o.ops)} value={p("op")} onChange={set("op")} testPrefix="mv-op" />
          <Chips label="FIRST PERSON" options={names(o.people)} value={p("a")} onChange={set("a")} testPrefix="mv-a" />
          <Chips label="SECOND PERSON" options={names(o.people)} value={p("b")} onChange={set("b")} testPrefix="mv-b" />
        </>
      ) : null}
      {kind === "build" ? (
        <>
          {(o.works || []).length ? (
            <Chips label="WHAT IS HERE" options={(o.works as any[]).map((w) => ({ id: w.id, text: `${w.label}${w.stock?.length ? `: ${w.stock.join(", ")}` : ""}` }))} value={p("work")} onChange={set("work")} testPrefix="mv-work" />
          ) : null}
          {p("work")[0] ? (
            <>
              <Chips label="WHAT NOW" options={MODES.build} value={p("mode")} onChange={set("mode")} testPrefix="mv-mode" />
              <Chips label="WHO" options={names(o.people)} value={p("with")} onChange={set("with")} testPrefix="mv-with" />
            </>
          ) : (
            <>
              <Chips label="WHAT TO MAKE" options={(o.kinds || []).map((k: any) => ({ id: k.kind, text: `${k.label}, costs ${k.cost}${k.can_afford ? "" : " (not enough)"}` }))} value={p("kind")} onChange={set("kind")} testPrefix="mv-kind" />
              <Chips label="WHAT YOU SPEND" options={strs(o.items)} value={p("items")} onChange={set("items")} multi testPrefix="mv-spend" />
              <Field label="A NOTE ONLY YOU CAN READ" value={f.t("note")} onChange={f.setT("note")} placeholder="So Tala can sleep dry" testID="mv-note" />
            </>
          )}
        </>
      ) : null}

      {error ? <Text style={styles.issue}>{error}</Text> : null}
      {preview ? (
        <View style={styles.previewBox} testID="move-preview">
          {preview.terms ? <Text style={styles.para}>{preview.terms}</Text> : null}
          {preview.issues.map((m, i) => (
            <Text key={i} style={styles.issue}>{m}</Text>
          ))}
          {(preview.notes || []).map((m, i) => (
            <Text key={`n${i}`} style={styles.note}>{m}</Text>
          ))}
        </View>
      ) : null}
      <TouchableOpacity style={[styles.ghostBtn, !ready && { opacity: 0.4 }]} disabled={!ready || checking} onPress={check} testID="move-check-btn">
        <Text style={styles.ghostBtnText}>{checking ? "CHECKING..." : "CHECK FIRST"}</Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={[styles.primaryBtn, !(ready && (!preview || preview.can_commit)) && { opacity: 0.4 }]}
        disabled={!(ready && (!preview || preview.can_commit))}
        onPress={() => f.move && onSend(f.move)}
        testID="move-send-btn"
      >
        <Text style={styles.primaryBtnText}>{busy ? "SENDING..." : "DO IT"}</Text>
      </TouchableOpacity>
      <Text style={styles.note}>This costs one action, like anything else you do.</Text>
    </View>
  );
}

export default function MovesPanel({ visible, sessionId, deviceId, busy, onSend, onClose, initialKind = null, prefill }: Props) {
  const [data, setData] = useState<MovesResponse | null>(null);
  const [kind, setKind] = useState<MoveKind | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!sessionId || !deviceId) return;
    setLoading(true);
    setError(null);
    try {
      setData(await getMoves(sessionId, deviceId));
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, deviceId]);

  useEffect(() => {
    if (visible) {
      setKind(initialKind);
      void load();
    }
  }, [visible, load, initialKind]);

  const current = useMemo(() => (kind && data ? data.moves[kind] : null), [kind, data]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <View style={styles.sheet} testID="moves-modal">
          <View style={styles.head}>
            {kind && !initialKind ? (
              <TouchableOpacity onPress={() => setKind(null)} hitSlop={12} testID="moves-back-btn">
                <Ionicons name="chevron-back" size={22} color={COLORS.textSecondary} />
              </TouchableOpacity>
            ) : null}
            <Text style={styles.title}>{kind ? MOVE_LABELS[kind].title.toUpperCase() : "THINGS YOU CAN DO HERE"}</Text>
            <TouchableOpacity onPress={onClose} hitSlop={12} testID="close-moves-btn">
              <Ionicons name="close" size={22} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
            {loading && !data ? <ActivityIndicator color={COLORS.primary} style={{ marginTop: 24 }} /> : null}
            {data && !kind
              ? KINDS.map((k) => {
                  const m = data.moves[k];
                  if (!m) return null;
                  return (
                    <TouchableOpacity key={k} style={[styles.card, !m.available && { opacity: 0.55 }]} disabled={!m.available} onPress={() => setKind(k)} testID={`move-${k}`}>
                      <Text style={styles.cardTitle}>{MOVE_LABELS[k].title}</Text>
                      <Text style={styles.note}>{m.available ? MOVE_LABELS[k].blurb : m.reason}</Text>
                    </TouchableOpacity>
                  );
                })
              : null}
            {kind && current ? <Form key={kind} kind={kind} o={current} busy={busy} sessionId={sessionId} deviceId={deviceId} onSend={onSend} prefill={prefill} /> : null}
            <View style={{ height: 32 }} />
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "flex-end" },
  sheet: { backgroundColor: COLORS.surface, borderTopWidth: 1, borderColor: COLORS.border, maxHeight: "92%", minHeight: "45%", width: "100%", maxWidth: 640, alignSelf: "center" },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 16, borderBottomWidth: 1, borderBottomColor: COLORS.borderDim, gap: 8 },
  title: { flex: 1, fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 2 },
  body: { padding: 16 },
  eyebrow: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 10, letterSpacing: 2, marginBottom: 8 },
  para: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 16, lineHeight: 24, marginBottom: 8 },
  note: { fontFamily: FONTS.body, color: COLORS.textSecondary, fontSize: 13, lineHeight: 19, marginBottom: 6 },
  issue: { fontFamily: FONTS.body, color: COLORS.danger, fontSize: 14, lineHeight: 20, marginBottom: 6 },
  error: { fontFamily: FONTS.body, color: COLORS.danger, fontSize: 13, paddingHorizontal: 16, paddingTop: 10 },
  card: { borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 8, backgroundColor: COLORS.background, minHeight: 48 },
  cardOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft },
  cardTitle: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 18 },
  cardText: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 15, lineHeight: 21 },
  input: { borderWidth: 1, borderColor: COLORS.border, color: COLORS.textPrimary, fontFamily: FONTS.body, fontSize: 16, padding: 12, minHeight: 48, backgroundColor: COLORS.background },
  previewBox: { borderWidth: 1, borderColor: COLORS.border, padding: 12, marginBottom: 10, backgroundColor: COLORS.surfaceDeep },
  ghostBtn: { borderWidth: 1, borderColor: COLORS.border, minHeight: 48, alignItems: "center", justifyContent: "center", marginBottom: 10 },
  ghostBtnText: { fontFamily: FONTS.monoBold, color: COLORS.textSecondary, fontSize: 11, letterSpacing: 2 },
  primaryBtn: { backgroundColor: COLORS.primary, minHeight: 48, alignItems: "center", justifyContent: "center", marginBottom: 10 },
  primaryBtnText: { fontFamily: FONTS.monoBold, color: "#000", fontSize: 12, letterSpacing: 2 },
});
