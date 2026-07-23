import React from "react";
import {
  ActivityIndicator,
  Image,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../theme";

/**
 * Quick Start world cards — one tap creates a chronicle.
 *
 * Each card maps to a curated scenario_pool (documented mirror of the backend
 * registry). Live scenario_id selection is backend-only:
 *   POST /story/new with quick_start_key + creation_request_id
 *   → SHA256("quick-scenario:" + creation_request_id) pick from pool.
 * Client must not send a client-selected scenario_id on the Quick Start path.
 */
export type QuickStartGenre = {
  key: string;
  label: string;
  tagline: string;
  image: string;
  /** Top-level `genre` sent to POST /story/new */
  genre: string;
  /** Card default role; session role is overwritten by selected scenario on server. */
  role: string;
  tone: string;
  difficulty: "soft" | "standard" | "hard" | "brutal";
  mode: "advanced";
  /**
   * Documented mirror of backend QUICK_START_SCENARIO_POOLS[key].
   * Not used for live selection — backend is sole authority.
   * Must never include dinosaur-containment-breach under prehistoric.
   */
  scenario_pool: readonly string[];
};

export const QUICK_START_GENRES: readonly QuickStartGenre[] = [
  {
    key: "fantasy",
    label: "Fantasy",
    tagline: "Oaths, relics, and kingdoms in slow collapse.",
    image:
      "https://static.prod-images.emergentagent.com/jobs/1f4993bf-965b-40a7-8797-1d8bc205019e/images/3faa0f0bf91c735e5727f826cce85e16076fff278b6a93a826f43d2fd235c453.png",
    genre: "fantasy",
    role: "oathbound steward",
    tone: "mythic",
    difficulty: "standard",
    mode: "advanced",
    scenario_pool: ["oath-broken-keep", "relic-road-toll", "kingdom-border-curse"],
  },
  {
    key: "post-apocalyptic",
    label: "Post-Apocalyptic",
    tagline: "Scarcity, salvage, trust as currency.",
    image:
      "https://static.prod-images.emergentagent.com/jobs/1f4993bf-965b-40a7-8797-1d8bc205019e/images/a077cabe987d3d5beec7cd3580f9cfd394a20bd25c13cc9aaed8a7e7ca462cbb.png",
    genre: "post-apocalyptic",
    role: "ordinary resident",
    tone: "grim",
    difficulty: "hard",
    mode: "advanced",
    scenario_pool: ["suburban-collapse", "ash-caravan-ambush", "dry-reservoir-claim"],
  },
  {
    key: "cosmic-horror",
    label: "Cosmic Horror",
    tagline: "Doomed curiosity, perception unraveling.",
    image:
      "https://static.prod-images.emergentagent.com/jobs/1f4993bf-965b-40a7-8797-1d8bc205019e/images/1871295a9e304d75675d6744ab08139cbbe71471bb4262e6baab1ddfbba19836.png",
    genre: "cosmic horror",
    role: "passing traveller",
    tone: "bleak",
    difficulty: "hard",
    mode: "advanced",
    scenario_pool: [
      "cosmic-horror-road-town",
      "lighthouse-signal-loop",
      "library-that-rewrites",
    ],
  },
  {
    key: "detective",
    label: "Detective / Noir",
    tagline: "Clues, lies, and a timeline that won't hold.",
    image:
      "https://images.unsplash.com/photo-1764536602389-07ee8e0b4f55?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    genre: "detective",
    role: "private investigator",
    tone: "grounded",
    difficulty: "standard",
    mode: "advanced",
    scenario_pool: [
      "rain-district-alibi",
      "warehouse-shift-murder",
      "jazz-club-blackmail",
    ],
  },
  {
    key: "dinosaur-survival",
    label: "Prehistoric Survival",
    tagline: "Tracks, scent, and the food chain.",
    image:
      "https://images.pexels.com/photos/1671324/pexels-photo-1671324.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    genre: "prehistoric survival",
    role: "hunt leader",
    tone: "tense, sweat-and-rain procedural",
    difficulty: "brutal",
    mode: "advanced",
    // Literal prehistoric only — never dinosaur-containment-breach (modern research).
    scenario_pool: ["flint-band-stalked", "river-ice-calving", "tar-pit-foraging"],
  },
  {
    key: "horror",
    label: "Horror",
    tagline: "Isolation, dread, false safety.",
    image:
      "https://images.unsplash.com/photo-1712777691122-8a10db0a78a2?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    genre: "horror",
    role: "stranded traveller",
    tone: "grim",
    difficulty: "hard",
    mode: "advanced",
    scenario_pool: [
      "farmhouse-false-safety",
      "mine-elevator-stuck",
      "fog-boarding-house",
    ],
  },
  {
    key: "urban-crime",
    label: "Urban Crime",
    tagline: "Heat, money, loyalty as leverage.",
    image:
      "https://images.unsplash.com/photo-1764536602389-07ee8e0b4f55?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    genre: "urban crime",
    role: "courier",
    tone: "grounded",
    difficulty: "standard",
    mode: "advanced",
    scenario_pool: ["dockside-cut", "rooftop-debt-run", "precinct-leak"],
  },
  {
    key: "war-survival",
    label: "War & Attrition",
    tagline: "Morale, supply lines, command pressure.",
    image:
      "https://images.unsplash.com/photo-1712777691122-8a10db0a78a2?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    genre: "war survival",
    role: "section leader",
    tone: "grim",
    difficulty: "hard",
    mode: "advanced",
    scenario_pool: [
      "trench-supply-gap",
      "convoy-bridge-hold",
      "occupied-quarter-curfew",
    ],
  },
] as const;

export type QuickStartRequest = {
  genre: string;
  tone: string;
  difficulty: string;
  mode: "advanced";
  role: string;
  /** Backend selects scenario_id from this card's pool. */
  quick_start_key: string;
};

/**
 * Build the POST /story/new body for a Quick Start card.
 * Does not select scenario_id — backend resolves from quick_start_key + creation_request_id.
 */
export function buildQuickStartRequest(option: QuickStartGenre): QuickStartRequest {
  return {
    genre: option.genre,
    tone: option.tone,
    difficulty: option.difficulty,
    mode: option.mode,
    role: option.role,
    quick_start_key: option.key,
  };
}

export function getQuickStartGenre(key: string): QuickStartGenre | undefined {
  return QUICK_START_GENRES.find((option) => option.key === key);
}

/** Every Quick card has a non-empty pool; prehistoric excludes modern containment. */
export function assertQuickStartPoolsHealthy(): void {
  for (const card of QUICK_START_GENRES) {
    if (card.scenario_pool.length < 3) {
      throw new Error(`${card.key} pool must have at least 3 scenarios`);
    }
    if (card.key === "dinosaur-survival") {
      if (card.scenario_pool.includes("dinosaur-containment-breach")) {
        throw new Error("Prehistoric Survival must not use dinosaur-containment-breach");
      }
    }
  }
}

type QuickStartProps = {
  creationLoading: boolean;
  launchingGenreKey: string | null;
  fontScale: number;
  onStart: (option: QuickStartGenre) => void;
};

export function QuickStart({
  creationLoading,
  launchingGenreKey,
  fontScale,
  onStart,
}: QuickStartProps) {
  const safeFontScale = fontScale > 0 ? fontScale : 1;
  const titleSize = Math.round(30 * safeFontScale);
  const bodySize = Math.round(15 * safeFontScale);

  return (
    <View testID="quick-start-panel">
      <Text style={styles.label}>QUICK START</Text>
      <Text
        style={[styles.heading, { fontSize: titleSize }]}
        testID="quick-start-heading"
      >
        Choose a world. Start immediately.
      </Text>
      <Text style={[styles.help, { fontSize: bodySize }]}>
        One broad setting. No questionnaire. Tap a world and the chronicle opens.
      </Text>

      <View style={styles.grid} testID="quick-start-genre-grid">
        {QUICK_START_GENRES.map((option) => {
          const launching = launchingGenreKey === option.key;
          return (
            <TouchableOpacity
              key={option.key}
              style={[styles.genreCard, creationLoading && styles.cardDisabled]}
              onPress={() => onStart(option)}
              disabled={creationLoading}
              activeOpacity={0.8}
              accessibilityRole="button"
              accessibilityLabel={`Start ${option.label} chronicle`}
              accessibilityHint={option.tagline}
              accessibilityState={{ disabled: creationLoading, busy: launching }}
              testID={`quick-start-genre-${option.key}`}
            >
              {option.image ? (
                <Image source={{ uri: option.image }} style={styles.genreImage} />
              ) : (
                <View style={[styles.genreImage, styles.genreImageFallback]}>
                  <Ionicons name="planet-outline" size={30} color={COLORS.textMuted} />
                </View>
              )}
              <View style={styles.genreOverlay} />
              {launching ? (
                <View style={styles.launchingOverlay} testID={`quick-start-launching-${option.key}`}>
                  <ActivityIndicator color={COLORS.primary} />
                </View>
              ) : null}
              <View style={styles.genreTextWrap}>
                <Text style={styles.genreTitle} numberOfLines={1}>
                  {option.label}
                </Text>
                <Text style={styles.genreTag} numberOfLines={2}>
                  {option.tagline}
                </Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      {creationLoading ? (
        <Text style={styles.creatingHint} testID="quick-start-creating-hint">
          Creating chronicle…
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  label: {
    fontFamily: FONTS.monoBold,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 3,
    marginBottom: 8,
  },
  heading: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    lineHeight: 36,
  },
  help: {
    marginTop: 10,
    marginBottom: 20,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    lineHeight: 22,
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    gap: 10,
  },
  genreCard: {
    width: "48.5%",
    aspectRatio: 0.95,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    overflow: "hidden",
    minHeight: 140,
  },
  cardDisabled: {
    opacity: 0.62,
  },
  genreImage: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    width: "100%",
    height: "100%",
  },
  genreImageFallback: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.surfaceDeep,
  },
  genreOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(5, 5, 5, 0.55)",
  },
  launchingOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(5, 5, 5, 0.45)",
    zIndex: 2,
  },
  genreTextWrap: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: 12,
    zIndex: 1,
  },
  genreTitle: {
    fontFamily: FONTS.headingBold,
    color: COLORS.textPrimary,
    fontSize: 18,
    lineHeight: 22,
  },
  genreTag: {
    marginTop: 4,
    fontFamily: FONTS.bodyItalic,
    color: COLORS.textSecondary,
    fontSize: 12,
    lineHeight: 16,
  },
  creatingHint: {
    marginTop: 16,
    fontFamily: FONTS.mono,
    color: COLORS.primary,
    fontSize: 11,
    letterSpacing: 1.5,
    textAlign: "center",
  },
});
