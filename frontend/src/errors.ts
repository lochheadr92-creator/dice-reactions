/**
 * Convert raw fetch / OpenRouter error messages into short user-friendly strings.
 *
 * Examples of raw input we expect:
 *   "502: {\"detail\":\"Story engine error: OpenRouter request failed after 3 attempts: OpenRouter HTTP 429: ..."}"
 *   "502: {\"detail\":\"Story engine error: OpenRouter HTTP 402: {...Insufficient credits...}\"}"
 *   "TypeError: Network request failed"
 *
 * The output is a single sentence (optionally with a sub-hint) safe to drop into an Alert.
 */

export function friendlyError(raw: unknown): { title: string; message: string } {
  const text = typeof raw === "string" ? raw : (raw as any)?.message || String(raw);

  // Network / transport
  if (/Network request failed|Failed to fetch|TypeError: NetworkError/i.test(text)) {
    return {
      title: "Connection lost",
      message: "Couldn't reach the engine. Check your connection and try again.",
    };
  }

  // Upstream provider rate-limited (free tiers)
  if (/HTTP 429|rate-limited|rate limit|temporarily rate/i.test(text)) {
    const m = /raw\\?":\\?"([^":]+)/i.exec(text);
    const model = m ? m[1].split(":")[0] : null;
    return {
      title: "Model is busy",
      message: model
        ? `${model} is rate-limited right now. Open Settings → ADMIN · AI ENGINE and pick another model (Mythomax or a paid one will work).`
        : "The selected free model is being rate-limited upstream. Open Settings → ADMIN · AI ENGINE and switch to another model.",
    };
  }

  // Out of credits
  if (/HTTP 402|Insufficient credits|insufficient_credits/i.test(text)) {
    return {
      title: "Out of credits",
      message:
        "The active OpenRouter model needs credits. Add some at openrouter.ai/settings/credits, or switch to a :FREE model in Settings → ADMIN · AI ENGINE.",
    };
  }

  // Auth / key
  if (/HTTP 401|invalid api key|unauthorized/i.test(text)) {
    return {
      title: "API key rejected",
      message:
        "OpenRouter rejected the API key. Check OPENROUTER_API_KEY in the backend .env.",
    };
  }

  // Unsupported / unknown model
  if (/HTTP 404|No endpoints found|Unsupported model/i.test(text)) {
    return {
      title: "Model unavailable",
      message:
        "The selected model is no longer available on OpenRouter. Open Settings → ADMIN · AI ENGINE and pick a different one.",
    };
  }

  // Bad output / empty content
  if (/empty content|no choices|finish_reason.*length/i.test(text)) {
    return {
      title: "Empty response",
      message:
        "The model returned no text — usually means max output tokens is too low for this model. Try raising MAX OUTPUT TOKENS in Settings → ADMIN · AI ENGINE.",
    };
  }

  // 5xx / generic backend
  if (/^5\d\d|HTTP 5\d\d|Story engine error|gateway/i.test(text)) {
    return {
      title: "Engine hesitated",
      message:
        "The story engine couldn't respond just now. Try again. If it persists, switch model in Settings → ADMIN · AI ENGINE.",
    };
  }

  // Fallback — truncate long JSON
  const clean = text.replace(/\s+/g, " ").slice(0, 220);
  return { title: "Something went wrong", message: clean };
}
