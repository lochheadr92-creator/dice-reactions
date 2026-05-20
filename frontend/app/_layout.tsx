import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useFonts } from "expo-font";
import { EBGaramond_400Regular, EBGaramond_500Medium, EBGaramond_600SemiBold, EBGaramond_400Regular_Italic } from "@expo-google-fonts/eb-garamond";
import { CormorantGaramond_400Regular, CormorantGaramond_500Medium, CormorantGaramond_600SemiBold, CormorantGaramond_700Bold } from "@expo-google-fonts/cormorant-garamond";
import { JetBrainsMono_400Regular, JetBrainsMono_500Medium, JetBrainsMono_700Bold } from "@expo-google-fonts/jetbrains-mono";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

export default function RootLayout() {
  const [loaded] = useFonts({
    EBGaramond_400Regular,
    EBGaramond_500Medium,
    EBGaramond_600SemiBold,
    EBGaramond_400Regular_Italic,
    CormorantGaramond_400Regular,
    CormorantGaramond_500Medium,
    CormorantGaramond_600SemiBold,
    CormorantGaramond_700Bold,
    JetBrainsMono_400Regular,
    JetBrainsMono_500Medium,
    JetBrainsMono_700Bold,
  });

  if (!loaded) {
    return (
      <View style={styles.loading} testID="font-loading-screen">
        <ActivityIndicator size="small" color="#F59E0B" />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: "#050505" },
          animation: "fade",
        }}
      />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    backgroundColor: "#050505",
    alignItems: "center",
    justifyContent: "center",
  },
});
