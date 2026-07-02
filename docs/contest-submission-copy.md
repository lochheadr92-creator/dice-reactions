# Statebound — Emergent Builders Contest Submission Copy

> **The engine owns reality. AI narrates it.**

---

## Product name

**Statebound**

## Tagline

*A world that remembers.*

## Problem being solved

AI-assisted stories lose continuity. Characters forget past events, established facts silently change, consequences disappear, and dead NPCs walk back into scenes. Creators end up doing the machine's job: maintaining notes, spreadsheets, summaries, and ever-growing "remember that…" prompts just to keep their own world consistent. The longer the story, the worse it gets — because the model is being asked to be both the narrator *and* the database, and it is only good at one of those.

## Target users

- Interactive-fiction writers who want long, coherent AI-assisted narratives
- Tabletop game masters running persistent campaigns and living NPCs
- Narrative designers prototyping reactive story systems
- Indie creators building story-driven experiences without an engine team

## What users did before

Manual continuity bookkeeping: session notes, character spreadsheets, timeline documents, lorekeeper wikis, summary-paste rituals at the top of every prompt, and re-reading old chats to check whether the innkeeper is still alive. When that failed — and it always eventually fails — they retconned, or quietly accepted a world where nothing they did last week matters.

## How Statebound works

Statebound separates **world truth** from **generated prose**:

- A deterministic engine owns the state: characters, memories, relationships, resources, locations, factions, pressure, and consequences.
- The player's *declared action* — not the AI's prose — is resolved into structured events. Kindness is recorded. A betrayal is recorded. The numbers move; the prose cannot move them.
- Characters act autonomously every turn from their own goals and standing — no prompt, no player input.
- Consequences are **booked in advance**: a broken bond on turn 4 is scheduled by the engine and returns on turn 6, with a receipt trail connecting cause to effect.
- Guards strip anything the model invents that contradicts recorded truth — the dead stay dead, destroyed things stay destroyed, secret state stays secret.
- The AI narrates the *resulting* state, and a player-facing **"Why this happened"** view shows the causal chain in plain sentences: what you did, what permanently changed, who acted on their own, and which earlier event caused which later consequence.

## Expected impact

Creators stop being their own continuity department. Stories can run long — dozens or hundreds of turns — without drift, because truth never lived in the prose to begin with. Consequence becomes a designed mechanic instead of a lucky accident, which changes what AI-assisted fiction can be: not a slot machine of paragraphs, but a world that holds.

## Proof-of-concept evidence

A live, repeatable five-minute showcase (see `docs/contest-demo-runbook.md`), executed end-to-end against the running app:

- Turn 2: sharing water with a neighbour was **recorded** — her trust and loyalty grew (fixed engine deltas from the typed action, verified against the persisted state).
- Turns 2–6: named characters **acted autonomously every turn**, with commit receipts.
- Turn 4: a betrayal **collapsed a relationship** — and the engine *scheduled the reprisal two turns before any narration of it existed*.
- Turn 6: the consequence **arrived on schedule**, traced to its origin turn in the in-app "Why this happened" view.
- The entire chain is backed by 100+ deterministic, provider-free tests, including tests that prove the player-facing history never leaks internal engine fields, and that the model's prose can never mutate relationship state.

## Scalability statement

The truth layer is small, structured, and bounded (capped registries, compressed rolling state, deterministic replay barriers), so cost grows with *state*, not with *story length* — the engine does not need the whole transcript to stay consistent. The same separation generalises beyond fiction: any LLM product where facts must survive generations — games, simulations, training scenarios, companion apps — can sit on the same pattern. One session or ten thousand, each world's truth is an independent, replayable document.

## Short submission description (~50 words)

Statebound is a continuity engine for AI-assisted fiction. A deterministic engine owns characters, relationships, resources, and consequences; the AI only narrates the resulting state. Actions leave permanent marks, characters act on their own, and consequences return on schedule — with a player-visible causal history proving it. The engine owns reality. AI narrates it.

## Medium submission description (~150 words)

AI stories forget. Characters lose their grudges, facts drift, and consequences evaporate — so writers, game masters, and narrative designers babysit continuity with notes, spreadsheets, and ever-longer prompts.

Statebound fixes the architecture instead of the prompt. It separates world truth from generated prose: a deterministic simulation engine owns characters, memories, relationships, resources, locations, and consequences, while the AI narrates only the state that results. Your declared actions — not the model's sentences — move the world. Kindness is recorded and remembered. A betrayal collapses a bond, and the engine schedules the reprisal turns before any narration of it exists. Characters pursue their own goals every turn, unprompted. Anti-hallucination guards strip anything the model invents against recorded truth.

Then Statebound shows its work: a plain-language "Why this happened" view traces every consequence back to the action that caused it — from engine state, never from prose.

The engine owns reality. AI narrates it.

## Social post for requesting upvotes

> I built **Statebound** for the Emergent Builders Contest — an AI story engine where the world actually *remembers*.
>
> The problem: AI stories forget. Characters drop grudges, facts drift, consequences vanish.
>
> The fix: a deterministic engine owns reality — characters, relationships, consequences — and the AI only narrates it. In my 5-minute demo I betray a neighbour on turn 4; the engine books his revenge before the narrator even knows, and it lands on turn 6 with a receipt trail. There's even a "Why this happened" view showing the whole causal chain.
>
> The engine owns reality. AI narrates it. 🎲
>
> If that sounds like the future of AI fiction, I'd love your vote: [link]
