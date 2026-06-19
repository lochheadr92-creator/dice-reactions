import React from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
} from "react-native";
import { COLORS, FONTS } from "../theme";

export type ReviewSummaryRow = {
  key: string;
  label: string;
  value?: string;
  onChange: () => void;
};

type ReviewSummaryProps = {
  testIdPrefix: string;
  heading: string;
  summary: string;
  rows: ReviewSummaryRow[];
  fontScale: number;
  loading: boolean;
  onBack: () => void;
  onStart: () => void;
};

export function ReviewSummary({
  testIdPrefix,
  heading,
  summary,
  rows,
  fontScale,
  loading,
  onBack,
  onStart,
}: ReviewSummaryProps) {
  const safeFontScale = fontScale > 0 ? fontScale : 1;
  const bodySize = Math.round(16 * safeFontScale);

  return (
    <View testID={`${testIdPrefix}-review-step`}>
      <Text
        style={[styles.stepText, { fontSize: Math.max(12, Math.round(12 * safeFontScale)) }]}
        testID={`${testIdPrefix}-review-label`}
      >
        Review
      </Text>
      <Text style={[styles.stepQuestion, { fontSize: Math.round(24 * safeFontScale) }]}>
        {heading}
      </Text>
      <Text
        style={[styles.reviewSummary, { fontSize: Math.max(18, Math.round(18 * safeFontScale)) }]}
        testID={`${testIdPrefix}-review-summary`}
      >
        {summary}
      </Text>

      <View style={styles.reviewList}>
        {rows.map((row) => (
          <View
            key={row.key}
            style={styles.reviewRow}
            testID={`${testIdPrefix}-review-row-${row.key}`}
          >
            <View style={styles.reviewTextWrap}>
              <Text
                style={[
                  styles.reviewLabel,
                  { fontSize: Math.max(12, Math.round(12 * safeFontScale)) },
                ]}
              >
                {row.label}
              </Text>
              <Text
                style={[styles.reviewValue, { fontSize: Math.round(17 * safeFontScale) }]}
                testID={`${testIdPrefix}-review-value-${row.key}`}
              >
                {row.value}
              </Text>
            </View>
            <TouchableOpacity
              style={styles.reviewChangeButton}
              onPress={row.onChange}
              testID={`${testIdPrefix}-change-${row.key}`}
            >
              <Text
                style={[
                  styles.reviewChangeText,
                  { fontSize: Math.max(12, Math.round(12 * safeFontScale)) },
                ]}
              >
                Change
              </Text>
            </TouchableOpacity>
          </View>
        ))}
      </View>

      <View style={styles.navRow}>
        <TouchableOpacity
          style={styles.secondaryButton}
          onPress={onBack}
          disabled={loading}
          testID={`${testIdPrefix}-review-back-button`}
        >
          <Text style={[styles.secondaryButtonText, { fontSize: bodySize }]}>Back</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.primaryButton, loading && styles.primaryButtonDisabled]}
          onPress={onStart}
          disabled={loading}
          accessibilityRole="button"
          accessibilityState={{ disabled: loading, busy: loading }}
          accessibilityLabel={loading ? "Starting your chronicle" : "Start chronicle"}
          testID={`${testIdPrefix}-start-button`}
        >
          {loading ? (
            <View style={styles.loadingRow} testID={`${testIdPrefix}-loading-state`}>
              <ActivityIndicator color={COLORS.background} />
              <Text
                style={[
                  styles.primaryButtonText,
                  { fontSize: bodySize, color: COLORS.background },
                ]}
              >
                Starting your chronicle…
              </Text>
            </View>
          ) : (
            <Text style={[styles.primaryButtonText, { fontSize: bodySize }]}>Start chronicle</Text>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stepText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    letterSpacing: 2,
    marginBottom: 8,
  },
  stepQuestion: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    lineHeight: 30,
  },
  reviewSummary: {
    marginTop: 8,
    marginBottom: 22,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textProse,
    lineHeight: 26,
  },
  reviewList: {
    gap: 12,
  },
  reviewRow: {
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  reviewTextWrap: {
    flex: 1,
  },
  reviewLabel: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textMuted,
    letterSpacing: 1.5,
    marginBottom: 4,
  },
  reviewValue: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
  },
  reviewChangeButton: {
    minWidth: 74,
    minHeight: 44,
    borderWidth: 1,
    borderColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 10,
  },
  reviewChangeText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    letterSpacing: 1.2,
  },
  navRow: {
    marginTop: 22,
    flexDirection: "row",
    gap: 12,
  },
  secondaryButton: {
    flex: 1,
    minHeight: 54,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surfaceDeep,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 12,
  },
  secondaryButtonText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.textSecondary,
    letterSpacing: 1.5,
  },
  primaryButton: {
    flex: 1.4,
    minHeight: 54,
    backgroundColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 12,
  },
  primaryButtonDisabled: {
    opacity: 0.45,
  },
  primaryButtonText: {
    fontFamily: FONTS.monoBold,
    color: COLORS.background,
    letterSpacing: 1.5,
  },
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
});