import { useEffect, useState, useCallback, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Image,
  ActivityIndicator,
  RefreshControl,
  Alert,
  Platform,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming, Easing } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../src/theme";
import { getDeviceId } from "../src/storage";
import { listSessions, deleteSession, SessionSummary } from "../src/api";

const D20_IMAGE =
  "https://static.prod-images.emergentagent.com/jobs/1f4993bf-965b-40a7-8797-1d8bc205019e/images/6ca182ece19601a7e83f15da0ac1edc27e4505443b98a52f245a92f57c3f48bb.png";

export default function HomeScreen() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const float = useSharedValue(0);
  const glow = useSharedValue(0);

  useEffect(() => {
    float.value = withRepeat(withTiming(1, { duration: 3200, easing: Easing.inOut(Easing.ease) }), -1, true);
    glow.value = withRepeat(withTiming(1, { duration: 2400, easing: Easing.inOut(Easing.ease) }), -1, true);
  }, [float, glow]);

  const heroStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: -6 + float.value * 12 }],
  }));
  const glowStyle = useAnimatedStyle(() => ({
    opacity: 0.25 + glow.value * 0.45,
  }));

  const load = useCallback(async () => {
    try {
      const id = await getDeviceId();
      const res = await listSessions(id);
      setSessions(res.sessions || []);
    } catch (e) {
      console.log("load sessions", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const handleDelete = (id: string) => {
    const doIt = async () => {
      try {
        await deleteSession(id);
        load();
      } catch (e) {
        console.log(e);
      }
    };
    if (Platform.OS === "web") {
      doIt();
    } else {
      Alert.alert("Delete Chronicle", "This cannot be undone.", [
        { text: "Cancel", style: "cancel" },
        { text: "Delete", style: "destructive", onPress: doIt },
      ]);
    }
  };

  return (
    <SafeAreaView style={styles.safe} testID="home-screen">
      <ScrollView
        contentContainerStyle={styles.container}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              load();
            }}
            tintColor={COLORS.primary}
          />
        }
      >
        <View style={styles.topRow}>
          <Text style={styles.brandMono} testID="brand-mono">DICE · REACTION · v3.3</Text>
          <TouchableOpacity onPress={() => router.push("/settings")} testID="open-settings-btn" hitSlop={12}>
            <Ionicons name="settings-outline" size={20} color={COLORS.textSecondary} />
          </TouchableOpacity>
        </View>

        <View style={styles.heroWrap}>
          <Animated.View style={[styles.heroGlow, glowStyle]} />
          <Animated.View style={heroStyle}>
            <Image source={{ uri: D20_IMAGE }} style={styles.hero} resizeMode="contain" />
          </Animated.View>
          <Text style={styles.title} testID="app-title">The Dice Reaction</Text>
          <Text style={styles.subtitle}>
            A persistent causal simulation.{"\n"}Hidden rolls. Lasting consequences.
          </Text>
          <View style={styles.ruleLine} />
        </View>

        <TouchableOpacity
          style={styles.primaryBtn}
          onPress={() => router.push("/new-story")}
          testID="new-story-btn"
          activeOpacity={0.75}
        >
          <Text style={styles.primaryBtnText}>[ NEW · STORY ]</Text>
        </TouchableOpacity>

        <View style={styles.sectionHead}>
          <Text style={styles.sectionLabel} testID="continue-header">CONTINUE · CHRONICLES</Text>
          <Text style={styles.sectionCount}>{sessions.length.toString().padStart(2, "0")}</Text>
        </View>

        {loading ? (
          <ActivityIndicator color={COLORS.primary} style={{ marginTop: 24 }} />
        ) : sessions.length === 0 ? (
          <View style={styles.emptyBox} testID="empty-chronicles">
            <Text style={styles.emptyMono}>—  no saved chronicles  —</Text>
            <Text style={styles.emptyProse}>
              Every failure redirects. Every success costs. Begin a new world and see where the dice bend you.
            </Text>
          </View>
        ) : (
          sessions.map((s) => (
            <TouchableOpacity
              key={s.id}
              style={styles.saveSlot}
              onPress={() => router.push(`/play/${s.id}`)}
              onLongPress={() => handleDelete(s.id)}
              testID={`save-slot-${s.id}`}
              activeOpacity={0.7}
            >
              <View style={styles.saveSlotHead}>
                <Text style={styles.saveSlotGenre}>{s.genre.toUpperCase()}</Text>
                <Text style={styles.saveSlotTurn}>T·{String(s.turn_count).padStart(3, "0")}</Text>
              </View>
              <Text style={styles.saveSlotTitle} numberOfLines={1}>{s.title}</Text>
              <Text style={styles.saveSlotSnippet} numberOfLines={2}>
                {s.last_narrative_snippet || "— not yet opened —"}
              </Text>
              <View style={styles.saveSlotFoot}>
                {s.last_state?.Health ? (
                  <Text style={styles.saveSlotStat}>HP · {s.last_state.Health}</Text>
                ) : null}
                {s.last_state?.Stress ? (
                  <Text style={styles.saveSlotStat}>STR · {s.last_state.Stress}</Text>
                ) : null}
                <Text style={styles.saveSlotDifficulty}>DIFF · {s.difficulty}</Text>
              </View>
              <TouchableOpacity
                style={styles.deleteChip}
                onPress={() => handleDelete(s.id)}
                testID={`delete-slot-${s.id}`}
                hitSlop={10}
              >
                <Ionicons name="trash-outline" size={14} color={COLORS.textMuted} />
              </TouchableOpacity>
            </TouchableOpacity>
          ))
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  container: { paddingHorizontal: 20, paddingBottom: 32 },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 12,
  },
  brandMono: {
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 3,
  },
  heroWrap: {
    alignItems: "center",
    paddingTop: 16,
    paddingBottom: 24,
    position: "relative",
  },
  heroGlow: {
    position: "absolute",
    width: 320,
    height: 320,
    borderRadius: 160,
    backgroundColor: COLORS.primaryDim,
    top: 0,
    alignSelf: "center",
  },
  hero: { width: 240, height: 240 },
  title: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 44,
    letterSpacing: 0.5,
    marginTop: 8,
    textAlign: "center",
  },
  subtitle: {
    fontFamily: FONTS.body,
    color: COLORS.textSecondary,
    fontSize: 16,
    textAlign: "center",
    marginTop: 10,
    lineHeight: 22,
    fontStyle: "italic",
  },
  ruleLine: {
    height: 1,
    width: 72,
    backgroundColor: COLORS.primary,
    opacity: 0.5,
    marginTop: 18,
  },
  primaryBtn: {
    marginTop: 8,
    paddingVertical: 18,
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    alignItems: "center",
  },
  primaryBtnText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 14,
    letterSpacing: 4,
  },
  sectionHead: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 36,
    marginBottom: 12,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  sectionLabel: {
    fontFamily: FONTS.mono,
    color: COLORS.textSecondary,
    fontSize: 11,
    letterSpacing: 3,
  },
  sectionCount: {
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 2,
  },
  emptyBox: {
    paddingVertical: 28,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    alignItems: "center",
  },
  emptyMono: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 11,
    letterSpacing: 2,
    marginBottom: 12,
  },
  emptyProse: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 15,
    textAlign: "center",
    lineHeight: 22,
  },
  saveSlot: {
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    padding: 16,
    marginBottom: 12,
    position: "relative",
  },
  saveSlotHead: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  saveSlotGenre: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 10,
    letterSpacing: 3,
  },
  saveSlotTurn: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 2,
  },
  saveSlotTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 22,
    marginBottom: 6,
  },
  saveSlotSnippet: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textProse,
    fontSize: 15,
    lineHeight: 21,
    marginBottom: 10,
  },
  saveSlotFoot: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  saveSlotStat: {
    fontFamily: FONTS.mono,
    color: COLORS.textSecondary,
    fontSize: 10,
    letterSpacing: 1.5,
  },
  saveSlotDifficulty: {
    fontFamily: FONTS.mono,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 1.5,
  },
  deleteChip: {
    position: "absolute",
    top: 12,
    right: 12,
    padding: 4,
  },
});
