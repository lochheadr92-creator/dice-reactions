import type { Turn } from "./api";

function compareTurns(a: Turn, b: Turn): number {
  const byNumber = a.turn_number - b.turn_number;
  if (byNumber !== 0) {
    return byNumber;
  }
  return a.id.localeCompare(b.id);
}

/**
 * Merge local and server turn lists without duplicates.
 * Deduplicates by turn.id; prefers incoming copy when IDs match.
 * Different IDs with the same turn_number are both kept; tie-break sorts by id.
 */
export function mergeChronicleTurns(current: Turn[], incoming: Turn[]): Turn[] {
  const byId = new Map<string, Turn>();
  for (const turn of current) {
    if (turn?.id) {
      byId.set(turn.id, turn);
    }
  }
  for (const turn of incoming) {
    if (turn?.id) {
      byId.set(turn.id, turn);
    }
  }
  return Array.from(byId.values()).sort(compareTurns);
}

export function maxTurnNumber(turns: Turn[]): number {
  return turns.reduce((max, turn) => Math.max(max, turn.turn_number || 0), 0);
}

export function hasNewerTurnThan(baselineMax: number, turns: Turn[]): boolean {
  return maxTurnNumber(turns) > baselineMax;
}