/**
 * Convert raw fetch / OpenRouter error messages into short user-friendly strings.
 */

import { ApiError } from "./api-error";

export const ACTION_CONFLICT_TITLE = "Chronicle already moving";
export const ACTION_CONFLICT_MESSAGE =
  "Another action is being resolved for this chronicle. Checking for the latest turn now.";
export const ACTION_CONFLICT_EXHAUSTION_MESSAGE =
  "The other action is still being resolved. Your text has been kept. Try again in a moment.";

function friendlyFromText(text: string): { title: string; message: string } {
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
        ? `${model} is rate-limited right now. Ask an operator to switch the admin model to DeepSeek or Haiku.`
        : "The active model is being rate-limited upstream. Ask an operator to switch the admin model to DeepSeek or Haiku.",
    };
  }

  // Out of credits
  if (/HTTP 402|Insufficient credits|insufficient_credits/i.test(text)) {
    return {
      title: "Out of credits",
      message:
        "The active OpenRouter model needs credits. Add credits at openrouter.ai/settings/credits, or ask an operator to switch to DeepSeek or Haiku.",
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

  const clean = text.replace(/\s+/g, " ").slice(0, 220);
  return { title: "Something went wrong", message: clean };
}

export function friendlyError(raw: unknown): { title: string; message: string } {
  if (raw instanceof ApiError) {
    if (raw.status === 409) {
      return {
        title: ACTION_CONFLICT_TITLE,
        message: ACTION_CONFLICT_MESSAGE,
      };
    }
    const text = `${raw.status}: ${raw.detail || raw.rawText || raw.message}`;
    return friendlyFromText(text);
  }

  const text = typeof raw === "string" ? raw : (raw as { message?: string })?.message || String(raw);
  if (/^409:|HTTP 409|status[^\d]*409/i.test(text)) {
    return {
      title: ACTION_CONFLICT_TITLE,
      message: ACTION_CONFLICT_MESSAGE,
    };
  }
  return friendlyFromText(text);
}