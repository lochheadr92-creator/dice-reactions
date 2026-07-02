# Builders Contest Demo Runbook — "The Engine Owns Reality"

**Scenario:** `suburban-collapse` (Suburban Collapse)
**Branch:** `emergent` · **Demo length:** 5 minutes · **Turns:** opening + 5 actions (T1–T6)
**Verified live:** 2026-07-04 — full six-turn spine executed against the running backend; every engine event below was observed in the raw export of that session.
**Pinned by tests:** `backend/tests/test_contest_demo_runbook.py` (deterministic, provider-free; keeps every scripted action string in sync with the engine's classification rules).

---

## 1. Why this scenario

- Grounded, instantly legible premise (suburban grid collapse) — judges need zero genre onboarding.
- Two named NPCs with opposite arcs: **Marlene Cho** (ally you warm up) and **Greg Stahl** (neutral you destroy). Full names matter — see §6.
- Seeded pressure (the Hendersons' silent generator) and a hidden threat give the pressure graph real nodes from turn 1.
- `hard` difficulty, not `brutal` — the player will not die mid-demo (the dinosaur scenario can kill you; the horror scenario burns turns on atmosphere).

## 2. Exact creation selections

1. Home screen → **NEW STORY** (`new-story-btn`).
2. The creation screen opens on the **Quick** flow — switch to the **Advanced** flow tab.
3. Tap the scenario card **"Suburban Collapse"** (`scenario-suburban-collapse`). Leave genre/role/tone/difficulty untouched — the scenario supplies them (`post-apocalyptic`, `ordinary resident`, `hard`, `advanced` mode).
4. Tap **Start**. Opening generation takes ~20–40 s (observed 38 s live).

API equivalent (for a terminal-driven demo or rehearsal):

```bash
curl -X POST $BASE/api/story/new \
  -H "Content-Type: application/json" -H "X-Device-Id: <device>" \
  -d '{"device_id":"<device>","genre":"post-apocalyptic","scenario_id":"suburban-collapse","mode":"advanced","difficulty":"hard"}'
```

## 3. The five-minute demo sequence (turn by turn)

Type each action **verbatim** (full NPC names included). Every turn takes ~20–45 s of narration generation (observed 20–42 s live); five actions ≈ 3 min of generation, leaving ~2 min for talking over the evidence.

| Turn | Player action (type exactly) | Engine-owned result (deterministic) |
|---|---|---|
| T1 | — (opening auto-generates) | Scenario NPCs seeded into agendas; pressure nodes created; an opening echo is scheduled by the engine (observed: fired on T3 — a free bonus delayed consequence). |
| T2 | `I share my bottled water with Marlene Cho and help her carry supplies inside.` | Relationship calculus classifies **gift + help** from the *declared action only* → Marlene Cho **trust +20, loyalty +18** (exact Ch 29.8 deltas; observed live). Guard receipt `rel:Marlene Cho:help+gift`. An **autonomous NPC world move** commits (observed: `gather` against a resource pressure node, receipt `npc_move_committed`, turn 2). |
| T3 | `I threaten Greg Stahl with the claw bar and tell him to stay off my property.` | **threaten** → Greg fear +25, resentment +15, trust −10. Guard receipt `rel:Greg Stahl:threaten`. (Observed bonus: the opening echo fired this turn; a second NPC move committed.) |
| T4 | `I betray Greg Stahl to the scavengers at the fence, telling them exactly where his supplies are hidden.` | **betrayal** (resentment +70, trust −60) → Greg's vector crosses the engine threshold: **state = `collapsed`** (observed live: trust −70, fear 45, resentment 85). The engine **asserts his stance → `hostile`** and schedules a **`relationship_fracture` echo** (`evt-rel-greg stahl-turn-4`, `mature_turn: 6`). Receipt `echo_scheduled` turn 4. |
| T5 | `I wait by the front window and watch the street.` | Neutral by design (zero relationship events — pinned by test). The world keeps moving: pressures tick, NPC moves continue (observed: the T3 faction-suspicion echo fired here). Point at the **PRS pressure bar** — engine pressure surfaced live. |
| T6 | `I look out at the street once more and listen.` | The **betrayal consequence fires**: receipt `echo_fired` for `evt-rel-greg stahl-turn-4` at turn 6. Narration must surface the fracture (observed live: Greg pacing his driveway on the phone, organising against you) — the LLM is *instructed by the engine directive*, not the other way round. |

**The arc in one sentence for judges:** kindness on T2 is remembered, a betrayal on T4 detonates on T6 — and every step of that memory is engine math with receipts, not LLM improvisation.

## 4. Expected engine-owned events (checklist)

All were observed in the verified live run:

- [ ] `transition_receipts`: `npc_move_committed` (≥1, usually turns 2–4) — autonomous NPC action.
- [ ] `transition_receipts`: `echo_scheduled` (turn 4, `evt-rel-greg stahl-turn-4`).
- [ ] `transition_receipts`: `echo_fired` (turn 6, same `source_event_id`) — scheduled→fired pair with matching IDs is the money shot.
- [ ] `rolling_state.relationship_vectors`: Marlene Cho trust/loyalty ≈ +20/+18; Greg Stahl trust ≤ −60, resentment ≥ 70, `state: collapsed` (or `betrayal_risk`).
- [ ] Greg Stahl's `stance` flipped to `hostile` by the engine (not by prose).
- [ ] Turn `debug.state_guard_adjustments` contains `rel:Marlene Cho:help+gift`, `rel:Greg Stahl:threaten`, `rel:Greg Stahl:betrayal`, and `rolling_active_pressures_engine_derived` (the engine overwriting LLM-authored pressure — ADR-023 live).
- [ ] `pressure_graph.nodes` with numeric magnitudes/trends ticking each turn.
- [ ] `consequence_echoes.fired` log entries with `fired_turn` values.

## 5. What to show judges in history/debug

Player-visible payloads are deliberately sanitised (allowlist API) — the structured evidence is admin-side. Two commands, both using the `ADMIN_API_KEY` from `backend/.env`:

```bash
# Full structured history: every turn + rolling_state + replayability_state
curl -s "$BASE/api/story/session/<session_id>/export/raw" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" | python3 -m json.tool | less

# Quick latest-turn diagnostics
curl -s "$BASE/api/admin/session/<session_id>/diagnostics" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" | python3 -m json.tool
```

Walk judges through, in this order (~60 s):

1. **`replayability_state.transition_receipts`** — read the `echo_scheduled` (turn 4) → `echo_fired` (turn 6) pair aloud; same `source_event_id`. "The consequence you just watched was booked two turns earlier, by the engine."
2. **`rolling_state.relationship_vectors`** — Greg's numbers: trust −70, resentment 85, `state: collapsed`. Diff against the same vector in the turn-3 document (each turn persists its own `rolling_state`) to show the exact betrayal delta.
3. **Turn 4 `debug.state_guard_adjustments`** — `rel:Greg Stahl:betrayal`: the engine classified the *typed action*, applied fixed deltas, and *narrative is never consulted* (`relationships.update_relationship_calculus` docstring: prose can never mutate a vector).
4. **`replayability_state.frozen_npc_move` + `npc_move_committed` receipts** — NPCs act from engine agendas and tiers, with stable receipt IDs.
5. **`rolling_active_pressures_engine_derived`** in guard adjustments — the model tried to author pressure; the engine overwrote it.
6. In-app, point at the **PRS pressure bar** and the state chips — the same engine state surfaced to players.

## 6. Fallback actions when narration varies

The narration is a live LLM (temperature 0.85) — prose WILL vary. The engine state will not, if you follow these rules:

- **Always use full NPC names** exactly as the app shows them (`Marlene Cho`, `Greg Stahl`). Event detection requires the verb and the NPC's recorded name within ~70 characters.
- **Never phrase intent hypothetically.** "I think about threatening Greg Stahl…" produces **zero** events (hypothetical guard — pinned by test). Declare the deed: "I threaten Greg Stahl…".
- **Narration ignores your kindness/threat?** Doesn't matter — the vectors already moved (show the receipts). Repeat the beat with a stronger verb only if you want bigger numbers: `I save Marlene Cho and pull her to safety` (save_life: trust +30) / `I attack Greg Stahl and hit him` (attack: fear +30).
- **Echo hasn't fired by T6?** `fire_echo` fires at most one echo per turn, and other engine echoes (opening fact, faction suspicion) share the queue — observed live they fired on T3/T5, leaving T6 free. If the queue is busier in your run, play **one extra neutral turn**: `I stay quiet and keep watch.` The fracture echo cannot be lost — show its `scheduled` entry with `mature_turn` while you wait.
- **Choices instead of typing:** ignore the suggested choice chips during beats T2–T4; type the scripted lines. Chips are fine for neutral turns.
- **A guard fires unexpectedly** (e.g. the model invents a death and gets stripped): that is a *feature* — read `state_guard_adjustments` aloud and enjoy the free demo of the anti-hallucination gateway.
- **Session goes sideways entirely:** create a fresh story (≤ ~1 min) — creation is rate-limited to **5 per device per hour**, so budget rehearsals (or rotate `X-Device-Id` when rehearsing via API).

## 7. 60-second pitch

> "Every AI story app has the same disease: the model narrates whatever it wants, and 'the world' is just vibes. Dice Reactions cures it. Underneath the prose is a deterministic simulation engine that owns reality — relationships are numbers moved only by what the player actually *does*, NPCs act on their own agendas on a fixed cadence, world pressure is a ticking graph, and consequences are *booked in advance* and detonate turns later, with receipts. Watch: I'll be kind to one neighbour, betray another, and the engine will schedule his revenge two turns before you see it — then I'll show you the receipt trail proving the model was never in charge. The LLM writes the sentences. The engine writes the history."

## 8. Five-minute stage sequence

| Time | Beat |
|---|---|
| 0:00–0:40 | Pitch (§7) while tapping NEW STORY → Advanced → Suburban Collapse → Start. Opening generates as you talk. |
| 0:40–1:20 | T2 kindness (type, submit, read one line of the reply). Say: "Trust +20, loyalty +18 — fixed math from my *typed action*, not the prose." |
| 1:20–2:00 | T3 threat. Say: "Fear and resentment just moved on Greg. And an NPC has already made its own move — receipt on file." |
| 2:00–2:45 | T4 betrayal. Say: "Greg's relationship state just collapsed. The engine flipped his stance to hostile and *scheduled his reaction for turn 6*. It's on the books right now — before any narration exists." |
| 2:45–3:20 | T5 neutral wait. Point at the PRS bar; mention the world moved without you (faction echo, NPC moves). |
| 3:20–4:00 | T6 — the fracture fires. Read the narration beat where Greg turns on you. |
| 4:00–5:00 | Evidence walk (§5): receipts pair, Greg's vector, `rel:Greg Stahl:betrayal` guard line, engine-derived pressure. Close: "The LLM writes the sentences. The engine writes the history." |

## 9. Rehearsal + risk notes

- **Provider latency:** 20–45 s per turn observed. Pre-create a **backup session already advanced to T4** before going on stage; if latency spikes live, switch to it and play T5–T6 only.
- **Creation rate limit:** 5/device/hour, 10/IP/hour — rotate rehearsal device IDs.
- **Pre-existing (not from this work):** `tests/test_provider_selection.py` expects model ID `anthropic/claude-haiku-4.5` while `.env` pins `anthropic/claude-3-5-haiku`; the pinned ID worked live end-to-end today, but re-verify the OpenRouter model ID is still serving the day before the contest.
- **Do not toggle** feature flags, provider settings, or the admin developer mode for the demo — everything above works with defaults (verified).
