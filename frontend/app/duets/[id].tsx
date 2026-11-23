import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { COLORS, FONTS } from "../../src/theme";
import { getDeviceId } from "../../src/storage";
import {
  DuetComparison,
  DuetView,
  duetAction,
  proposeDuetSignal,
  respondDuetSignal,
  endDuetChapter,
  getDuet,
  getDuetComparison,
  shareDuetComparison,
} from "../../src/api";
import { friendlyError } from "../../src/errors";

const POLL_MS = 4000;

function newRequestId(): string {
  return `duet-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export default function DuetPlay() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [duet, setDuet] = useState<DuetView | null>(null);
  const [cmp, setCmp] = useState<DuetComparison | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [faint, setFaint] = useState(false);
  const [flashes, setFlashes] = useState("");
  const [meaning, setMeaning] = useState("");
  const pending = useRef<{ text: string; rid: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const deviceId = await getDeviceId();
      const res = await getDuet(deviceId, String(id));
      setDuet(res.duet);
      if (res.duet.chapter_ended) setCmp(await getDuetComparison(deviceId, String(id)));
    } catch (e) {
      setError(friendlyError(e).message);
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Resume and wait: poll only while it is the other player's turn (or they have not joined yet).
  useEffect(() => {
    if (!duet || busy) return;
    const waiting = duet.status === "waiting_for_friend" || (duet.status === "active" && !duet.your_turn);
    if (!waiting) return;
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [duet, busy, refresh]);

  const send = async (action: string) => {
    const body = action.trim();
    if (!body || !duet || busy) return;
    // The same text keeps the same request id, so a retry after a lost response cannot play twice.
    if (!pending.current || pending.current.text !== body) pending.current = { text: body, rid: newRequestId() };
    setBusy(true);
    setError(null);
    try {
      const res = await duetAction(await getDeviceId(), duet.id, {
        action_text: body,
        action_request_id: pending.current.rid,
        expected_turn_count: duet.turn_count,
        ...(faint ? { clarity: "faint" as const } : {}),
      });
      pending.current = null;
      setDuet(res.duet);
      setText("");
    } catch (e) {
      setError(friendlyError(e).message);
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const offerSignal = async () => {
    const count = parseInt(flashes, 10);
    if (!duet || busy || !(count >= 1) || !meaning.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await proposeDuetSignal(await getDeviceId(), duet.id, { request_id: newRequestId(), count, meaning: meaning.trim() });
      setDuet(res.duet);
      setFlashes("");
      setMeaning("");
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setBusy(false);
    }
  };

  const answerSignal = async (id: string, accept: boolean) => {
    if (!duet || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await respondDuetSignal(await getDeviceId(), duet.id, id, accept);
      setDuet(res.duet);
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setBusy(false);
    }
  };

  const endChapter = async () => {
    if (!duet) return;
    setBusy(true);
    try {
      const deviceId = await getDeviceId();
      const res = await endDuetChapter(deviceId, duet.id);
      setDuet(res.duet);
      setCmp(await getDuetComparison(deviceId, duet.id));
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setBusy(false);
    }
  };

  const share = async (value: boolean) => {
    if (!duet) return;
    setBusy(true);
    try {
      setCmp(await shareDuetComparison(await getDeviceId(), duet.id, value));
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setBusy(false);
    }
  };

  if (!duet) {
    return (
      <SafeAreaView style={s.safe} testID="duet-play">
        {error ? <Text style={s.error} testID="duet-error">{error}</Text> : <ActivityIndicator color={COLORS.primary} style={{ marginTop: 40 }} />}
      </SafeAreaView>
    );
  }

  const c = duet.you.character;
  return (
    <SafeAreaView style={s.safe} testID="duet-play">
      <ScrollView contentContainerStyle={s.body}>
        <View style={s.top}>
          <TouchableOpacity onPress={() => router.push("/duets")} testID="duet-back-btn" hitSlop={12}>
            <Text style={s.link}>{"< TWO PLAYERS"}</Text>
          </TouchableOpacity>
          <Text style={s.label} testID="duet-you">{c.name.toUpperCase()}, {duet.you.label.toUpperCase()}</Text>
        </View>
        <Text style={s.title}>{duet.title}</Text>
        <Text style={s.note} testID="duet-inventory">Carrying: {c.inventory.join(", ") || "nothing"}</Text>
        <Text style={s.note} testID="duet-boat">The boat, as you know it: {duet.known.boat}</Text>

        {duet.history.map((e, i) => (
          <View key={`${e.turn}-${i}`} style={e.kind === "observed" ? s.seen : s.entry} testID={`duet-entry-${i}`}>
            {e.kind === "you" ? <Text style={s.action}>{`> ${e.action}`}</Text> : null}
            {e.kind === "observed" ? <Text style={s.label}>YOU SEE</Text> : null}
            <Text style={s.prose}>{e.text}</Text>
          </View>
        ))}

        {duet.status === "active" && ((duet.signals || []).length > 0 || duet.signal_window_open) ? (
          <View style={s.box} testID="duet-signals">
            <Text style={s.label}>SIGNALS</Text>
            {(duet.signals || []).map((g) => (
              <View key={g.id} style={{ marginTop: 8 }} testID={`duet-signal-${g.count}`}>
                <Text style={s.prose}>
                  {`${g.count} flash${g.count === 1 ? "" : "es"}: ${g.meaning}`}
                  {g.status === "agreed" ? " (agreed)" : g.mine ? " (waiting for your friend)" : ""}
                </Text>
                {g.status === "proposed" && !g.mine ? (
                  <View style={s.row}>
                    <TouchableOpacity style={s.btn} disabled={busy} onPress={() => answerSignal(g.id, true)} testID={`duet-signal-accept-${g.count}`}>
                      <Text style={s.btnText}>AGREE</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={s.btn} disabled={busy} onPress={() => answerSignal(g.id, false)} testID={`duet-signal-decline-${g.count}`}>
                      <Text style={s.btnText}>NO</Text>
                    </TouchableOpacity>
                  </View>
                ) : null}
              </View>
            ))}
            {duet.signal_window_open ? (
              <View style={{ marginTop: 10 }}>
                <Text style={s.note}>Settle what a number of flashes means before the first lamp is lit.</Text>
                <TextInput style={s.input} value={flashes} onChangeText={setFlashes} keyboardType="number-pad" placeholder="How many flashes" placeholderTextColor={COLORS.textMuted} testID="duet-signal-count" />
                <TextInput style={s.input} value={meaning} onChangeText={setMeaning} placeholder="What it means" placeholderTextColor={COLORS.textMuted} testID="duet-signal-meaning" />
                <TouchableOpacity style={s.btn} disabled={busy || !(parseInt(flashes, 10) >= 1) || !meaning.trim()} onPress={offerSignal} testID="duet-signal-offer-btn">
                  <Text style={s.btnText}>OFFER THIS SIGNAL</Text>
                </TouchableOpacity>
              </View>
            ) : null}
          </View>
        ) : null}

        {duet.status === "waiting_for_friend" ? (
          <Text style={s.waiting} testID="duet-state">WAITING FOR YOUR FRIEND TO JOIN</Text>
        ) : duet.status === "active" ? (
          duet.your_turn ? (
            <View testID="duet-your-turn">
              <Text style={s.yourTurn} testID="duet-state">YOUR TURN</Text>
              {duet.choices.map((ch) => (
                <TouchableOpacity key={ch.label} style={s.choice} disabled={busy} onPress={() => send(ch.text)} testID={`duet-choice-${ch.label}`}>
                  <Text style={s.prose}>{`${ch.label}. ${ch.text}`}</Text>
                </TouchableOpacity>
              ))}
              <TextInput
                style={s.input}
                value={text}
                onChangeText={setText}
                placeholder="Or do something else…"
                placeholderTextColor={COLORS.textMuted}
                multiline
                testID="duet-input"
              />
              <TouchableOpacity onPress={() => setFaint(!faint)} testID="duet-faint-toggle">
                <Text style={s.link}>{faint ? "LAMP HALF-SHUTTERED: TAP FOR FULL LIGHT" : "HALF-SHUTTER THE LAMP, SO IT IS EASY TO MISS"}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.btn} disabled={busy || !text.trim()} onPress={() => send(text)} testID="duet-send-btn">
                <Text style={s.btnText}>{busy ? "…" : "ACT"}</Text>
              </TouchableOpacity>
              {duet.turn_count > 0 ? (
                <TouchableOpacity onPress={endChapter} disabled={busy} testID="duet-end-chapter-btn">
                  <Text style={s.link}>END THE CHAPTER FOR BOTH OF US</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          ) : (
            <Text style={s.waiting} testID="duet-state">{`WAITING FOR ${(duet.waiting_for || duet.other.name).toUpperCase()}`}</Text>
          )
        ) : null}

        {cmp && duet.chapter_ended ? (
          <View style={s.box} testID="duet-comparison">
            <Text style={s.label}>CHAPTER ENDED</Text>
            {cmp.both_shared ? (
              cmp.accounts.map((a) => (
                <View key={a.seat} style={s.account} testID={`duet-account-${a.seat}`}>
                  <Text style={s.cardTitle}>{a.mine ? "Your account" : `${a.character.name}'s account`}</Text>
                  {a.entries.map((e, i) => (
                    <Text key={i} style={s.prose}>{e.kind === "you" ? `> ${e.action}\n${e.text}` : e.kind === "observed" ? `Seen: ${e.text}` : e.text}</Text>
                  ))}
                </View>
              ))
            ) : (
              <>
                <Text style={s.note} testID="duet-share-note">
                  Each of you can choose to compare accounts side by side. Nothing is shown to your friend unless you both agree.
                </Text>
                {cmp.you_shared === true ? (
                  <Text style={s.waiting} testID="duet-share-state">YOU AGREED. WAITING FOR YOUR FRIEND.</Text>
                ) : (
                  <View style={s.row}>
                    <TouchableOpacity style={s.btn} disabled={busy} onPress={() => share(true)} testID="duet-share-yes">
                      <Text style={s.btnText}>COMPARE ACCOUNTS</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={s.btn} disabled={busy} onPress={() => share(false)} testID="duet-share-no">
                      <Text style={s.btnText}>KEEP MINE PRIVATE</Text>
                    </TouchableOpacity>
                  </View>
                )}
                {cmp.you_shared === false ? <Text style={s.note} testID="duet-share-state">Your account stays private.</Text> : null}
              </>
            )}
          </View>
        ) : null}

        {error ? <Text style={s.error} testID="duet-error">{error}</Text> : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  body: { padding: 20, paddingBottom: 60, maxWidth: 720, width: "100%", alignSelf: "center" },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  title: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 30, marginBottom: 6 },
  label: { fontFamily: FONTS.mono, color: COLORS.primary, fontSize: 10, letterSpacing: 2.5 },
  link: { fontFamily: FONTS.mono, color: COLORS.primary, fontSize: 11, letterSpacing: 2, marginTop: 12 },
  note: { fontFamily: FONTS.bodyItalic, color: COLORS.textSecondary, fontSize: 14, lineHeight: 20, marginTop: 4 },
  prose: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 16, lineHeight: 24 },
  entry: { marginTop: 18 },
  seen: { marginTop: 14, borderLeftWidth: 2, borderLeftColor: COLORS.primary, paddingLeft: 10 },
  action: { fontFamily: FONTS.mono, color: COLORS.textSecondary, fontSize: 13, marginBottom: 6 },
  yourTurn: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 3, marginTop: 24, marginBottom: 8 },
  waiting: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 12, letterSpacing: 2, marginTop: 24 },
  choice: { borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface, padding: 12, marginBottom: 8 },
  input: { borderWidth: 1, borderColor: COLORS.border, color: COLORS.textPrimary, fontFamily: FONTS.body, fontSize: 16, padding: 12, minHeight: 60, marginTop: 6, marginBottom: 10 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 10 },
  btn: { borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft, paddingVertical: 12, paddingHorizontal: 16, alignItems: "center" },
  btnText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 3 },
  box: { borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface, padding: 14, marginTop: 28 },
  account: { marginTop: 16 },
  cardTitle: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 20, marginBottom: 6 },
  error: { fontFamily: FONTS.body, color: COLORS.danger, marginTop: 14 },
});
