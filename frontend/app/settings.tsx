import { useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Switch,
  Alert,
  TextInput,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../src/theme";
import { getSettings, saveSettings, AppSettings } from "../src/storage";
import { getAdminSettings, updateAdminSettings } from "../src/api";
import type { AdminSettingsResponse } from "../src/api";

export default function SettingsScreen() {
  const router = useRouter();
  const [settings, setSettings] = useState<AppSettings>({ debugDefault: false, fontScale: 1 });

  const [devUnlocked, setDevUnlocked] = useState(false);
  const versionTapCount = useRef(0);
  const versionTapReset = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [adminKey, setAdminKey] = useState("");
  const [adminData, setAdminData] = useState<AdminSettingsResponse | null>(null);
  const [adminError, setAdminError] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);
  const [savingModel, setSavingModel] = useState<string | null>(null);

  useEffect(() => {
    getSettings().then((s) => {
      setSettings(s);
      setDevUnlocked(!!s.developerUnlocked);
    });
    return () => {
      if (versionTapReset.current) {
        clearTimeout(versionTapReset.current);
      }
    };
  }, []);

  const bumpVersionTap = async () => {
    const next = versionTapCount.current + 1;
    versionTapCount.current = next;
    if (next >= 7 && !devUnlocked) {
      setDevUnlocked(true);
      const updated = { ...settings, developerUnlocked: true };
      setSettings(updated);
      await saveSettings(updated);
      Alert.alert(
        "Developer access",
        "Local diagnostics preferences unlocked. Server admin settings require operator credentials — see docs/api.md."
      );
    }
    if (versionTapReset.current) {
      clearTimeout(versionTapReset.current);
    }
    versionTapReset.current = setTimeout(() => {
      versionTapCount.current = 0;
    }, 2000);
  };

  const lockDeveloper = async () => {
    setDevUnlocked(false);
    versionTapCount.current = 0;
    setAdminData(null);
    setAdminError("");
    setAdminKey("");
    const updated = { ...settings, developerUnlocked: false, debugDefault: false };
    setSettings(updated);
    await saveSettings(updated);
  };

  const update = async (patch: Partial<AppSettings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    await saveSettings(next);
  };

  const adminModelLabel = (modelId: string | undefined) => {
    if (!modelId) return "Unknown";
    return adminData?.models.find((m) => m.id === modelId)?.label || modelId;
  };

  const loadAdminSettings = async () => {
    const key = adminKey.trim();
    if (!key) {
      Alert.alert("Admin key required", "Enter the server ADMIN_API_KEY to use AI engine controls.");
      return;
    }
    setAdminLoading(true);
    setAdminError("");
    try {
      const data = await getAdminSettings(key);
      setAdminData(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setAdminError(message);
      setAdminData(null);
    } finally {
      setAdminLoading(false);
    }
  };

  const selectModel = async (modelId: string) => {
    const key = adminKey.trim();
    if (!key) {
      Alert.alert("Admin key required", "Enter the server ADMIN_API_KEY to use AI engine controls.");
      return;
    }
    setSavingModel(modelId);
    setAdminError("");
    try {
      const result = await updateAdminSettings(key, { model: modelId });
      setAdminData((current) =>
        current ? { ...current, settings: result.settings } : { settings: result.settings, models: [] }
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setAdminError(message);
    } finally {
      setSavingModel(null);
    }
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
        <Text style={styles.section}>· READING ·</Text>
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

        {devUnlocked && (
          <View style={[styles.row, { marginTop: 28 }]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>DEVELOPER · DIAGNOSTICS</Text>
              <Text style={styles.rowHelp}>
                Local preference: request debug blocks on new actions when server developer_mode is
                enabled by an operator. Player API responses remain sanitised.
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
        )}

        {devUnlocked && (
          <TouchableOpacity
            style={[styles.row, { marginTop: 10 }]}
            onPress={() =>
              Alert.alert(
                "Lock developer mode?",
                "Hide local diagnostics preferences on this device.",
                [
                  { text: "Cancel", style: "cancel" },
                  { text: "Lock", style: "destructive", onPress: lockDeveloper },
                ]
              )
            }
            testID="lock-developer"
          >
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>LOCK · DEVELOPER · MODE</Text>
              <Text style={styles.rowHelp}>Hide local diagnostics controls on this device.</Text>
            </View>
            <Ionicons name="lock-closed-outline" size={18} color={COLORS.textSecondary} />
          </TouchableOpacity>
        )}

        {devUnlocked && <Text style={[styles.section, { marginTop: 36 }]}>ADMIN</Text>}
        {devUnlocked && (
          <View style={styles.adminPanel} testID="admin-ai-engine">
            <Text style={styles.rowTitle}>ADMIN - AI ENGINE</Text>
            <Text style={styles.rowHelp}>
              Enter the server admin key to read and update runtime model selection.
            </Text>
            <TextInput
              value={adminKey}
              onChangeText={setAdminKey}
              placeholder="ADMIN_API_KEY"
              placeholderTextColor={COLORS.textMuted}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.adminInput}
              testID="admin-key-input"
            />
            <TouchableOpacity
              style={[styles.adminButton, adminLoading && styles.adminButtonDisabled]}
              onPress={loadAdminSettings}
              disabled={adminLoading}
              testID="admin-load-settings"
            >
              <Text style={styles.adminButtonText}>
                {adminLoading ? "LOADING" : "LOAD AI SETTINGS"}
              </Text>
            </TouchableOpacity>
            {adminError ? (
              <Text style={styles.adminError} testID="admin-error">
                {adminError}
              </Text>
            ) : null}
            {adminData ? (
              <View style={styles.adminModelBox}>
                <Text style={styles.adminLabel}>ACTIVE MODEL</Text>
                <Text style={styles.activeModel} testID="active-model-value">
                  {adminModelLabel(adminData.settings.model)}
                </Text>
                <View style={styles.modelList}>
                  {adminData.models.map((model) => {
                    const selected = adminData.settings.model === model.id;
                    const saving = savingModel === model.id;
                    return (
                      <TouchableOpacity
                        key={model.id}
                        style={[styles.modelButton, selected && styles.modelButtonActive]}
                        onPress={() => selectModel(model.id)}
                        disabled={savingModel !== null}
                        testID={`model-select-${model.id}`}
                      >
                        <Text
                          style={[
                            styles.modelButtonText,
                            selected && styles.modelButtonTextActive,
                          ]}
                        >
                          {saving ? "SAVING" : model.label}
                        </Text>
                        <Text style={styles.modelNote}>{model.note || model.id}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            ) : null}
          </View>
        )}

        <Text style={[styles.section, { marginTop: 36 }]}>· ABOUT ·</Text>
        <TouchableOpacity activeOpacity={1} onPress={bumpVersionTap} style={styles.aboutBox} testID="version-tap">
          <Text style={styles.aboutTitle}>Statebound</Text>
          <Text style={styles.aboutVer}>
            Master Runtime · v3.4{devUnlocked ? "  ·  DEV" : ""}
          </Text>
          <Text style={styles.aboutBody}>
            A persistent causal simulation. Every action resolved through hidden D20 logic. Failure
            redirects, success costs, and consequences carry. Powered by OpenRouter.
          </Text>
        </TouchableOpacity>
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
  container: { padding: 20, paddingBottom: 48 },
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
  adminPanel: {
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.borderDim,
    backgroundColor: COLORS.surfaceDeep,
    gap: 12,
  },
  adminInput: {
    borderWidth: 1,
    borderColor: COLORS.border,
    color: COLORS.textPrimary,
    fontFamily: FONTS.mono,
    fontSize: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginTop: 4,
  },
  adminButton: {
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
    paddingVertical: 11,
    alignItems: "center",
  },
  adminButtonDisabled: {
    opacity: 0.55,
  },
  adminButtonText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 2,
  },
  adminError: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.danger,
    fontSize: 13,
    lineHeight: 18,
  },
  adminModelBox: {
    borderTopWidth: 1,
    borderTopColor: COLORS.borderDim,
    paddingTop: 12,
  },
  adminLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    fontSize: 10,
    letterSpacing: 2,
  },
  activeModel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textPrimary,
    fontSize: 12,
    marginTop: 6,
  },
  modelList: {
    gap: 8,
    marginTop: 12,
  },
  modelButton: {
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  modelButtonActive: {
    borderColor: COLORS.primary,
    backgroundColor: COLORS.primarySoft,
  },
  modelButtonText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    fontSize: 11,
    letterSpacing: 1,
  },
  modelButtonTextActive: {
    color: COLORS.primary,
  },
  modelNote: {
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textMuted,
    fontSize: 12,
    lineHeight: 16,
    marginTop: 4,
  },
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
