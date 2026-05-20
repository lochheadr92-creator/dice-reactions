import { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Switch,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../src/theme";
import { getSettings, saveSettings, AppSettings } from "../src/storage";

export default function SettingsScreen() {
  const router = useRouter();
  const [settings, setSettings] = useState<AppSettings>({ debugDefault: false, fontScale: 1 });

  useEffect(() => {
    getSettings().then(setSettings);
  }, []);

  const update = async (patch: Partial<AppSettings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    await saveSettings(next);
  };

  return (
    <SafeAreaView style={styles.safe} testID="settings-screen">
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} testID="back-btn">
          <Ionicons name="chevron-back" size={22} color={COLORS.textSecondary} />
        </TouchableOpacity>
        <Text style={styles.topTitle}>SETTINGS</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
        <Text style={styles.section}>· ENGINE ·</Text>

        <View style={styles.row}>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>DEBUG · MODE · DEFAULT</Text>
            <Text style={styles.rowHelp}>
              Reveal hidden rolls, modifiers, and active systems for new chronicles.
            </Text>
          </View>
          <Switch
            value={settings.debugDefault}
            onValueChange={(v) => update({ debugDefault: v })}
            trackColor={{ false: COLORS.border, true: COLORS.primary }}
            thumbColor={settings.debugDefault ? COLORS.primary : COLORS.textMuted}
            testID="debug-default-switch"
          />
        </View>

        <Text style={[styles.section, { marginTop: 28 }]}>· READING ·</Text>
        <Text style={styles.rowHelp}>Story prose size.</Text>
        <View style={styles.scaleRow}>
          {[0.9, 1, 1.1, 1.25].map((s) => (
            <TouchableOpacity
              key={s}
              style={[styles.scaleChip, settings.fontScale === s && styles.scaleChipActive]}
              onPress={() => update({ fontScale: s })}
              testID={`font-scale-${s}`}
            >
              <Text
                style={[
                  styles.scaleChipText,
                  settings.fontScale === s && styles.scaleChipTextActive,
                ]}
              >
                {s === 0.9 ? "S" : s === 1 ? "M" : s === 1.1 ? "L" : "XL"}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={[styles.section, { marginTop: 36 }]}>· ABOUT ·</Text>
        <View style={styles.aboutBox}>
          <Text style={styles.aboutTitle}>Dice Reaction Story Engine</Text>
          <Text style={styles.aboutVer}>Master Runtime · v3.3</Text>
          <Text style={styles.aboutBody}>
            A persistent causal simulation. Every action resolved through hidden D20 logic. Failure
            redirects, success costs, and consequences carry. Powered by Claude Sonnet 4.5.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderDim,
  },
  topTitle: {
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 3,
  },
  container: { padding: 20 },
  section: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 11,
    letterSpacing: 4,
    marginBottom: 14,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 16,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
    gap: 12,
  },
  rowTitle: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textPrimary,
    fontSize: 11,
    letterSpacing: 2,
  },
  rowHelp: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 13,
    marginTop: 4,
    lineHeight: 18,
  },
  scaleRow: { flexDirection: "row", gap: 8, marginTop: 12 },
  scaleChip: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
  },
  scaleChipActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  scaleChipText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 12,
    letterSpacing: 2,
  },
  scaleChipTextActive: { color: COLORS.primary },
  aboutBox: {
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
  },
  aboutTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 22,
    marginBottom: 4,
  },
  aboutVer: {
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 2,
    marginBottom: 12,
  },
  aboutBody: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textProse,
    fontSize: 14,
    lineHeight: 21,
  },
});
