import React, { useCallback, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { COLORS, FONTS } from "../../src/theme";
import { getDeviceId } from "../../src/storage";
import { createDuet, DuetListItem, joinDuet, listDuets, reissueDuetInvite } from "../../src/api";
import { friendlyError } from "../../src/errors";

const STATUS: Record<string, string> = {
  waiting_for_friend: "WAITING FOR YOUR FRIEND",
  active: "IN PROGRESS",
  chapter_ended: "CHAPTER ENDED",
};

export default function DuetsHome() {
  const router = useRouter();
  const [items, setItems] = useState<DuetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [invite, setInvite] = useState<{ id: string; code: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await listDuets(await getDeviceId());
      setItems(res.duets);
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(friendlyError(e).message);
    } finally {
      setBusy(false);
    }
  };

  const start = (seat: string) =>
    run(async () => {
      const res = await createDuet(await getDeviceId(), seat);
      setInvite({ id: res.duet.id, code: res.invite_code });
      load();
    });

  const join = () =>
    run(async () => {
      const res = await joinDuet(await getDeviceId(), code.trim());
      setCode("");
      router.push(`/duets/${res.duet.id}`);
    });

  const reissue = (id: string) =>
    run(async () => {
      const res = await reissueDuetInvite(await getDeviceId(), id);
      setInvite({ id, code: res.invite_code });
    });

  return (
    <SafeAreaView style={s.safe} testID="duets-home">
      <ScrollView contentContainerStyle={s.body}>
        <View style={s.top}>
          <TouchableOpacity onPress={() => router.back()} testID="duets-back-btn" hitSlop={12}>
            <Text style={s.link}>{"< BACK"}</Text>
          </TouchableOpacity>
          <Text style={s.label}>TWO · PLAYERS</Text>
        </View>
        <Text style={s.title}>Two Lights</Text>
        <Text style={s.prose}>
          One night, two sides of the water. One of you is the ferryman, the other keeps the signal lamp. You take turns and
          each of you sees only what your own character could see.
        </Text>

        <Text style={s.section}>START A STORY, INVITE ONE FRIEND</Text>
        <View style={s.row}>
          <TouchableOpacity style={s.btn} disabled={busy} onPress={() => start("ferryman")} testID="duet-start-ferryman">
            <Text style={s.btnText}>PLAY THE FERRYMAN</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.btn} disabled={busy} onPress={() => start("keeper")} testID="duet-start-keeper">
            <Text style={s.btnText}>PLAY THE KEEPER</Text>
          </TouchableOpacity>
        </View>

        {invite ? (
          <View style={s.box} testID="duet-invite-box">
            <Text style={s.label}>INVITATION CODE, SHOWN ONCE</Text>
            <Text selectable style={s.code} testID="duet-invite-code">{invite.code}</Text>
            <Text style={s.note}>Send this to one friend. It works once, for the other seat.</Text>
          </View>
        ) : null}

        <Text style={s.section}>JOIN WITH A CODE</Text>
        <TextInput
          style={s.input}
          value={code}
          onChangeText={setCode}
          placeholder="DUET-…"
          placeholderTextColor={COLORS.textMuted}
          autoCapitalize="none"
          autoCorrect={false}
          testID="duet-code-input"
        />
        <TouchableOpacity style={s.btn} disabled={busy || code.trim().length < 8} onPress={join} testID="duet-join-btn">
          <Text style={s.btnText}>JOIN</Text>
        </TouchableOpacity>

        {error ? <Text style={s.error} testID="duets-error">{error}</Text> : null}

        <Text style={s.section}>YOUR TWO PLAYER STORIES</Text>
        {loading ? (
          <ActivityIndicator color={COLORS.primary} />
        ) : items.length === 0 ? (
          <Text style={s.note} testID="duets-empty">None yet.</Text>
        ) : (
          items.map((d) => (
            <View key={d.id} style={s.card} testID={`duet-slot-${d.id}`}>
              <TouchableOpacity onPress={() => router.push(`/duets/${d.id}`)} testID={`duet-open-${d.id}`}>
                <Text style={s.label}>{STATUS[d.status] || d.status}</Text>
                <Text style={s.cardTitle}>{d.title}</Text>
                <Text style={s.note}>
                  You are the {d.label}, with {d.other_name}. Turn {d.turn_count}.
                </Text>
                {d.status === "active" ? (
                  <Text style={d.your_turn ? s.yourTurn : s.waiting} testID={`duet-state-${d.id}`}>
                    {d.your_turn ? "YOUR TURN" : `WAITING FOR ${d.other_name.toUpperCase()}`}
                  </Text>
                ) : null}
              </TouchableOpacity>
              {d.status === "waiting_for_friend" ? (
                <TouchableOpacity onPress={() => reissue(d.id)} testID={`duet-reinvite-${d.id}`}>
                  <Text style={s.link}>NEW INVITATION CODE</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  body: { padding: 20, paddingBottom: 48, maxWidth: 720, width: "100%", alignSelf: "center" },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  title: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 34, marginBottom: 8 },
  prose: { fontFamily: FONTS.body, color: COLORS.textProse, fontSize: 16, lineHeight: 23 },
  section: { fontFamily: FONTS.mono, color: COLORS.textSecondary, fontSize: 11, letterSpacing: 3, marginTop: 28, marginBottom: 10 },
  label: { fontFamily: FONTS.mono, color: COLORS.primary, fontSize: 10, letterSpacing: 2.5 },
  link: { fontFamily: FONTS.mono, color: COLORS.primary, fontSize: 11, letterSpacing: 2, marginTop: 8 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  btn: { borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft, paddingVertical: 14, paddingHorizontal: 18, alignItems: "center" },
  btnText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 3 },
  box: { borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface, padding: 14, marginTop: 14 },
  code: { fontFamily: FONTS.mono, color: COLORS.textPrimary, fontSize: 14, marginVertical: 8 },
  note: { fontFamily: FONTS.bodyItalic, color: COLORS.textSecondary, fontSize: 14, lineHeight: 20, marginTop: 4 },
  input: { borderWidth: 1, borderColor: COLORS.border, color: COLORS.textPrimary, fontFamily: FONTS.mono, padding: 12, marginBottom: 10 },
  error: { fontFamily: FONTS.body, color: COLORS.danger, marginTop: 12 },
  card: { borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface, padding: 14, marginBottom: 10 },
  cardTitle: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 22, marginTop: 4 },
  yourTurn: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 11, letterSpacing: 2, marginTop: 8 },
  waiting: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 11, letterSpacing: 2, marginTop: 8 },
});
