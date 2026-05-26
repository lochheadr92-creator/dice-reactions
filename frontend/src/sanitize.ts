// ---------------------------------------------------------------------------
// Player-facing presentation sanitiser.
//
// The engine occasionally lets internal mechanics bleed into the narrative
// payload (malformed LLM output, truncated tags, or mechanic lines written
// inside the <narrative> block). This module strips those artifacts before
// the Chronicle view renders them.
//
// IMPORTANT: this is a PRESENTATION-only filter. It must NEVER touch the
// underlying turn object stored in state — only the array of strings we hand
// to <Text>. Rolling state, debug data, raw JSON, and consequence ledger
// remain intact in memory/API and are still rendered inside the Developer
// Mode diagnostics panel.
// ---------------------------------------------------------------------------

// Engine wrapper tags we never want to show the player. We match either a
// complete <tag>…</tag> span (greedy across newlines) OR a stray opening
// tag through the end of the paragraph when no close tag was emitted.
const ENGINE_TAG_NAMES = [
  "rolling_state",
  "debug",
  "state",
  "ledger",
  "choices",
  "prior_state",
  "scenario",
  "system",
];

const ENGINE_TAG_GROUP = ENGINE_TAG_NAMES.join("|");

// Matches a balanced <tag>…</tag> span.
const ENGINE_TAG_BLOCK_RE = new RegExp(
  `<(${ENGINE_TAG_GROUP})\\b[^>]*>[\\s\\S]*?<\\/\\1\\s*>`,
  "gi",
);

// Matches an unclosed opening engine tag through the end of the string
// (handles truncated LLM responses that leak rolling_state JSON).
const ENGINE_OPEN_TAG_TO_END_RE = new RegExp(
  `<(${ENGINE_TAG_GROUP})\\b[^>]*>[\\s\\S]*$`,
  "i",
);

// Matches any leftover stray engine tag fragments.
const STRAY_ENGINE_TAG_RE = new RegExp(
  `<\\/?(?:${ENGINE_TAG_GROUP}|narrative)\\b[^>]*>`,
  "gi",
);

// A single line that is purely a mechanics readout. Anchored to start-of-line
// and requires the colon/equals separator so that prose like
// "Roll a stone in your palm" or "Modifiers were never the point" survive.
const MECHANIC_LINE_RE =
  /^\s*(?:Roll|Modifiers?|Final|Outcome|Tier|Difficulty(?:\s*Modifier)?|Active\s*systems?|Consequence(?:\s*budget)?|Delayed\s*trigger(?:\s*stored)?|Latent\s*trigger(?:\s*stored)?|Scale|Pressure\s*horizon|Rolling\s*state|Debug|Trigger|System|DEV[_\s-]?MODE)\s*[:=]\s*\S/i;

// A line that looks like raw JSON / object fragment.
const JSON_LIKE_LINE_RE = /^\s*[\{\}\[\]]/;

// Choice text that effectively says "no choice".
const EMPTY_CHOICE_RE =
  /^[\s\-_—–·.,;:()\[\]"'`]*(?:none|empty|n\/?a|nothing|null|undefined|—+|-+)?[\s\-_—–·.,;:()\[\]"'`]*$/i;

function stripEngineMarkup(input: string): string {
  if (!input) return "";
  let out = input;
  // Repeatedly strip complete <tag>…</tag> blocks until none remain.
  let prev = "";
  while (prev !== out) {
    prev = out;
    out = out.replace(ENGINE_TAG_BLOCK_RE, " ");
  }
  // Strip any leaked open tag (no matching close) to end of paragraph.
  out = out.replace(ENGINE_OPEN_TAG_TO_END_RE, " ");
  // Strip any stray tag fragments still lying around.
  out = out.replace(STRAY_ENGINE_TAG_RE, " ");
  return out;
}

function cleanSingleParagraph(raw: string): string {
  if (!raw) return "";
  const stripped = stripEngineMarkup(raw);
  const keptLines: string[] = [];
  for (const line of stripped.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (MECHANIC_LINE_RE.test(trimmed)) continue;
    if (JSON_LIKE_LINE_RE.test(trimmed)) continue;
    keptLines.push(trimmed);
  }
  return keptLines.join(" ").replace(/\s{2,}/g, " ").trim();
}

/**
 * Sanitise the paragraphs we render in the Chronicle view.
 *
 * Behaviour:
 *  - Prefer the structured `paragraphs` array when present.
 *  - Otherwise fall back to splitting the raw `narrative` on blank lines.
 *  - Strip engine tags, mechanic lines, and JSON-like fragments per paragraph.
 *  - Discard paragraphs that become empty after cleaning.
 */
export function sanitizeParagraphs(
  paragraphs: string[] | undefined | null,
  fallbackNarrative?: string | null,
): string[] {
  let source: string[] = [];
  if (paragraphs && paragraphs.length > 0) {
    source = paragraphs;
  } else if (fallbackNarrative) {
    source = fallbackNarrative
      .split(/\n\s*\n/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  const cleaned: string[] = [];
  for (const p of source) {
    const c = cleanSingleParagraph(p);
    if (c) cleaned.push(c);
  }
  return cleaned;
}

/**
 * Filter the A-F choices so empty / placeholder slots are removed.
 */
export function sanitizeChoices<T extends { label: string; text: string }>(
  choices: T[] | undefined | null,
): T[] {
  if (!choices || choices.length === 0) return [];
  return choices.filter((c) => {
    if (!c || typeof c.text !== "string") return false;
    const t = c.text.trim();
    if (!t) return false;
    if (EMPTY_CHOICE_RE.test(t)) return false;
    return true;
  });
}
