import type { MoveKind, MoveRequest } from "./api";

// Kept out of api.ts so screens that stub the network layer still get these constants.

export const MOVE_KINDS: MoveKind[] = ["challenge", "bargain", "route", "regard", "build", "signal", "teach"];

export const MOVE_LABELS: Record<MoveKind, { title: string; blurb: string }> = {
  challenge: { title: "Challenge a claim", blurb: "Put what someone said against what you have seen or hold." },
  bargain: { title: "Strike a bargain", blurb: "Offer something real for something real." },
  route: { title: "Routes", blurb: "Mark a way through you have seen, and choose who learns it." },
  regard: { title: "Between two others", blurb: "Introduce, vouch for, mediate or expose." },
  build: { title: "Leave something behind", blurb: "Set up a shelter, hideout or cache others can use." },
  signal: { title: "Agree a signal", blurb: "Settle a sign with someone you trust, or give one." },
  teach: { title: "Teach a skill", blurb: "Show someone how, then let them use it." },
};

export function moveActionText(m: MoveRequest): string {
  const who = String(m.args.audience ?? m.args.with ?? m.args.learner ?? m.args.a ?? "someone here");
  const base: Record<MoveKind, string> = {
    challenge: `You challenge ${who} with what you have`,
    bargain: `You make ${who} an offer`,
    route: "You deal with a way through",
    regard: `You work on how ${who} sees someone`,
    build: "You set something up for others",
    signal: `You settle a signal with ${who}`,
    teach: `You teach ${who}`,
  };
  // A short fingerprint of the exact move, so a retry of the same move reuses its request id and a different move never does.
  const raw = JSON.stringify([m.kind, m.op ?? null, m.args]);
  let h = 0;
  for (let i = 0; i < raw.length; i++) h = (h * 31 + raw.charCodeAt(i)) | 0;
  return `${base[m.kind]}${m.op ? ` (${m.op})` : ""} #${(h >>> 0).toString(36)}`;
}
