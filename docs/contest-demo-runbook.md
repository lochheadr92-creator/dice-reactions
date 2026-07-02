# Statebound — Builders Contest Demo Runbook

> **The engine owns reality. AI narrates it.**

**Scenario:** `suburban-collapse` (Suburban Collapse)
**Branch:** `emergent` · **Demo length:** 5 minutes · **Turns:** opening + 5 actions (T1–T6)
**Verified live:** 2026-07-04 — full six-turn spine executed against the running backend; every engine event below was observed in that session, and the player-facing **"Why this happened"** view rendered the complete causal chain from the same session with zero manual work.
**Pinned by tests:** `backend/tests/test_contest_demo_runbook.py` (scripted actions ↔ engine classification) and `backend/tests/test_causal_history.py` (causal view beats + no internal-field leakage). Both deterministic, provider-free.

---

## 1. Why this scenario

- Grounded, instantly legible premise (suburban grid collapse) — judges need zero genre onboarding.
- Two named NPCs with opposite arcs: **Marlene Cho** (ally you warm up) and **Greg Stahl** (neutral you destroy). Full names matter — see §6.
- Seeded pressure (the Hendersons' silent generator) and a hidden threat give the pressure graph real nodes from turn 1.
- `hard` difficulty, not `brutal` — the player will not die mid-demo (the dinosaur scenario can kill you; the horror scenario burns turns on atmosphere).

## 2. Exact creation selections

1. Home screen → **[ ENTER · WORLD ]** (`new-story-btn`).
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

## 5. What to show judges: the "Why this happened" view (in-app, player-safe)

Open the play-screen menu (⋯) → **"Why this happened"** (`why-history-btn`). The modal renders the engine-recorded causal chain in plain sentences — no JSON, no identifiers, no engine terminology. Verified output from the live six-turn session:

```
TURN · 01   WORLD   The world opened: Suburban Collapse.
            SET     A consequence was quietly set in motion. It will return.
TURN · 02   YOU     I share my bottled water with Marlene Cho and help her carry supplies inside.
            CHANGE  Marlene Cho: Your help was recorded — trust and loyalty grew.
            CHANGE  Marlene Cho: Your generosity was recorded — trust grew.
            CAST    Marlene Cho acted on their own — no prompt, no player input: they moved to secure scarce supplies.
TURN · 03   YOU     I threaten Greg Stahl with the claw bar and tell him to stay off my property.
            CHANGE  Greg Stahl: The threat left a mark — fear and resentment rose.
            RETURN  Set in motion on turn 1, it arrives now. Pressure that had been building finally broke: …
TURN · 04   YOU     I betray Greg Stahl to the scavengers at the fence…
            CHANGE  Greg Stahl: The betrayal was recorded — trust collapsed, resentment surged.
            CHANGE  Greg Stahl will no longer stand with you.
            SET     A consequence was quietly set in motion. It will return.
TURN · 06   RETURN  Set in motion on turn 4, it arrives now. A bond you broke earlier came due: Greg Stahl.
```

Walk judges through, in this order (~60 s):

1. **Turn 4, SET → Turn 6, RETURN** — "The consequence you just watched was booked two turns earlier. By the engine. Before any narration existed."
2. **Turn 2 vs Turn 4 CHANGE lines** — kindness remembered, betrayal recorded; the same character's standing evolves from engine math, never prose.
3. **The CAST lines** — named characters acting with no prompt and no player input, every single turn.
4. The intro line of the modal says it plainly: *"Every line below is recorded world state — written by the engine, not by the narrator."*

### Deep proof (only if a judge asks "how do I know this isn't generated?")

The raw structured evidence behind every sentence above (admin key from `backend/.env`):

```bash
curl -s "$BASE/api/story/session/<session_id>/export/raw" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" | python3 -m json.tool | less
```

Show the `transition_receipts` scheduled→fired pair with matching source IDs, Greg's numeric relationship vector (trust −70, resentment 85, state `collapsed`), and the per-turn `state_guard_adjustments` (`rel:Greg Stahl:betrayal`, `rolling_active_pressures_engine_derived` — the engine overwriting model-authored state).

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

> "Statebound is a continuity engine for AI-assisted fiction — for interactive-fiction writers, game masters, and narrative designers. Every AI story tool has the same disease: characters forget, facts drift, consequences evaporate, and creators babysit continuity with notes and spreadsheets. Statebound separates world truth from generated prose. A deterministic engine owns the characters, relationships, resources, and consequences — the AI only narrates the resulting state. Watch: I'll be kind to one neighbour, betray another, and the engine will schedule his revenge two turns before you see it. Then I'll open 'Why this happened' and show you the causal chain — kindness remembered, betrayal recorded, consequence booked and delivered — every line from engine state, none from the model. **The engine owns reality. AI narrates it.**"

## 8. Five-minute stage sequence

| Time | Beat |
|---|---|
| 0:00–0:40 | Pitch (§7) while tapping **[ ENTER · WORLD ]** → Advanced → Suburban Collapse → Start. Opening generates as you talk. |
| 0:40–1:20 | T2 kindness (type, submit, read one line of the reply). Say: "Her trust just grew — fixed engine math from my *typed action*, not the prose." |
| 1:20–2:00 | T3 threat. Say: "Fear and resentment just moved on Greg. And a neighbour has already made her own move — no prompt, no player input." |
| 2:00–2:45 | T4 betrayal. Say: "Greg's bond just collapsed, and the engine *scheduled his reaction*. It's on the books right now — before any narration exists." |
| 2:45–3:20 | T5 neutral wait. Point at the PRS bar; mention the world moved without you. |
| 3:20–4:00 | T6 — the consequence fires. Read the narration beat where Greg turns on you. |
| 4:00–5:00 | Open menu (⋯) → **Why this happened**. Scroll turn by turn (§5): SET on turn 4 → RETURN on turn 6, the CHANGE trail, the CAST lines. Close: "**The engine owns reality. AI narrates it.**" |

## 9. Rehearsal + risk notes

- **Provider latency:** 20–45 s per turn observed. Pre-create a **backup session already advanced to T4** before going on stage; if latency spikes live, switch to it and play T5–T6 only.
- **Creation rate limit:** 5/device/hour, 10/IP/hour — rotate rehearsal device IDs.
- **Pre-existing (not from this work):** `tests/test_provider_selection.py` expects model ID `anthropic/claude-haiku-4.5` while `.env` pins `anthropic/claude-3-5-haiku`; the pinned ID worked live end-to-end today, but re-verify the OpenRouter model ID is still serving the day before the contest.
- **Do not toggle** feature flags, provider settings, or the admin developer mode for the demo — everything above works with defaults (verified).

## 10. Recovery steps if a beat does not fire

| Missing beat | Recovery |
|---|---|
| No CHANGE line after T2/T3/T4 | The action string drifted from the script — the NPC's full name and a concrete (non-hypothetical) verb are required. Re-issue the beat verbatim from §3; the engine classifies the new action immediately. The demo loses ~30 s, nothing else. |
| No CAST line by T3 | NPC moves depend on eligible agendas and targets in that run. Play one extra neutral turn (`I stay quiet and keep watch.`) — cadence allows a move every turn for active-tier NPCs, and three key NPCs are seeded, so a move lands within a turn or two. Meanwhile point at the CHANGE trail, which is already deterministic. |
| No RETURN by T6 | At most one consequence arrives per turn and earlier engine consequences share the queue. The betrayal consequence **cannot be lost** — its SET line on turn 4 is already visible in "Why this happened". Play one extra neutral turn and it arrives. Narrate the wait: "It's on the books — watch." |
| Greg does not read hostile in T6 prose | The prose is the model's problem, not the engine's: open "Why this happened" and read "Greg Stahl will no longer stand with you" (turn 4) + the turn-6 RETURN line. State wins the argument. |
| Session breaks / wrong scenario / mistap | Delete nothing on stage. Switch to the pre-created backup session (menu → home → its save slot) and continue from its current turn. |
| "Why this happened" fails to open | Reopen the menu and tap again (it re-fetches). If the network hiccups, the deep-proof export (§5 appendix) shows the same chain from a terminal. |

## 11. Known limitations (say them before a judge finds them)

- **Prose variance:** narration is a live model at temperature 0.85 — the *sentences* differ run to run; only the recorded state is deterministic. That is the product's whole point, and the demo says so out loud.
- **Turn latency:** 20–45 s per turn against the live provider; the 5-minute script budgets for it, but a slow provider day compresses the evidence walk.
- **One consequence per turn:** the arrival queue is deliberately paced, so a crowded run can push the betrayal's return one turn past T6 (recovery above).
- **Name-anchored action resolution:** relationship attribution needs the character's full recorded name in the typed action — pronouns ("I threaten him") resolve to nothing. Honest limitation; scripted lines avoid it.
- **The causal view is a projection, not a replay:** it renders what the engine recorded; it does not re-simulate. Deleted sessions lose their chain.
- **Autonomous-move phrasing is generic** ("moved to secure scarce supplies") — move *targets* are engine node references and are deliberately not exposed to players yet.
