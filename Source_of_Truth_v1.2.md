# Dice Reaction Story Engine

## Source of Truth – Living World Simulation Bible

**Version:** 1.2  
**Status:** Canonical  
**Last Updated:** 2026-06-12  

---

## About

### What Is This Document?

This is the **Source of Truth** for the Dice Reaction Story Engine – a persistent, AI‑driven living world simulation. It is not a game design document. It is not a technical implementation manual (though it contains many implementation chapters). It is the **constitution** of the simulation.

Every system, mechanic, rule, and behaviour must conform to this document. If any future feature conflicts with a chapter here, the feature is considered incorrect until reconciled.

### Core Philosophy

Dice Reaction does not generate stories. It simulates worlds. Stories are a by‑product.

> "A living world continues changing even when the player is not looking."

The player enters an existing reality. That reality evolves independently. Pressure creates action. Action creates consequence. Consequence creates history. History creates new pressure. The cycle never ends.

### Status

All chapters are **Canonical**. This means they are the authoritative statement of the engine’s design philosophy and required mechanics. Future amendments must be clearly marked and versioned.

### Changelog

**v1.2 (2026-06-12)** – Correction and completion release.

- Defined the canonical numeric gravity scale and gravity decay formula (20.13, 20.17). All downstream thresholds now resolve to a single scale.
- Corrected the Retention Score formula (26.3): player relevance is now a bonus, not a multiplicative gate. Resolves total-retention collapse during burn-in worlds with no player. Duration factor formula corrected to match its stated intent.
- Normalised the Utility AI formula to a weighted average bounded 0–100 (27.1, 27.4). Tie-breaking noise now sits inside the tie window and draws from the seeded RNG (27.5), preserving determinism (30.10).
- Unified relationship decay into a single authority (29.10, exponential form). Removed conflicting per-dimension decay rates from 29.3 and 29.5.
- Resolved relationship state authority: the stored four-dimension vector is canonical; memory retrieval applies situational modifiers only (13.1, 29.12).
- Unified forgetting under the Gravity Governance Layer: 12.19 and 28.8 now defer to Chapter 26 as mechanism, not independent authority.
- Declared the canonical clock for all durations (25.6): all rates and grace periods use simulation time unless explicitly marked real time.
- Defined the Standard Value Unit for resource scoring (27.4.1).
- Corrected stale and mislabelled cross-references (27.7); removed formatting artefact after Chapter 24.
- **NEW Chapter 33: NPC Lifecycle & Generational Succession** – aging, death, birth, inheritance, and leadership succession. Required for burn-in (Chapter 30) to function over multi-generational timescales.
- **NEW Appendix A: Constants Registry** – every numeric constant, threshold, and formula in one authoritative table.

**v1.1 (2026-06-09)** – Merged expanded implementation chapters (25–32); resolved retention authority, relationship state modeling, and utility normalization contradictions identified in review.

**v1.0** – Initial canonical release, Chapters 1–24.


---

## Table of Contents

1. [Living World Doctrine](#chapter-1-living-world-doctrine)
2. [Simulation First Philosophy](#chapter-2-simulation-first-philosophy)
3. [State Is Truth](#chapter-3-state-is-truth)
4. [The Simulation Loop](#chapter-4-the-simulation-loop)
5. [World Heartbeat Architecture](#chapter-5-world-heartbeat-architecture)
6. [Pressure Ecology](#chapter-6-pressure-ecology)
7. [Settlement Organism Theory](#chapter-7-settlement-organism-theory)
8. [Resource Flow Theory](#chapter-8-resource-flow-theory)
9. [Information Theory](#chapter-9-information-theory)
10. [NPC Architecture](#chapter-10-npc-architecture)
11. [Goal Systems](#chapter-11-goal-systems)
12. [Memory Systems](#chapter-12-memory-systems)
13. [Relationship Systems](#chapter-13-relationship-systems)
14. [Stress & Breaking Point Systems](#chapter-14-stress--breaking-point-systems)
15. [Social Structures](#chapter-15-social-structures)
16. [Reputation Systems](#chapter-16-reputation-systems)
17. [Faction Architecture](#chapter-17-faction-architecture)
18. [Consequence Ledger](#chapter-18-consequence-ledger)
19. [Delayed Consequences](#chapter-19-delayed-consequences)
20. [Context Gravity](#chapter-20-context-gravity)
21. [Scar Theory](#chapter-21-scar-theory)
22. [Event Sourcing](#chapter-22-event-sourcing)
23. [Historical Layering](#chapter-23-historical-layering)
24. [Discovery Architecture](#chapter-24-discovery-architecture)
25. [Actor Resolution Scaling](#chapter-25-actor-resolution-scaling)
26. [Gravity Governance Layer](#chapter-26-gravity-governance-layer)
27. [NPC Decision Engine (Utility AI)](#chapter-27-npc-decision-engine-utility-ai)
28. [Memory Retrieval System](#chapter-28-memory-retrieval-system)
29. [Relationship Calculus](#chapter-29-relationship-calculus)
30. [World Genesis & Burn‑In](#chapter-30-world-genesis--burn-in)
31. [LLM Architecture & Integration](#chapter-31-llm-architecture--integration)
32. [Simulation Testing Framework](#chapter-32-simulation-testing-framework)
33. [NPC Lifecycle & Generational Succession](#chapter-33-npc-lifecycle--generational-succession)

Appendix A. [Constants Registry](#appendix-a-constants-registry)

# CHAPTER 1

# LIVING WORLD DOCTRINE

## Status

Canonical

This chapter establishes the highest-level truth of the Dice Reaction Story Engine.

All future systems, mechanics, simulation rules, rendering logic, AI orchestration layers, memory systems, faction systems, economy systems, and player-facing experiences must conform to this doctrine.

If any future system conflicts with this chapter, the future system is considered incorrect until reconciled.

---

# 1.1 Purpose

Dice Reaction is not designed to generate stories.

Dice Reaction is designed to simulate worlds.

Stories are a by-product of simulation.

This distinction is the foundation upon which the entire project rests.

Most narrative systems begin with a story and then construct a world around it.

Dice Reaction reverses this relationship.

The world comes first.

The story emerges afterward.

The objective is not to entertain the player with prewritten events.

The objective is to create a reality capable of producing events naturally.

The player is not consuming a story.

The player is entering an existing reality.

---

# 1.2 Core Statement

The central doctrine of the entire project is:

"A living world continues changing even when the player is not looking."

This sentence serves as the primary test for every future feature.

When evaluating any mechanic, the following question should be asked:

If the player disappeared completely, would this system continue functioning?

If the answer is no, the system is not truly part of the simulation.

It is merely part of the presentation layer.

---

# 1.3 The Failure Of Traditional Systems

Most games create the illusion of life.

Few actually simulate it.

Common failures include:

### Frozen Settlements

Villages remain unchanged until visited.

Merchants stand in the same location indefinitely.

Resources never move.

Construction never progresses.

Nothing changes.

---

### Waiting Wars

Kingdoms remain locked in conflict forever.

Armies never advance.

Battles never occur.

The world patiently waits for the hero.

---

### Static NPCs

Characters exist only when observed.

When the player leaves:

The NPC effectively ceases to exist.

No decisions occur.

No goals advance.

No life continues.

---

### Infinite Reversibility

Mistakes carry no lasting consequences.

Opportunities never disappear.

Failures rarely matter.

The world continually forgives.

---

### Narrative Dependency

Events exist solely because the player triggered them.

The world has no independent motion.

Everything revolves around the protagonist.

---

These systems produce entertaining games.

They do not produce living worlds.

Dice Reaction seeks a different outcome.

---

# 1.4 Definition Of A Living World

A world is considered alive only when all of the following conditions are true.

### Condition 1: Independent Motion

Entities pursue goals.

Groups pursue goals.

Settlements pursue goals.

Events advance.

The player is not required.

---

### Condition 2: Persistent Memory

The world remembers.

History accumulates.

Past actions leave evidence.

Consequences remain discoverable.

---

### Condition 3: Resource Movement

Resources circulate.

Food moves.

Money moves.

Information moves.

Labour moves.

Power moves.

Influence moves.

Static resources create dead worlds.

---

### Condition 4: Pressure Generation

Conflict emerges naturally.

Scarcity emerges naturally.

Competition emerges naturally.

Threats emerge naturally.

Instability emerges naturally.

Without pressure there is no movement.

Without movement there is no life.

---

# 1.5 The Player's True Role

The player is not the centre of reality.

The player is one actor within reality.

This does not diminish the player.

It enhances them.

A player becomes meaningful when the world does not revolve around them.

The player's actions matter because the world is real enough to react.

Not because the world was designed to flatter them.

The player may:

* Save a kingdom.
* Destroy a kingdom.
* Ignore a kingdom.

All three outcomes must remain valid.

The simulation must not secretly prefer one.

---

# 1.6 The Observer Principle

Observation is not existence.

The player seeing something does not cause it to exist.

The player failing to see something does not cause it to stop existing.

This rule applies to:

* NPCs
* Settlements
* Resources
* Relationships
* Factions
* Threats
* Events

The world exists independently of observation.

Observation merely reveals state.

---

# 1.7 World First, Narrative Second

The simulation always takes priority over storytelling.

This is one of the most important principles in the project.

A compelling story should emerge from reality.

Reality should never be altered simply to create a compelling story.

Bad approach:

"The story would be better if the villain escaped."

Good approach:

"The villain escaped because conditions allowed escape."

The distinction is critical.

Narrative must emerge from causality.

Causality must never emerge from narrative convenience.

---

# 1.8 Causality As The Prime Law

Everything important must have a cause.

Every meaningful event should be traceable.

A developer should always be able to answer:

Why did this happen?

If no answer exists:

The simulation failed.

Examples:

A town starved.

Why?

Trade routes collapsed.

Why?

Bandit attacks increased.

Why?

Regional instability increased.

Why?

A faction leader was assassinated.

This chain of causality creates realism.

The player may never see the entire chain.

The simulation must still know it exists.

---

# 1.9 The Consequence Chain

The fundamental engine of world evolution is:

Pressure
↓
Action
↓
Reaction
↓
Consequence
↓
History
↓
New Pressure

This loop never ends.

This loop drives the entire world.

Every major event originates somewhere within this cycle.

---

# 1.10 Pressure As The Source Of Story

Stories are not generated.

Stories are discovered.

Pressure generates stories.

Examples of pressure:

* Hunger
* Fear
* Greed
* Ambition
* Disease
* Revenge
* Curiosity
* Faith
* Love
* Survival

Pressure causes behaviour.

Behaviour causes consequences.

Consequences create narrative.

The engine's responsibility is not to create stories.

The engine's responsibility is to create believable pressure.

---

# 1.11 The Scar Principle

A world without scars cannot feel alive.

Every significant event should leave traces.

Examples:

Physical scars:

* Ruined buildings
* Battlefields
* Graves
* Burned forests

Social scars:

* Distrust
* Reputation
* Hatred
* Alliances

Psychological scars:

* Trauma
* Fear
* Obsession
* Grief

Political scars:

* Laws
* Borders
* Rebellions
* Faction fractures

Scars are history made visible.

---

# 1.12 The Persistence Mandate

Nothing important should vanish without reason.

Important actions persist.

Important events persist.

Important relationships persist.

Important consequences persist.

The world should not forget simply because remembering is inconvenient.

Memory is expensive.

Forgetting reality is more expensive.

---

# 1.13 The Dead World Test

Every major system must pass the Dead World Test.

Procedure:

Remove the player.

Run the simulation.

Observe.

Questions:

Do settlements change?

Do factions evolve?

Do relationships shift?

Do resources move?

Do events progress?

Do consequences accumulate?

Does history continue forming?

If the answer to most of these questions is no:

The world is dead.

The system has failed.

---

# 1.14 The Living World Test

A living world demonstrates:

Motion.

Persistence.

Causality.

Adaptation.

Memory.

Pressure.

Scar formation.

History accumulation.

Independent evolution.

The player should feel as though they entered a reality already in motion.

Not a stage waiting for performance.

---

# 1.15 Final Doctrine

Dice Reaction is not a storytelling engine.

Dice Reaction is not an RPG engine.

Dice Reaction is not a branching narrative system.

Dice Reaction is a living world simulation.

The player enters an existing reality.

The reality evolves.

Pressure creates action.

Action creates reaction.

Reaction creates consequence.

Consequence creates history.

History creates new pressure.

The cycle continues whether the player watches or not.

That cycle is the heart of the entire project.

Everything else exists to serve it.

END OF CHAPTER 1
CANONICAL VERSION

# CHAPTER 2

# SIMULATION FIRST PHILOSOPHY

## Status

Canonical

This chapter defines the philosophical hierarchy of the Dice Reaction Story Engine.

It establishes the order of authority between simulation, narrative, content generation, player expectation, drama, realism, and game design.

This chapter exists to prevent long-term project drift.

Most projects do not fail because of technical limitations.

Most projects fail because they gradually become something different from what they originally intended to be.

The purpose of this chapter is to ensure Dice Reaction remains a living-world simulation regardless of future features, models, technologies, contributors, or commercial pressures.

---

# 2.1 The Hierarchy Of Authority

Every system within Dice Reaction operates under a strict hierarchy.

Higher layers always override lower layers.

The hierarchy is:

```text
Reality
↓
Simulation
↓
Causality
↓
Consequences
↓
Narrative
↓
Presentation
```

This hierarchy must never be reversed.

---

## Reality

Reality represents the current world state.

Reality is the source of truth.

Reality includes:

* NPC conditions
* Resource locations
* Active events
* Faction status
* Settlement status
* Relationships
* History

Reality exists independently of the player.

---

## Simulation

Simulation determines how reality changes.

Simulation governs:

* Time progression
* Resource movement
* Goal pursuit
* Pressure generation
* Event advancement

Simulation operates regardless of observation.

---

## Causality

Causality explains why changes occur.

Every meaningful change should have a cause.

No major outcome should exist without explanation.

---

## Consequences

Consequences are the results of causal chains.

Consequences may be:

* Immediate
* Delayed
* Hidden
* Cascading

Consequences create history.

---

## Narrative

Narrative is a description of events.

Narrative is not reality.

Narrative is not simulation.

Narrative is a lens through which reality is observed.

---

## Presentation

Presentation is the final layer.

Examples:

* Prose
* Dialogue
* Visuals
* Audio
* User Interface

Presentation exists solely to communicate reality.

Presentation must never control reality.

---

# 2.2 The Primary Rule

Simulation always takes priority over story.

Always.

No exceptions.

---

# 2.3 Why Traditional Storytelling Fails

Traditional storytelling assumes:

The story is the product.

The world exists to support the story.

The characters exist to support the story.

Events occur because the story requires them.

This works for:

* Books
* Films
* Television

It does not work for living simulations.

---

Example:

A writer may decide:

"The king must survive because he is important later."

A simulation asks:

"Can the king survive?"

These are fundamentally different questions.

Dice Reaction always chooses the second question.

---

# 2.4 The Anti-Script Doctrine

The engine must never secretly protect outcomes.

Protected outcomes create dead worlds.

Examples:

The villain cannot die.

The kingdom cannot collapse.

The merchant always survives.

The quest must always be available.

The rebellion must always occur.

These systems create inevitability.

Inevitability destroys agency.

---

The simulation should instead ask:

What would happen?

Then allow that outcome.

Even if it creates unexpected results.

Especially if it creates unexpected results.

---

# 2.5 Emergence Over Design

Traditional games design experiences.

Dice Reaction designs conditions.

The difference is critical.

Bad approach:

Create a questline.

Create encounters.

Create outcomes.

Guide player through content.

---

Simulation approach:

Create pressures.

Create actors.

Create resources.

Create incentives.

Allow outcomes to emerge.

---

The first creates content.

The second creates worlds.

---

# 2.6 The Narrative Trap

One of the greatest risks facing the project is what shall be known as:

The Narrative Trap.

The Narrative Trap occurs when developers begin modifying reality to improve storytelling.

Examples:

A dramatic betrayal is inserted because it feels exciting.

An NPC survives because the plot needs them.

A faction acts irrationally because it creates tension.

A disaster occurs because it feels cinematic.

---

All of these violate simulation-first design.

The simulation must never ask:

"What would make a better story?"

The simulation must ask:

"What would happen next?"

The resulting story may be dramatic.

It may be boring.

It may be tragic.

It may be hilarious.

It may be unexpected.

All are acceptable.

---

# 2.7 The Boring Is Allowed Rule

Many systems fail because they fear boredom.

Reality occasionally contains uneventful periods.

A living world requires contrast.

If every moment contains:

* Danger
* Drama
* Mystery
* Combat
* Revelation

Then nothing feels important.

Constant intensity destroys intensity.

Quiet moments provide scale.

Quiet moments provide recovery.

Quiet moments make major events meaningful.

---

# 2.8 The World Does Not Care

The simulation is not obligated to reward the player.

The simulation is not obligated to punish the player.

The simulation is not obligated to entertain the player.

The simulation is obligated only to remain internally consistent.

Consistency creates trust.

Trust creates immersion.

Immersion creates engagement.

Engagement creates memorable experiences.

---

# 2.9 The Player Is Not The Engine

Many systems secretly depend upon player actions.

Dice Reaction rejects this approach.

The player is an influence.

Not a requirement.

The simulation should continue functioning if:

* The player acts aggressively.
* The player acts passively.
* The player ignores major events.
* The player disappears entirely.

A functioning world cannot require constant player input to remain alive.

---

# 2.10 Independent Motion Doctrine

Every major system should possess self-generated motion.

NPCs should pursue goals.

Factions should pursue goals.

Settlements should pursue needs.

Resources should circulate.

Events should advance.

Information should spread.

The player should discover motion.

Not create motion.

---

# 2.11 Discovery Over Delivery

Traditional narratives deliver information.

Living worlds allow information to be discovered.

Important distinction:

Delivery:

The player is told.

Discovery:

The player learns.

Discovery produces ownership.

Ownership produces investment.

Investment produces attachment.

Attachment produces stories people remember.

---

# 2.12 Simulation Integrity

Simulation integrity measures how faithfully the world follows its own rules.

High integrity means:

The same conditions produce similar outcomes.

Low integrity means:

Reality changes whenever convenient.

---

Example:

A city normally starves when food imports stop.

If the same city magically survives because the player is nearby:

Simulation integrity has been broken.

---

# 2.13 The Cost Of Integrity

Simulation-first design creates challenges.

Players may:

Miss content.

Fail objectives.

Lose opportunities.

Cause disasters.

Kill important figures.

Break intended plans.

This is not a flaw.

This is evidence the simulation is functioning.

A world that cannot be changed is not alive.

---

# 2.14 The Price Of Agency

Agency is expensive.

True agency means outcomes cannot be guaranteed.

Many games promise agency.

Few actually allow it.

Dice Reaction accepts the cost.

Meaningful choice requires meaningful risk.

Without risk:

Choice becomes decoration.

---

# 2.15 The Emergence Principle

The highest form of success in Dice Reaction is emergence.

Emergence occurs when:

Simple rules interact to create complex outcomes.

Example:

A drought occurs.

Food prices rise.

Banditry increases.

Trade routes shift.

Merchants relocate.

Settlements weaken.

Political pressure grows.

Civil unrest begins.

No script required.

Only simulation.

---

# 2.16 The Content Illusion

Many projects believe content creates longevity.

Simulation-first design rejects this assumption.

Content is finite.

Simulation is renewable.

A thousand handcrafted quests eventually end.

A living world continues generating situations indefinitely.

The objective is not infinite content.

The objective is infinite possibility.

---

# 2.17 Simulation As Infrastructure

Simulation should be viewed as infrastructure.

Narrative sits on top of simulation.

Quests sit on top of simulation.

Dialogue sits on top of simulation.

Events sit on top of simulation.

Everything depends upon simulation.

Nothing should bypass it.

---

# 2.18 The Drift Warning

As the project grows, there will be pressure to:

Add story shortcuts.

Protect major characters.

Guarantee content.

Force dramatic moments.

Increase spectacle.

Reduce uncertainty.

Each of these creates drift.

Each moves the project away from its identity.

Every major feature should be evaluated against one question:

Does this strengthen simulation?

Or replace simulation?

If it replaces simulation, reject it.

---

# 2.19 The Simulation First Test

Before any feature is approved, ask:

Would this still make sense if no player existed?

If yes:

It probably belongs in the simulation.

If no:

It probably belongs in presentation.

This simple test prevents years of architectural drift.

---

# 2.20 Final Doctrine

Simulation is the foundation.

Reality is the source of truth.

Causality governs change.

Consequences create history.

Narrative describes history.

Presentation communicates narrative.

The hierarchy must remain intact.

The world must never bend for the story.

The story must emerge from the world.

A living world does not ask:

"What would be interesting?"

A living world asks:

"What would happen?"

Everything else follows from that question.

END OF CHAPTER 2
CANONICAL VERSION

# CHAPTER 3

# STATE IS TRUTH

## Status

Canonical

This chapter establishes the most important technical doctrine in the Dice Reaction Story Engine.

If Chapter 1 defines what the world is, and Chapter 2 defines how the world should behave, Chapter 3 defines where reality actually exists.

This chapter governs:

* World State
* Persistence
* Memory
* Event Tracking
* Consequence Tracking
* NPC Continuity
* Settlement Continuity
* Narrative Generation
* Save Systems
* Compression Systems

Every future subsystem depends on this chapter.

---

# 3.1 Core Doctrine

The central doctrine is:

**State Is Truth.**

Reality exists within state.

Reality does not exist within narrative.

Reality does not exist within memory context.

Reality does not exist within generated prose.

Reality does not exist within AI output.

Reality exists only within state.

---

# 3.2 The Fundamental Mistake

Most AI storytelling systems treat narrative as reality.

Example:

The AI writes:

> The blacksmith's arm is broken.

The system then assumes:

The blacksmith has a broken arm.

This creates catastrophic failures.

The AI later forgets.

The injury disappears.

The world changes arbitrarily.

Reality becomes unstable.

---

This is forbidden.

Narrative must never be the source of truth.

---

# 3.3 Reality Hierarchy

Dice Reaction operates under the following hierarchy:

```text
World State
↓
Simulation
↓
Consequences
↓
Narrative Rendering
↓
Player Observation
```

Not:

```text
Narrative
↓
Player Observation
↓
AI Memory
↓
Reality
```

The second model creates hallucinated worlds.

The first model creates persistent worlds.

---

# 3.4 The Source Of Reality

Every important fact must exist somewhere in state.

Examples:

Player injuries.

NPC relationships.

Settlement conditions.

Faction influence.

Resource inventories.

Event progression.

World history.

All must exist in state.

If information exists only in prose:

It does not exist.

---

# 3.5 State Before Narrative

The simulation always updates state first.

Only after state changes are complete may narrative be generated.

Sequence:

```text
State Loaded
↓
Simulation Runs
↓
State Updated
↓
State Saved
↓
Narrative Generated
```

Never:

```text
Narrative Generated
↓
State Inferred
```

That approach causes drift.

Drift destroys persistence.

---

# 3.6 Narrative As A View

Narrative is not reality.

Narrative is a view of reality.

The narrative renderer functions similarly to a camera.

The camera records reality.

The camera does not create reality.

The renderer describes state.

The renderer does not define state.

---

# 3.7 The Camera Principle

Imagine two players observing the same village.

One enters from the north.

One enters from the south.

Both receive different descriptions.

Different observations.

Different experiences.

Yet the underlying state remains identical.

Reality exists beneath observation.

---

# 3.8 State Categories

All persistent information belongs to one of several state categories.

---

## Player State

Tracks:

* Health
* Injuries
* Fatigue
* Inventory
* Skills
* Conditions
* Reputation
* Relationships

---

## NPC State

Tracks:

* Identity
* Goals
* Stress
* Memory
* Relationships
* Location
* Resources
* Current Activity

---

## Settlement State

Tracks:

* Population
* Food
* Wealth
* Stability
* Security
* Influence
* Culture

---

## Faction State

Tracks:

* Goals
* Assets
* Territory
* Influence
* Relationships
* Leadership

---

## Event State

Tracks:

* Origin
* Progress
* Participants
* Consequences
* Resolution Status

---

## World State

Tracks:

* Weather
* Season
* Time
* Global Events
* Active Pressures
* Historical Changes

---

# 3.9 State Persistence Doctrine

State must survive.

If reality changes:

Reality remains changed.

Examples:

A bridge collapses.

The bridge remains collapsed.

A mayor dies.

The mayor remains dead.

A forest burns.

The forest remains burned.

The simulation may later repair these conditions.

But repair must itself occur through simulation.

Nothing simply resets.

---

# 3.10 Persistence Versus Memory

Persistence and memory are different systems.

Persistence answers:

"What is true?"

Memory answers:

"What is remembered?"

A king may be dead.

That remains true.

An NPC may not know the king is dead.

That is memory.

Truth and awareness are separate.

This distinction becomes critical later.

---

# 3.11 Objective State Versus Subjective State

Reality contains both objective and subjective information.

---

## Objective State

Universally true.

Examples:

Bridge destroyed.

Weather conditions.

Food stockpile quantity.

Location of a city.

Population count.

---

## Subjective State

True only from a specific perspective.

Examples:

Beliefs.

Rumours.

Trust.

Fear.

Suspicion.

Misunderstanding.

Opinion.

Both forms are important.

Both require persistence.

---

# 3.12 State Ownership

Every piece of information should have an owner.

Examples:

A wound belongs to a character.

A debt belongs to a relationship.

A crop shortage belongs to a settlement.

A war belongs to factions.

Ownership prevents ambiguity.

Ownership simplifies updates.

Ownership simplifies debugging.

---

# 3.13 The Anti-Hallucination Rule

The simulation must never invent reality during rendering.

The renderer may describe.

The renderer may emphasize.

The renderer may interpret.

The renderer may not create.

Example:

Bad:

Renderer mentions an abandoned tower.

Tower now exists.

Good:

Renderer queries state.

Tower exists in state.

Renderer describes tower.

Reality remains consistent.

---

# 3.14 State Mutation

State changes only through approved mechanisms.

Examples:

Simulation Tick.

Player Action.

NPC Action.

Faction Action.

Event Resolution.

Environmental Change.

No other system may alter reality.

This creates traceability.

---

# 3.15 Traceability Doctrine

Every major change should be traceable.

Developers should always be able to answer:

What changed?

Why did it change?

When did it change?

Who changed it?

What caused the change?

If these questions cannot be answered:

State governance has failed.

---

# 3.16 World Drift

World Drift occurs when narrative and state diverge.

Examples:

Narrative says a bridge exists.

State says bridge destroyed.

Narrative says NPC alive.

State says NPC dead.

Narrative says town prosperous.

State says famine active.

World Drift is considered a critical failure.

All systems should actively prevent it.

---

# 3.17 State Compression Doctrine

Reality is expensive.

Infinite storage is impossible.

Not every fact deserves equal attention forever.

Therefore state must support compression.

Compression reduces processing cost.

Compression does not alter truth.

Important distinction.

---

Example:

Detailed memory:

```text
The merchant sold three apples on the morning
of the seventh day.
```

Compressed memory:

```text
Merchant operated normally during spring.
```

Truth remains.

Detail decreases.

---

# 3.18 The Layers Of Truth

Reality exists in layers.

---

### Active State

Currently affecting simulation.

---

### Relevant State

Not active.

Still important.

---

### Dormant State

Potentially recoverable.

Rarely referenced.

---

### Archived State

Historical truth.

No active processing.

Still exists.

---

This structure allows enormous worlds without infinite computational cost.

---

# 3.19 State And Save Systems

Save systems do not save stories.

Save systems save state.

A story can always be regenerated.

Reality cannot.

Priority order:

1. State
2. Consequences
3. Memory
4. Narrative

Narrative is disposable.

State is not.

---

# 3.20 State And Multiplayer

Future-proofing rule.

Regardless of future multiplayer implementation:

All players must interact with the same reality.

Different perspectives.

Same state.

This chapter makes multiplayer possible without rewriting the simulation.

---

# 3.21 The State Integrity Test

Before any feature is approved, ask:

Can this exist entirely within state?

Can it persist?

Can it be queried?

Can it be updated?

Can it be traced?

Can it survive regeneration?

If yes:

The feature respects State Is Truth.

If no:

The feature requires redesign.

---

# 3.22 Final Doctrine

Reality exists within state.

Simulation modifies state.

Consequences emerge from state.

Narrative describes state.

Observation reveals state.

State is the foundation beneath every system.

Without state:

There is no persistence.

Without persistence:

There is no history.

Without history:

There is no living world.

Therefore:

State is truth.

Everything else is interpretation.

# 3.23 The Primacy of Events

The doctrine "State Is Truth" is not contradicted by Event Sourcing (Chapter 22).

Rather, they are two sides of the same foundation.

Events are the immutable source of truth.
State is the current projection of those events.

Every truth in the simulation originates either from an initial condition or from an immutable event. No truth is ever invented by narrative, rendering, or AI output.

The event log is the ultimate historical record. State is a cache – a high‑performance view of the present.

This preserves the anti‑hallucination rule (3.13) while making event sourcing the technical backbone of causality.

Therefore:

- To know what is true now → query state.
- To know why it is true → query events.
- To know what was true at any past time → replay events.

State Is Truth means: the simulation never derives truth from narrative. But events are the proof of that truth.

END OF CHAPTER 3

CANONICAL VERSION


# CHAPTER 4

# THE SIMULATION LOOP

## Status

Canonical

This chapter defines the operational heartbeat of the Dice Reaction Story Engine.

If Chapter 1 defines what the world is, Chapter 2 defines how it should think, and Chapter 3 defines where reality exists, Chapter 4 defines how reality changes.

This chapter is the engine's central nervous system.

Every action, consequence, event, relationship, faction movement, settlement change, and world evolution process ultimately passes through this loop.

No system is exempt.

---

# 4.1 Core Doctrine

The simulation loop is the only approved pathway through which reality may change.

Reality cannot change arbitrarily.

Reality cannot change because a narrative demands it.

Reality cannot change because a developer wishes it.

Reality changes only through simulation.

---

# 4.2 The Master Loop

The master loop is:

```text
Intent
↓
Validation
↓
Context Evaluation
↓
Resolution
↓
Consequence Generation
↓
State Update
↓
World Tick
↓
Persistence
↓
Narrative Rendering
```

Every player action follows this structure.

Every NPC action follows this structure.

Every faction action follows this structure.

Every simulation event follows this structure.

---

# 4.3 Why The Loop Exists

Without a structured loop:

* Reality becomes inconsistent.
* Consequences become arbitrary.
* Persistence breaks.
* Traceability disappears.
* Debugging becomes impossible.

The loop creates order.

The loop guarantees causality.

The loop preserves integrity.

---

# 4.4 Stage 1: Intent

Intent is the desired outcome of an action.

The player does not submit mechanics.

The player submits intention.

Examples:

"I sneak past the guards."

"I burn the warehouse."

"I convince the merchant."

"I hide the evidence."

The player thinks naturally.

The engine translates intent into simulation language.

---

# 4.5 Intent Over Commands

Dice Reaction is not command driven.

It is intention driven.

Bad:

```text
STEALTH CHECK
```

Good:

```text
I wait until the rain gets heavier,
then move between the patrols.
```

The simulation interprets behaviour.

The player expresses thought.

---

# 4.6 Stage 2: Validation

Before an action can occur, the simulation must determine whether the action is possible.

Validation answers:

Can this happen?

Not:

Will this succeed?

---

Examples:

Can the player reach the roof?

Can the player access the vault?

Can the player physically lift the object?

Can the player communicate with the target?

Can the player even attempt the action?

---

Invalid actions never enter resolution.

---

# 4.7 Validation Doctrine

Validation protects realism.

Examples:

A dead character cannot negotiate.

A blind character cannot identify colours.

A prisoner cannot freely walk away.

A starving settlement cannot feed an army.

Reality imposes limits.

Simulation must respect them.

---

# 4.8 Stage 3: Context Evaluation

Once an action is possible, the engine evaluates surrounding circumstances.

Context determines difficulty.

Context determines opportunity.

Context determines risk.

---

Examples:

Weather.

Lighting.

Fatigue.

Injuries.

Witnesses.

Stress.

Resources.

Relationships.

Terrain.

Distance.

Time pressure.

All influence outcomes.

---

# 4.9 Context Is Reality

Context is not a modifier system.

Context is reality.

Reality naturally influences outcomes.

Modifiers are merely mathematical representations of reality.

The player should experience context.

Not numbers.

---

# 4.10 Stage 4: Resolution

Resolution determines uncertainty.

Not all actions require resolution.

Only uncertain actions enter this stage.

Examples:

Walking through an open doorway.

No resolution.

Picking a difficult lock.

Resolution required.

---

# 4.11 Resolution Philosophy

Resolution answers:

What happens?

Not:

Did you win?

The outcome space is broader than success or failure.

Reality contains shades of outcome.

The simulation should reflect that.

---

# 4.12 Hidden D20 Resolution

Dice Reaction uses hidden D20 resolution bands.

The player never sees:

* Rolls
* DCs
* Modifiers
* Internal calculations

The player experiences outcomes.

Not mechanics.

---

Bands:

```text
1–5   Critical Failure
6–10  Failure
11–15 Partial Success
16–19 Success
20    Critical Success
```

These bands describe narrative consequence.

Not player value.

---

# 4.13 Outcome Richness

The simulation should avoid binary outcomes whenever possible.

Bad:

Success.

Failure.

Good:

Success with complication.

Failure with opportunity.

Partial success.

Costly success.

Unexpected success.

Escalation.

Discovery.

Diversified outcomes create richer worlds.

---

# 4.14 Stage 5: Consequence Generation

Resolution creates consequences.

Consequences are the true product of the simulation.

Not outcomes.

Consequences.

Example:

Lockpick succeeds.

Immediate outcome:

Door opens.

Consequences:

Noise generated.

Witness alerted.

Evidence left behind.

Timeline altered.

Future opportunities changed.

---

# 4.15 Immediate Consequences

Immediate consequences occur now.

Examples:

Damage.

Noise.

Movement.

Resource use.

Detection.

Reputation shifts.

They affect the current scene.

---

# 4.16 Delayed Consequences

Delayed consequences enter the ledger.

They may emerge:

Minutes later.

Days later.

Months later.

Years later.

The player may never connect them to the original action.

Reality often works this way.

---

# 4.17 Cascading Consequences

The most important consequences create further consequences.

Example:

Crop failure.

↓

Food shortage.

↓

Price increase.

↓

Theft increase.

↓

Guard expansion.

↓

Public resentment.

↓

Political instability.

↓

Civil unrest.

The simulation should favour chains.

Not isolated events.

---

# 4.18 Stage 6: State Update

Once consequences are determined, reality changes.

This is the moment where state mutates.

Examples:

Resources removed.

Relationships altered.

Injuries applied.

Events advanced.

Reputation updated.

The world becomes different.

---

# 4.19 State Mutation Rules

State mutation must be:

Traceable.

Persistent.

Causal.

Consistent.

Nothing updates without reason.

Nothing updates without ownership.

---

# 4.20 Stage 7: World Tick

After local changes occur, the broader world advances.

The world tick represents independent motion.

This stage is critical.

Without it, the world becomes reactive instead of alive.

---

# 4.21 World Tick Responsibilities

The world tick evaluates:

NPC goals.

Faction goals.

Settlement pressures.

Resource movement.

Information spread.

Delayed consequences.

Active events.

Emerging pressures.

Latent pressures.

Historical progression.

This stage ensures the world moves even when the player does not.

---

# 4.22 The Independent Motion Rule

The world tick must be capable of generating meaningful change without player involvement.

If the player waits:

The world advances.

If the player travels:

The world advances.

If the player ignores a crisis:

The crisis advances.

Reality continues.

---

# 4.23 Stage 8: Persistence

Once updates are complete, reality must be preserved.

State is written.

Events recorded.

Consequences archived.

Memory updated.

The simulation commits reality.

Nothing remains temporary.

---

# 4.24 Persistence Before Narrative

This rule is mandatory.

Reality must be saved before narrative is generated.

Reason:

Narrative can fail.

Generation can fail.

Context can fail.

Reality cannot be lost.

State always comes first.

---

# 4.25 Stage 9: Narrative Rendering

Only now may narrative occur.

The renderer observes reality.

The renderer describes reality.

The renderer does not create reality.

---

# 4.26 The Observer Layer

The player never sees the loop.

The player sees only results.

The loop should remain invisible.

Visible machinery weakens immersion.

Invisible machinery strengthens belief.

---

# 4.27 Nested Loops

The master loop contains smaller loops.

Examples:

Combat loops.

Conversation loops.

Trade loops.

Investigation loops.

Travel loops.

All remain subordinate to the master loop.

None may bypass it.

---

# 4.28 Simulation Scalability

The loop must function at every scale.

A single conversation.

A village economy.

A regional war.

A continental famine.

A global catastrophe.

The process remains identical.

Only scope changes.

---

# 4.29 The Fairness Requirement

Every outcome must be explainable.

If a developer cannot explain:

Why something happened.

When it happened.

How it happened.

Then the loop failed.

Simulation integrity has been compromised.

---

# 4.30 Final Doctrine

The simulation loop is the engine's heartbeat.

Intent enters.

Reality evaluates.

Consequences emerge.

State changes.

The world advances.

History accumulates.

Narrative reveals the result.

The player experiences a story.

The simulation experiences reality.

Everything in Dice Reaction ultimately flows through this loop.

END OF CHAPTER 4

CANONICAL VERSION


# CHAPTER 5

# WORLD HEARTBEAT ARCHITECTURE

## Status

Canonical

This chapter defines how time advances inside the Dice Reaction Story Engine.

If Chapter 4 defines how reality changes, Chapter 5 defines when reality changes.

The World Heartbeat is the mechanism that allows a living world to continue existing independently of observation.

Without a heartbeat:

The world becomes reactive.

With a heartbeat:

The world becomes alive.

This chapter governs:

* Time progression
* World ticks
* Background simulation
* Independent motion
* Event advancement
* Pressure advancement
* Resource circulation
* Information propagation
* Simulation scaling
* Processing efficiency

Every future system that changes over time must conform to this chapter.

---

# 5.1 Core Doctrine

The world is always moving.

The player may stop.

The simulation may not.

The World Heartbeat exists to ensure that reality continues evolving whether or not the player directly interacts with it.

A living world must possess motion.

Motion requires time.

Time requires a heartbeat.

---

# 5.2 Definition

A World Heartbeat is the smallest approved unit of world progression.

The heartbeat is not narrative.

The heartbeat is not rendering.

The heartbeat is not player activity.

The heartbeat is simulation advancement.

Every heartbeat updates reality.

---

# 5.3 Purpose

The purpose of the heartbeat is simple:

Advance the world.

Not the player.

Not the story.

The world.

The simulation should never ask:

"What should happen next?"

The simulation should ask:

"What changed since the last heartbeat?"

---

# 5.4 Heartbeat Layers

Reality operates at multiple scales simultaneously.

Not every system requires equal update frequency.

Therefore the heartbeat exists in layers.

---

## Micro Heartbeat

Handles:

* Combat
* Conversations
* Investigations
* Immediate actions
* Scene interactions

Time scale:

Seconds to minutes.

---

## Local Heartbeat

Handles:

* NPC activity
* Settlement activity
* Resource usage
* Daily routines

Time scale:

Hours.

---

## Regional Heartbeat

Handles:

* Trade movement
* Political shifts
* Criminal activity
* Migration
* Faction operations

Time scale:

Days.

---

## Macro Heartbeat

Handles:

* Wars
* Economic shifts
* Cultural change
* Population trends
* Infrastructure growth

Time scale:

Weeks, months, years.

---

# 5.5 Layer Synchronisation

All heartbeat layers operate from the same reality.

Different scales.

Same truth.

Example:

A murder occurs.

Micro Layer:

Murder event.

Local Layer:

Investigation begins.

Regional Layer:

Political concern grows.

Macro Layer:

Public trust declines.

One event.

Multiple scales.

---

# 5.6 Active Simulation

Not all reality requires equal processing.

Active Simulation refers to systems currently relevant.

Examples:

Current location.

Nearby NPCs.

Ongoing investigations.

Immediate threats.

Current conversations.

Active simulation receives maximum detail.

---

# 5.7 Passive Simulation

Passive Simulation governs everything outside immediate attention.

Examples:

Distant cities.

Remote factions.

Foreign trade.

Unseen conflicts.

These systems continue progressing.

They simply operate at lower resolution.

---

# 5.8 The Resolution Principle

Reality does not stop existing when unseen.

Reality merely becomes less detailed.

This principle is critical.

The simulation does not unload reality.

The simulation reduces resolution.

---

Example:

Active settlement:

Tracks:

* Individuals
* Inventories
* Relationships
* Activities

Passive settlement:

Tracks:

* Population
* Stability
* Food
* Wealth
* Influence

Same settlement.

Different simulation depth.

---

# 5.9 Dynamic Resolution Scaling

The world continuously adjusts simulation detail.

Closer systems receive greater attention.

Distant systems receive less attention.

This creates scalability.

Without resolution scaling:

The world eventually becomes impossible to simulate.

---

# 5.10 The Attention Rule

Simulation detail follows attention.

Attention determines:

Processing priority.

Memory priority.

Update frequency.

Narrative relevance.

Reality remains true regardless of attention.

Only detail changes.

---

# 5.11 World Tick Processing

Every heartbeat evaluates:

Active Pressures.

Active Events.

NPC Goals.

Faction Goals.

Settlement Needs.

Resource Movement.

Information Spread.

Delayed Consequences.

Historical Progression.

Relationship Changes.

This sequence remains consistent.

---

# 5.12 Time Compression

Not all periods require equal detail.

A week of travel should not require 10,000 simulation cycles.

Time compression exists to preserve realism while reducing waste.

The simulation may safely compress periods where meaningful change is unlikely.

---

Example:

Three peaceful travel days.

Can become:

One compressed update.

Reality remains consistent.

Processing remains efficient.

---

# 5.13 Time Expansion

The opposite is also true.

Important moments require expansion.

Examples:

Combat.

Negotiations.

Investigations.

Disasters.

Crises.

These situations receive greater simulation granularity.

---

# 5.14 The Density Principle

Simulation density should match consequence density.

High consequence situations:

High detail.

Low consequence situations:

Low detail.

This principle governs processing efficiency.

---

# 5.15 Independent Motion

Independent motion is the defining characteristic of a living world.

Every heartbeat should create the possibility of change.

Examples:

NPCs move.

Prices shift.

Relationships evolve.

Threats grow.

Opportunities emerge.

Information spreads.

The player is not required.

---

# 5.16 Event Advancement

Events possess lifecycles.

Heartbeats move events through those lifecycles.

Example:

```text
Rumour
↓
Concern
↓
Investigation
↓
Discovery
↓
Reaction
↓
Resolution
↓
Historical Record
```

Events evolve naturally.

Not because the player observed them.

---

# 5.17 Pressure Advancement

Pressures evolve through heartbeat progression.

Pressure stages:

Formation.

Expansion.

Collision.

Escalation.

Resolution.

Scar Formation.

Every heartbeat may advance pressure.

---

# 5.18 Background History Generation

History is constantly forming.

Most history will never involve the player.

This is intentional.

Examples:

A distant mayor resigns.

A merchant family gains influence.

A bridge collapses.

A religious movement spreads.

Reality becomes richer through unseen history.

---

# 5.19 The Illusion Of A Larger World

Players should frequently encounter evidence that life continued elsewhere.

Examples:

New rumours.

Political changes.

Price shifts.

New leadership.

Destroyed settlements.

Refugees.

Returning traders.

These signals reinforce independent motion.

---

# 5.20 Simulation Priority System

Not all systems deserve equal processing.

Priority tiers:

Critical.

Important.

Relevant.

Dormant.

Archived.

Processing effort should follow priority.

This preserves performance.

---

# 5.21 Critical Priority

Critical systems include:

Current threats.

Current scene.

Player condition.

Immediate consequences.

These receive maximum update frequency.

---

# 5.22 Important Priority

Important systems include:

Nearby factions.

Nearby settlements.

Active investigations.

Major relationships.

These update frequently.

---

# 5.23 Relevant Priority

Relevant systems include:

Known distant events.

Moderately important history.

Secondary NPCs.

These update periodically.

---

# 5.24 Dormant Priority

Dormant systems include:

Old conflicts.

Inactive characters.

Past opportunities.

These update rarely.

---

# 5.25 Archived Priority

Archived systems are historical records.

They remain true.

They consume minimal resources.

History survives.

Processing does not.

---

# 5.26 Heartbeat Stability

A healthy heartbeat produces:

Motion.

Predictability.

Traceability.

Consistency.

A healthy heartbeat should never create chaos merely for activity.

Movement must remain causal.

---

# 5.27 Heartbeat Failure Modes

The most dangerous failures are:

### Frozen World

Nothing advances.

---

### Hyperactive World

Everything changes constantly.

---

### Random World

Changes lack causality.

---

### Memoryless World

Changes leave no history.

---

### Expensive World

Simulation cost exceeds value.

---

All future systems should be evaluated against these failure modes.

---

# 5.28 The Living World Test

Run simulation.

Remove player.

Advance time.

Questions:

Did events evolve?

Did factions act?

Did settlements change?

Did resources move?

Did pressures spread?

Did history accumulate?

If yes:

The heartbeat is functioning.

If no:

The world is not alive.

---

# 5.29 Scalability Doctrine

The heartbeat must function equally well for:

One village.

One kingdom.

One continent.

One planet.

The architecture must scale without fundamentally changing.

Only resolution changes.

Reality remains reality.

---

# 5.30 Final Doctrine

The heartbeat is the pulse of reality.

Every tick advances the world.

Events evolve.

Pressures spread.

Resources move.

History accumulates.

The player experiences moments.

The heartbeat experiences time.

A living world is not defined by what exists.

A living world is defined by what continues changing.

The World Heartbeat is the mechanism that makes that possible.

END OF CHAPTER 5

CANONICAL VERSION

# CHAPTER 6

# PRESSURE ECOLOGY

## Status

Canonical

This chapter defines the primary force that drives all change within the Dice Reaction Story Engine.

If the World Heartbeat provides motion, Pressure provides direction.

Pressure is the fuel of emergence.

Pressure is the source of behaviour.

Pressure is the origin of consequence.

Pressure is the foundation of narrative.

Without pressure, a world becomes static.

Without pressure, a world becomes predictable.

Without pressure, a world becomes dead.

This chapter governs:

* NPC motivation
* Settlement behaviour
* Faction behaviour
* Economic instability
* Political instability
* Crime generation
* Conflict generation
* Opportunity generation
* Event formation
* Narrative emergence

All future systems must treat pressure as a first-class simulation resource.

---

# 6.1 Core Doctrine

Every meaningful action originates from pressure.

Nobody acts without a reason.

Every reason is a pressure.

A starving man steals.

A frightened king raises taxes.

A desperate faction starts a war.

A lonely person seeks companionship.

A merchant lowers prices.

A guard accepts a bribe.

Pressure creates behaviour.

Behaviour creates consequences.

Consequences create history.

History creates new pressure.

This cycle drives the entire world.

---

# 6.2 Definition

Pressure is any condition that encourages change.

Pressure is not necessarily negative.

Pressure is not necessarily dangerous.

Pressure is simply a force that makes the current state unstable.

Examples:

Hunger.

Ambition.

Fear.

Love.

Greed.

Curiosity.

Faith.

Survival.

Competition.

Scarcity.

Opportunity.

All are forms of pressure.

---

# 6.3 The Universal Rule

No major event should occur without pressure.

If something significant happens:

The simulation should be able to identify the pressure responsible.

Examples:

A rebellion begins.

Why?

Political pressure.

Economic pressure.

Social pressure.

A merchant relocates.

Why?

Profit pressure.

Competition pressure.

A kingdom invades.

Why?

Resource pressure.

Strategic pressure.

Power pressure.

Pressure always comes first.

---

# 6.4 Pressure Versus Events

Pressure is not an event.

Pressure creates events.

Example:

Pressure:

Food shortage.

Event:

Bread riots.

Pressure:

Political instability.

Event:

Assassination attempt.

Pressure:

Territorial tension.

Event:

Border conflict.

Pressure is the cause.

Events are symptoms.

---

# 6.5 Pressure Categories

All pressures belong to one or more categories.

---

## Survival Pressure

Needs required for existence.

Examples:

Food.

Water.

Shelter.

Safety.

Health.

---

## Economic Pressure

Resource acquisition.

Examples:

Debt.

Profit.

Poverty.

Trade disruption.

Competition.

---

## Social Pressure

Human relationships.

Examples:

Acceptance.

Reputation.

Belonging.

Status.

Isolation.

---

## Political Pressure

Power distribution.

Examples:

Corruption.

Leadership conflict.

Rebellion.

Authority disputes.

Succession crises.

---

## Cultural Pressure

Shared beliefs.

Examples:

Religious conflict.

Tradition.

Identity.

Values.

Ideological change.

---

## Environmental Pressure

Natural forces.

Examples:

Drought.

Floods.

Disease.

Winter.

Predators.

Natural disasters.

---

## Psychological Pressure

Internal emotional forces.

Examples:

Fear.

Guilt.

Love.

Hatred.

Jealousy.

Obsession.

Trauma.

---

# 6.6 Pressure Is Not Morality

Pressure is neutral.

The simulation must never assign moral judgement.

Starvation creates pressure.

Whether a person steals is a response.

Fear creates pressure.

Whether a person attacks is a response.

The simulation models behaviour.

The simulation does not preach behaviour.

---

# 6.7 Pressure Intensity

Every pressure possesses intensity.

Intensity measures urgency.

Low intensity pressure:

Can be ignored.

Moderate pressure:

Influences behaviour.

High pressure:

Forces behaviour.

Extreme pressure:

Dominates behaviour.

The higher the intensity, the greater the likelihood of action.

---

# 6.8 Pressure Accumulation

Pressure rarely appears instantly.

Most pressure accumulates.

Example:

One missed harvest.

Minor concern.

Two missed harvests.

Food anxiety.

Three missed harvests.

Regional panic.

Four missed harvests.

Famine.

Pressure grows through accumulation.

---

# 6.9 Pressure Thresholds

Every system possesses tolerance.

Pressure can exist below tolerance levels.

Once tolerance is exceeded:

Behaviour changes.

Example:

A city tolerates minor crime.

Crime rises.

Crime rises further.

Tolerance exceeded.

Curfews begin.

The pressure existed long before visible action occurred.

---

# 6.10 Pressure Lifecycle

Every pressure follows a lifecycle.

Formation.

Growth.

Expansion.

Collision.

Escalation.

Resolution.

Scar Formation.

No pressure remains static forever.

---

# 6.11 Formation

A destabilising condition emerges.

Examples:

Poor harvest.

Political scandal.

Bandit activity.

Disease outbreak.

Leadership death.

Formation is the birth of pressure.

---

# 6.12 Growth

Pressure increases.

Conditions worsen.

Concern spreads.

More systems become affected.

Growth often remains invisible.

This makes it dangerous.

---

# 6.13 Expansion

Pressure spreads beyond its origin.

Example:

Crop failure.

↓

Food shortage.

↓

Price increase.

↓

Trade disruption.

↓

Migration.

↓

Crime increase.

Pressure rarely stays contained.

---

# 6.14 Collision

Pressures frequently collide.

Example:

Economic pressure.

*

Political pressure.

=

Civil unrest.

Example:

Religious pressure.

*

Territorial pressure.

=

Holy war.

Collisions generate complexity.

---

# 6.15 Escalation

When unresolved, pressure intensifies.

Escalation creates visible outcomes.

Examples:

Riots.

Murders.

Coups.

Wars.

Mass migration.

Social collapse.

Escalation transforms pressure into history.

---

# 6.16 Resolution

Pressure eventually resolves.

Resolution does not necessarily mean improvement.

A famine resolves.

People die.

A war resolves.

Cities burn.

Resolution simply means stability returns.

---

# 6.17 Scar Formation

All major pressure should leave scars.

Examples:

Destroyed infrastructure.

Population decline.

Distrust.

New laws.

Cultural change.

Trauma.

Scars are evidence of resolved pressure.

---

# 6.18 Pressure Networks

Pressures rarely exist alone.

Most pressures connect.

Example:

```text
Food Shortage
↓
Economic Pressure
↓
Crime Pressure
↓
Political Pressure
↓
Civil Conflict
```

Networks generate emergence.

Emergence generates stories.

---

# 6.19 Pressure Ecology

Pressure behaves similarly to ecology.

It grows.

Spreads.

Competes.

Consumes.

Mutates.

Collides.

Dies.

No central planner is required.

Pressure naturally organizes behaviour.

---

# 6.20 Opportunity Pressure

Not all pressure is negative.

Opportunities generate pressure too.

Examples:

Gold discovered.

New trade route.

Political vacancy.

Technological innovation.

Inheritance.

Power vacuum.

Opportunity creates movement just as effectively as danger.

---

# 6.21 Positive Pressure

Examples:

Hope.

Prosperity.

Ambition.

Innovation.

Exploration.

Growth.

Positive pressures can reshape the world as dramatically as disasters.

---

# 6.22 Pressure Horizon System

The simulation tracks three primary pressure layers.

---

## Immediate Pressure

Current visible threat.

Examples:

Combat.

Starvation.

Fire.

Investigation.

---

## Emerging Pressure

Developing instability.

Examples:

Trade collapse.

Political tension.

Crime growth.

Resource depletion.

---

## Latent Pressure

Hidden instability.

Examples:

Secret cult.

Unseen corruption.

Succession crisis.

Foreign invasion preparation.

The horizon system prevents chaos.

---

# 6.23 Pressure Visibility

Not all pressure should be visible.

Reality often contains hidden instability.

Visible pressure creates tension.

Hidden pressure creates discovery.

Both are required.

---

# 6.24 NPC Pressure

Every NPC contains active pressures.

Examples:

Debt.

Fear.

Loneliness.

Duty.

Greed.

Love.

Revenge.

These pressures drive behaviour.

Not scripts.

---

# 6.25 Settlement Pressure

Settlements possess collective pressures.

Examples:

Food insecurity.

Crime.

Economic decline.

Housing shortages.

Political division.

These pressures shape community behaviour.

---

# 6.26 Faction Pressure

Factions exist largely because of pressure.

Pressure creates goals.

Goals create actions.

Actions create consequences.

A faction without pressure becomes inert.

Inert factions eventually become irrelevant.

---

# 6.27 Narrative Emergence

Narrative emerges naturally from pressure.

Example:

A miner loses work.

↓

Debt increases.

↓

Joins smugglers.

↓

Smugglers gain strength.

↓

Trade disruption occurs.

↓

Authorities investigate.

↓

Player becomes involved.

No story was written.

The story emerged.

---

# 6.28 Pressure Health

A healthy world contains pressure.

Too little pressure:

The world stagnates.

Too much pressure:

The world becomes noise.

Balance is essential.

The simulation should continuously seek dynamic equilibrium.

---

# 6.29 Dead Pressure

Dead pressure occurs when conditions exist but produce no behaviour.

Example:

A starving city that never reacts.

A corrupt government nobody resists.

A collapsing economy with no consequences.

Dead pressure is a major simulation failure.

---

# 6.30 Final Doctrine

Pressure is the primary driver of change.

Pressure creates behaviour.

Behaviour creates consequences.

Consequences create history.

History creates new pressure.

The world is not driven by stories.

The world is driven by pressure.

Stories merely emerge from the resulting collisions.

Pressure is the fuel of the living world.

# 6.31 Baseline Pressure Generation

Pressure drives all change. But without a minimum pressure floor, a quiet period could become permanent stagnation.

Therefore, even when no major pressures exist, the simulation generates **baseline pressure** through:

- Environmental cycles: seasons, weather changes, day/night.
- Resource renewal and depletion: crops grow, mines empty.
- Routine low‑intensity events: minor disputes, small crimes, ordinary trade fluctuations.
- Random social friction: gossip, minor slights, small favours.

Baseline pressure is never zero. Its typical intensity is 0.05–0.1 on a 0‑1 scale – enough to keep actors moving, but not enough to trigger crises.

This ensures the world never freezes. Quiet periods are still *alive* – they simply lack emergencies.

The simulation may temporarily suspend baseline pressure only during debugging or developer overrides. In normal operation, baseline pressure is always present.

END OF CHAPTER 6

CANONICAL VERSION

# CHAPTER 7

# SETTLEMENT ORGANISM THEORY

## Status

Canonical

This chapter establishes one of the most important concepts within the Dice Reaction Story Engine:

A settlement is not a location.

A settlement is an organism.

Villages, towns, cities, forts, colonies, outposts, kingdoms, and megacities should not be treated as scenery.

They should be treated as living systems attempting to survive.

The purpose of this chapter is to define how settlements think, grow, adapt, suffer, evolve, and die.

This chapter governs:

* Settlement simulation
* Population behaviour
* Settlement growth
* Settlement decline
* Resource demand
* Resource consumption
* Infrastructure development
* Stability systems
* Settlement identity
* Settlement evolution

Every future system involving communities must conform to this chapter.

---

# 7.1 Core Doctrine

A settlement exists to continue existing.

This is its primary goal.

Everything else is secondary.

Every settlement:

Consumes resources.

Responds to pressure.

Protects itself.

Adapts to threats.

Attempts survival.

The size of the settlement changes.

The behaviour does not.

A city and a village follow the same fundamental rules.

Only scale differs.

---

# 7.2 Definition

A settlement is a self-sustaining concentration of population that consumes resources, generates pressures, and produces history.

A settlement is not:

A map marker.

A quest hub.

A backdrop.

A static container.

A settlement is a simulation actor.

---

# 7.3 Settlement As Organism

Every organism requires:

Input.

Processing.

Output.

Settlements are no different.

---

Inputs:

Food.

Water.

Labour.

Information.

Security.

Trade.

Population.

Resources.

---

Processing:

Production.

Governance.

Culture.

Conflict.

Adaptation.

Distribution.

---

Outputs:

Goods.

Services.

Waste.

Influence.

Information.

Migration.

History.

---

# 7.4 Settlement Life Cycle

Every settlement moves through stages.

Birth.

Growth.

Maturity.

Decline.

Collapse.

Transformation.

Few settlements remain permanently stable.

Change is normal.

---

# 7.5 Settlement Core Variables

Every settlement contains six foundational variables.

These variables determine behaviour.

---

## Population

Represents available people.

Population affects:

Labour.

Production.

Military capability.

Growth potential.

Economic activity.

A settlement without people cannot function.

---

## Food

Represents survival capacity.

Food shortages generate immediate pressure.

Food abundance encourages growth.

Food is among the most important variables in the simulation.

---

## Wealth

Represents economic capacity.

Wealth affects:

Trade.

Construction.

Influence.

Defensive capability.

Recovery speed.

Wealth is not survival.

But wealth often improves survival.

---

## Security

Represents safety.

Security affects:

Crime.

Trade confidence.

Population retention.

Political stability.

Settlement attractiveness.

---

## Stability

Represents internal cohesion.

Low stability increases:

Riots.

Corruption.

Migration.

Violence.

Civil unrest.

High stability increases resilience.

---

## Influence

Represents external significance.

Influence affects:

Trade routes.

Political leverage.

Regional importance.

Faction interest.

Cultural spread.

---

# 7.6 Settlement Needs

Every settlement possesses needs.

Needs create pressure.

Pressure creates behaviour.

Core needs:

Food.

Water.

Shelter.

Security.

Labour.

Trade.

Governance.

Information.

Failure to satisfy needs creates instability.

---

# 7.7 The Need Hierarchy

Needs exist in priority order.

A starving city does not care about art.

A besieged city does not care about fashion.

Priority:

Survival.

Security.

Stability.

Prosperity.

Expansion.

Culture.

This hierarchy influences behaviour.

---

# 7.8 Settlement Metabolism

Settlements consume resources continuously.

Food consumed.

Water consumed.

Goods consumed.

Labour consumed.

Infrastructure consumed.

No settlement remains static.

Everything requires maintenance.

---

# 7.9 Resource Dependency

No settlement is completely self-sufficient.

Every settlement depends on something.

Examples:

Trade routes.

Farmland.

Fishing grounds.

Mining operations.

Water sources.

Import networks.

Dependency creates vulnerability.

Vulnerability creates pressure.

---

# 7.10 Growth

Growth occurs when inputs exceed requirements.

Conditions encouraging growth:

Food surplus.

Trade surplus.

Security.

Stable leadership.

Resource abundance.

Population confidence.

Growth is never free.

Growth increases future demands.

---

# 7.11 Decline

Decline occurs when requirements exceed inputs.

Common causes:

Food shortages.

Trade collapse.

Disease.

War.

Migration.

Environmental damage.

Political failure.

Decline creates pressure.

Pressure accelerates decline.

---

# 7.12 Collapse

Collapse occurs when core systems fail simultaneously.

Common indicators:

Food crisis.

Population loss.

Governance failure.

Security breakdown.

Economic collapse.

Collapse should emerge naturally.

Not through scripted events.

---

# 7.13 Transformation

Not all collapse results in destruction.

Some settlements transform.

Examples:

Trade town becomes military outpost.

Fishing village becomes port city.

Religious centre becomes political capital.

Transformation creates historical depth.

---

# 7.14 Settlement Identity

Every settlement develops identity.

Identity emerges from:

History.

Geography.

Resources.

Culture.

Threats.

Leadership.

Trade.

Religion.

Identity influences behaviour.

Identity should not be assigned arbitrarily.

Identity should emerge.

---

# 7.15 Identity Persistence

Identity changes slowly.

Major events can reshape identity.

Examples:

War.

Occupation.

Famine.

Religious revolution.

Economic boom.

Identity creates continuity across generations.

---

# 7.16 Geography Matters

Location influences settlement behaviour.

Mountain settlements behave differently from ports.

Desert settlements behave differently from river cities.

Environment shapes culture.

Environment shapes economy.

Environment shapes survival strategies.

---

# 7.17 Infrastructure

Infrastructure increases settlement capability.

Examples:

Roads.

Walls.

Harbours.

Bridges.

Markets.

Aqueducts.

Power systems.

Infrastructure improves efficiency.

Infrastructure requires maintenance.

---

# 7.18 Infrastructure Decay

Nothing lasts forever.

Infrastructure deteriorates.

Roads break.

Walls crumble.

Pipes fail.

Buildings age.

Maintenance is a recurring requirement.

Ignoring decay creates future pressure.

---

# 7.19 Settlement Memory

Settlements remember.

Not literally.

Collectively.

Examples:

Historic battles.

Disasters.

Heroes.

Traitors.

Victories.

Injustices.

This memory influences behaviour.

---

# 7.20 Settlement Trauma

Major events can permanently alter behaviour.

Examples:

Repeated invasions.

Famine.

Occupation.

Civil war.

Disease outbreaks.

Trauma becomes part of identity.

---

# 7.21 Settlement Reputation

Other settlements develop opinions.

Examples:

Prosperous.

Dangerous.

Corrupt.

Reliable.

Lawless.

Religious.

Progressive.

Isolationist.

Reputation influences interaction.

---

# 7.22 Internal Factions

No settlement is unified.

Every settlement contains competing interests.

Examples:

Merchants.

Workers.

Criminal groups.

Religious groups.

Political blocs.

Military leadership.

Competing pressures generate realism.

---

# 7.23 Migration

People move.

Migration is a critical simulation mechanic.

Reasons include:

Opportunity.

Safety.

Resources.

Family.

Religion.

Conflict.

Migration changes settlements.

Migration changes regions.

Migration changes history.

---

# 7.24 Population Dynamics

Population is not static.

Births occur.

Deaths occur.

Immigration occurs.

Emigration occurs.

Population shifts alter behaviour.

---

# 7.25 Settlement Pressure Generation

Settlements continuously generate pressure.

Examples:

Housing shortages.

Crime.

Trade competition.

Political rivalry.

Food demand.

Infrastructure stress.

Settlements are pressure engines.

---

# 7.26 Settlement Relationships

Settlements interact.

Trade.

Alliance.

Competition.

Conflict.

Dependency.

Isolation.

No settlement exists alone.

---

# 7.27 Settlement Hierarchies

Settlements naturally form hierarchies.

Examples:

Village.

Town.

City.

Capital.

Regional centre.

The hierarchy influences influence distribution.

---

# 7.28 Settlement Resilience

Resilience determines recovery capacity.

High resilience:

Absorbs shocks.

Recovers quickly.

Maintains stability.

Low resilience:

Breaks easily.

Recovers slowly.

Escalates pressure rapidly.

Resilience emerges from preparation.

---

# 7.29 The Dead Settlement Test

A settlement is considered dead if:

Nothing changes.

Nothing adapts.

Nothing consumes resources.

Nothing produces pressure.

Nothing generates history.

A dead settlement is scenery.

Dice Reaction settlements must never become scenery.

---

# 7.30 Final Doctrine

A settlement is not a location.

A settlement is a living system.

It consumes.

Produces.

Adapts.

Remembers.

Changes.

Grows.

Declines.

Transforms.

Every settlement exists as an organism attempting to survive within a world of competing pressures.

The player visits settlements.

The simulation lives through them.

END OF CHAPTER 7

CANONICAL VERSION

# CHAPTER 8

# RESOURCE FLOW THEORY

## Status

Canonical

This chapter defines the circulatory system of the Dice Reaction Story Engine.

If settlements are organisms, resources are blood.

If pressure is the fuel of change, resources are the fuel of survival.

Nothing survives without resources.

Nothing grows without resources.

Nothing collapses without resource failure.

This chapter governs:

* Resource generation
* Resource movement
* Resource consumption
* Resource scarcity
* Resource abundance
* Trade foundations
* Settlement sustainability
* Faction sustainability
* Economic behaviour
* Systemic collapse

Every future economic, political, military, social, and settlement system depends upon the principles established here.

---

# 8.1 Core Doctrine

Resources must move.

Static resources create dead worlds.

A mine that never exports ore is dead.

A farm that never produces food is dead.

A city that never consumes resources is dead.

A kingdom that never competes for resources is dead.

Movement creates dependency.

Dependency creates vulnerability.

Vulnerability creates pressure.

Pressure creates history.

---

# 8.2 Definition

A resource is anything that possesses utility and can influence behaviour.

Resources are not limited to physical goods.

Resources may be:

Physical.

Social.

Political.

Informational.

Economic.

Psychological.

Anything valuable enough to influence decisions becomes a resource.

---

# 8.3 Resource Categories

Resources fall into several major categories.

---

## Survival Resources

Required for continued existence.

Examples:

Food.

Water.

Fuel.

Medicine.

Shelter.

Air.

Energy.

These resources create the strongest pressures.

---

## Material Resources

Used for production.

Examples:

Wood.

Stone.

Iron.

Steel.

Timber.

Coal.

Concrete.

Electronics.

Manufacturing inputs.

---

## Economic Resources

Used to facilitate exchange.

Examples:

Currency.

Credit.

Trade goods.

Investment capital.

Debt capacity.

Financial reserves.

---

## Human Resources

People themselves are resources.

Examples:

Labour.

Expertise.

Leadership.

Education.

Military capability.

Knowledge.

---

## Information Resources

Information possesses value.

Examples:

Maps.

Secrets.

Intelligence.

Rumours.

Trade data.

Research.

Technology.

Information is treated as a real resource.

---

## Influence Resources

Power itself is a resource.

Examples:

Political authority.

Reputation.

Social standing.

Religious legitimacy.

Military prestige.

Influence can be spent.

Influence can be accumulated.

Influence can be lost.

---

# 8.4 Resource Lifecycle

Every resource follows a lifecycle.

Generation.

Storage.

Movement.

Consumption.

Renewal.

Depletion.

Transformation.

Nothing exists outside this cycle.

---

# 8.5 Resource Generation

Resources originate somewhere.

Examples:

Food from farms.

Ore from mines.

Labour from populations.

Information from observation.

Influence from achievements.

Generation establishes supply.

---

# 8.6 Resource Storage

Resources often require storage.

Examples:

Granaries.

Warehouses.

Banks.

Archives.

Memory systems.

Stockpiles.

Stored resources create resilience.

Stored resources create strategic value.

---

# 8.7 Resource Movement

Resources rarely remain where they originate.

Food travels.

Money travels.

People travel.

Information travels.

Influence travels.

Movement creates connections.

Connections create systems.

Systems create complexity.

---

# 8.8 Resource Consumption

Every system consumes resources.

Settlements consume food.

Armies consume supplies.

Governments consume labour.

Industries consume materials.

Consumption drives demand.

Demand drives behaviour.

---

# 8.9 Resource Renewal

Some resources regenerate.

Examples:

Forests.

Fish populations.

Agricultural output.

Population growth.

Trust.

Influence.

Renewal prevents permanent depletion.

---

# 8.10 Resource Depletion

Some resources can be exhausted.

Examples:

Mines.

Groundwater.

Stored food.

Financial reserves.

Political goodwill.

Resource depletion creates pressure.

Pressure drives adaptation.

---

# 8.11 Resource Transformation

Resources frequently transform into other resources.

Examples:

Ore becomes steel.

Steel becomes tools.

Tools increase production.

Production increases wealth.

Wealth increases influence.

Transformation creates economic depth.

---

# 8.12 The Dependency Principle

Every actor depends on resources.

Every dependency creates vulnerability.

Examples:

A city depends on grain imports.

A kingdom depends on tax revenue.

An army depends on supply lines.

A corporation depends on labour.

Dependency creates strategic importance.

---

# 8.13 Resource Chains

Most resources exist within chains.

Example:

```text
Farmland
↓
Grain
↓
Transportation
↓
Storage
↓
Market
↓
Consumer
```

Disruption anywhere affects everything downstream.

This principle creates realistic consequences.

---

# 8.14 Bottlenecks

A bottleneck is any point where flow becomes restricted.

Examples:

Destroyed bridge.

Closed port.

Corrupt official.

Limited workforce.

Supply shortage.

Bottlenecks create pressure.

Pressure drives events.

---

# 8.15 Resource Scarcity

Scarcity occurs when demand exceeds supply.

Scarcity creates behaviour.

Examples:

Price increases.

Crime.

Migration.

Competition.

Conflict.

Innovation.

Scarcity is one of the strongest generators of emergence.

---

# 8.16 Resource Abundance

Abundance also creates behaviour.

Examples:

Growth.

Expansion.

Complacency.

Investment.

Specialisation.

Prosperity.

Abundance changes incentives.

---

# 8.17 Resource Competition

Resources create competition.

Competition occurs between:

Individuals.

Groups.

Settlements.

Factions.

Kingdoms.

Corporations.

Competition creates pressure.

Pressure creates movement.

---

# 8.18 Resource Hoarding

Resources are not always distributed efficiently.

Actors often hoard.

Examples:

Food stockpiles.

Wealth concentration.

Knowledge monopolies.

Political power.

Strategic materials.

Hoarding creates imbalance.

Imbalance creates instability.

---

# 8.19 Resource Inequality

Unequal distribution generates pressure.

Examples:

Rich versus poor.

Urban versus rural.

Elite versus worker.

Powerful versus powerless.

Inequality is a persistent source of emergent conflict.

---

# 8.20 Resource Security

Resource availability matters.

Resource reliability matters more.

Example:

A city with one food source.

High risk.

A city with five food sources.

High resilience.

Diversification increases stability.

---

# 8.21 Resource Shock

A resource shock is a sudden disruption.

Examples:

Crop failure.

Market collapse.

Mine exhaustion.

Trade embargo.

Natural disaster.

Resource shocks often trigger major historical events.

---

# 8.22 Resource Resilience

Resilience measures the ability to survive disruption.

Factors include:

Storage.

Redundancy.

Diversification.

Infrastructure.

Governance.

Preparation.

Resilience reduces pressure.

---

# 8.23 Resource Waste

Not all resources are used efficiently.

Waste exists in every system.

Examples:

Corruption.

Spoilage.

Theft.

Mismanagement.

Bureaucracy.

War.

Waste should emerge naturally.

---

# 8.24 Invisible Resources

Many important resources are intangible.

Examples:

Trust.

Reputation.

Knowledge.

Morale.

Legitimacy.

These resources often influence outcomes more than physical goods.

---

# 8.25 Information As Resource

Information deserves special treatment.

Information can:

Spread.

Mutate.

Decay.

Accumulate.

Monopolise.

Information behaves like a physical resource.

Future chapters expand this concept.

---

# 8.26 Resource Gravity

Large resource concentrations attract activity.

Examples:

Gold rush towns.

Major ports.

Trade hubs.

Research centres.

Political capitals.

Resources naturally create centres of gravity.

---

# 8.27 Resource Pressure

Resource pressure occurs when flow becomes unstable.

Examples:

Food demand exceeds supply.

Labour shortages emerge.

Water becomes scarce.

Trust collapses.

Pressure forms before crisis becomes visible.

---

# 8.28 Resource Flow Health

Healthy systems display:

Generation.

Movement.

Consumption.

Renewal.

Adaptation.

Unhealthy systems display:

Stagnation.

Shortage.

Collapse.

Isolation.

Deadlock.

---

# 8.29 The Dead Resource Test

Ask:

Where does it come from?

Where does it go?

Who consumes it?

Who depends on it?

What happens if it disappears?

If these questions cannot be answered:

The resource system is incomplete.

---

# 8.30 Final Doctrine

Resources are the bloodstream of the world.

They must be generated.

They must move.

They must be consumed.

They must create dependency.

They must create vulnerability.

They must create pressure.

Every living settlement.

Every living faction.

Every living economy.

Every living society.

Exists because resources continue flowing.

When resources move, the world lives.

When resources stop, the world begins to die.

END OF CHAPTER 8

CANONICAL VERSION

# CHAPTER 9

# INFORMATION THEORY

## Status

Canonical

This chapter defines one of the most important systems within the Dice Reaction Story Engine.

Information is not flavour.

Information is not narration.

Information is not exposition.

Information is a resource.

Information moves.

Information spreads.

Information mutates.

Information decays.

Information creates pressure.

Information creates opportunity.

Information creates history.

Most games treat information as something the player automatically receives.

Dice Reaction rejects this model.

Knowledge must exist somewhere.

Knowledge must travel.

Knowledge must be discovered.

Knowledge must have owners.

This chapter governs:

* Rumours
* Secrets
* Reputation
* Witnesses
* Intelligence
* Investigation
* Communication
* Discovery
* Misinformation
* Knowledge propagation

Every future system involving awareness must conform to this chapter.

---

# 9.1 Core Doctrine

Information behaves like a resource.

The same principles that govern food, wealth, and materials also govern information.

Information has:

Origin.

Ownership.

Movement.

Storage.

Reliability.

Scarcity.

Value.

Information is never free.

Even when acquisition cost appears small.

---

# 9.2 The Knowledge Rule

Reality and knowledge are separate systems.

Something can be true without being known.

Something can be believed without being true.

The simulation must track both.

This distinction is critical.

---

Example:

A king dies.

Reality:

The king is dead.

Knowledge:

Only three people know.

The event exists.

Awareness does not.

---

# 9.3 Truth Versus Belief

The simulation maintains two layers.

---

## Objective Truth

What actually happened.

Examples:

The bridge collapsed.

The assassin escaped.

The harvest failed.

The king died.

Truth exists regardless of awareness.

---

## Subjective Belief

What an actor thinks happened.

Examples:

The bridge was sabotaged.

The assassin died.

The harvest was cursed.

The king was poisoned.

Belief influences behaviour.

Truth determines reality.

Both matter.

---

# 9.4 Information Lifecycle

Every piece of information follows a lifecycle.

Creation.

Storage.

Transmission.

Interpretation.

Mutation.

Decay.

Archiving.

No information remains unchanged forever.

---

# 9.5 Information Creation

Information originates from events.

Examples:

A murder occurs.

A treaty is signed.

A monster attacks.

A merchant arrives.

Reality creates information.

Information cannot exist without origin.

---

# 9.6 Information Ownership

Every piece of information has an owner.

Examples:

Witnesses.

Participants.

Investigators.

Officials.

Observers.

Ownership determines who knows something.

Knowledge without ownership creates simulation failures.

---

# 9.7 Information Storage

Information must exist somewhere.

Examples:

Memory.

Books.

Records.

Archives.

Maps.

Databases.

Rumour networks.

Stored information survives beyond direct observation.

---

# 9.8 Information Transmission

Information spreads through carriers.

Examples:

People.

Messengers.

Letters.

Trade routes.

Newspapers.

Digital networks.

Word of mouth.

Information does not teleport.

It travels.

---

# 9.9 The Carrier Principle

Information speed depends on carriers.

A secret known by one person spreads slowly.

A public announcement spreads rapidly.

A trade network spreads information further than an isolated village.

Carriers determine reach.

---

# 9.10 Information Velocity

Not all information spreads equally fast.

Examples:

Public executions spread quickly.

Private conversations spread slowly.

Military intelligence may spread selectively.

Velocity affects world awareness.

---

# 9.11 Information Range

Information loses strength over distance.

Nearby settlements often know more.

Distant settlements often know less.

Range creates regional perspectives.

This prevents unrealistic omniscience.

---

# 9.12 Information Reliability

Information is not always accurate.

Reliability varies.

Sources may be:

Accurate.

Mistaken.

Biased.

Corrupt.

Manipulated.

Uninformed.

Reliability should influence belief formation.

---

# 9.13 Information Mutation

Information changes during transmission.

Example:

Original:

Bandits attacked a caravan.

First retelling:

Twenty bandits attacked.

Second retelling:

Fifty bandits attacked.

Third retelling:

A legendary outlaw army attacked.

Mutation creates realistic rumours.

---

# 9.14 Information Decay

Information weakens over time.

Details fade.

Witnesses forget.

Records are lost.

Context disappears.

Truth remains.

Awareness declines.

---

# 9.15 Information Scarcity

Rare information gains value.

Examples:

Secret routes.

Military plans.

Hidden resources.

Political scandals.

Ancient knowledge.

Scarcity creates demand.

Demand creates behaviour.

---

# 9.16 Information Abundance

Too much information creates problems.

Examples:

Noise.

Confusion.

Contradictions.

Misinformation.

Overload.

Information abundance is not always beneficial.

---

# 9.17 Secrets

A secret is information with restricted ownership.

Secrets create pressure.

Pressure creates behaviour.

Examples:

Hidden identities.

Political corruption.

Affairs.

Criminal activity.

Forbidden knowledge.

Secrets generate emergent stories.

---

# 9.18 Witness Systems

Witnesses are critical information carriers.

Witnesses create:

Evidence.

Rumours.

Investigations.

Reputation changes.

Consequences.

Without witnesses, information flow becomes unrealistic.

---

# 9.19 Reputation Systems

Reputation is information at population scale.

People do not know you directly.

They know information about you.

Reputation emerges from:

Actions.

Witnesses.

Rumours.

Records.

History.

Reputation is informational pressure.

---

# 9.20 Intelligence Systems

Intelligence is organised information gathering.

Examples:

Spies.

Scouts.

Investigators.

Informants.

Surveillance.

Intelligence increases awareness.

Awareness improves decision-making.

---

# 9.21 Information As Power

Information often creates greater influence than wealth.

Knowing something valuable creates leverage.

Examples:

Blackmail.

Trade secrets.

Political intelligence.

Military intelligence.

Knowledge changes behaviour.

---

# 9.22 Information As Currency

Information can be exchanged.

Sold.

Bartered.

Traded.

Protected.

Stolen.

Information possesses economic value.

---

# 9.23 Discovery

Discovery occurs when information changes ownership.

Discovery is one of the most powerful forms of player reward.

The player should frequently discover information.

Not receive exposition.

Discovery creates investment.

---

# 9.24 Investigation

Investigation is the process of tracing information.

Investigations move backward through causality.

Event.

↓

Evidence.

↓

Witnesses.

↓

Leads.

↓

Origin.

Investigation should reveal reality.

Not generate reality.

---

# 9.25 Misinformation

False information should emerge naturally.

Examples:

Mistaken witnesses.

Rumours.

Propaganda.

Assumptions.

Bias.

Misinformation creates complexity.

Complexity creates realism.

---

# 9.26 Propaganda

Propaganda is intentional information manipulation.

Factions may spread information strategically.

Governments may control narratives.

Groups may distort truth.

Information warfare should be possible.

---

# 9.27 Information Pressure

Information creates pressure.

Examples:

Scandal.

Exposure.

Secrets.

Rumours.

Political revelations.

Knowledge frequently changes behaviour without changing physical reality.

---

# 9.28 Information Networks

Communities form information networks.

Examples:

Trade routes.

Religious institutions.

Criminal organisations.

Political systems.

Media systems.

Network structure affects information flow.

---

# 9.29 The Omniscience Failure

One of the most dangerous simulation failures is omniscience.

Symptoms:

Everyone knows everything.

Information spreads instantly.

Secrets cannot exist.

Distance becomes irrelevant.

History becomes universally known.

This destroys realism.

The simulation must actively prevent omniscience.

---

# 9.30 The Discovery Doctrine

Players should rarely receive information simply because they exist.

Knowledge should require:

Observation.

Investigation.

Inference.

Relationships.

Travel.

Risk.

Discovery feels earned.

Exposition feels delivered.

The simulation should favour discovery.

---

# 9.31 Information Ecology

Information behaves similarly to biological systems.

It spreads.

Competes.

Mutates.

Dies.

Survives.

Dominates.

Information is alive.

Treating it as alive produces believable worlds.

---

# 9.32 Information And History

History is stored information.

Without information:

History disappears.

Without history:

Identity disappears.

Without identity:

Worlds become generic.

Information preserves continuity.

---

# 9.33 The Dead Information Test

Ask:

Who knows?

How do they know?

How did they learn it?

How quickly does it spread?

Can it be forgotten?

Can it be wrong?

If these questions cannot be answered:

The information system is incomplete.

---

# 9.34 Final Doctrine

Information is not narration.

Information is not exposition.

Information is a resource.

Information exists.

Information travels.

Information changes.

Information creates power.

Information creates pressure.

Information creates opportunity.

The player should not automatically know reality.

The player should discover reality.

A living world is not defined by what is true.

A living world is defined by who knows the truth.

END OF CHAPTER 9

CANONICAL VERSION

# CHAPTER 10

# NPC ARCHITECTURE

## Status

Canonical

This chapter defines the fundamental structure of all non-player characters within the Dice Reaction Story Engine.

This is one of the most important chapters in the entire Bible.

Most games treat NPCs as content.

Most games treat NPCs as dialogue machines.

Most games treat NPCs as quest dispensers.

Dice Reaction rejects this model entirely.

NPCs are not content.

NPCs are simulation actors.

NPCs exist independently of the player.

NPCs possess goals.

NPCs possess fears.

NPCs possess needs.

NPCs possess memory.

NPCs possess relationships.

NPCs possess pressure.

NPCs possess agency.

The player interacts with NPCs.

The simulation lives through NPCs.

This chapter governs:

* Character simulation
* Decision making
* Memory ownership
* Behaviour generation
* Relationships
* Stress systems
* Goal pursuit
* Social interaction
* Character persistence
* Character evolution

Every future human simulation system depends upon this chapter.

---

# 10.1 Core Doctrine

NPCs are not scripted.

NPCs are not authored outcomes.

NPCs are persistent actors pursuing objectives within a living world.

The simulation should never ask:

"What dialogue should this NPC say?"

The simulation should ask:

"What would this NPC do?"

Dialogue emerges afterward.

Behaviour comes first.

Always.

---

# 10.2 Definition

An NPC is a persistent simulation entity capable of:

Perception.

Memory.

Decision making.

Goal pursuit.

Relationship formation.

Pressure response.

Adaptation.

Change.

An NPC is not defined by dialogue.

An NPC is defined by behaviour.

---

# 10.3 The Actor Principle

Every NPC is an actor.

Not an object.

Actors create change.

Objects receive change.

NPCs should actively influence the world.

Not merely react to the player.

---

# 10.4 Independent Existence

NPCs continue existing when unobserved.

They work.

Travel.

Trade.

Sleep.

Fight.

Plan.

Recover.

Age.

Learn.

Fail.

The player does not create their existence.

The player merely encounters it.

---

# 10.5 The Persistence Rule

An NPC should remain the same person across time.

Not identical.

Consistent.

Consistency creates trust.

Trust creates immersion.

Immersion creates attachment.

Without persistence:

Characters become random generators.

---

# 10.6 The Identity Layer

Every NPC possesses identity.

Identity answers:

Who is this person?

Identity includes:

Name.

Background.

Role.

Culture.

History.

Values.

Environment.

Identity is the foundation of behaviour.

---

# 10.7 The Core Architecture

Every NPC contains seven foundational anchors.

These anchors form the minimum viable person.

---

## Drive

What they want.

---

## Fear

What they avoid.

---

## Objective

What they are currently trying to achieve.

---

## Stress

Current pressure load.

---

## Relationships

Who matters.

---

## Memory

What they remember.

---

## Breaking Point

What causes major behavioural change.

---

These seven anchors create consistency.

---

# 10.8 Drive

Drive is the primary motivational force.

Examples:

Wealth.

Power.

Safety.

Family.

Recognition.

Knowledge.

Faith.

Survival.

Revenge.

Freedom.

Most people possess multiple drives.

One usually dominates.

---

# 10.9 Fear

Fear constrains behaviour.

Examples:

Failure.

Humiliation.

Poverty.

Death.

Loneliness.

Authority.

Conflict.

Exposure.

Fear often explains behaviour better than desire.

---

# 10.10 Objective

Objectives are immediate goals.

Examples:

Pay debt.

Find missing child.

Protect business.

Secure promotion.

Win election.

Objectives change frequently.

Drive changes slowly.

---

# 10.11 Stress

Stress measures active pressure.

Stress accumulates.

Stress influences decisions.

Stress alters priorities.

Stress reduces flexibility.

Stress creates realism.

A person under pressure behaves differently.

---

# 10.12 Relationships

Humans are social creatures.

Relationships influence:

Decisions.

Trust.

Loyalty.

Conflict.

Cooperation.

Sacrifice.

Relationships often override logic.

The simulation should reflect this.

---

# 10.13 Memory

Memory provides continuity.

Without memory:

No learning.

No growth.

No attachment.

No history.

Memory transforms events into experience.

---

# 10.14 Breaking Point

Every person possesses limits.

Breaking points represent behavioural thresholds.

Examples:

Violence.

Withdrawal.

Betrayal.

Flight.

Collapse.

Desperation.

Breaking points create dramatic but believable change.

---

# 10.15 Human Complexity

People are contradictory.

NPCs should be contradictory.

Examples:

Brave but insecure.

Kind but selfish.

Loyal but jealous.

Honest but fearful.

Ambitious but compassionate.

Contradiction creates realism.

---

# 10.16 Personality Versus Behaviour

Personality influences behaviour.

It does not determine behaviour.

A generous person may steal when starving.

A coward may become heroic when cornered.

Pressure matters.

Context matters.

Reality matters.

---

# 10.17 Behaviour Generation

Behaviour should emerge from:

Drive.

Fear.

Pressure.

Relationships.

Memory.

Current context.

The simulation should avoid random actions.

Every meaningful action requires explanation.

---

# 10.18 The Consistency Principle

An NPC should feel like the same person over time.

Not because they repeat dialogue.

Because their decisions remain understandable.

Consistency is measured through causality.

Not repetition.

---

# 10.19 Internal Conflict

Humans frequently possess competing motivations.

Example:

A guard wants promotion.

A guard loves their family.

A bribe appears.

Internal conflict emerges.

Conflict creates realism.

---

# 10.20 Social Masks

People present different versions of themselves.

Public behaviour.

Private behaviour.

Professional behaviour.

Intimate behaviour.

Fearful behaviour.

Angry behaviour.

NPCs should not reveal their entire identity immediately.

---

# 10.21 Knowledge Boundaries

NPCs know only what they know.

Knowledge must be earned.

Knowledge must be acquired.

Knowledge must be transmitted.

NPCs are not omniscient.

This rule is mandatory.

---

# 10.22 Decision Architecture

Decision making follows:

```text
Perception
↓
Interpretation
↓
Pressure Evaluation
↓
Goal Evaluation
↓
Action Selection
↓
Consequence
```

NPCs act based on perception.

Not objective reality.

This distinction matters.

---

# 10.23 Rationality

NPCs should be rational from their perspective.

Not necessarily from an objective perspective.

People make mistakes.

People possess bias.

People act emotionally.

All of these remain rational within context.

---

# 10.24 Emotional State

Emotion influences decisions.

Examples:

Fear.

Anger.

Hope.

Grief.

Excitement.

Shame.

Jealousy.

Emotion should affect behaviour.

Not replace logic.

---

# 10.25 Adaptation

NPCs should learn.

Repeated experiences should alter future behaviour.

Examples:

Being betrayed.

Experiencing war.

Losing family.

Gaining wealth.

Experiences create change.

Change creates growth.

---

# 10.26 Competence

NPCs possess varying competence.

Competence affects:

Decision quality.

Execution quality.

Problem solving.

Risk assessment.

Leadership.

Not everyone performs equally.

---

# 10.27 Agency

Agency measures ability to influence reality.

A king possesses high agency.

A prisoner possesses low agency.

Agency affects possible actions.

Not value as a character.

---

# 10.28 Character Evolution

NPCs are not static.

They should evolve.

Examples:

Merchant becomes politician.

Soldier becomes pacifist.

Farmer becomes revolutionary.

Priest becomes heretic.

People change.

The simulation should support transformation.

---

# 10.29 Character Death

NPCs may die.

Death is real.

Death is permanent unless setting rules dictate otherwise.

The simulation must not protect characters simply because they are important.

Importance increases consequence.

Not immunity.

---

# 10.30 Legacy

Important NPCs should leave traces.

Examples:

Students.

Children.

Institutions.

Ideas.

Policies.

Enemies.

Allies.

Death ends a person.

Not necessarily their influence.

---

# 10.31 The Quest Dispenser Failure

One of the greatest threats to NPC realism is reducing people to functions.

Examples:

Shopkeeper.

Quest giver.

Guard.

Healer.

These are roles.

Not identities.

Roles should emerge from people.

People should not emerge from roles.

---

# 10.32 Human Texture

Not every interaction should serve a purpose.

People joke.

Complain.

Daydream.

Gossip.

Celebrate.

Mourn.

Waste time.

Small behaviours create realism.

---

# 10.33 The Dead NPC Test

Ask:

What do they want?

What do they fear?

What are they doing right now?

Who matters to them?

What pressures affect them?

What would they do if the player vanished?

If these questions cannot be answered:

The NPC is incomplete.

---

# 10.34 Final Doctrine

NPCs are not dialogue generators.

NPCs are not quest dispensers.

NPCs are persistent actors operating within a living world.

They possess drives.

They possess fears.

They possess memories.

They possess relationships.

They possess agency.

The player experiences the world through interaction.

NPCs create the world through action.

A believable world is ultimately a collection of believable people.

END OF CHAPTER 10

CANONICAL VERSION

# CHAPTER 11

# GOAL SYSTEMS

## Status

Canonical

This chapter defines how actors decide what they are trying to achieve.

If Chapter 10 defines what an NPC is, Chapter 11 defines what drives an NPC forward through time.

Goals are the engine of behaviour.

Pressure creates motivation.

Goals convert motivation into action.

Without goals:

NPCs become reactive.

Settlements become static.

Factions become decorative.

The world stops moving.

This chapter governs:

* NPC objectives
* Goal generation
* Goal prioritisation
* Goal conflict
* Goal adaptation
* Goal failure
* Goal succession
* Long-term ambition
* World motion

Every actor within the simulation must operate through goals.

---

# 11.1 Core Doctrine

Actors do not exist to perform actions.

Actors exist to pursue goals.

Actions are merely tools.

The simulation should never ask:

"What should this character do?"

The simulation should ask:

"What is this character trying to accomplish?"

Behaviour emerges afterward.

---

# 11.2 Goal Hierarchy

All actors possess goals at multiple levels.

These levels operate simultaneously.

```text
Core Drive
↓
Life Goal
↓
Strategic Goal
↓
Operational Goal
↓
Immediate Action
```

This hierarchy creates consistency.

---

# 11.3 Core Drives

Core drives change rarely.

Examples:

Survival.

Freedom.

Power.

Knowledge.

Belonging.

Faith.

Security.

Legacy.

These drives influence the entire life trajectory of a character.

---

# 11.4 Life Goals

Life goals are major ambitions.

Examples:

Become wealthy.

Build a family.

Gain political power.

Protect a kingdom.

Discover forbidden knowledge.

Avenge a loved one.

Life goals may last years.

---

# 11.5 Strategic Goals

Strategic goals support life goals.

Example:

Life Goal:

Become wealthy.

Strategic Goals:

Acquire trade routes.

Expand business.

Eliminate competition.

Increase production.

Strategic goals create direction.

---

# 11.6 Operational Goals

Operational goals are short-term projects.

Examples:

Meet supplier.

Collect debt.

Recruit workers.

Investigate theft.

Repair bridge.

Operational goals create movement.

---

# 11.7 Immediate Actions

Actions are the smallest unit.

Examples:

Travel.

Speak.

Trade.

Fight.

Hide.

Negotiate.

Actions serve goals.

Goals do not serve actions.

---

# 11.8 Goal Ownership

Every goal must belong to an actor.

Ownership provides accountability.

Examples:

Person.

Family.

Organisation.

Settlement.

Faction.

Government.

No goal should exist without ownership.

---

# 11.9 Goal Creation

Goals emerge from pressure.

Pressure is the origin of goals.

Examples:

Debt.

↓

Goal: Earn money.

Starvation.

↓

Goal: Secure food.

Political instability.

↓

Goal: Gain control.

Pressure always comes first.

---

# 11.10 Goal Persistence

Goals should persist until:

Achieved.

Abandoned.

Replaced.

Rendered impossible.

Goals do not disappear randomly.

Persistence creates realism.

---

# 11.11 Goal Priority

Not all goals matter equally.

Priority determines attention.

Higher priority goals consume more resources.

Higher priority goals influence more decisions.

Priority emerges from pressure.

---

# 11.12 Goal Conflict

Actors frequently possess competing goals.

Example:

Protect family.

↓

Keep dangerous job.

Conflict emerges.

Goal conflict creates realism.

Most interesting behaviour emerges from competing priorities.

---

# 11.13 Internal Goal Conflict

Examples:

Safety versus ambition.

Loyalty versus profit.

Love versus duty.

Faith versus survival.

Internal conflict creates human complexity.

---

# 11.14 External Goal Conflict

Multiple actors frequently pursue incompatible goals.

Examples:

Two merchants competing.

Two factions claiming territory.

Two politicians seeking office.

Conflict generates emergent events.

---

# 11.15 Goal Feasibility

Actors should recognise impossible goals.

A starving peasant may dream of ruling a kingdom.

The simulation should distinguish between:

Desire.

And realistic pursuit.

Feasibility affects behaviour.

---

# 11.16 Goal Adaptation

Goals evolve.

New information changes priorities.

Examples:

Merchant discovers opportunity.

Soldier loses commander.

Kingdom enters war.

Disease outbreak occurs.

Actors adapt.

Adaptation creates realism.

---

# 11.17 Goal Failure

Failure should matter.

Failed goals create pressure.

Pressure creates new goals.

Example:

Business fails.

↓

Debt grows.

↓

Need employment.

↓

Accept risky opportunity.

Failure creates narrative momentum.

---

# 11.18 Goal Success

Success changes reality.

Examples:

Debt repaid.

Promotion earned.

Settlement defended.

Election won.

Success resolves pressure.

Success often creates new pressure.

---

# 11.19 Goal Cascades

Goals frequently generate additional goals.

Example:

Build mine.

↓

Recruit workers.

↓

Construct housing.

↓

Secure supplies.

↓

Protect trade routes.

One goal creates a network of goals.

---

# 11.20 Hidden Goals

Not all goals are visible.

Examples:

Secret agendas.

Political schemes.

Personal obsessions.

Covert operations.

Hidden goals create mystery.

---

# 11.21 Revealed Goals

Goal discovery should be rewarding.

Players learn about people through goals.

Goals reveal:

Values.

Fears.

Priorities.

Character.

Goals often reveal more than dialogue.

---

# 11.22 Group Goals

Groups possess goals too.

Examples:

Families.

Businesses.

Religions.

Guilds.

Governments.

Factions.

Group goals influence members.

---

# 11.23 Settlement Goals

Settlements pursue goals.

Examples:

Growth.

Security.

Trade.

Expansion.

Recovery.

Survival.

Settlements are actors.

Therefore settlements require goals.

---

# 11.24 Faction Goals

Factions exist largely because of goals.

Examples:

Power.

Control.

Influence.

Profit.

Faith.

Territory.

Without goals, factions become scenery.

---

# 11.25 Goal Networks

Goals influence other goals.

Example:

Food security.

↓

Agricultural expansion.

↓

Land disputes.

↓

Political tension.

↓

Military involvement.

Networks create complexity.

---

# 11.26 Goal Inertia

Large goals possess inertia.

Major ambitions rarely disappear overnight.

A kingdom preparing for war does not instantly abandon preparations.

Goal inertia creates realism.

---

# 11.27 Goal Momentum

Progress encourages persistence.

Repeated success strengthens commitment.

Repeated failure weakens commitment.

Momentum influences decision making.

---

# 11.28 Goal Replacement

When goals disappear, replacements emerge.

Humans rarely exist without objectives.

The simulation should continuously generate new goals.

A world without goals loses motion.

---

# 11.29 Goal Ecology

Goals compete.

Cooperate.

Merge.

Split.

Cascade.

Conflict.

The entire world can be viewed as interacting goal systems.

Goals create behaviour.

Behaviour creates history.

---

# 11.30 Goal Transparency

The simulation knows goals.

Actors may not fully understand their own goals.

Players rarely know all goals.

This asymmetry creates depth.

---

# 11.31 The Living World Test

Remove the player.

Run simulation.

Observe.

Do actors still pursue objectives?

Do plans advance?

Do conflicts emerge?

Do priorities change?

If yes:

Goal systems are functioning.

If no:

The world is dead.

---

# 11.32 The Quest Replacement Doctrine

Traditional RPGs use quests.

Dice Reaction uses goals.

Quests are authored.

Goals are simulated.

A player should encounter goals already in motion.

Not receive tasks generated for their convenience.

This distinction is fundamental.

---

# 11.33 Final Doctrine

Pressure creates goals.

Goals create behaviour.

Behaviour creates consequences.

Consequences create history.

Every actor in the world should be pursuing something.

Every settlement should be pursuing something.

Every faction should be pursuing something.

Motion emerges from goals.

A world without goals is a world without direction.

A world without direction cannot truly live.

END OF CHAPTER 11

CANONICAL VERSION

# CHAPTER 12

# MEMORY SYSTEMS

## Status

Canonical

This chapter defines how the Dice Reaction Story Engine remembers.

Memory is one of the most critical systems in the entire project.

Without memory:

There is no continuity.

Without continuity:

There is no history.

Without history:

There is no living world.

The purpose of memory is not information storage.

The purpose of memory is behavioural continuity.

Memory exists so the world can learn from its past.

This chapter governs:

* NPC memory
* Relationship memory
* Settlement memory
* Faction memory
* Historical memory
* Emotional memory
* Memory decay
* Memory compression
* Memory persistence
* Memory retrieval

Every future system involving continuity must conform to this chapter.

---

# 12.1 Core Doctrine

Memory exists to influence future behaviour.

If a remembered event never changes behaviour:

The memory has little simulation value.

The simulation should not ask:

"What happened?"

The simulation should ask:

"What does this actor remember, and how does it affect what they do next?"

---

# 12.2 Memory Is Not History

History and memory are separate systems.

History records truth.

Memory records experience.

Example:

A war occurred.

History:

The war happened.

Memory:

Each participant remembers different parts.

Both systems matter.

Both must exist independently.

---

# 12.3 The Memory Rule

Actors remember experiences.

Not transcripts.

Bad memory:

```text
Player said:
"Hello."
```

Good memory:

```text
Player warned me about the ambush.
```

Memory should capture significance.

Not conversation logs.

---

# 12.4 Memory Ownership

Every memory belongs to someone.

Examples:

Individual.

Family.

Faction.

Settlement.

Organisation.

Ownership determines access.

No memory exists without an owner.

---

# 12.5 Memory Formation

Not every event becomes memory.

Events must pass significance thresholds.

Factors:

Emotion.

Novelty.

Risk.

Reward.

Shock.

Loss.

Victory.

Repeated exposure.

Significance creates memory.

---

# 12.6 Memory Weight

Every memory possesses weight.

Weight determines persistence.

Weight determines influence.

Weight determines retrieval priority.

---

Memory categories:

Minor.

Moderate.

Major.

Defining.

---

# 12.7 Minor Memories

Short-lived.

Low impact.

Examples:

Brief conversations.

Routine transactions.

Minor observations.

Most memories belong here.

Most eventually disappear.

---

# 12.8 Moderate Memories

Influence behaviour.

Remain relevant.

Examples:

Helpful stranger.

Successful trade.

Public embarrassment.

Unexpected kindness.

Moderate memories shape relationships.

---

# 12.9 Major Memories

Long-term influence.

Examples:

Betrayal.

Promotion.

Serious injury.

Marriage.

Loss of property.

Major memories strongly affect future behaviour.

---

# 12.10 Defining Memories

Identity-level experiences.

Examples:

War trauma.

Loss of a child.

Religious revelation.

Life-saving intervention.

Revolutionary success.

Defining memories may persist indefinitely.

---

# 12.11 Emotional Memory

Emotion increases retention.

Examples:

Fear.

Joy.

Shame.

Grief.

Love.

Hatred.

Emotion acts as memory reinforcement.

The stronger the emotion, the stronger the retention.

---

# 12.12 Repetition Reinforcement

Repeated experiences strengthen memory.

Example:

One insult.

Minor memory.

One hundred insults.

Strong emotional memory.

Patterns matter more than isolated incidents.

---

# 12.13 Memory Compression

Reality generates more information than can be stored indefinitely.

Compression is mandatory.

Compression reduces detail.

Compression does not remove truth.

---

Example:

Detailed:

```text
Merchant sold apples every morning for six months.
```

Compressed:

```text
Merchant operated a successful produce business.
```

Truth remains.

Cost decreases.

---

# 12.14 Memory Layers

Memories exist in layers.

---

## Active

Currently influencing behaviour.

---

## Relevant

Not active.

Still important.

---

## Dormant

Rarely referenced.

Potentially recoverable.

---

## Archived

Historical.

No active processing.

Still true.

---

This structure mirrors Relevance Decay throughout the simulation.

---

# 12.15 Retrieval

Remembering is not constant.

Actors retrieve memories when triggered.

Triggers include:

Locations.

People.

Objects.

Events.

Pressure.

Emotion.

Context determines retrieval.

---

# 12.16 Memory Triggers

Examples:

Seeing an old enemy.

Returning to a battlefield.

Visiting childhood home.

Hearing familiar music.

Finding a family heirloom.

Triggers increase realism.

---

# 12.17 Memory Accuracy

Memory is not perfect.

People misremember.

Forget details.

Confuse events.

Merge experiences.

The simulation should allow imperfect memory.

Not random memory.

Imperfect memory.

---

# 12.18 Memory Distortion

Over time:

Details fade.

Interpretations change.

Emotion alters recollection.

Distortion affects belief.

Not objective history.

---

# 12.19 Memory Decay

Some memories weaken naturally.

**Authority:** Memory decay is governed exclusively by the Gravity Governance Layer (Chapter 26). This chapter defines what memory decay *means* for an NPC; Chapter 26 defines *when* it happens, via the unified retention score. No independent decay formula exists in this chapter.

The factors below are inputs to that retention score, expressed in memory terms:

Importance – maps to the gravity of the originating event.

Emotion – maps to emotional weight, which feeds gravity intensity (20.9).

Repetition – maps to connectivity (repeated similar events form pattern memories, 12.13, raising connectivity).

Recency – maps to the age term in the retention formula (26.3).

Personality – applied as a per-NPC modifier on retrieval probability (Chapter 28), not on retention itself.

Not all memories decay equally – because not all events carry equal gravity.

---

# 12.20 Memory Persistence

Some memories should effectively never disappear.

Examples:

Trauma.

Great achievements.

Major betrayals.

Life-changing events.

Persistence is determined by weight.

---

# 12.21 Relationship Memory

Relationships are collections of memories.

Trust.

Hatred.

Affection.

Suspicion.

Loyalty.

These emerge from accumulated experiences.

Not arbitrary values.

---

# 12.22 Trust Formation

Trust emerges from memory.

Repeated positive experiences:

Trust increases.

Repeated negative experiences:

Trust decreases.

Trust should be earned.

Not assigned.

---

# 12.23 Grudges

Negative memories can persist.

Examples:

Theft.

Betrayal.

Humiliation.

Violence.

Grudges create long-term consequences.

---

# 12.24 Forgiveness

Forgiveness is not forgetting.

Forgiveness changes behavioural response.

The memory remains.

The meaning changes.

---

# 12.25 Family Memory

Families possess collective memory.

Examples:

Traditions.

Stories.

Historical grievances.

Shared pride.

Family memory influences future generations.

---

# 12.26 Settlement Memory

Settlements remember collectively.

Examples:

Wars.

Heroes.

Disasters.

Founders.

Betrayals.

Collective memory influences culture.

---

# 12.27 Faction Memory

Factions accumulate memory.

Examples:

Past wars.

Broken treaties.

Victories.

Humiliations.

Leadership changes.

Faction memory shapes policy.

---

# 12.28 Historical Memory

Not all memories belong to individuals.

Some belong to civilisation.

Examples:

Ancient wars.

Founding myths.

Religious events.

National disasters.

Historical memory creates identity.

---

# 12.29 Generational Transfer

Some memories survive beyond original participants.

Examples:

Oral traditions.

Education.

Records.

Legends.

Institutions.

This creates continuity across centuries.

---

# 12.30 Memory And Identity

Identity emerges from memory.

Without memory:

No continuity.

No growth.

No self.

Characters become random behaviour generators.

Memory creates personhood.

---

# 12.31 Memory And Pressure

Pressure affects memory.

High stress:

Strengthens some memories.

Weakens others.

Pressure influences recall.

Pressure influences interpretation.

---

# 12.32 Memory And Decision Making

Actors do not decide based solely on reality.

Actors decide based on remembered reality.

This distinction is critical.

Behaviour emerges from perceived experience.

Not objective truth.

---

# 12.33 Institutional Memory

Organisations remember.

Examples:

Governments.

Guilds.

Corporations.

Military units.

Religions.

Institutional memory often outlives individuals.

---

# 12.34 Memory Inheritance

Successors inherit information.

New leaders inherit records.

Children inherit stories.

Students inherit teachings.

Inheritance preserves continuity.

---

# 12.35 Memory Networks

Memories interact.

A betrayal influences trust.

Trust influences decisions.

Decisions create new memories.

Memory systems form networks.

Not isolated records.

---

# 12.36 Memory Cost Doctrine

Infinite memory is impossible.

Infinite forgetting is unacceptable.

Compression exists to balance:

Persistence.

Performance.

Believability.

This is one of the core architectural principles of the engine.

---

# 12.37 The Memory Integrity Rule

Compression may reduce detail.

Compression may reduce frequency.

Compression may never alter truth.

Truth remains sacred.

---

# 12.38 The Dead Memory Test

Ask:

What does this actor remember?

Why do they remember it?

How does it affect behaviour?

Can it fade?

Can it strengthen?

Can it be triggered?

If these questions cannot be answered:

The memory system is incomplete.

---

# 12.39 The Living World Test

Remove the player.

Advance time.

Do memories form?

Do memories fade?

Do relationships evolve?

Do grudges persist?

Do institutions remember?

If yes:

The memory system is functioning.

---

# 12.40 Final Doctrine

Memory is not storage.

Memory is continuity.

Memory transforms events into experience.

Experience shapes behaviour.

Behaviour shapes history.

History shapes the world.

A living world is not defined by what happened.

A living world is defined by what is remembered.

END OF CHAPTER 12

CANONICAL VERSION

# CHAPTER 13

# RELATIONSHIP SYSTEMS

## Status

Canonical

This chapter defines how relationships form, evolve, strengthen, weaken, fracture, and persist within the Dice Reaction Story Engine.

Relationships are among the most powerful forces in human behaviour.

People rarely act in isolation.

People act because of people.

Relationships influence:

* Trust
* Loyalty
* Cooperation
* Conflict
* Sacrifice
* Betrayal
* Leadership
* Family structure
* Group cohesion
* Social stability

A living world cannot exist without living relationships.

This chapter governs:

* Interpersonal relationships
* Family bonds
* Friendships
* Rivalries
* Loyalty
* Trust
* Betrayal
* Social attachment
* Group cohesion
* Relationship evolution

Every future social system depends upon this chapter.

---

# 13.1 Core Doctrine

Relationships are not numbers.

Relationships are histories.

A relationship is the accumulated result of shared experiences.

The simulation should never ask:

"What is this relationship value?"

The simulation should ask:

"What has happened between these people?"

The relationship emerges from the answer.

**Reconciliation with Chapter 29:** This doctrine is philosophical, not an implementation prohibition. Chapter 29 (Relationship Calculus) stores a four-dimension vector (trust, loyalty, fear, resentment) per relationship. That vector is not an "arbitrary value" – it is the **running projection of the relationship's history**, mutated only by events, exactly as state is the running projection of the event log (Chapter 22). The history remains the source; the vector is its computed summary. Asking "what is the trust value" is therefore asking "what has the history accumulated to" – which is this doctrine, made executable.

---

# 13.2 Definition

A relationship is a persistent connection between actors that influences behaviour.

Relationships may exist between:

Individuals.

Families.

Settlements.

Factions.

Institutions.

Groups.

The same principles apply at every scale.

---

# 13.3 Relationship Foundations

Relationships are built from:

Memory.

Trust.

Dependency.

History.

Emotion.

Pressure.

Shared experiences.

Without these foundations, relationships become artificial.

---

# 13.4 Relationship Formation

Relationships begin through interaction.

Examples:

Trade.

Conversation.

Cooperation.

Conflict.

Shared danger.

Shared success.

Repeated interaction increases relationship significance.

---

# 13.5 The Repetition Principle

One event rarely creates a strong relationship.

Repeated experiences create attachment.

Repeated cooperation builds trust.

Repeated conflict builds hostility.

Patterns matter more than isolated incidents.

---

# 13.6 Relationship Ownership

Every relationship belongs to both participants.

However:

Each participant experiences the relationship differently.

Relationships are rarely symmetrical.

---

Example:

Person A trusts Person B.

Person B distrusts Person A.

Both views are valid.

Reality often works this way.

---

# 13.7 Relationship Layers

Relationships exist in layers.

---

## Familiarity

Recognition.

Knowledge of existence.

Minimal interaction.

---

## Association

Regular interaction.

Limited emotional significance.

---

## Connection

Meaningful social value.

Recognisable history.

---

## Attachment

Emotional investment.

Behavioural influence.

---

## Bond

High significance.

Strong influence over decisions.

---

## Identity-Level Relationship

Part of self-definition.

Family.

Lifelong friendships.

Deep rivalries.

Mentorship.

Partnership.

These relationships can reshape identity.

---

# 13.8 Trust

Trust is one of the most important relationship outputs.

Trust emerges from evidence.

Trust is not assigned.

Trust is earned.

Examples:

Reliability.

Honesty.

Protection.

Competence.

Consistency.

Trust influences risk tolerance.

---

# 13.9 Distrust

Distrust emerges similarly.

Examples:

Broken promises.

Manipulation.

Deception.

Incompetence.

Abandonment.

Distrust influences future cooperation.

---

# 13.10 Loyalty

Loyalty is not trust.

A person may trust someone without being loyal.

A person may remain loyal despite low trust.

Loyalty emerges from:

History.

Identity.

Duty.

Family.

Shared hardship.

Belief.

Loyalty often survives logic.

---

# 13.11 Respect

Respect differs from affection.

People can respect enemies.

People can dislike allies.

Respect often emerges from:

Competence.

Courage.

Consistency.

Achievement.

Respect influences behaviour independently of emotion.

---

# 13.12 Affection

Affection emerges from positive emotional experiences.

Examples:

Friendship.

Love.

Admiration.

Comfort.

Affection influences decision making.

Affection increases willingness to sacrifice.

---

# 13.13 Dependency

Dependency forms when one actor relies on another.

Examples:

Economic support.

Protection.

Guidance.

Emotional support.

Knowledge.

Dependency creates vulnerability.

Dependency creates pressure.

---

# 13.14 Resentment

Dependency often generates resentment.

Especially when:

Needs remain unmet.

Power imbalances grow.

Sacrifices feel unequal.

Resentment is a powerful long-term relationship force.

---

# 13.15 Rivalry

Not all strong relationships are positive.

Rivalries can become identity-defining.

Examples:

Political opponents.

Competing merchants.

Military leaders.

Sibling competition.

Rivalry generates motion.

---

# 13.16 Hatred

Hatred emerges from accumulated negative experiences.

Hatred rarely appears instantly.

Hatred usually forms through:

Loss.

Humiliation.

Fear.

Betrayal.

Repeated harm.

Hatred influences long-term behaviour.

---

# 13.17 Betrayal

Betrayal is one of the most powerful relationship events.

Betrayal requires:

Trust.

Expectation.

Violation.

Without trust, betrayal is impossible.

The stronger the relationship, the greater the impact.

---

# 13.18 Forgiveness

Forgiveness is behavioural adaptation.

Not memory deletion.

The memory remains.

The relationship changes.

Forgiveness should emerge naturally.

Not automatically.

---

# 13.19 Relationship Momentum

Strong relationships resist rapid change.

A lifelong friendship should not collapse from a minor disagreement.

A lifelong enemy should not become a trusted ally overnight.

Relationship momentum creates realism.

---

# 13.20 Relationship Inertia

The longer a relationship exists:

The more stable it becomes.

Large shifts require major events.

Inertia prevents unrealistic volatility.

---

# 13.21 Relationship Pressure

Pressure affects relationships.

Examples:

Debt.

War.

Jealousy.

Distance.

Competition.

Fear.

Pressure can strengthen bonds.

Pressure can destroy bonds.

Context matters.

---

# 13.22 Shared Adversity

Shared hardship often accelerates relationship growth.

Examples:

War.

Disaster.

Survival situations.

Danger.

Shared adversity creates powerful memories.

Powerful memories strengthen relationships.

---

# 13.23 Shared Success

Success also strengthens bonds.

Examples:

Business growth.

Victory.

Exploration.

Achievement.

People often become attached to those associated with success.

---

# 13.24 Relationship Decay

Relationships require maintenance.

Without interaction:

Some relationships weaken.

Others persist.

Decay depends on:

Importance.

History.

Emotional significance.

Distance.

Identity integration.

---

# 13.25 Relationship Persistence

Identity-level relationships may persist indefinitely.

Examples:

Parents.

Children.

Lifelong partners.

Defining rivals.

Mentors.

These relationships become part of identity.

---

# 13.26 Family Systems

Families represent relationship networks.

Family relationships possess:

History.

Expectation.

Obligation.

Inheritance.

Identity.

Family influence extends beyond individuals.

---

# 13.27 Friendship Systems

Friendships emerge through:

Trust.

Shared experience.

Repeated positive interaction.

Friendships often produce cooperation.

---

# 13.28 Romantic Systems

Romantic relationships are not separate systems.

They are relationship systems with:

High attachment.

High emotional significance.

High behavioural influence.

The same rules apply.

Only intensity changes.

---

# 13.29 Professional Relationships

Many important relationships remain non-emotional.

Examples:

Business partners.

Employers.

Military officers.

Political allies.

Professional relationships influence behaviour significantly.

---

# 13.30 Social Networks

Individuals exist within networks.

Relationships rarely operate in isolation.

Examples:

Family networks.

Trade networks.

Political networks.

Criminal networks.

Religious networks.

Networks influence information flow.

Networks influence opportunities.

---

# 13.31 Reputation And Relationships

Reputation affects relationship formation.

Positive reputation accelerates trust.

Negative reputation creates barriers.

Reputation acts as second-hand relationship information.

---

# 13.32 Relationship Memory

Relationships are built from memory.

Without memory:

Relationships cannot evolve.

Relationship systems depend directly upon Chapter 12.

---

# 13.33 Relationship Transformation

Relationships change.

Friend becomes rival.

Enemy becomes ally.

Student becomes teacher.

Follower becomes leader.

Transformation should emerge through events.

Not arbitrary reassignment.

---

# 13.34 Relationship Collapse

Relationships can fail.

Collapse usually follows:

Accumulated pressure.

Repeated betrayal.

Irreconcilable conflict.

Identity divergence.

Major trauma.

Relationship collapse should feel earned.

---

# 13.35 Relationship Legacy

Relationships can outlive participants.

Examples:

Family traditions.

Political alliances.

Generational feuds.

Inherited obligations.

Relationship history influences future generations.

---

# 13.36 The Living Network Principle

A world is not a collection of people.

A world is a collection of relationships.

Relationships create societies.

Societies create history.

History creates identity.

Identity creates civilisation.

Relationships are the connective tissue of the simulation.

---

# 13.37 The Dead Relationship Test

Ask:

What connects these actors?

Why does the connection exist?

What memories support it?

What pressures affect it?

What would change it?

If these questions cannot be answered:

The relationship is incomplete.

---

# 13.38 Final Doctrine

Relationships are not statistics.

Relationships are histories.

They emerge from memory.

They evolve through experience.

They influence behaviour.

They generate loyalty.

They generate conflict.

They generate sacrifice.

They generate betrayal.

A living world is not defined by individuals alone.

A living world is defined by the connections between them.

END OF CHAPTER 13

CANONICAL VERSION

# CHAPTER 14

# STRESS & BREAKING POINT SYSTEMS

## Status

Canonical

This chapter defines how actors respond to pressure over time.

If Chapter 6 explains how pressure exists within the world, this chapter explains what pressure does to people.

Stress is the bridge between external reality and internal behaviour.

Without stress:

Actors become perfectly rational.

Without stress:

Pressure becomes meaningless.

Without stress:

People stop feeling human.

Stress transforms circumstances into behaviour.

Breaking points transform behaviour into change.

This chapter governs:

* Stress accumulation
* Stress reduction
* Behavioural degradation
* Emotional pressure
* Decision quality
* Breaking points
* Crisis responses
* Recovery
* Burnout
* Psychological adaptation

Every actor within the simulation is affected by stress.

No one is exempt.

---

# 14.1 Core Doctrine

Pressure creates stress.

Stress alters behaviour.

Behaviour creates consequences.

Consequences create history.

Stress is not a status effect.

Stress is a behavioural force.

Its purpose is not to punish.

Its purpose is to make actors react realistically.

---

# 14.2 Definition

Stress represents the accumulated burden of unresolved pressure.

Examples:

Fear.

Responsibility.

Debt.

Conflict.

Danger.

Uncertainty.

Loss.

Isolation.

Trauma.

Stress is not the event.

Stress is the impact of the event.

---

# 14.3 Stress Is Personal

The same event affects different actors differently.

Example:

A merchant loses 10 gold.

Minor inconvenience.

A starving worker loses 10 gold.

Major crisis.

Stress depends on context.

Not objective severity.

---

# 14.4 The Pressure-Stress Relationship

Pressure generates stress.

Not all pressure becomes stress.

Actors possess tolerance.

Example:

```text
Pressure
↓
Interpretation
↓
Tolerance Check
↓
Stress Generation
↓
Behavioural Impact
```

The interpretation stage is critical.

Reality matters.

Perception matters more.

---

# 14.5 Stress Capacity

Every actor possesses stress capacity.

Capacity determines how much pressure can be absorbed before behavioural degradation begins.

Factors include:

Personality.

Experience.

Support networks.

Resources.

Confidence.

Training.

History.

Capacity is not fixed.

It can grow.

It can shrink.

---

# 14.6 Stress Accumulation

Stress accumulates over time.

Small pressures can become major burdens.

Example:

One bad day.

Minor impact.

One hundred bad days.

Major impact.

Accumulation is often more dangerous than catastrophe.

---

# 14.7 Acute Stress

Acute stress results from immediate threats.

Examples:

Combat.

Fire.

Disaster.

Attack.

Acute stress produces rapid behavioural changes.

---

# 14.8 Chronic Stress

Chronic stress results from long-term pressure.

Examples:

Debt.

Caregiving.

Political instability.

Poverty.

Workload.

Chronic stress creates gradual degradation.

---

# 14.9 Stress Thresholds

Stress exists in stages.

---

## Stable

Normal functioning.

---

## Strained

Minor behavioural effects.

---

## Stressed

Noticeable behavioural changes.

---

## Overloaded

Decision quality declines.

---

## Critical

Breaking point risk emerges.

---

## Collapse

Major behavioural disruption.

---

Thresholds are behavioural, not numerical.

---

# 14.10 Stable State

Actors function normally.

Decision quality remains high.

Emotional regulation remains intact.

Goals remain balanced.

This is the baseline.

---

# 14.11 Strained State

Early warning signs emerge.

Examples:

Irritability.

Distraction.

Fatigue.

Reduced patience.

Most actors spend time here.

---

# 14.12 Stressed State

Behaviour becomes visibly affected.

Examples:

Risk avoidance.

Poor concentration.

Conflict sensitivity.

Reduced empathy.

Tunnel vision.

The actor remains functional.

Performance begins degrading.

---

# 14.13 Overloaded State

Priorities narrow.

Complex decisions become difficult.

Actors focus on immediate pressures.

Long-term thinking weakens.

Relationship strain increases.

Goal flexibility decreases.

---

# 14.14 Critical State

Breaking point risk becomes significant.

Behaviour becomes unstable.

Examples:

Aggression.

Withdrawal.

Desperation.

Obsession.

Impulsivity.

Major decisions may occur.

---

# 14.15 Collapse State

The actor can no longer maintain normal behaviour.

Examples:

Emotional breakdown.

Abandonment of responsibilities.

Violence.

Panic.

Flight.

Shutdown.

Collapse is a consequence.

Not a punishment.

---

# 14.16 Breaking Points

Every actor possesses breaking points.

A breaking point is a threshold where behaviour changes fundamentally.

Breaking points are among the most important simulation mechanisms in the engine.

---

# 14.17 Breaking Point Definition

A breaking point occurs when accumulated stress exceeds an actor's ability to cope.

The result is behavioural transformation.

Not necessarily failure.

Transformation.

---

# 14.18 Types Of Breaking Points

Common examples:

Aggression.

Withdrawal.

Submission.

Rebellion.

Escape.

Obsessive control.

Emotional shutdown.

Risk-taking.

Each actor responds differently.

---

# 14.19 Aggressive Breaking Point

Examples:

Violence.

Threats.

Domination attempts.

Escalation.

Aggression often emerges from fear and powerlessness.

---

# 14.20 Withdrawal Breaking Point

Examples:

Isolation.

Avoidance.

Disengagement.

Silence.

Withdrawal protects the actor from further pressure.

---

# 14.21 Rebellion Breaking Point

Examples:

Refusal.

Defiance.

Resistance.

Mutiny.

Rebellion often emerges when control feels impossible.

---

# 14.22 Collapse Breaking Point

Examples:

Panic.

Despair.

Hopelessness.

Burnout.

This form reduces functionality dramatically.

---

# 14.23 Adaptive Breaking Points

Not all breaking points are destructive.

Examples:

Leaving abusive environment.

Changing careers.

Seeking help.

Ending toxic relationship.

Major growth often begins at breaking points.

---

# 14.24 Stress And Decision Making

Stress changes priorities.

High stress favours:

Immediate survival.

Short-term certainty.

Risk avoidance.

Emotional reasoning.

Long-term planning becomes harder.

---

# 14.25 Stress And Relationships

Stress alters social behaviour.

Examples:

Reduced patience.

Increased conflict.

Dependency.

Isolation.

Seeking support.

Relationships both create and relieve stress.

---

# 14.26 Stress And Memory

Stress influences memory.

Examples:

Enhanced recall of threatening events.

Reduced recall of minor details.

Distorted interpretation.

Stress and memory are tightly linked.

---

# 14.27 Stress And Goals

High stress narrows goal selection.

Example:

Normal state:

Five active priorities.

Critical state:

One priority dominates.

Stress simplifies behaviour.

---

# 14.28 Stress And Leadership

Leaders experience amplified stress.

Leadership multiplies responsibility.

Responsibility multiplies pressure.

Pressure affects decision quality.

Leadership should not grant immunity.

---

# 14.29 Stress Transfer

Stress spreads socially.

Examples:

Family tension.

Workplace pressure.

Community fear.

Political instability.

One actor's stress can become another actor's stress.

---

# 14.30 Collective Stress

Groups experience stress.

Examples:

Settlements.

Factions.

Religious communities.

Military units.

Collective stress alters group behaviour.

---

# 14.31 Settlement Stress

Settlement stress emerges from:

Crime.

Famine.

Economic instability.

War.

Disease.

Migration pressure.

High settlement stress increases instability.

---

# 14.32 Faction Stress

Faction stress emerges from:

Leadership conflict.

Resource shortages.

Military defeats.

Political pressure.

Internal divisions.

High faction stress increases fragmentation risk.

---

# 14.33 Burnout

Burnout is prolonged unresolved stress.

Characteristics:

Exhaustion.

Detachment.

Reduced motivation.

Reduced effectiveness.

Burnout should emerge naturally.

Not as a scripted condition.

---

# 14.34 Recovery

Stress can decrease.

Recovery requires:

Time.

Safety.

Support.

Resources.

Success.

Relief of pressure.

Recovery is as important as accumulation.

---

# 14.35 Resilience

Resilience determines recovery efficiency.

Resilience emerges from:

Experience.

Support.

Resources.

Identity.

Purpose.

Resilience is not immunity.

Resilience improves recovery.

---

# 14.36 Trauma

Some stress leaves permanent scars.

Examples:

War.

Abuse.

Disaster.

Loss.

Trauma creates long-term behavioural effects.

Trauma belongs to memory systems as well as stress systems.

---

# 14.37 Stress And Culture

Cultures influence stress responses.

Examples:

Stoicism.

Collectivism.

Individualism.

Religious belief.

Social expectations.

Stress should not appear identical everywhere.

---

# 14.38 The Resilience Loop

Healthy cycle:

Pressure.

Stress.

Adaptation.

Recovery.

Growth.

Unhealthy cycle:

Pressure.

Stress.

Accumulation.

Collapse.

The simulation should support both.

---

# 14.39 The Dead Stress Test

Ask:

What pressures affect this actor?

How much stress do they create?

How does behaviour change?

What is the breaking point?

How does recovery occur?

If these questions cannot be answered:

The stress system is incomplete.

---

# 14.40 Final Doctrine

Pressure creates stress.

Stress alters behaviour.

Behaviour creates consequences.

Consequences create history.

Breaking points are not failures.

Breaking points are transformations.

A living world is not populated by perfectly rational actors.

A living world is populated by people carrying burdens.

The simulation must remember those burdens.

The simulation must allow them to matter.

END OF CHAPTER 14

CANONICAL VERSION


# CHAPTER 15

# SOCIAL STRUCTURES

## Status

Canonical

This chapter defines how people organize themselves into larger systems.

If Chapter 10 defines individuals, Chapter 13 defines relationships, and Chapter 14 defines stress, Chapter 15 defines society.

No person exists alone.

No relationship exists in isolation.

Humans naturally create structures.

These structures influence:

* Behaviour
* Opportunity
* Power
* Information flow
* Resource distribution
* Identity
* Conflict
* Stability

A living world is not merely a collection of individuals.

A living world is a network of social structures.

This chapter governs:

* Families
* Communities
* Classes
* Organisations
* Institutions
* Social hierarchies
* Informal power
* Formal power
* Group identity
* Social cohesion

All future civilisation systems depend upon this chapter.

---

# 15.1 Core Doctrine

People create structures.

Structures create behaviour.

Behaviour reinforces structures.

Structures emerge naturally from repeated human interaction.

The simulation should never ask:

"What social system should exist here?"

The simulation should ask:

"What structures would emerge from these people under these conditions?"

---

# 15.2 Definition

A social structure is a persistent pattern of relationships that influences behaviour.

Examples:

Families.

Guilds.

Governments.

Religions.

Corporations.

Tribes.

Criminal groups.

Neighbourhoods.

Schools.

Military units.

Social structures are larger than individuals.

But ultimately built from individuals.

---

# 15.3 Why Social Structures Exist

Social structures solve problems.

Examples:

Security.

Resource sharing.

Knowledge transfer.

Child raising.

Conflict resolution.

Trade.

Governance.

Every social structure exists because it provides value.

If value disappears:

Pressure for change emerges.

---

# 15.4 Emergence Over Design

Social structures should emerge from conditions.

Examples:

Danger creates tribes.

Trade creates markets.

Wealth creates classes.

Faith creates religious institutions.

Conflict creates militaries.

The simulation should favour emergence.

Not arbitrary creation.

---

# 15.5 The Family Unit

The family is the most fundamental social structure.

Families provide:

Support.

Protection.

Identity.

Inheritance.

Education.

Care.

Family influence often exceeds formal authority.

---

# 15.6 Family Networks

Families form networks.

Marriage.

Kinship.

Lineage.

Inheritance.

These networks influence:

Trade.

Politics.

Conflict.

Power.

Families often become institutions.

---

# 15.7 Communities

Communities emerge from repeated proximity and interaction.

Examples:

Villages.

Neighbourhoods.

Districts.

Cultural enclaves.

Communities create belonging.

Belonging influences behaviour.

---

# 15.8 Social Cohesion

Social cohesion measures collective unity.

High cohesion:

Cooperation.

Trust.

Resilience.

Mutual support.

Low cohesion:

Conflict.

Distrust.

Isolation.

Fragmentation.

Cohesion is a major stability factor.

---

# 15.9 Social Fragmentation

Fragmentation occurs when shared identity weakens.

Examples:

Political division.

Class conflict.

Religious conflict.

Resource competition.

Fragmentation generates pressure.

Pressure generates instability.

---

# 15.10 Social Hierarchies

Most societies create hierarchies.

Hierarchies distribute:

Power.

Influence.

Responsibility.

Resources.

Status.

Hierarchy emergence is natural.

Not necessarily desirable.

But historically common.

---

# 15.11 Formal Authority

Formal authority derives from recognised systems.

Examples:

Kings.

Governments.

Managers.

Military officers.

Judges.

Formal authority possesses legitimacy.

Legitimacy affects effectiveness.

---

# 15.12 Informal Authority

Not all power is official.

Examples:

Respected elders.

Popular leaders.

Criminal bosses.

Influential merchants.

Community organisers.

Informal power often rivals formal power.

---

# 15.13 Status

Status influences social behaviour.

Status emerges from:

Wealth.

Achievement.

Lineage.

Competence.

Influence.

Reputation.

Status affects opportunities.

---

# 15.14 Social Mobility

Societies vary in mobility.

High mobility:

Status changes frequently.

Low mobility:

Status remains fixed.

Mobility affects ambition.

Mobility affects conflict.

Mobility affects culture.

---

# 15.15 Class Structures

Class emerges when resource distribution becomes unequal.

Examples:

Nobility.

Workers.

Merchants.

Peasants.

Executives.

Labourers.

Classes influence behaviour and perspective.

---

# 15.16 Class Pressure

Class differences create pressure.

Examples:

Resentment.

Competition.

Reform.

Rebellion.

Class pressure is a powerful driver of historical change.

---

# 15.17 Institutions

Institutions are long-lived social structures.

Examples:

Governments.

Religions.

Schools.

Guilds.

Corporations.

Military organisations.

Institutions outlive individuals.

---

# 15.18 Institutional Power

Institutions accumulate:

Resources.

Knowledge.

Authority.

Legitimacy.

Influence.

Power often survives leadership changes because institutions persist.

---

# 15.19 Organisational Behaviour

Groups behave differently than individuals.

Examples:

Risk distribution.

Shared responsibility.

Collective identity.

Bureaucracy.

Group behaviour requires separate simulation treatment.

---

# 15.20 Group Identity

Groups develop identities.

Examples:

National identity.

Religious identity.

Guild identity.

Military identity.

Corporate identity.

Identity influences loyalty.

Identity influences conflict.

---

# 15.21 In-Groups And Out-Groups

People naturally distinguish:

Us.

Them.

This tendency influences:

Trust.

Cooperation.

Conflict.

Bias.

Belonging.

The simulation should recognise this reality.

---

# 15.22 Social Norms

Norms are unwritten rules.

Examples:

Etiquette.

Tradition.

Expectations.

Customs.

Norms regulate behaviour.

Often more effectively than laws.

---

# 15.23 Social Enforcement

Societies enforce norms.

Methods include:

Approval.

Disapproval.

Reward.

Punishment.

Exclusion.

Reputation damage.

Enforcement maintains cohesion.

---

# 15.24 Social Roles

Individuals occupy roles.

Examples:

Parent.

Worker.

Leader.

Teacher.

Soldier.

Merchant.

Roles influence expectations.

Roles influence behaviour.

---

# 15.25 Role Conflict

People frequently occupy multiple roles.

Example:

Parent.

Leader.

Business owner.

Friend.

Conflicting roles create difficult decisions.

Role conflict creates realism.

---

# 15.26 Collective Behaviour

Groups often behave differently than members individually.

Examples:

Crowds.

Riots.

Celebrations.

Movements.

Collective behaviour emerges from interaction.

Not central control.

---

# 15.27 Social Movements

Movements emerge from shared pressure.

Examples:

Reform movements.

Religious movements.

Political movements.

Labour movements.

Movements are organised pressure.

---

# 15.28 Leadership

Leadership emerges when individuals influence group behaviour.

Leadership may be:

Earned.

Inherited.

Appointed.

Seized.

Leadership is a relationship system scaled upward.

---

# 15.29 Legitimacy

Authority without legitimacy is unstable.

Legitimacy emerges from:

Tradition.

Performance.

Belief.

Law.

Success.

Legitimacy influences compliance.

---

# 15.30 Corruption

Corruption occurs when structures serve private interests over collective interests.

Corruption is not random evil.

Corruption emerges from incentives.

The simulation should model causes.

Not stereotypes.

---

# 15.31 Social Pressure

Groups create pressure.

Examples:

Expectations.

Obligations.

Traditions.

Reputation concerns.

Conformity demands.

Social pressure shapes behaviour constantly.

---

# 15.32 Trust Networks

Trust rarely spreads evenly.

People trust networks.

Families.

Friends.

Communities.

Organisations.

Trust networks influence information flow.

---

# 15.33 Information Flow

Social structures influence information movement.

Information spreads differently through:

Families.

Guilds.

Religions.

Governments.

Criminal groups.

Structure affects knowledge.

---

# 15.34 Structural Stability

Stable structures:

Adapt.

Recover.

Replace leadership.

Maintain legitimacy.

Unstable structures:

Fragment.

Radicalise.

Collapse.

Decay.

Stability emerges from resilience.

---

# 15.35 Structural Collapse

Collapse occurs when structures can no longer fulfil their purpose.

Examples:

Government failure.

Institutional corruption.

Religious schism.

Corporate bankruptcy.

Collapse creates pressure.

Pressure creates new structures.

---

# 15.36 Structural Evolution

Social structures evolve.

Examples:

Families become dynasties.

Guilds become corporations.

Tribes become nations.

Movements become governments.

Evolution creates historical depth.

---

# 15.37 Structural Memory

Structures remember.

Through:

Records.

Traditions.

Culture.

Policies.

Institutions possess memory beyond individuals.

---

# 15.38 Structural Inheritance

Knowledge transfers between generations.

Successors inherit:

Power.

Responsibility.

Resources.

History.

Identity.

Inheritance preserves continuity.

---

# 15.39 The Living Society Test

Ask:

How are people organised?

Who holds power?

Why do others follow?

How is trust distributed?

How does information move?

How does conflict emerge?

If these questions cannot be answered:

The society is incomplete.

---

# 15.40 Final Doctrine

Individuals create relationships.

Relationships create groups.

Groups create structures.

Structures create societies.

Societies create civilisation.

Social structures are not background details.

They are active forces shaping behaviour.

A living world is not merely populated.

A living world is organised.

The simulation must understand that organisation.

Only then can civilisation truly emerge.

END OF CHAPTER 15

CANONICAL VERSION

# CHAPTER 16

# REPUTATION SYSTEMS

## Status

Canonical

This chapter defines how information about actors spreads throughout the world and influences future behaviour.

If Chapter 9 defines Information Theory, Chapter 13 defines Relationships, and Chapter 15 defines Social Structures, Chapter 16 defines how the wider world forms opinions.

Reputation is second-hand experience.

Most people will never meet you.

Most people will know of you.

That knowledge influences behaviour.

Reputation acts as a force multiplier.

Reputation creates opportunity.

Reputation creates danger.

Reputation creates pressure.

Reputation creates history.

This chapter governs:

* Personal reputation
* Group reputation
* Settlement reputation
* Faction reputation
* Fame
* Infamy
* Credibility
* Trustworthiness
* Public perception
* Reputation propagation

Every social system in the simulation depends upon reputation.

---

# 16.1 Core Doctrine

Reputation is distributed memory.

Relationships are direct experience.

Reputation is indirect experience.

A person trusts a friend because of memory.

A person trusts a stranger because of reputation.

This distinction is fundamental.

---

# 16.2 Definition

Reputation is the collection of beliefs held by others regarding an actor.

The actor may be:

Individual.

Family.

Settlement.

Faction.

Institution.

Organisation.

Nation.

Anything capable of accumulating social perception.

---

# 16.3 Reputation Is Not Truth

This is one of the most important rules.

Reputation is perception.

Not reality.

Examples:

Honest person accused falsely.

Dishonest person admired publicly.

Hero misunderstood.

Villain celebrated.

Reality and reputation frequently diverge.

The simulation must support this.

---

# 16.4 Reputation Formation

Reputation forms through information.

Examples:

Witnesses.

Rumours.

Records.

News.

Stories.

Achievements.

Failures.

Information creates perception.

Perception creates reputation.

---

# 16.5 Reputation Sources

Not all information sources possess equal credibility.

Examples:

Trusted witness.

Official report.

Friend.

Enemy.

Rumour.

Propaganda.

Source quality influences reputation formation.

---

# 16.6 Direct Reputation

Derived from personal experience.

Examples:

Known merchant.

Local leader.

Neighbour.

Friend.

Direct reputation is generally more reliable.

---

# 16.7 Indirect Reputation

Derived from transmitted information.

Examples:

Stories.

News.

Rumours.

Legends.

Indirect reputation spreads further.

Indirect reputation is often less accurate.

---

# 16.8 Reputation Ownership

Reputation exists within observers.

Not actors.

A person does not own their reputation.

Other people do.

This distinction is critical.

Actors may influence reputation.

Actors cannot fully control reputation.

---

# 16.9 Reputation Categories

Common reputation dimensions include:

Competence.

Honesty.

Reliability.

Danger.

Generosity.

Cruelty.

Wisdom.

Influence.

Authority.

Reputation should be multidimensional.

Not a single score.

---

# 16.10 Competence Reputation

Measures perceived capability.

Examples:

Skilled surgeon.

Reliable soldier.

Brilliant engineer.

Competence creates opportunity.

---

# 16.11 Trust Reputation

Measures perceived reliability.

Examples:

Keeps promises.

Pays debts.

Protects allies.

Trust influences cooperation.

---

# 16.12 Danger Reputation

Measures perceived threat.

Examples:

Violent criminal.

Elite warrior.

Unpredictable leader.

Danger influences behaviour.

Even when respect is absent.

---

# 16.13 Influence Reputation

Measures perceived ability to affect reality.

Examples:

Political figures.

Business leaders.

Religious authorities.

Influence attracts attention.

---

# 16.14 Moral Reputation

Measures perceived ethics.

Examples:

Honourable.

Corrupt.

Fair.

Cruel.

Different groups may disagree completely.

---

# 16.15 Reputation Scope

Reputation possesses range.

---

## Personal Scope

Known by few.

---

## Local Scope

Known within community.

---

## Regional Scope

Known across settlements.

---

## National Scope

Known broadly.

---

## Legendary Scope

Known across generations.

---

Scope affects impact.

---

# 16.16 Reputation Propagation

Reputation spreads through information networks.

Examples:

Trade routes.

Political channels.

Religious networks.

Criminal networks.

Media systems.

Propagation speed depends on network quality.

---

# 16.17 Reputation Decay

Without reinforcement:

Reputation weakens.

People forget.

Stories fade.

Attention shifts.

Decay prevents permanent relevance.

---

# 16.18 Reputation Reinforcement

Repeated evidence strengthens reputation.

Example:

Reliable actions repeated.

↓

Trust increases.

Repeated patterns matter more than isolated events.

---

# 16.19 Reputation Mutation

Information changes during transmission.

Reputation changes too.

Examples:

Success exaggerated.

Failure exaggerated.

Context removed.

Stories embellished.

Mutation creates realism.

---

# 16.20 Reputation And Relationships

Relationships influence reputation interpretation.

Friends forgive.

Enemies condemn.

Neutral observers evaluate differently.

Reputation is filtered through existing relationships.

---

# 16.21 Reputation And Opportunity

Good reputation creates:

Access.

Trust.

Partnerships.

Investment.

Influence.

Opportunity often follows perception.

---

# 16.22 Reputation And Risk

Bad reputation creates:

Suspicion.

Fear.

Monitoring.

Exclusion.

Resistance.

Reputation influences future interactions.

---

# 16.23 Reputation And Power

Power magnifies reputation.

A rumour about a king matters more than a rumour about a labourer.

Visibility amplifies consequences.

---

# 16.24 Reputation And Identity

Over time:

Reputation can influence identity.

People may begin behaving according to expectations.

This feedback loop creates realism.

---

# 16.25 Group Reputation

Groups accumulate reputation.

Examples:

Families.

Corporations.

Religions.

Military units.

Guilds.

Group reputation influences members.

---

# 16.26 Settlement Reputation

Settlements develop reputations.

Examples:

Prosperous.

Dangerous.

Lawless.

Innovative.

Corrupt.

Religious.

Settlement reputation affects migration and trade.

---

# 16.27 Faction Reputation

Factions accumulate social perception.

Examples:

Trustworthy.

Violent.

Competent.

Corrupt.

Faction reputation affects recruitment and diplomacy.

---

# 16.28 Institutional Reputation

Institutions develop reputations too.

Examples:

Courts.

Governments.

Universities.

Corporations.

Military organisations.

Institutional trust affects stability.

---

# 16.29 Reputation Crises

Major events can rapidly alter perception.

Examples:

Scandal.

Military defeat.

Disaster response failure.

Corruption exposure.

Reputation crises generate pressure.

---

# 16.30 Reputation Recovery

Recovery is possible.

But rarely immediate.

Recovery requires:

Time.

Evidence.

Consistency.

Behavioural change.

Trust rebuilds slowly.

---

# 16.31 Fame

Fame is widespread awareness.

Fame is not automatically positive.

Many famous people possess terrible reputations.

Awareness and approval are separate.

---

# 16.32 Infamy

Infamy is negative high-scope reputation.

Infamy creates:

Fear.

Attention.

Opportunity.

Danger.

Infamy remains influence.

---

# 16.33 Legends

Some reputations outlive reality.

Stories become myths.

Facts become symbolic.

Legends are reputation detached from direct experience.

---

# 16.34 Reputation And Information Theory

Reputation depends entirely upon information systems.

Without information flow:

Reputation cannot exist.

Chapter 9 and Chapter 16 are inseparable.

---

# 16.35 Reputation And Memory

Reputation is collective memory.

Memory creates reputation.

Reputation influences future memory formation.

The systems reinforce one another.

---

# 16.36 Reputation And Social Structures

Social structures determine:

Who hears information.

Who believes information.

Who spreads information.

Structure shapes reputation.

---

# 16.37 Reputation And Conflict

Many conflicts emerge from perception.

Examples:

Misunderstanding.

Distrust.

Historical grievances.

Rumours.

False accusations.

Perception often drives behaviour more strongly than truth.

---

# 16.38 The Dead Reputation Test

Ask:

What is believed?

Who believes it?

Why do they believe it?

How did they learn it?

How far has it spread?

Can it change?

If these questions cannot be answered:

The reputation system is incomplete.

---

# 16.39 The Living World Test

Remove the player.

Do reputations form?

Do stories spread?

Do legends emerge?

Do scandals matter?

Do institutions gain trust?

Do institutions lose trust?

If yes:

The reputation system is functioning.

---

# 16.40 Final Doctrine

Reputation is distributed memory.

Reputation is perception.

Not truth.

Reputation emerges from information.

Reputation influences behaviour.

Reputation creates opportunity.

Reputation creates danger.

A living world is shaped not only by what happens.

A living world is shaped by what people believe happened.

END OF CHAPTER 16

CANONICAL VERSION

# CHAPTER 17

# FACTION ARCHITECTURE

## Status

Canonical

This chapter defines how groups become actors within the Dice Reaction Story Engine.

If Chapter 10 defines individuals, Chapter 15 defines social structures, and Chapter 16 defines reputation, Chapter 17 defines factions.

Factions are among the most important forces in the simulation.

Most historical events are not caused by individuals.

Most historical events are caused by organised groups pursuing objectives.

Factions generate:

* Conflict
* Cooperation
* Competition
* Expansion
* Stability
* Instability
* Political pressure
* Economic pressure
* Cultural change
* Historical change

A living world requires living factions.

This chapter governs:

* Faction creation
* Faction behaviour
* Faction identity
* Faction goals
* Faction resources
* Faction growth
* Faction decline
* Faction fragmentation
* Faction influence
* Faction evolution

Every large-scale simulation system depends upon factions.

---

# 17.1 Core Doctrine

A faction is a persistent actor composed of multiple individuals pursuing shared interests.

A faction is not scenery.

A faction is not a label.

A faction is not a quest provider.

A faction is a living simulation entity.

The simulation should never ask:

"What content does this faction provide?"

The simulation should ask:

"What is this faction trying to achieve?"

Everything else follows.

---

# 17.2 Definition

A faction is an organised group capable of coordinated action.

Examples:

Kingdoms.

Corporations.

Religions.

Criminal organisations.

Guilds.

Political parties.

Military organisations.

Tribes.

Revolutionary movements.

Trade alliances.

Scale does not matter.

Behavioural principles remain the same.

---

# 17.3 Why Factions Exist

Factions emerge because individuals cannot achieve everything alone.

Factions provide:

Coordination.

Protection.

Resources.

Identity.

Influence.

Efficiency.

Factions solve collective problems.

---

# 17.4 Faction Formation

Factions emerge from shared interests.

Examples:

Shared profit goals.

Shared beliefs.

Shared threats.

Shared identity.

Shared opportunities.

Pressure creates cooperation.

Cooperation creates factions.

---

# 17.5 Faction Lifecycle

Every faction moves through stages.

Formation.

Growth.

Maturity.

Expansion.

Decline.

Collapse.

Transformation.

Few factions remain static.

Change is normal.

---

# 17.6 Faction Identity

Every faction possesses identity.

Identity answers:

Who are we?

Why do we exist?

Identity emerges from:

History.

Belief.

Culture.

Goals.

Leadership.

Shared experience.

Identity influences behaviour.

---

# 17.7 Faction Core Components

Every faction contains:

Identity.

Goals.

Leadership.

Members.

Resources.

Influence.

Relationships.

Memory.

Pressure.

Without these components, the faction is incomplete.

---

# 17.8 Faction Goals

Factions pursue goals.

Examples:

Expand territory.

Increase profit.

Spread religion.

Gain political influence.

Control resources.

Destroy rivals.

Goals create motion.

Motion creates history.

---

# 17.9 Faction Resources

Factions consume resources.

Examples:

Money.

Food.

Labour.

Influence.

Information.

Weapons.

Infrastructure.

Resources determine capability.

---

# 17.10 Faction Leadership

Leadership coordinates action.

Leadership may be:

Democratic.

Autocratic.

Inherited.

Merit-based.

Religious.

Military.

Leadership structure affects behaviour.

---

# 17.11 Leadership Stability

Leadership is a source of both strength and vulnerability.

Stable leadership:

Predictability.

Coordination.

Long-term planning.

Unstable leadership:

Conflict.

Fragmentation.

Confusion.

Power struggles.

---

# 17.12 Members

Members are the foundation of factions.

Without members:

No labour.

No influence.

No legitimacy.

No action.

Members are not resources alone.

Members possess goals of their own.

---

# 17.13 Faction Legitimacy

Legitimacy measures perceived right to exist and exercise authority.

Legitimacy may derive from:

Tradition.

Performance.

Belief.

Law.

Force.

Legitimacy influences stability.

---

# 17.14 Faction Cohesion

Cohesion measures internal unity.

High cohesion:

Coordination.

Loyalty.

Resilience.

Low cohesion:

Infighting.

Defection.

Fragmentation.

Collapse.

---

# 17.15 Internal Pressures

Every faction experiences pressure.

Examples:

Leadership disputes.

Resource shortages.

Corruption.

Ideological conflict.

Member dissatisfaction.

Internal pressure often proves more dangerous than external threats.

---

# 17.16 External Pressures

Examples:

War.

Competition.

Trade disruption.

Political opposition.

Economic instability.

External pressure shapes faction behaviour.

---

# 17.17 Faction Memory

Factions remember.

Through:

Records.

Traditions.

Institutions.

Culture.

Policies.

Faction memory influences future decisions.

---

# 17.18 Institutional Continuity

Factions often survive leadership changes.

Leaders die.

Factions persist.

Institutional continuity creates historical depth.

---

# 17.19 Faction Reputation

Factions accumulate reputation.

Examples:

Trustworthy.

Violent.

Corrupt.

Competent.

Innovative.

Reputation influences recruitment and cooperation.

---

# 17.20 Recruitment

Factions seek growth.

Recruitment depends on:

Reputation.

Opportunity.

Resources.

Ideology.

Protection.

Recruitment influences long-term survival.

---

# 17.21 Retention

Keeping members is as important as gaining members.

Loss of members weakens capability.

Retention depends on:

Trust.

Rewards.

Identity.

Leadership.

Shared success.

---

# 17.22 Defection

Members may leave.

Reasons include:

Disagreement.

Fear.

Opportunity.

Corruption.

Failure.

Defection creates instability.

---

# 17.23 Fragmentation

Factions may split.

Common causes:

Leadership conflict.

Ideological division.

Resource disputes.

Geographic separation.

Fragmentation creates new actors.

---

# 17.24 Mergers

Factions may combine.

Examples:

Trade alliances.

Political coalitions.

Religious unions.

Military confederations.

Mergers alter power distribution.

---

# 17.25 Alliances

Alliances are relationships between factions.

Examples:

Military.

Economic.

Political.

Religious.

Alliances create mutual influence.

---

# 17.26 Rivalries

Rivalries emerge naturally.

Causes include:

Competition.

History.

Territory.

Resources.

Ideology.

Rivalries generate pressure.

---

# 17.27 Territory

Many factions possess territory.

Territory provides:

Resources.

Population.

Strategic value.

Influence.

Territory also creates obligations.

---

# 17.28 Resource Competition

Factions frequently compete over resources.

Examples:

Trade routes.

Farmland.

Water.

Labour.

Minerals.

Competition drives conflict.

---

# 17.29 Information Competition

Factions compete for information.

Examples:

Espionage.

Propaganda.

Intelligence gathering.

Narrative control.

Information is power.

---

# 17.30 Influence Expansion

Factions naturally seek greater influence.

Influence expands through:

Trade.

Diplomacy.

Military action.

Culture.

Religion.

Economic dominance.

---

# 17.31 Power Projection

Power matters only if it can be applied.

Examples:

Military reach.

Economic leverage.

Political influence.

Information networks.

Projection determines real capability.

---

# 17.32 Faction Growth

Growth occurs when resources and opportunities exceed pressures.

Growing factions attract attention.

Attention creates new pressures.

Growth is never free.

---

# 17.33 Faction Decline

Decline occurs when pressures exceed capacity.

Examples:

Debt.

Military defeat.

Corruption.

Population loss.

Leadership failure.

Decline generates instability.

---

# 17.34 Faction Collapse

Collapse occurs when cohesion fails.

Examples:

Civil war.

Bankruptcy.

Schism.

Conquest.

Institutional failure.

Collapse creates historical consequences.

---

# 17.35 Faction Transformation

Not all decline ends in destruction.

Examples:

Empire becomes republic.

Guild becomes corporation.

Cult becomes religion.

Rebels become government.

Transformation creates depth.

---

# 17.36 Faction Ecology

Factions exist within ecosystems.

They compete.

Cooperate.

Merge.

Split.

Adapt.

No faction exists in isolation.

---

# 17.37 Independent Motion

Factions must remain active without player involvement.

Recruitment.

Expansion.

Conflict.

Trade.

Politics.

The player is not required.

This is mandatory.

---

# 17.38 The Dead Faction Test

Ask:

What does the faction want?

What resources does it control?

Who leads it?

Why do members stay?

What pressures affect it?

What happens if the player vanishes?

If these questions cannot be answered:

The faction is incomplete.

---

# 17.39 The Living World Test

Remove the player.

Do factions recruit?

Do alliances change?

Do conflicts emerge?

Do leaders change?

Do factions grow?

Do factions decline?

If yes:

The faction system is functioning.

---

# 17.40 Final Doctrine

Factions are not background organisations.

Factions are actors.

They possess goals.

They possess memory.

They possess pressure.

They possess resources.

They possess identity.

They compete.

They cooperate.

They evolve.

A living world is shaped by organised groups pursuing collective objectives.

The simulation must treat factions as living entities.

Only then can history emerge naturally.

END OF CHAPTER 17

CANONICAL VERSION

# CHAPTER 18

# CONSEQUENCE LEDGER

## Status

Canonical

This chapter defines the most important persistence mechanism in the Dice Reaction Story Engine.

If State Is Truth is the foundation of reality, the Consequence Ledger is the foundation of history.

Most games remember outcomes.

Dice Reaction remembers consequences.

This distinction is critical.

A living world is not created by actions.

A living world is created by the lingering effects of actions.

The Consequence Ledger exists to ensure that actions continue influencing reality long after the original event has ended.

This chapter governs:

* Consequence tracking
* Delayed outcomes
* Persistent world changes
* Historical causality
* State mutation accountability
* Event persistence
* World scars
* Long-term effects
* Chain reactions
* Historical continuity

Every future simulation system depends upon the Consequence Ledger.

---

# 18.1 Core Doctrine

Nothing important disappears.

This is the central doctrine of the ledger.

If an event meaningfully changes reality:

The change must be tracked.

The change must persist.

The change must remain capable of influencing future events.

The world remembers through consequences.

Not through stories.

---

# 18.2 Definition

A consequence is any lasting change to reality caused by an event.

Examples:

Broken bridge.

Lost trust.

Political instability.

Economic decline.

War.

Fame.

Trauma.

Migration.

Dead leader.

These are not events.

They are consequences.

---

# 18.3 Why The Ledger Exists

Without a ledger:

Events become isolated.

History disappears.

The world resets itself.

Actions lose meaning.

The ledger prevents reality from forgetting.

---

# 18.4 The Event Problem

Most systems track:

What happened.

Dice Reaction tracks:

What changed.

Example:

Bad tracking:

```text
Bandits attacked caravan.
```

Good tracking:

```text
Trade route reliability decreased.
Merchant trust reduced.
Regional prices increased.
```

The second version creates future behaviour.

---

# 18.5 Event Versus Consequence

Events are moments.

Consequences are conditions.

Example:

Event:

Castle burns.

Consequences:

Housing shortage.

Political instability.

Resource loss.

Refugee movement.

The event ends.

The consequences continue.

---

# 18.6 Ledger Ownership

Every consequence must have ownership.

Examples:

Settlement.

NPC.

Faction.

Region.

Relationship.

Institution.

Ownership determines where effects propagate.

---

# 18.7 Consequence Creation

Consequences emerge through simulation.

Not narrative.

Not developer intervention.

Not random generation.

Every consequence requires a causal source.

---

# 18.8 Consequence Lifecycle

Every consequence moves through stages.

Creation.

Activation.

Propagation.

Transformation.

Resolution.

Historical Integration.

This lifecycle governs persistence.

---

# 18.9 Creation

A meaningful event alters reality.

A consequence enters the ledger.

Example:

Mayor assassinated.

Consequence:

Leadership instability.

---

# 18.10 Activation

The consequence begins affecting systems.

Example:

Leadership instability influences:

Decision making.

Faction confidence.

Public trust.

Political pressure.

---

# 18.11 Propagation

Consequences spread.

Example:

Political instability.

↓

Economic uncertainty.

↓

Reduced investment.

↓

Unemployment.

↓

Crime increase.

Propagation creates emergence.

---

# 18.12 Transformation

Consequences evolve.

Example:

Food shortage.

↓

Famine.

↓

Migration.

↓

Labour shortage.

The original consequence changes form.

---

# 18.13 Resolution

Some consequences eventually stabilise.

Example:

New leader elected.

Political instability resolved.

The original consequence no longer actively influences reality.

---

# 18.14 Historical Integration

Resolved consequences become history.

They stop driving active simulation.

They remain true.

History preserves continuity.

---

# 18.15 Consequence Categories

Common categories include:

Physical.

Social.

Political.

Economic.

Psychological.

Environmental.

Informational.

Cultural.

Most major events generate multiple categories.

---

# 18.16 Physical Consequences

Examples:

Destroyed buildings.

Road damage.

Infrastructure loss.

Environmental damage.

Physical consequences are highly visible.

---

# 18.17 Social Consequences

Examples:

Distrust.

Fear.

Loyalty shifts.

Community fragmentation.

Social consequences often outlast physical ones.

---

# 18.18 Political Consequences

Examples:

Power vacuums.

Leadership crises.

Policy changes.

Faction instability.

Political consequences frequently cascade.

---

# 18.19 Economic Consequences

Examples:

Price shifts.

Debt.

Trade disruption.

Labour shortages.

Economic consequences spread rapidly.

---

# 18.20 Psychological Consequences

Examples:

Trauma.

Obsession.

Grief.

Resentment.

Psychological consequences influence behaviour directly.

---

# 18.21 Informational Consequences

Examples:

Rumours.

Reputation shifts.

Public awareness.

Exposure of secrets.

Information often changes behaviour without altering physical reality.

---

# 18.22 Cultural Consequences

Examples:

New traditions.

Social taboos.

Political beliefs.

Collective identity changes.

Cultural consequences may persist for generations.

---

# 18.23 Consequence Weight

Not all consequences are equal.

Weight determines:

Priority.

Persistence.

Propagation strength.

Processing frequency.

Higher weight means greater impact.

---

# 18.24 Minor Consequences

Examples:

Small arguments.

Routine trade delays.

Temporary inconvenience.

Minor consequences fade quickly.

---

# 18.25 Moderate Consequences

Examples:

Business failure.

Political scandal.

Local drought.

Moderate consequences influence multiple systems.

---

# 18.26 Major Consequences

Examples:

War.

Famine.

Economic collapse.

Leadership assassination.

Major consequences reshape regions.

---

# 18.27 Defining Consequences

Examples:

Empire collapse.

Religious revolution.

Extinction event.

Civilisation-changing discovery.

Defining consequences alter history permanently.

---

# 18.28 Consequence Persistence

Persistence depends on:

Weight.

Scope.

Affected systems.

Historical significance.

Some consequences last days.

Others last centuries.

---

# 18.29 Consequence Propagation Rules

A consequence should spread only through valid causal pathways.

Bad:

Random spread.

Good:

Traceable spread.

Causality remains mandatory.

---

# 18.30 Chain Reactions

The ledger exists primarily to support chain reactions.

Example:

Bridge collapse.

↓

Trade disruption.

↓

Price increase.

↓

Public anger.

↓

Political pressure.

↓

Election loss.

One event.

Multiple consequences.

---

# 18.31 Ledger Traceability

Every consequence should answer:

What caused me?

Who owns me?

What am I affecting?

When was I created?

When will I resolve?

Traceability is mandatory.

---

# 18.32 The Historical Spine

The ledger acts as the historical spine of the world.

It links:

Past.

Present.

Future.

Without this spine:

History becomes disconnected.

---

# 18.33 State Integration

Consequences do not replace state.

Consequences influence state.

State remains truth.

The ledger records how truth changed.

---

# 18.34 Narrative Independence

Narrative may describe consequences.

Narrative does not create consequences.

This distinction protects simulation integrity.

---

# 18.35 Resolution Does Not Mean Erasure

A resolved consequence is not deleted.

Example:

War ends.

Veterans remain.

Destroyed cities remain.

Political scars remain.

Resolution ends activity.

Not history.

---

# 18.36 Ledger Compression

Large worlds generate enormous consequence volume.

Compression is required.

Compression reduces detail.

Compression preserves causality.

History remains intact.

---

# 18.37 The Ledger Integrity Rule

No major consequence may disappear without explanation.

Consequences may:

Resolve.

Transform.

Merge.

Archive.

They may never simply vanish.

---

# 18.38 The Dead Consequence Test

Ask:

What changed?

Why did it change?

Who is affected?

How long does it persist?

What future events may emerge?

If these questions cannot be answered:

The consequence system is incomplete.

---

# 18.39 The Living World Test

Remove the player.

Do consequences continue influencing events?

Do old actions still matter?

Does history continue shaping reality?

If yes:

The ledger is functioning.

---

# 18.40 Final Doctrine

Events create consequences.

Consequences create history.

History creates pressure.

Pressure creates future events.

The Consequence Ledger is the mechanism that binds those stages together.

Without it:

Actions become isolated.

With it:

Reality develops memory.

A living world is not defined by what happened.

A living world is defined by what continues to matter afterward.

END OF CHAPTER 18

CANONICAL VERSION

# CHAPTER 19

# DELAYED CONSEQUENCES

## Status

Canonical

This chapter defines one of the defining features of the Dice Reaction Story Engine:

Consequences do not need to occur immediately.

Most games concentrate consequences into the present.

Dice Reaction distributes consequences through time.

Reality rarely responds instantly.

A careless comment may destroy a relationship months later.

A political decision may trigger unrest years later.

A forgotten favour may save a life decades afterward.

The purpose of this chapter is to ensure that time itself becomes a simulation mechanic.

This chapter governs:

* Delayed outcomes
* Latent consequences
* Triggered consequences
* Consequence scheduling
* Hidden causality
* Future event generation
* Historical payoff
* Long-term consequence chains
* Opportunity creation
* Emergent narrative timing

Every major simulation system depends upon delayed consequences.

---

# 19.1 Core Doctrine

Not all consequences happen now.

This is the central doctrine.

A consequence may exist long before it becomes visible.

A consequence may be active long before anyone notices.

A consequence may alter the future without affecting the present.

Time is part of causality.

---

# 19.2 Definition

A delayed consequence is a consequence whose activation occurs after its originating event.

The originating event creates the consequence.

The consequence remains dormant.

A future condition activates it.

This distinction is critical.

---

# 19.3 Why Delayed Consequences Matter

Without delayed consequences:

The world becomes predictable.

The world becomes shallow.

Actions become disconnected from history.

Delayed consequences create:

Surprise.

Depth.

Realism.

Historical continuity.

Player caution.

Long-term planning.

---

# 19.4 Immediate Versus Delayed

Immediate consequence:

```text id="8gq5tw"
Punch guard.
↓
Guard attacks.
```

Delayed consequence:

```text id="g57a4r"
Punch guard.
↓
Months later:
Promotion denied.
```

Both are valid.

Both should exist.

---

# 19.5 The Time Gap Principle

The longer the gap between cause and effect:

The more important traceability becomes.

The simulation must never forget causality.

Even if the player does.

---

# 19.6 Latent Consequences

Latent consequences exist but are inactive.

Examples:

Hidden resentment.

Unnoticed structural damage.

Political dissatisfaction.

Financial instability.

Unresolved trauma.

Latent consequences are among the most important systems in the engine.

---

# 19.7 Dormant State

A dormant consequence:

Exists.

Persists.

Consumes minimal processing.

Remains capable of activation.

Dormancy is not deletion.

---

# 19.8 Trigger Conditions

Every delayed consequence requires activation conditions.

Examples:

Time.

Location.

Person.

Event.

Pressure threshold.

Information discovery.

Without triggers, delayed consequences become arbitrary.

---

# 19.9 Time Triggers

Examples:

Harvest season arrives.

Election cycle begins.

Debt repayment date arrives.

Construction deadline passes.

Time itself may activate consequences.

---

# 19.10 Pressure Triggers

Examples:

Public anger exceeds tolerance.

Food reserves fall below threshold.

Military losses become unacceptable.

Pressure often activates dormant instability.

---

# 19.11 Information Triggers

Examples:

Secret revealed.

Evidence discovered.

Witness comes forward.

Information frequently activates dormant consequences.

---

# 19.12 Relationship Triggers

Examples:

Former ally returns.

Old betrayal rediscovered.

Family conflict resurfaces.

Relationships create powerful delayed effects.

---

# 19.13 Location Triggers

Examples:

Returning to battlefield.

Entering abandoned city.

Visiting crime scene.

Places can activate dormant history.

---

# 19.14 Activation

Activation occurs when trigger conditions are met.

Activation moves a consequence from dormant state into active simulation.

Once activated:

Behaviour changes.

Pressure changes.

Reality changes.

---

# 19.15 Hidden Consequences

Many delayed consequences should remain invisible.

Reality often contains unseen instability.

The player should discover consequences.

Not receive warnings.

---

# 19.16 Foreshadowing Doctrine

Hidden does not mean arbitrary.

Major delayed consequences require signals.

Examples:

Rumours.

Warnings.

Behaviour changes.

Environmental clues.

Patterns.

Players may miss them.

The clues should still exist.

---

# 19.17 The Fairness Doctrine

A consequence may surprise the player.

A consequence should not confuse the player.

The simulation must remain fair.

Fairness requires causality.

Not predictability.

---

# 19.18 Delayed Rewards

Delayed consequences are not always negative.

Examples:

Old investment matures.

Past kindness remembered.

Former apprentice becomes leader.

Successful reform bears fruit.

Positive delayed consequences are essential.

---

# 19.19 Delayed Harm

Examples:

Corruption exposed.

Disease spreads.

Debt accumulates.

Infrastructure fails.

Unresolved pressure often generates delayed harm.

---

# 19.20 Cascading Delay

One delayed consequence may create another.

Example:

```text id="jgxvsa"
Road neglected.
↓
Bridge weakens.
↓
Bridge collapses.
↓
Trade declines.
↓
Settlement weakens.
```

This creates historical depth.

---

# 19.21 Compound Consequences

Multiple dormant consequences may activate simultaneously.

Examples:

Economic decline.

Leadership crisis.

Food shortage.

Together they produce instability.

Compound activation creates realism.

---

# 19.22 Opportunity Windows

Some consequences create temporary opportunities.

Examples:

Political vacancy.

Trade disruption.

Leadership death.

Opportunity itself can be a consequence.

---

# 19.23 Historical Debt

The world accumulates unresolved obligations.

Examples:

Unpaid debts.

Unavenged murders.

Broken promises.

Unresolved treaties.

History carries obligations forward.

---

# 19.24 Historical Momentum

Past decisions influence future possibilities.

The longer a consequence persists:

The greater its potential influence.

History accumulates weight.

---

# 19.25 Delayed Consequence Ownership

Every delayed consequence must belong somewhere.

Examples:

NPC.

Settlement.

Faction.

Institution.

Region.

Ownership determines activation scope.

---

# 19.26 Delayed Consequence Persistence

Dormant consequences remain persistent.

The simulation must not forget them.

Dormancy reduces processing.

It does not reduce truth.

---

# 19.27 Activation Strength

Not all activations are equal.

Examples:

Minor revelation.

Major scandal.

Regional collapse.

Activation strength depends upon accumulated conditions.

---

# 19.28 Delayed Consequence Networks

Dormant consequences frequently connect.

Example:

```text id="zlf9lr"
Corruption
↓
Infrastructure neglect
↓
Economic weakness
↓
Political instability
```

Networks create emergent outcomes.

---

# 19.29 Narrative Timing

The simulation should determine timing.

Not the story.

A consequence activates when conditions justify activation.

Not when drama demands it.

This distinction protects simulation integrity.

---

# 19.30 Historical Echoes

Some events continue influencing reality long after resolution.

Examples:

Wars.

Disasters.

Revolutions.

Trauma.

Historical echoes are delayed consequences at civilisational scale.

---

# 19.31 Consequence Visibility

Delayed consequences may be:

Visible.

Partially visible.

Invisible.

The simulation should support all three.

---

# 19.32 Investigation And Delay

Delayed consequences create investigations.

Investigations often work backward through history.

This creates discovery gameplay.

---

# 19.33 Time As A Resource

Delayed consequences make time meaningful.

Waiting becomes a decision.

Delay becomes a strategy.

Patience becomes valuable.

Time becomes part of the simulation.

---

# 19.34 The Forgotten Seed Principle

Many important future events begin as insignificant present events.

Small actions plant seeds.

History determines which seeds grow.

The simulation must support seed formation.

---

# 19.35 The Butterfly Rule

Minor actions may create major outcomes.

Not because of randomness.

Because of cumulative causality.

The simulation should allow scale amplification.

---

# 19.36 Delayed Consequence Compression

Dormant consequences should compress efficiently.

The simulation tracks:

Origin.

Ownership.

Trigger.

Potential impact.

Dormancy should remain affordable.

---

# 19.37 The Ledger Connection

Every delayed consequence belongs within the Consequence Ledger.

Chapter 18 records existence.

Chapter 19 governs activation.

The systems are inseparable.

---

# 19.38 The Dead Delay Test

Ask:

What future effect exists?

Why has it not occurred yet?

What activates it?

Who is affected?

How does it propagate?

If these questions cannot be answered:

The delayed consequence system is incomplete.

---

# 19.39 The Living World Test

Remove the player.

Advance time.

Do dormant consequences activate?

Do old actions matter?

Do forgotten events resurface?

Does history continue generating outcomes?

If yes:

The system is functioning.

---

# 19.40 Final Doctrine

Not all consequences belong to the present.

Some belong to the future.

History plants seeds.

Time nurtures them.

Pressure activates them.

Reality changes because of them.

A living world is not merely a chain of events.

A living world is a chain of consequences waiting for their moment to matter.

END OF CHAPTER 19

# CHAPTER 20

# CONTEXT GRAVITY

## Status

Canonical

This chapter defines how the Dice Reaction Story Engine decides what continues to matter.

Without Context Gravity, a living world eventually collapses under its own history.

Every action creates consequences.

Every consequence creates history.

Every history creates memory.

Without prioritisation:

Nothing fades.

Everything remains equally important.

The simulation becomes impossible to scale.

Context Gravity solves this problem.

Context Gravity determines:

* What remains important.
* What fades into the background.
* What resurfaces later.
* What receives processing priority.
* What receives memory priority.
* What receives narrative attention.
* What receives simulation resources.

Context Gravity is one of the most important scalability systems in the entire engine.

---

# 20.1 Core Doctrine

Not all truths possess equal importance.

Everything that happened remains true.

Not everything that happened remains relevant.

This distinction is fundamental.

Context Gravity determines relevance.

Not truth.

Truth remains sacred.

Relevance changes.

---

# 20.2 Definition

Context Gravity is the tendency of important events, actors, pressures, and consequences to continue influencing the simulation.

Gravity is not attention.

Gravity is influence.

The greater the gravity:

The more likely something is to continue affecting reality.

---

# 20.3 Why Context Gravity Exists

Without gravity:

Every event receives equal treatment.

Examples:

A spilled drink.

A kingdom collapse.

A casual greeting.

A religious revolution.

This is absurd.

Reality naturally prioritises significance.

The simulation must do the same.

---

# 20.4 Truth Versus Relevance

Every event remains true.

Not every event remains relevant.

Example:

A merchant sneezed.

True.

Not relevant.

An emperor was assassinated.

True.

Highly relevant.

Context Gravity determines the difference.

---

# 20.5 The Gravity Rule

Importance is earned through impact.

Not visibility.

Not drama.

Not narrative preference.

Impact.

This is mandatory.

---

# 20.6 Sources Of Gravity

Gravity emerges from several factors.

Scope.

Duration.

Intensity.

Connectivity.

Symbolic value.

Historical significance.

The more factors present:

The greater the gravity.

---

# 20.7 Scope

How many systems are affected?

Examples:

Minor argument.

Low scope.

Regional famine.

High scope.

Large scope creates stronger gravity.

---

# 20.8 Duration

How long does the effect persist?

Examples:

Brief inconvenience.

Low duration.

Generational trauma.

High duration.

Long-lived effects possess greater gravity.

---

# 20.9 Intensity

How strongly does it affect behaviour?

Examples:

Minor annoyance.

Low intensity.

Civil war.

High intensity.

Intensity increases gravity.

---

# 20.10 Connectivity

How many other systems connect to it?

Examples:

Broken mug.

Few connections.

Trade route collapse.

Many connections.

Connectivity is one of the strongest gravity multipliers.

---

# 20.11 Symbolic Value

Some events become symbols.

Examples:

National tragedy.

Founding battle.

Religious miracle.

Political assassination.

Symbolism increases gravity beyond practical effects.

---

# 20.12 Historical Significance

Some events alter future possibilities.

Examples:

Constitution written.

Empire falls.

Technology discovered.

Historical significance creates immense gravity.

---

# 20.13 Gravity Levels

Events naturally settle into gravity tiers.

Gravity is stored as a continuous value from 0.0 to 1.0. The named tiers below are the **canonical mapping** between that numeric scale and the qualitative language used throughout this Bible. Every chapter that references a gravity threshold (Chapters 22, 24, 25, 26, 30, and others) resolves to this scale and no other.

| Tier | Numeric Range | Impact |
|------|---------------|--------|
| **Negligible** | 0.00 – 0.20 | Minimal impact. Routine, daily-life events. |
| **Minor** | 0.20 – 0.50 | Local impact. Affects one actor or one location. |
| **Significant** | 0.50 – 0.70 | Multiple systems affected. Settlement-level consequence. |
| **Major** | 0.70 – 0.90 | Regional impact. Reshapes factions, settlements, or regions. |
| **Defining** | 0.90 – 1.00 | Civilisational impact. Permanent scars, turning points, era boundaries. |

Where any chapter uses an alternative tier name (e.g., "Moderate"), it maps to the range above by its numeric value, and the names in this table are authoritative.

Gravity influences simulation priority.

---

# 20.14 Gravity And Processing

Gravity determines processing attention.

High gravity:

Frequent evaluation.

Low gravity:

Compression.

Archiving.

Reduced simulation cost.

This enables scalability.

---

# 20.15 Gravity And Memory

Memory systems use gravity.

High-gravity memories persist.

Low-gravity memories decay.

The two systems reinforce one another.

---

# 20.16 Gravity And Consequences

Consequences inherit gravity.

Example:

King assassinated.

High gravity.

Political instability.

Inherited gravity.

Civil conflict.

Inherited gravity.

Gravity propagates through consequence chains.

---

# 20.17 Gravity Decay

Gravity naturally decreases.

The canonical decay function is exponential, with a half-life determined by the event's **peak tier** (the highest tier the event ever reached):

```
G(t) = G_peak × 0.5^(t / half_life)
```

Where `t` is elapsed simulation time since the event, and `half_life` is:

| Peak Tier | Half-Life (simulation time) |
|-----------|------------------------------|
| Negligible | 3 days |
| Minor | 30 days |
| Significant | 1 year |
| Major | 10 years |
| Defining | 100 years (see 20.18 – may be exempt entirely) |

Decay is recomputed lazily – when the Gravity Governance Layer (Chapter 26) reads an event's gravity, it applies the decay function to the stored peak value rather than mutating gravity every tick.

Connectivity slows decay: each new event that links to an existing event (Chapter 22 causality chains) resets the elapsed-time clock by 25% of the time since the last reference. Heavily referenced history stays heavy.

Examples of natural fade:

Minor scandals.

Short-term shortages.

Routine disputes.

Most events fade.

This is healthy.

---

# 20.18 Gravity Persistence

Some events resist decay.

Examples:

Wars.

Revolutions.

Founding myths.

Trauma.

These events continue influencing reality.

---

# 20.19 Gravity Amplification

Events can gain gravity over time.

Example:

Minor corruption.

↓

Systemic corruption.

↓

Government crisis.

↓

Revolution.

Gravity increases through consequences.

---

# 20.20 Gravity Collapse

Events can lose relevance rapidly.

Example:

Brief rumour disproven.

Temporary inconvenience resolved.

Not all events deserve permanence.

---

# 20.21 Relationship Gravity

Relationships possess gravity.

Examples:

Casual acquaintance.

Low gravity.

Lifelong partner.

High gravity.

Relationship gravity influences behaviour.

---

# 20.22 NPC Gravity

Not all actors matter equally.

Examples:

Random traveller.

Low gravity.

Faction founder.

High gravity.

Gravity influences simulation investment.

---

# 20.23 Settlement Gravity

Settlements possess gravity.

Examples:

Tiny outpost.

Low gravity.

Regional capital.

High gravity.

Gravity affects processing priority.

---

# 20.24 Faction Gravity

Faction influence creates gravity.

Examples:

Local gang.

Regional power.

Empire.

Scale affects impact.

Impact affects gravity.

---

# 20.25 Information Gravity

Information possesses gravity.

Examples:

Tavern gossip.

Low gravity.

Evidence of conspiracy.

High gravity.

Information gravity affects spread and persistence.

---

# 20.26 Pressure Gravity

Pressures possess gravity.

Examples:

Minor shortage.

Low gravity.

Approaching famine.

High gravity.

Gravity influences simulation attention.

---

# 20.27 Historical Gravity

History accumulates gravity.

Repeated events strengthen significance.

Patterns matter.

Examples:

Single riot.

Low gravity.

Decades of unrest.

High gravity.

---

# 20.28 Gravity Networks

Important events connect.

Example:

```text id="i7z8kp"
War
↓
Debt
↓
Political unrest
↓
Leadership change
↓
Reform movement
```

Connected events reinforce one another.

This creates gravity clusters.

---

# 20.29 Gravity Clusters

Clusters emerge when multiple high-gravity systems interact.

Examples:

War.

Economic collapse.

Political crisis.

Migration.

Clusters often produce historical turning points.

---

# 20.30 Gravity And Narrative

Narrative attention should follow gravity.

Not the reverse.

The simulation determines importance.

The renderer observes importance.

This protects simulation-first design.

---

# 20.31 Gravity And Discovery

Players naturally discover high-gravity events more frequently.

Not because the system favours them.

Because they influence more systems.

This creates realistic visibility.

---

# 20.32 Gravity And Compression

Compression decisions should use gravity.

Low gravity:

Compress aggressively.

High gravity:

Retain detail.

This is essential for long-term scalability.

---

# 20.33 Relevance Decay

Gravity directly powers Relevance Decay.

States transition:

```text id="vwxq6s"
Active
↓
Relevant
↓
Dormant
↓
Archived
```

Gravity determines transition speed.

---

# 20.34 Historical Echoes

Some low-activity events retain gravity.

Examples:

Ancient wars.

Founding myths.

Religious origins.

Historical echoes continue influencing identity.

---

# 20.35 Resurfacing

Dormant events may return.

Examples:

Old crime discovered.

Historical grievance revived.

Lost technology recovered.

Gravity determines resurfacing probability.

---

# 20.36 The Gravity Integrity Rule

Gravity affects attention.

Gravity never affects truth.

An archived event remains true.

Even if nobody cares anymore.

Truth and relevance remain separate.

---

# 20.37 The Dead Gravity Test

Ask:

Why does this still matter?

Who is affected?

What systems connect to it?

What would change if it disappeared?

If no answers exist:

Gravity should decay.

---

# 20.38 The Living World Test

Remove the player.

Advance time.

Do major events remain influential?

Do minor events fade?

Do important histories persist?

Do forgotten histories remain recoverable?

If yes:

Context Gravity is functioning.

---

# 20.39 The Scalability Doctrine

A world can only grow if importance is selective.

Context Gravity provides that selectivity.

Without it:

History becomes noise.

With it:

History becomes structure.

---

# 20.40 Final Doctrine

Truth persists.

Relevance changes.

Context Gravity determines what continues to matter.

The simulation remembers everything important.

The simulation compresses everything unimportant.

History remains intact.

Processing remains manageable.

A living world is not defined by remembering everything equally.

A living world is defined by knowing what still matters.

# 20.41 Gravity As The Master Retention System

Context Gravity is the sole arbiter of what the simulation retains, compresses, archives, or forgets.

All other retention systems (Memory Decay, Chapter 12; Event Compression, Chapter 22) derive their behaviour from Gravity.

Rules:

1. **Memory decay half‑life** (Chapter 12) = `base_half_life / (gravity + ε)`, where `base_half_life` is a configurable constant (e.g., 30 days). Higher gravity → much longer retention.

2. **Compression threshold** (Chapter 22): Only events with gravity below a dynamic threshold are eligible for summarisation. The threshold is `max(0.05, global_average_gravity * 0.5)`. This ensures that during high‑gravity periods (wars, crises), even minor events are retained longer.

3. **Archival trigger**: An event is automatically archived when:
   - Its gravity has been below 0.05 for 30 consecutive simulation days, AND
   - No active consequence or delayed consequence references it.

4. **Overriding rule**: If any other chapter (e.g., Chapter 12, Chapter 22) conflicts with the above, this section takes precedence. Gravity decides. Memory and compression obey.

This unification prevents three separate retention systems from fighting each other. Reality remembers what gravity says is worth remembering.

END OF CHAPTER 20

CANONICAL VERSION

# CHAPTER 21

# SCAR THEORY

## Status

Canonical

This chapter defines how the Dice Reaction Story Engine preserves the long-term effects of history.

If Chapter 18 explains consequences, Chapter 19 explains delayed consequences, and Chapter 20 explains relevance over time, Chapter 21 explains permanence.

Not all consequences disappear when resolved.

Some become scars.

Scars are the enduring marks left by history.

A world without scars cannot feel alive.

A person without scars cannot feel real.

A civilisation without scars cannot possess identity.

Scar Theory governs:

* Long-term world change
* Lasting psychological effects
* Historical persistence
* Cultural memory
* Settlement identity
* Faction identity
* Trauma systems
* Recovery systems
* Historical continuity
* World character

This chapter is one of the primary mechanisms through which history becomes visible.

---

# 21.1 Core Doctrine

History leaves marks.

This is the central doctrine.

Events end.

Consequences resolve.

Scars remain.

The simulation should never ask:

"What happened?"

The simulation should ask:

"What remains because it happened?"

That remainder is the scar.

---

# 21.2 Definition

A scar is a persistent alteration caused by a resolved consequence.

The original event may be over.

The scar remains.

Examples:

Destroyed trust.

Battlefield ruins.

National trauma.

Changed laws.

Religious traditions.

Generational hatred.

Scars are history made visible.

---

# 21.3 Why Scars Matter

Without scars:

The world heals too perfectly.

Actions lose meaning.

History loses weight.

Identity becomes shallow.

Scars ensure that history continues influencing the future.

---

# 21.4 Event → Consequence → Scar

The full chain is:

```text id="scar01"
Event
↓
Consequence
↓
Resolution
↓
Scar
↓
Future Behaviour
```

Most simulations stop at consequence.

Dice Reaction continues into scar formation.

---

# 21.5 Scar Formation

Not every consequence becomes a scar.

Scar formation depends upon:

Intensity.

Duration.

Impact.

Memory.

Symbolic value.

Identity disruption.

The greater these factors:

The greater the chance of scar formation.

---

# 21.6 Minor Scars

Examples:

Embarrassing memory.

Small reputation loss.

Brief financial setback.

Minor scars fade quickly.

They rarely alter identity.

---

# 21.7 Moderate Scars

Examples:

Business failure.

Divorce.

Major injury.

Public humiliation.

Moderate scars influence future decisions.

---

# 21.8 Major Scars

Examples:

War trauma.

Political collapse.

Mass migration.

Economic depression.

Major scars reshape systems.

---

# 21.9 Defining Scars

Examples:

Civilisational collapse.

Founding revolution.

Religious schism.

Extinction-level disaster.

Defining scars shape generations.

---

# 21.10 Physical Scars

Physical scars alter environments.

Examples:

Battlefields.

Cratered cities.

Collapsed bridges.

Abandoned mines.

Environmental damage.

Physical scars make history visible.

---

# 21.11 Psychological Scars

Psychological scars alter behaviour.

Examples:

Fear.

Distrust.

Obsession.

Grief.

Trauma.

Psychological scars influence future choices.

---

# 21.12 Social Scars

Examples:

Broken communities.

Family feuds.

Ethnic tensions.

Generational distrust.

Social scars often outlive participants.

---

# 21.13 Political Scars

Examples:

Constitutional reforms.

Authoritarian systems.

Power-sharing agreements.

Political taboos.

Politics frequently preserves historical scars.

---

# 21.14 Economic Scars

Examples:

Persistent poverty.

Debt culture.

Resource dependency.

Trade distrust.

Economic scars influence generations.

---

# 21.15 Cultural Scars

Examples:

Traditions.

Memorial days.

Religious practices.

National narratives.

Cultural scars shape identity.

---

# 21.16 Informational Scars

Examples:

Legends.

Warnings.

Historical lessons.

Institutional procedures.

Information often preserves scars.

---

# 21.17 Relationship Scars

Relationships accumulate scars.

Examples:

Betrayal.

Abandonment.

Humiliation.

Loss.

Trust may recover.

The scar remains.

---

# 21.18 Family Scars

Families transmit scars.

Examples:

Old feuds.

Inherited fears.

Generational trauma.

Family myths.

Scars can outlive the original event.

---

# 21.19 Settlement Scars

Settlements remember through scars.

Examples:

Destroyed district.

Defensive walls.

Memorials.

Economic decline.

Settlement identity often emerges from scars.

---

# 21.20 Faction Scars

Factions carry historical wounds.

Examples:

Lost war.

Failed revolution.

Leadership betrayal.

Religious split.

Faction behaviour is heavily influenced by scars.

---

# 21.21 Civilisational Scars

Entire civilisations can scar.

Examples:

Plagues.

World wars.

Mass migrations.

Technological disasters.

These scars reshape history.

---

# 21.22 Scar Persistence

Scars persist longer than consequences.

Consequences resolve.

Scars remain embedded.

Persistence varies by significance.

---

# 21.23 Scar Decay

Some scars fade.

Examples:

Minor disputes.

Short-term hardship.

Local controversies.

Not all scars remain forever.

---

# 21.24 Permanent Scars

Some scars never disappear.

Examples:

Founding events.

National trauma.

Identity-forming moments.

Permanent scars become part of historical structure.

---

# 21.25 Scar Visibility

Scars may be:

Visible.

Partially visible.

Hidden.

Not all scars are obvious.

Many exist beneath the surface.

---

# 21.26 Hidden Scars

Examples:

Suppressed trauma.

Institutional distrust.

Cultural fear.

Historical resentment.

Hidden scars often create delayed instability.

---

# 21.27 Scar Reactivation

Old scars may reopen.

Examples:

Historical grievance revived.

Old battlefield rediscovered.

Past betrayal repeated.

Scars can regain active influence.

---

# 21.28 Scar Reinforcement

Repeated experiences strengthen scars.

Example:

Repeated invasions.

↓

Increased cultural fear.

↓

Stronger defensive identity.

Patterns matter.

---

# 21.29 Scar Mitigation

Scars may soften.

Examples:

Reconciliation.

Prosperity.

Education.

Cooperation.

Healing is possible.

Erasure is not.

---

# 21.30 Healing Doctrine

Healing changes influence.

Not history.

The event remains true.

The scar remains real.

Its behavioural impact changes.

---

# 21.31 Scar Inheritance

Scars transfer across generations.

Examples:

Stories.

Education.

Tradition.

Family culture.

Institutions.

History survives through inheritance.

---

# 21.32 Scar Symbolism

Some scars become symbols.

Examples:

Monuments.

Flags.

Anniversaries.

Ceremonies.

Symbols preserve memory.

---

# 21.33 Scar Geography

Landscapes remember.

Examples:

Mass graves.

Ruins.

Sacred sites.

Battlefields.

The world itself can carry scars.

---

# 21.34 Scar And Identity

Identity emerges partly from scars.

Examples:

Individuals.

Families.

Settlements.

Factions.

Nations.

Scars help answer:

Who are we?

---

# 21.35 Scar And Behaviour

Scars influence future decisions.

Examples:

Fear creates caution.

Humiliation creates ambition.

Loss creates protection.

Behaviour emerges from remembered pain.

---

# 21.36 Scar And Context Gravity

Scars possess gravity.

High-gravity scars persist.

Low-gravity scars fade.

Chapter 20 directly governs scar longevity.

---

# 21.37 Scar And Memory

Scars rely upon memory.

Without memory:

No scar can persist.

Chapter 12 and Chapter 21 are tightly linked.

---

# 21.38 The Dead Scar Test

Ask:

What remains?

Who changed?

How has behaviour altered?

What evidence survives?

If these questions cannot be answered:

The scar system is incomplete.

---

# 21.39 The Living World Test

Remove the player.

Advance decades.

Can past events still be observed?

Can old wounds still influence behaviour?

Can history still be discovered?

If yes:

Scar Theory is functioning.

---

# 21.40 Final Doctrine

Events end.

Consequences resolve.

Scars remain.

Scars are the mechanism by which history becomes visible.

Scars shape identity.

Scars shape behaviour.

Scars shape civilisation.

A living world is not defined by what happened yesterday.

A living world is defined by what still matters because of yesterday.

END OF CHAPTER 21

CANONICAL VERSION

# CHAPTER 22

# EVENT SOURCING

## Status

Canonical

This chapter defines the technical backbone of historical truth within the Dice Reaction Story Engine.

If Chapter 3 defines State Is Truth, and Chapter 4 defines how reality changes, and Chapter 18 defines the Consequence Ledger, then Chapter 22 defines how we know what changed, why it changed, and in what order.

Event Sourcing is the mechanism that makes traceability possible.

Without Event Sourcing:

- Causality becomes guesswork.
- Delayed consequences become unreliable.
- Historical layering becomes impossible.
- Debugging becomes archaeology.

This chapter governs:

- Immutable event logs
- State reconstruction
- Causal traceability
- Event summarization
- Log compression
- Temporal queries
- Historical replay
- Consequence verification

All future systems that depend on knowing what happened when must conform to this chapter.

---

# 22.1 Core Doctrine

**Reality changes through events.**

**Events are immutable.**

**State is derived from events.**

This reverses the traditional database model.

Traditional model:

```text
State
↓
Update
↓
New State
(Old state lost)
```

Event Sourcing model:

```text
Event
↓
Event
↓
Event
↓
State (derived)
```

Nothing is ever deleted.

Everything is recorded.

State is merely the current projection of history.

---

# 22.2 Definition

An event is an immutable record of a state change.

Every event must contain:

- **Timestamp** – When it occurred.
- **Actor** – Who caused it (player, NPC, faction, settlement, environment).
- **Action** – What type of change occurred.
- **Before** – Previous state reference (or snapshot).
- **After** – New state values.
- **Causality link** – Which prior event(s) caused this one.
- **Gravity** – Initial weight (from Context Gravity).

Events are never modified.

Events are never deleted.

Events are only appended.

---

# 22.3 Why Event Sourcing Exists

Without immutable events:

- Traceability fails.
- Delayed consequences cannot be reliably triggered.
- Historical layering collapses.
- Bugs corrupt state permanently.
- The world cannot be rewound or debugged.

Event Sourcing provides:

- Perfect audit trail.
- Ability to replay history.
- Ability to reconstruct any past state.
- Ability to verify consequence chains.
- Natural foundation for delayed consequences.

---

# 22.4 The Immutability Principle

Once written, an event never changes.

If a correction is needed:

- Write a new event that supersedes or compensates.
- Never edit the original.

Example:

```text
Event 42: Bridge collapsed.
Event 43: Bridge repaired. (Supersedes)
```

The collapse remains true.

The repair is also true.

History is preserved.

---

# 22.5 Event Types

Every event belongs to a category.

## State Mutation Events

Direct changes to world state.

Examples:

- NPC moves.
- Food stock changes.
- Relationship value shifts.
- Building destroyed.

---

## Consequence Events

Events generated by the Consequence Ledger.

Examples:

- Delayed consequence activates.
- Pressure threshold exceeded.
- Scar forms.

---

## Actor Action Events

Events caused by intentional behaviour.

Examples:

- Player attacks.
- NPC trades.
- Faction declares war.

---

## Environmental Events

Events caused by natural systems.

Examples:

- Weather changes.
- Crop grows.
- River floods.

---

## Meta Events

Events about events.

Examples:

- Event summarization.
- Archival.
- Gravity update.

---

# 22.6 Event Structure

Every event conforms to a standard schema.

```text
{
  "id": "unique identifier",
  "timestamp": "simulation time",
  "actor_type": "player|npc|faction|settlement|environment|system",
  "actor_id": "identifier of actor",
  "action_type": "category of change",
  "before_snapshot_ref": "optional reference",
  "after_state_delta": "what changed",
  "caused_by": ["event_id", ...],
  "gravity": 0.0 ... 1.0,
  "compressed": false|true,
  "archived": false|true
}
```

The schema is mandatory.

Extensions per action type are permitted.

---

# 22.7 The Causality Chain

Events form directed acyclic graphs (DAGs).

```text
Event A (harvest fails)
    ↓
Event B (food shortage begins)
    ↓
Event C (prices rise)
    ↓
Event D (riots begin)
```

Every event (except initial conditions) has at least one cause.

Causality chains are traversable.

This enables:

- "Why did X happen?" queries.
- Root cause analysis.
- Consequence verification.

---

# 22.8 State Reconstruction

State is not stored directly.

State is rebuilt by replaying events.

Procedure:

```text
Start with initial state.
Apply events in chronological order.
Current state = result.
```

This is computationally expensive for full rebuilds.

Therefore: **Snapshots** are permitted.

---

# 22.9 Snapshots

A snapshot is a compressed representation of state at a specific event.

Snapshots are stored periodically.

Recovery procedure:

```text
Load latest snapshot.
Apply events after snapshot.
```

Snapshots are derived from events.

Snapshots never replace events.

---

# 22.10 Event Summarization

Immutable event logs grow without bound.

Compression is required.

Summarization replaces a sequence of low-gravity events with a single higher-level event.

Example:

```text
Events 100-200: Daily bread purchases.
Summarized as:
Event 201: Regular trade occurred.
```

Rules:

- Causality must be preserved.
- Truth must remain intact.
- Original events may be archived (not deleted).
- Summarization must be recorded as a meta-event.

---

# 22.11 Summarization Thresholds

Gravity determines when summarization occurs.

Negligible gravity events:

- Summarized daily.

Minor gravity events:

- Summarized weekly.

Significant gravity events:

- Never summarized (retain individually).

Major and Defining events:

- Never summarized.
- Never archived.

---

# 22.12 Archival

Events older than a certain threshold may be moved to cold storage.

Archived events remain true.

Archived events are not loaded during normal simulation.

Archived events can be restored if needed.

Archival is recorded as a meta-event.

---

# 22.13 Temporal Queries

The event log must support:

- "What was the state at time T?"
- "What events occurred between T1 and T2?"
- "What caused event E?"
- "What consequences followed event E?"
- "What is the current gravity of event E?"

These queries are the foundation of Discovery Architecture.

---

# 22.14 The Replay Capability

Developers (and potentially players with appropriate access) may replay history.

Replay shows:

- State evolution.
- Causality chains.
- Consequence propagation.
- Delayed consequence activation.

Replay is essential for debugging.

Replay is essential for player discovery mechanics.

---

# 22.15 Event Sourcing And The Player Loop

The player's discovery loop depends entirely on event sourcing.

When the player investigates:

```text
Observe a current state.
Query events that led to that state.
Follow causality chains.
Discover root causes.
```

Without event sourcing:

Discovery becomes superficial.

With event sourcing:

Discovery becomes archaeology.

---

# 22.16 Event Sourcing And Delayed Consequences

Delayed consequences are events waiting to happen.

The event log tracks dormant consequences as pending events.

When trigger conditions are met:

- The pending event is written.
- Causality links to the originating event.

This guarantees traceability across time.

---

# 22.17 The Immutable Truth Doctrine

Once an event is written:

- It is true.
- It cannot be erased.
- It can be superseded by later events.
- It can be summarized.
- It can be archived.

But it can never be made false.

This is the foundation of historical integrity.

---

# 22.18 The Event Sourcing Test

Ask:

- Can every state change be traced to an event?
- Does every event have a cause (except initial conditions)?
- Can the current state be reconstructed from events?
- Can past states be reconstructed?
- Are events never modified after writing?

If yes: Event Sourcing is functioning.

If no: The system has failed.

---

# 22.19 Final Doctrine

State is truth.

Events are the path to truth.

Without events:

Truth is asserted.

With events:

Truth is proven.

Event Sourcing is not optional.

Event Sourcing is the foundation upon which all historical systems rest.

END OF CHAPTER 22

CANONICAL VERSION

# CHAPTER 23

# HISTORICAL LAYERING

## Status

Canonical

This chapter defines how the Dice Reaction Story Engine transforms raw events into meaningful history.

If Chapter 22 defines how events are recorded, Chapter 23 defines how events become structure.

Raw events are noise.

Layered history is signal.

The purpose of Historical Layering is to organise events into coherent narratives of change.

This chapter governs:

- Historical strata
- Era formation
- Turning points
- Historical momentum
- Civilisational memory
- Deep time simulation
- Historical discovery
- Legend formation

All long-term simulation systems depend upon this chapter.

---

# 23.1 Core Doctrine

**History is not a list of events.**

**History is a layered structure.**

Events accumulate.

Layers form.

Strata compress.

The present rests upon the past.

This is not metaphor.

This is simulation architecture.

---

# 23.2 Definition

A historical layer is a period of simulation time with coherent characteristics.

Layers are defined by:

- Start event.
- End event (or ongoing).
- Dominant pressures.
- Dominant actors.
- Dominant scars.
- Gravity weight.

Layers may be:

- Seconds.
- Days.
- Years.
- Centuries.
- Eras.

The scale depends on significance.

---

# 23.3 Why Layering Exists

Without layering:

- History is flat.
- Ancient events drown in noise.
- Civilisational memory is impossible.
- Long-term patterns are invisible.
- Deep time cannot be simulated.

With layering:

- History has depth.
- Ancient events can retain significance.
- Patterns emerge across centuries.
- Civilisations remember.

---

# 23.4 Historical Strata

Strata are layers that have closed.

A stratum is a completed historical period.

Examples:

- The Founding Era (Year 0-50).
- The War Years (Year 51-60).
- The Reconstruction (Year 61-80).
- The Golden Age (Year 81-120).

Strata are immutable.

Strata can be queried.

Strata form the backbone of historical identity.

---

# 23.5 Active Layer

The present is always an active layer.

Active layers are still accumulating events.

Active layers may:

- End (becoming a stratum).
- Merge with adjacent layers.
- Fragment.
- Transform.

The simulation continuously evaluates layer boundaries.

---

# 23.6 Layer Formation

Layers form when:

- Dominant pressures shift.
- Key actors change.
- Major scars appear.
- Turning points occur.
- Stability regimes change.

The simulation does not manually assign layers.

Layers emerge from event patterns.

---

# 23.7 Layer Detection

The simulation should detect layer boundaries algorithmically.

Signals:

- Change in settlement growth rate.
- Change in dominant faction.
- Major war begins or ends.
- Economic regime shift.
- Cultural identity change.
- Technological transition.

When multiple signals coincide:

A layer boundary is declared.

---

# 23.8 Era Formation

Multiple strata group into eras.

Example:

```text
The Imperial Era
├── Founding Strata
├── Expansion Strata
├── Peak Strata
└── Decline Strata
```

Eras are larger than strata.

Eras are detected similarly.

Eras are useful for civilisational memory.

---

# 23.9 Turning Points

A turning point is an event that creates a new layer.

Turning points are:

- High gravity.
- High connectivity.
- Often defining scars.

Examples:

- Empire falls.
- Religion founded.
- Technology invented.
- Natural disaster reshapes region.

Turning points are recorded as layer boundaries.

---

# 23.10 Historical Momentum

Layers possess momentum.

Momentum answers:

"What direction was history moving?"

Momentum emerges from:

- Consequence chains.
- Pressure trends.
- Scar accumulation.

High momentum layers are difficult to redirect.

Low momentum layers are volatile.

---

# 23.11 Layer Gravity

Layers possess gravity.

Ancient high-gravity layers continue influencing the present.

Examples:

- Founding myth of a nation.
- Ancient religious schism.
- Millennia-old trade route.

Layer gravity decays slowly.

Layer gravity can be reactivated.

---

# 23.12 Layer Accessibility

Not all layers are equally accessible.

Recent layers:

- High detail.
- Many events.
- Many witnesses.

Ancient layers:

- Summarized.
- Possibly legendary.
- Few direct witnesses.

Accessibility affects discovery.

---

# 23.13 Civilisational Memory

Civilisations remember through layers.

Examples:

- National origin story.
- Historical grievances.
- Golden age nostalgia.
- Past trauma.

Civilisational memory is stored in layer summaries.

Not raw events.

---

# 23.14 Deep Time Simulation

Dice Reaction may simulate centuries or millennia.

Deep time requires aggressive layering.

Procedure:

```text
Simulate at high resolution for active layer.
Compress ancient layers into strata.
Strata become summaries.
Summaries become myths.
```

Truth remains.

Detail decreases.

---

# 23.15 Legend Formation

When an event passes beyond living memory:

It may become legend.

Legends are:

- True in essence.
- Possibly distorted in detail.
- Symbolically significant.

Legend formation is a natural compression mechanism.

---

# 23.16 Historical Queries

The layering system must support:

- "What era was this settlement founded?"
- "What were the dominant pressures during the War Years?"
- "What scars remain from the Collapse?"
- "How did the current faction identity form?"

These queries power historical discovery.

---

# 23.17 Layering And Discovery Architecture

Players should discover history by penetrating layers.

```text
Present observation.
↓
Recent past (1-10 years).
↓
Decades past.
↓
Generations past.
↓
Mythic past.
```

Each layer deeper requires more investigation.

This creates natural difficulty scaling.

---

# 23.18 Layer Conflict

Different layers may conflict.

Example:

Official history of a war (layer A).

Veteran memories (layer B).

Archaeological evidence (layer C).

The simulation tracks all layers.

Truth remains objective.

Perception varies by layer.

---

# 23.19 Rewriting History

Actors may attempt to revise historical layers.

Examples:

- Propaganda.
- Destruction of records.
- Creation of false evidence.

The simulation must allow:

- Attempts at revision.
- Discovery of revision.
- Preservation of original events.

Truth remains.

Belief may change.

---

# 23.20 The Historical Layering Test

Ask:

- Can the simulation identify layer boundaries?
- Can ancient history be queried?
- Does high-gravity history still influence the present?
- Can players discover deeper layers through investigation?

If yes: Historical Layering is functioning.

---

# 23.21 Final Doctrine

History is not flat.

History is stratified.

The present stands upon layers of the past.

Each layer contributed scars.

Each layer contributed identity.

Each layer contributed pressure.

A living world is not defined by what happened this year.

A living world is defined by what happened across centuries, and how it still matters today.

END OF CHAPTER 23

CANONICAL VERSION

# CHAPTER 24

# DISCOVERY ARCHITECTURE

## Status

Canonical

This chapter defines how the player learns about the world.

If Chapter 22 defines how reality is recorded, and Chapter 23 defines how history is layered, Chapter 24 defines how the player penetrates those layers.

Discovery is the player's interface to causality.

This is one of the most important gameplay chapters in the entire Bible.

Most games deliver information.

Dice Reaction requires discovery.

The distinction is the difference between passive consumption and active investigation.

This chapter governs:

- Investigation systems
- Rumour systems
- Witness systems
- Evidence systems
- Lead generation
- Information synthesis
- Hypothesis formation
- Confirmation mechanics
- Discovery loops
- Knowledge representation

Every player-facing system that conveys information must conform to this chapter.

---

# 24.1 Core Doctrine

**Discovery is the player's interface to causality.**

The simulation knows reality.

The player does not.

The gap between them is the discovery space.

The engine's job is to provide tools to cross that gap.

Not to eliminate the gap.

---

# 24.2 Definition

Discovery is the process by which the player transforms observation into knowledge.

Stages:

```text
Observe a state.
↓
Investigate surrounding events.
↓
Gather evidence and witness testimony.
↓
Form hypotheses.
↓
Test hypotheses.
↓
Confirm knowledge.
↓
Act on knowledge.
```

Each stage is a mechanical system.

---

# 24.3 The Knowledge Gap

At any moment:

- The simulation knows everything.
- The player knows almost nothing.

Examples of player knowledge states:

**Unknown** – No information exists in player memory.

**Rumour** – Unconfirmed information received.

**Claim** – Information from a source (possibly unreliable).

**Evidence** – Physical or recorded information.

**Confirmed** – Verified through multiple independent sources.

**Truth** – Matches simulation reality.

The player may believe something that is not true.

The player may disbelieve something that is true.

This is intentional.

---

# 24.4 Observation

The most basic discovery mechanism.

The player sees:

- Current state.
- Visible actors.
- Visible objects.
- Visible scars.
- Visible events.

Observation alone reveals little causality.

Observation raises questions.

Investigation answers them.

---

# 24.5 The Observation Doctrine

Observation reveals state.

Not history.

Not causes.

Not future.

The player sees:

A collapsed bridge.

Not:

Why it collapsed.

Who collapsed it.

When it collapsed.

That requires investigation.

---

# 24.6 Investigation

Investigation is the active pursuit of information.

Investigation mechanics include:

- Questioning NPCs.
- Examining locations.
- Searching records.
- Following leads.
- Connecting evidence.

Investigation is not a skill check.

Investigation is a process.

---

# 24.7 Leads

A lead is a piece of information that points to another piece of information.

Leads are the atomic unit of investigation.

Examples:

- "The blacksmith saw something."
- "The mayor has a document."
- "The old tower might contain clues."
- "Someone fled north."

Leads can be:

- Strong (reliable source).
- Weak (rumour).
- False (misinformation).
- Outdated.

Leads connect to evidence or witnesses.

---

# 24.8 Lead Generation

Leads emerge from:

- Witness statements.
- Rumours.
- Document examination.
- Environmental clues.
- NPC behaviour patterns.
- Contradictions.

The simulation generates leads naturally.

Not through scripted quest markers.

---

# 24.9 Witness Systems

Witnesses are NPCs who possess information.

Witnesses may be:

- Willing.
- Reluctant.
- Fearful.
- Deceptive.
- Mistaken.
- Unaware of their own knowledge.

Witness mechanics:

- Determining who saw what.
- Determining willingness to share.
- Determining reliability.
- Determining what can be offered in exchange.

Witnesses are not quest dispensers.

Witnesses are information sources with their own pressures.

---

# 24.10 Evidence Systems

Evidence is physical or recorded information.

Examples:

- Documents.
- Letters.
- Maps.
- Physical objects.
- Scars.
- Environmental damage.
- Corpses.

Evidence is objective.

Evidence does not lie.

Evidence can be misinterpreted.

---

# 24.11 Evidence Integrity

Evidence can be:

- Intact.
- Damaged.
- Tampered with.
- Forged.
- Destroyed.

The simulation tracks evidence condition.

The player must interpret condition.

Discovery includes realising evidence is unreliable.

---

# 24.12 Rumour Systems

Rumours are unverified information in circulation.

Rumour characteristics:

- May be true, false, or distorted.
- Spread through information networks.
- Change during transmission.
- Have owners (who believe them).
- Have carriers (who spread them).

Players encounter rumours passively.

Verification requires investigation.

---

# 24.13 Information Synthesis

The player collects:

- Observations.
- Witness statements.
- Evidence.
- Leads.
- Rumours.

These pieces must be synthesised.

The engine should assist synthesis through:

- Relationship mapping.
- Timeline visualisation.
- Connection highlighting.

But never provide conclusions.

The player must think.

---

# 24.14 Hypothesis Formation

A hypothesis is a player's proposed explanation.

The engine does not test hypotheses automatically.

The player tests hypotheses through:

- Prediction ("If X is true, then Y should be found").
- Investigation (seeking confirming/disconfirming evidence).
- Action (acting on belief, observing results).

Hypotheses can be wrong.

Wrong hypotheses have consequences.

---

# 24.15 Confirmation

Knowledge becomes confirmed when:

- Multiple independent sources agree.
- Evidence supports it.
- Predictions succeed.
- No contradictory evidence exists.

Confirmation is never 100% in a living world.

New evidence may overturn confirmed knowledge.

This is intentional.

---

# 24.16 The Discovery Loop

The complete player loop:

```text
Observe anomaly or curiosity.
↓
Generate questions.
↓
Follow leads.
↓
Gather evidence and witness testimony.
↓
Form hypothesis.
↓
Test hypothesis.
↓
Act on knowledge (or revise hypothesis).
↓
Consequences create new anomalies.
```

This loop never ends.

This loop replaces traditional quest design.

---

# 24.17 Discovery Versus Exposition

Forbidden: Exposition.

The player is never told:

- "The king was assassinated."
- "The bridge collapsed because of bandits."
- "The merchant is lying."

Allowed: Discovery.

The player may learn:

- By finding the king's body.
- By interviewing witnesses.
- By examining the bridge and finding axe marks.
- By noticing the merchant's inconsistent story.

Exposition is narrative.

Discovery is gameplay.

---

# 24.18 The Reward Structure

Traditional rewards:

- Experience points.
- Loot.
- Quest completion.

Discovery rewards:

- Understanding.
- Predictive power.
- Agency.
- Ability to act effectively.
- Satisfaction of solving.

Understanding is its own reward.

---

# 24.19 Discovery And Failure

The player may:

- Fail to discover.
- Discover incorrectly.
- Act on false beliefs.
- Miss critical information.

This is not a bug.

This is realism.

The world continues regardless.

The player learns from failure.

---

# 24.20 Discovery And Replayability

Discovery creates replay value.

Two players may discover different truths.

Two players may hold different beliefs.

Two players may act on different information.

The same world yields different experiences.

---

# 24.21 Discovery Tools

The engine should provide:

- Notebook (player records findings).
- Timeline (events known to player).
- Relationship map (known connections).
- Evidence inventory.
- Lead list.

These tools are player-owned.

Not character-owned.

The player learns.

Not just the character.

---

# 24.22 Information Asymmetry

Different players (or characters) may know different things.

The simulation tracks:

- What the player knows (out-of-character).
- What the character knows (in-character).

These may differ.

The engine should respect both.

---

# 24.23 The Discovery Test

Ask:

- Can the player learn something the engine never told them?
- Does investigation yield information not provided by exposition?
- Can the player be wrong?
- Can the player discover through multiple independent paths?
- Is the world discoverable without handholding?

If yes: Discovery Architecture is functioning.

---

# 24.24 Final Doctrine

Discovery is the player's interface to causality.

The simulation knows.

The player learns.

The gap between them is the game.

Exposition fills the gap with words.

Discovery fills the gap with understanding.

A living world is not defined by what the player is told.

A living world is defined by what the player can discover.

# 24.25 Evidence Persistence Windows

Evidence and witnesses are not permanent. The world changes. Clues decay.

Therefore, every piece of evidence and every witness memory has a **discovery window** – the period during which it can be directly observed.

The discovery window is determined by the gravity of the originating event:

| Event Gravity | Discovery Window (Typical) |
|---------------|----------------------------|
| > 0.8 (Defining) | Decades to centuries |
| 0.5 – 0.8 (Major) | Years |
| 0.2 – 0.5 (Moderate) | Weeks to months |
| < 0.2 (Minor) | Days |

After the discovery window closes:

- Physical evidence degrades (rust, overgrowth, decay) or is removed (cleaned up, rebuilt).
- Witness memories fade or become unreliable (distorted, merged with other events).
- The event may still be discoverable through **secondary evidence** – records, rumours, legends, or scars – but not through direct observation.

The simulation tracks evidence degradation as part of the World Tick (Chapter 5). When a player investigates, the simulation checks whether the discovery window is still open. If closed, the player may find only degraded or secondary evidence.

This rule balances Discovery Architecture (Chapter 24) with Independent Motion (Chapter 5). The world does not wait for the player, but neither does it erase history without trace.

END OF CHAPTER 24

CANONICAL VERSION

# CHAPTER 25

# ACTOR RESOLUTION SCALING

## Status

Canonical

This chapter defines how the Dice Reaction Story Engine simulates thousands of actors without computational explosion.

If Chapter 5 defines the World Heartbeat, Chapter 10 defines NPC architecture, and Chapter 20 defines Context Gravity, Chapter 25 defines *how much* of that architecture is actually processed at any given moment.

The core tension is:

Every actor *could* be simulated at full depth.

But full depth for every actor is impossible.

Therefore, **resolution must scale**.

Resolution is not truth.

Truth persists.

Resolution changes.

This chapter governs:

- Actor fidelity tiers
- Tick frequency per tier
- Memory depth per tier
- Goal depth per tier
- Relationship depth per tier
- Decision complexity per tier
- Promotion triggers
- Demotion rules
- Cost limits per tier
- Dynamic resolution adjustment

Every actor in the simulation—NPC, faction, settlement, institution—must conform to this scaling hierarchy.

---

# 25.1 Core Doctrine

**Resolution is not truth.**

**Truth persists.**

**Resolution changes.**

A character does not stop existing when simulated at low resolution. Their truth remains: their identity, core drives, major memories, key relationships, and long‑term goals are preserved. Only the *detail* and *frequency* of their simulation are reduced.

The simulation must never delete an actor. It may only demote them to a lower resolution tier.

---

# 25.2 Definition

Actor Resolution Scaling is the dynamic adjustment of simulation fidelity based on current relevance.

Relevance is determined by:

- Distance to player (spatial proximity).
- Faction importance (Context Gravity of the actor’s faction).
- Current involvement in active events.
- Presence in player memory or active investigation.
- Pressure horizon (actor is part of an emerging crisis).
- Context Gravity of the actor’s recent actions.

Higher relevance → higher resolution.

Lower relevance → lower resolution.

---

# 25.3 The Resolution Tiers

Every actor belongs to exactly one tier at any moment.

Movement between tiers is automatic, governed by promotion triggers and demotion rules.

```text
Hero Actors
    ↓
Active Actors
    ↓
Relevant Actors
    ↓
Dormant Actors
    ↓
Archived Actors
```

---

## 25.3.1 Hero Actors

**Definition:** Directly involved in the player’s current scene, or essential to the immediate critical path of an active investigation.

**Tick frequency:** Every micro‑heartbeat (seconds to minutes).

**Memory depth:** Full detail. Every significant event remembered. Emotional weight tracked.

**Goal depth:** Full hierarchy (core drive → life goal → strategic goals → operational goals → immediate actions). All conflicts evaluated.

**Relationship depth:** Full network. All direct relationships maintained. Trust, loyalty, resentment values updated in real time.

**Decision complexity:** Full utility or GOAP evaluation. All options considered. Full context integration (weather, fatigue, stress, witnesses).

**Promotion triggers:** Player enters same location; actor becomes target of player action; actor’s faction becomes the centre of an active event chain; actor is named in a high‑gravity rumour the player is investigating.

**Demotion rules:** Player leaves the location AND no active event involving the actor remains unresolved AND no high‑gravity consequence points to the actor within the next simulation hour.

**Cost limits:** Maximum 16 Hero Actors at any time (configurable). Exceeding this forces immediate demotion of the lowest‑gravity Hero to Active.

---

## 25.3.2 Active Actors

**Definition:** Within the player’s current region (same settlement or adjacent area), or part of an active event that the player is aware of, or a key member of a faction that is currently making strategic decisions affecting the player.

**Tick frequency:** Every local heartbeat (hours).

**Memory depth:** Major and defining memories fully retained. Moderate memories summarised (e.g., “had several positive trades with X” instead of each transaction). Minor memories discarded unless recently reinforced.

**Goal depth:** Core drive and life goal retained. Strategic goals retained. Operational goals summarised (e.g., “working to expand business” instead of “contact supplier, negotiate price, arrange delivery”). Immediate actions not simulated.

**Relationship depth:** Only identity‑level relationships (family, lifelong allies/rivals) and relationships directly involving the player or player’s faction. Other relationships reduced to reputation scores.

**Decision complexity:** Simplified utility using only core drives and strategic goals. No per‑action deliberation; behaviour is selected from a predefined set of high‑level activities (e.g., trade, patrol, rest, travel) with probability weighted by pressure.

**Promotion triggers:** Player enters same settlement; actor becomes witness to an event the player investigates; actor’s delayed consequence becomes imminent (trigger condition expected within 24h).

**Demotion rules:** Player leaves settlement AND no active event involving the actor AND actor’s faction is not currently making strategic decisions affecting the player. After 24 hours of inactivity, demote to Relevant.

**Cost limits:** No hard limit, but total Active actors should be ≤200 for typical hardware. Beyond that, the system uses Context Gravity to select which Active actors remain Active; the rest are forced to Relevant.

---

## 25.3.3 Relevant Actors

**Definition:** Not currently near the player, but known to the player by name or reputation; or a member of a faction the player has interacted with; or an actor whose past actions have created a scar that remains discoverable.

**Tick frequency:** Every regional heartbeat (days).

**Memory depth:** Only defining memories retained. Major memories compressed into a single “character summary” (e.g., “fought in the war, lost a son, became bitter”). Moderate and minor memories are lost unless they have become part of reputation.

**Goal depth:** Only core drive and life goal retained. No strategic or operational goals. The actor is assumed to be pursuing their life goal through background activity, but the specific steps are not simulated.

**Relationship depth:** Only identity‑level relationships. All other relationships reduced to a reputation score for each faction/group. Family connections preserved.

**Decision complexity:** No active decisions. Behaviour is determined by a simple rule set based on core drive and life goal, with a small random factor to simulate background activity. For example: a merchant with “wealth” drive will slowly accumulate resources; a guard with “safety” drive will patrol.

**Promotion triggers:** Player enters the actor’s settlement; actor’s name appears in a rumour the player actively investigates; actor’s faction becomes the target of player action; a delayed consequence involving the actor enters its final warning period.

**Demotion rules:** Player leaves settlement AND no active event involving the actor AND actor’s name not mentioned in player investigation for 7 days. After 7 days, demote to Dormant.

**Cost limits:** No hard limit. Expected range: 500–2000 Relevant actors depending on world size.

---

## 25.3.4 Dormant Actors

**Definition:** No longer relevant to current gameplay, but still potentially recoverable. The player may have heard the name, but has no active interest. The actor is not part of any active pressure that affects the player.

**Tick frequency:** Every macro heartbeat (weeks or months). Many Dormant actors may be advanced in batches.

**Memory depth:** Only a “historical note” – identity, core drive, and a short list of defining memories (up to 3) that could become relevant again (e.g., “was betrayed by the player’s faction”). All other memory deleted.

**Goal depth:** Only core drive retained. The actor’s life goal is assumed to be pursued in a generic way, not simulated.

**Relationship depth:** No active relationships. Only relationship records that involve the player or player’s faction are kept as “historical facts” (e.g., “the player owes me a favour”). All other relationship data deleted.

**Decision complexity:** None. The actor does not act independently. They only react if a trigger (e.g., the player enters their settlement, or a delayed consequence activates) promotes them to a higher tier.

**Promotion triggers:** Player enters the actor’s settlement; a rumour involving the actor reaches the player; a delayed consequence involving the actor activates; the actor’s faction becomes relevant due to world events.

**Demotion rules:** After 30 days without any interaction or mention, the actor is automatically archived.

**Cost limits:** No effective limit. Thousands or tens of thousands of Dormant actors can be stored as lightweight records.

---

## 25.3.5 Archived Actors

**Definition:** Actors who have not been relevant for an extended period, or whose death was so long ago that no living character remembers them directly (only through records or legends). Archived actors are part of history, not active simulation.

**Tick frequency:** Never. Archived actors are not processed by the heartbeat.

**Memory depth:** Only a historical record: name, lifespan, core drive, and a short summary (1‑2 sentences) of their most defining actions. This summary is generated during archiving.

**Goal depth:** None.

**Relationship depth:** None, except as referenced in the historical records of other actors (e.g., “killed by X” becomes part of X’s historical note).

**Decision complexity:** None.

**Promotion triggers:** An archived actor may be restored to Dormant only if a major historical discovery (e.g., finding a lost journal, a witness’s testimony) reopens their story, AND that discovery becomes part of player investigation. This should be extremely rare.

**Demotion rules:** After 90 days of Dormant status with no activity, an actor is automatically archived.

**Cost limits:** Effectively unlimited. Archived actors are stored in cold storage (disk, not memory).

---

# 25.4 Resolution Scaling And Truth

The most important rule of this chapter:

**Lower resolution does not change truth.**

If an actor has a defining memory of being betrayed by the player, that memory remains true even when the actor is Dormant. When the actor is promoted back to Active, that memory must be fully restored, with all its emotional weight and consequences.

Implementation requirement:

- The actor’s persistent state (identity, core drive, defining memories, key relationships, major scars) is stored in a **core record** that never changes with resolution.
- Higher‑resolution tiers add *ephemeral* data (short‑term memory, current goals, detailed relationship states) that can be recomputed from the core record and the event log if lost.
- Promotion from a lower tier loads or recomputes the ephemeral data from the event log, ensuring no loss of causal continuity.

---

# 25.5 Promotion Triggers – Evaluation

Promotion triggers are evaluated:

- Every heartbeat for actors within one tier of the player’s current focus (Hero, Active).
- Every regional heartbeat for Relevant actors.
- Every macro heartbeat for Dormant actors.

To avoid a cascade of promotions every tick, the simulation uses a **lazy evaluation** model: an actor is only checked for promotion when the relevant conditions (e.g., player enters settlement, a named rumour appears) occur, or when a scheduled global scan (every N ticks) runs.

---

# 25.6 Demotion Rules – Timing

**Canonical clock:** All durations, rates, decay constants, and grace periods in this Bible are expressed in **simulation time** unless explicitly marked "real time". During burn-in acceleration (Chapter 30.7), all simulation-time rates scale with the acceleration factor automatically – a 7-day grace period elapses in 7 simulated days regardless of how many real seconds that takes.

Demotion is never immediate after conditions are lost. Grace periods prevent thrashing:

- Hero → Active: 5 minutes after player leaves location, unless an unresolved event ties the actor to the player.
- Active → Relevant: 24 hours after last interaction, unless the actor’s faction is still strategic.
- Relevant → Dormant: 7 days after last mention.
- Dormant → Archived: 30 days after last activity.

Demotion is processed during the world tick, after all promotion evaluations.

---

# 25.7 Cost Limits – Hard Ceilings

The simulation may enforce hard ceilings per tier to protect performance.

If a ceiling is reached:

- No new promotions into that tier are allowed until existing actors are demoted.
- Among candidates for promotion, the ones with highest Context Gravity are promoted first; the rest remain in the lower tier.
- If the ceiling is still exceeded (e.g., too many Hero actors because of a large battle), the simulation degrades gracefully by temporarily reducing tick frequency for all Hero actors (e.g., from micro to local) until the ceiling is no longer exceeded.

Default hard ceilings (configurable):

- Hero: 16
- Active: 200
- Relevant: 2000
- Dormant: no ceiling
- Archived: no ceiling

---

# 25.8 Resolution Scaling And Context Gravity

Context Gravity (Chapter 20) is the primary input to promotion decisions.

An actor’s current gravity score determines the urgency of promotion:

- Gravity > 0.8 → eligible for Hero.
- Gravity > 0.5 → eligible for Active.
- Gravity > 0.2 → eligible for Relevant.
- Gravity ≤ 0.2 → remains Dormant or Archived.

Gravity is recomputed when an actor is involved in a new event, or periodically during global scans.

---

# 25.9 Resolution Scaling And Memory Systems

Memory depth per tier (25.3) interacts with Chapter 12.

When an actor is demoted, the simulation **summarises** their recent memories into the higher‑level memory format of the lower tier. This summarisation must preserve causality: if a memory influenced a decision that later had a consequence, that link must remain traceable through the event log.

When an actor is promoted, the simulation **reconstructs** detailed memory from the event log for the period since they were last at that tier. This is computationally expensive but occurs relatively rarely.

---

# 25.10 The Actor Resolution Test

For any given actor at any time, ask:

- What tier are they in?
- Is that tier justified by current relevance (distance, faction gravity, event involvement)?
- Are their tick frequency, memory depth, goal depth, relationship depth, and decision complexity correctly set for that tier?
- If promoted, can their missing higher‑tier data be reconstructed from the event log?
- If demoted, has their memory been summarised without losing causality?

If yes: Resolution scaling is functioning.

---

# 25.11 Final Doctrine

Resolution is not truth.

Truth persists.

Resolution changes.

Every actor exists, always.

But the cost of simulating them changes with their relevance.

Hero actors live in full detail.

Active actors live in high detail.

Relevant actors live in medium detail.

Dormant actors sleep, waiting to wake.

Archived actors become history, but never cease to be true.

A living world is not defined by simulating everything equally.

A living world is defined by simulating everything *appropriately*.

Actor Resolution Scaling is the mechanism that makes that possible.

END OF CHAPTER 25

CANONICAL VERSION

# CHAPTER 26

# GRAVITY GOVERNANCE LAYER

## Status

Canonical

This chapter defines the master authority that determines what the simulation retains, compresses, archives, or forgets.

If Chapter 20 defines Context Gravity, Chapter 12 defines Memory Decay, and Chapter 22 defines Event Compression, Chapter 26 unifies them under a single governance layer.

Without a governance layer:

- Gravity wants to keep everything important.
- Memory decay wants to fade old information.
- Compression wants to summarise aggressively.
- Three systems conflict, creating unpredictable retention.

The Gravity Governance Layer resolves all conflicts. It is the sole decision‑maker for:

- Which events remain active.
- Which events are summarised.
- Which events are archived.
- Which memories are retained or decayed.
- Which actors are promoted or demoted (in coordination with Chapter 25).

All other retention systems must defer to this layer.

---

# 26.1 Core Doctrine

**Gravity governs retention.**

Not memory decay.

Not compression heuristics.

Gravity.

The Governance Layer computes a single **retention score** for every event, memory, and actor. That score determines what happens to it over time.

Retention = f(gravity, age, connectivity, player relevance)

If retention falls below a threshold, the item is summarised, archived, or deleted (if safe to delete).

This chapter replaces ad‑hoc rules in Chapters 12, 20, and 22 with a unified, deterministic system.

---

# 26.2 Definition

The **Gravity Governance Layer** is a centralised service that:

- Maintains a global retention score for every event, memory, and actor.
- Periodically recalculates scores based on gravity decay, new connections, and player relevance.
- Triggers summarisation, archival, or memory decay when scores cross thresholds.
- Coordinates with Actor Resolution Scaling (Chapter 25) to promote/demote actors.

The Governance Layer is not a separate simulation. It runs as part of the World Tick (Chapter 5), typically every macro heartbeat (weekly) for low‑gravity items, and every regional heartbeat (daily) for high‑gravity items.

---

# 26.3 Retention Score Formula

For any item (event, memory, or actor), the retention score `R` is computed as:

```
R = G × (1 + 0.5 × C) × (1 + 0.5 × P) × D / 2.25
```

Where:

- `G` = current Context Gravity (0–1, from Chapter 20, with decay per 20.17 applied at read time).
- `C` = connectivity bonus (0–1). Number of other active items that reference this item, normalised (0 references = 0, 10+ references = 1).
- `P` = player relevance (0–1). How recently the player encountered or investigated this item: `P = e^(-days_since_last_encounter / 7)`. **If no player exists (burn-in, headless simulation) or the player has never encountered the item, P = 0 and the term resolves to 1 – player relevance is a bonus, never a gate.** This guarantees world history is retained on its own gravity during burn-in (Chapter 30.7).
- `D` = duration factor (0.8–1.2). Recent items are neutral; old low-gravity items decay slightly faster; ancient high-gravity items gain a preservation bonus:

```
If G ≥ 0.7:  D = min(1.2, 1 + age_in_years / 500)     (ancient defining history is protected)
If G < 0.7:  D = max(0.8, 1 - age_in_years / 200)      (ordinary old history fades faster)
```

- The `/ 2.25` term normalises the maximum product (1 × 1.5 × 1.5 × 1.2 / 2.25 = 1.2, clamped) so that clamping to 0–1 only affects a narrow top band and ordering among high-retention items is preserved.

`R` is clamped to 0–1.

---

# 26.4 Retention Thresholds

The Governance Layer uses fixed thresholds to decide what happens to an item.

| Retention Range | Action |
|----------------|--------|
| 0.8 – 1.0 | Keep fully active. No compression. No summarisation. |
| 0.6 – 0.8 | Keep active. Eligible for lightweight summarisation (metadata only, not content). |
| 0.4 – 0.6 | Compress. Replace with a summary event (see Chapter 22). Original event archived but recoverable. |
| 0.2 – 0.4 | Archive. Move to cold storage. Only a one‑line historical note remains in active state. |
| 0.0 – 0.2 | Eligible for deletion (only if it has no causal links to any active event or consequence). |

These thresholds apply to events and memories. For actors, retention score determines resolution tier (see 26.7).

---

# 26.5 Governance Override Rules

The Governance Layer is the master, but certain items are **protected** from summarisation or archival:

- **Defining scars** (Chapter 21) with gravity > 0.7 are never archived, only summarised at most.
- **Active delayed consequences** (Chapter 19) that have not yet triggered are kept active regardless of retention score.
- **Player‑created events** (actions directly taken by the player) have a minimum retention of 0.5 for 30 days.
- **Events that are part of an active investigation** (player has leads pointing to them) are temporarily boosted to retention ≥ 0.6 until the investigation closes.

All other items obey the thresholds exactly.

---

# 26.6 Recalculation Frequency

The Governance Layer does not recompute every item every tick.

Instead:

- **High gravity (G > 0.6)** : recompute every regional heartbeat (daily).
- **Medium gravity (0.3 ≤ G ≤ 0.6)** : recompute every macro heartbeat (weekly).
- **Low gravity (G < 0.3)** : recompute every month of simulation time, or when referenced by a new event.

Recalculation is performed in a background thread, prioritising items with the highest current retention (because they are most likely to cross thresholds).

---

# 26.7 Coordination with Actor Resolution Scaling

Actor Resolution Scaling (Chapter 25) uses retention scores to help determine promotion/demotion:

- Actor with retention > 0.7 → eligible for Hero tier (if also meets spatial/event criteria).
- Actor with retention > 0.5 → eligible for Active tier.
- Actor with retention > 0.3 → eligible for Relevant tier.
- Actor with retention ≤ 0.3 → Dormant or Archived.

The Governance Layer communicates retention scores to the Actor Resolution system once per macro heartbeat.

---

# 26.8 Memory Decay Integration

Chapter 12 (Memory Systems) no longer has its own decay formula. Instead:

- Memory retention is governed by the same retention score as the event it recalls.
- When an event’s retention score falls below 0.4, the memory of that event in NPCs is automatically **compressed** (specific details lost, general gist retained).
- When an event’s retention score falls below 0.2, the memory is **archived** (only a note that “something happened” remains, with no emotional weight).

This ensures memory decay is consistent with event gravity, not an independent process.

---

# 26.9 Compression Integration

Chapter 22 (Event Sourcing) still defines *how* compression works, but the *decision* to compress is made by the Governance Layer based on retention thresholds.

When an event’s retention score falls into the 0.4–0.6 range, the Governance Layer signals the Event Compression system to summarise it. The summary’s gravity is set to the original event’s gravity × 0.8 (to reflect loss of detail).

---

# 26.10 Archival Integration

Archival (Chapter 22) is triggered when retention score falls below 0.2. The Governance Layer moves the event to cold storage. The event remains true and recoverable, but is not loaded during normal simulation.

---

# 26.11 The Governance Test

For any event, memory, or actor at any time, ask:

- Does its retention score correctly reflect its gravity, connectivity, player relevance, and age?
- Is it in the correct retention band (active, compressible, archivable, deletable)?
- If it crossed a threshold, was the appropriate action taken (compression, archival, demotion)?
- Are protected items (player actions, active investigations) never archived prematurely?

If yes: The Gravity Governance Layer is functioning.

---

# 26.12 Final Doctrine

Three systems cannot govern retention.

One system must.

Gravity is the master.

The Governance Layer is the executor.

It decides what lives.

What fades.

What dies.

What becomes legend.

A living world is not defined by remembering everything.

It is defined by remembering what still matters, and letting go of what does not.

The Governance Layer makes that possible.

END OF CHAPTER 26

CANONICAL VERSION

# CHAPTER 27

# NPC DECISION ENGINE (UTILITY AI)

## Status

Canonical

This chapter defines how NPCs select actions in the Dice Reaction Story Engine.

If Chapter 10 defines NPC architecture and Chapter 11 defines goals, Chapter 27 defines the decision mechanism that turns goals, pressures, stress, relationships, memories, and resources into concrete behaviour.

The engine does not script NPC actions.

The engine does not ask an LLM to choose actions (LLM is for prose only, see Chapter 31).

The engine uses **Utility AI** – a deterministic, numerically‑driven decision system that evaluates possible actions and selects the one with the highest utility.

Utility AI is:

- Predictable (same inputs → same output, except for small randomness).
- Explainable (the engine can state why an action was chosen).
- Performant (pure arithmetic, no LLM latency).
- Compatible with Actor Resolution Scaling (lower tiers use simplified utility).

This chapter governs:

- Action space definition
- Utility calculation formula
- Input weighting (pressures, goals, stress, relationships, memories, resources)
- Action selection (max utility, with tie‑breaking)
- Randomness and personality
- Decision frequency per resolution tier

Every NPC action must be chosen by this engine (or a simplified version for lower tiers).

---

# 27.1 Core Doctrine

**An NPC chooses the action that maximises expected utility.**

Utility is a numeric score (0–100) representing how well an action serves the NPC’s current needs, goals, and pressures. It is computed as a **weighted average** of dimension scores (27.4), which guarantees the 0–100 bound regardless of how many dimensions apply or how large their weights grow.

The engine does not ask “What would be interesting?” or “What would a human do?” It asks: “Given this NPC’s state, which action has the highest utility?”

Behaviour emerges from arithmetic.

---

# 27.2 Definition

**Utility** = weighted sum of expected outcomes across multiple evaluation dimensions.

Each possible action is evaluated across the following dimensions:

- **Survival** – Does this action help the NPC survive (food, water, shelter, safety)?
- **Goal progression** – Does this action move the NPC closer to their current goals (life, strategic, operational)?
- **Pressure relief** – Does this action reduce the most intense pressure the NPC feels?
- **Stress reduction** – Does this action lower stress (e.g., resting, seeking help)?
- **Relationship impact** – Does this action improve relationships with important actors (or harm enemies)?
- **Resource gain/loss** – Does this action acquire needed resources or avoid losing them?
- **Memory avoidance** – Does this action avoid repeating a traumatic memory (fear)?

Each dimension is scored 0–100, then multiplied by a **weight** that depends on the NPC’s current state (e.g., starving → survival weight = 100; well‑fed → survival weight = 10).

---

# 27.3 Action Space

Every NPC has a set of possible actions defined by their role, capabilities, and context.

Examples:

- Move to location
- Rest
- Eat (if food available)
- Trade (if merchant)
- Attack (if enemy present)
- Flee
- Speak (to another NPC or player)
- Work (perform profession)
- Steal (if desperate or criminal)
- Hide
- Investigate (follow a lead)
- Request help

The action space is **dynamic** – only actions that are currently possible (validation per Chapter 4) are considered.

For Hero and Active actors, the action space is fully enumerated (typically 5–20 actions). For Relevant actors, actions are simplified (e.g., “work”, “rest”, “socialise”). For Dormant actors, no actions are chosen – they only react to triggers.

---

# 27.4 Utility Calculation – Base Formula

For each possible action `a`:

```
U(a) = Σ (dimension_score(d) × weight(d)) / Σ weight(d)
```

Where `d` ranges over the evaluation dimensions (Survival, Goal progression, Pressure relief, Stress reduction, Relationship impact, Resource gain/loss, Memory avoidance).

Because each `dimension_score` is bounded 0–100 and the sum is divided by the total weight, `U(a)` is always bounded 0–100. Weights therefore express **relative importance only** – doubling every weight changes nothing, which is the correct property: a starving NPC's survival weight of 200 dominates the average without breaking the scale. The worked example in 27.8 ("Total utility = 85") follows directly from this formula.

## 27.4.1 Dimension Scores

Each dimension score is computed from the action’s expected outcome, normalised to 0–100.

**Survival score** – How much does this action improve the NPC’s survival metrics (food, water, shelter, safety)?  
`Survival_score = (Δ_food × 25) + (Δ_water × 25) + (Δ_shelter × 25) + (Δ_safety × 25)`, each Δ ∈ [-1, 1], clamped to 0–100.

**Goal progression score** – For each active goal, compute how much the action moves the NPC toward that goal. Weighted by goal priority (1–10). Sum and normalise to 0–100.

**Pressure relief score** – Identify the NPC’s highest intensity pressure (0–1). Score = pressure intensity reduction × 100. (e.g., pressure from hunger = 0.8, eating reduces it by 0.6 → score = 60).

**Stress reduction score** – If action reduces stress (e.g., rest, talk to friend), score = stress reduction × 100. Max 100.

**Relationship impact score** – For each relationship that would change, compute Δ (‑100 to +100) weighted by relationship importance (1‑10). Sum and normalise to 0–100.

**Resource gain/loss score** – Net resource value change, expressed in **Standard Value Units (SVU)**, normalised to 0–100 with diminishing returns. One SVU is defined as the value of one day of basic food for one adult, evaluated at the local settlement's current scarcity (Chapter 8). SVU is an internal accounting unit, not a currency; in-world currencies, where they exist, are priced in SVU by local market state. This anchors all resource comparisons to survival value, which is the only universal denominator across cultures and economies.

**Memory avoidance score** – If the action would repeat a situation similar to a negative defining memory, score is low (0–20). If it avoids that situation, score is high (80–100). Calculated by matching current context (location, actor type, activity) to memory signatures.

---

## 27.4.2 Dimension Weights

Weights are dynamic and determined by the NPC’s current state.

| Dimension | Base weight (normal state) | Modifiers |
|-----------|----------------------------|------------|
| Survival | 100 | Multiply by (1 + pressure_intensity) for each survival need. Starvation → 200. |
| Goal progression | 50 | Multiply by goal priority / 10. Life goal → 100; minor operational → 10. |
| Pressure relief | 30 | Multiply by pressure intensity. |
| Stress reduction | 20 | Multiply by (stress / 100). High stress → up to 80. |
| Relationship impact | 40 | Multiply by relationship importance to affected actor. |
| Resource gain/loss | 25 | Multiply by resource scarcity (1 + (max_need - current)/max_need). |
| Memory avoidance | 15 | Multiply by trauma intensity (0‑2) if memory is traumatic. |

Weights are recalculated every decision cycle.

---

# 27.5 Action Selection

Once utility is calculated for all possible actions:

1. Add small whim noise to every utility before comparison: `U'(a) = U(a) + noise(-0.5, +0.5)`. Noise simulates momentary whim and is drawn from the **seeded simulation RNG** (Chapter 30.10) – never from an unseeded source. This preserves full determinism: the same world seed produces the same whims, the same decisions, the same history.
2. Select the action with the highest `U'(a)`.
3. If two or more actions are tied after noise (within 0.01), break ties using **personality bias**: each NPC has a fixed preference order over action types (e.g., prefers social over combat), generated once from the seeded RNG at NPC creation.
4. If still tied, choose the action that appears first in a canonical ordering (deterministic).

The noise range (±0.5) is deliberately smaller than the tie window used in earlier drafts; noise is applied *before* tie detection, not after, so ordering is coherent.

The chosen action is then passed to the Simulation Loop (Chapter 4) for validation, context evaluation, resolution, and consequence generation.

---

# 27.6 Decision Frequency and Actor Resolution

Per Chapter 25 (Actor Resolution Scaling), decision frequency varies by tier:

| Tier | Decision frequency | Utility complexity |
|------|-------------------|--------------------|
| Hero | Every micro‑heartbeat (seconds) | Full utility (all dimensions, full action space) |
| Active | Every local heartbeat (hours) | Full utility, but action space may be simplified (e.g., no per‑minute choices) |
| Relevant | Every regional heartbeat (days) | Simplified utility (only Survival, Goal progression, Pressure relief); action space reduced to 3‑5 generic actions (work, rest, move) |
| Dormant | No decisions | Only react to triggers (e.g., player enters settlement) then promote |
| Archived | Never | N/A |

Relevant actors may use a **cached decision** – they repeat the same action for the entire period unless a trigger (e.g., new pressure, player arrival) forces a recalculation.

---

# 27.7 Integration with Goals, Pressure, Stress, Relationships, Memories, Resources

The NPC Decision Engine reads from:

- **Goals** (Chapter 11): active goals and their priorities.
- **Pressure** (Chapter 6): current pressure intensities.
- **Stress** (Chapter 14): current stress level (0–100).
- **Relationships** (Chapters 13 and 29): trust, loyalty, fear, resentment scores for each relevant actor.
- **Memories** (Chapters 12 and 28): retrieved memories that affect the Memory avoidance dimension.
- **Resources** (Chapter 8): current inventory, wealth, food, etc.
- **Retention and promotion state** (Chapters 25 and 26): the actor's resolution tier determines decision frequency and utility complexity.

All these are stored in **state** (Chapter 3). The utility function reads state directly.

---

# 27.8 Explainability

For debugging and player discovery (if they investigate an NPC’s motives), the engine can generate an **explanation** of why an action was chosen:

```text
“The guard chose to attack because:
- Survival (threat to self): 90
- Goal progression (protect the city): 80
- Pressure relief (fear of attack): 85
- Relationship impact (loyalty to captain): 70
Total utility = 85 (attack) vs 20 (flee) vs 10 (do nothing).”
```

This explanation is derived from the utility calculation and can be presented narratively (via LLM) without modifying state.

---

# 27.9 The Decision Engine Test

For any NPC at any time, ask:

- Is the set of possible actions correctly derived from state (location, inventory, abilities)?
- Are utility scores computed using the current weights (pressure, stress, goal priorities)?
- Is the action with the highest utility selected (with tie‑breaking and small noise)?
- Does the chosen action proceed to the Simulation Loop (Validation → Context → Resolution)?
- Can the decision be explained in terms of the utility dimensions?

If yes: The NPC Decision Engine is functioning.

---

# 27.10 Final Doctrine

NPCs do not act because a script tells them to.

NPCs act because utility arithmetic tells them to.

Pressure creates weight.

Weight creates utility.

Utility creates action.

Action creates consequence.

Consequence creates history.

The engine does not simulate intelligence. It simulates **decision‑making under pressure**.

Utility AI is the arithmetic of survival, desire, fear, and loyalty.

It is predictable enough to be trusted.

It is flexible enough to be surprising.

A living world is not defined by clever scripts.

A living world is defined by NPCs who consistently choose what is best for them, given what they know and what they feel.

END OF CHAPTER 27

CANONICAL VERSION

# CHAPTER 28

# MEMORY RETRIEVAL SYSTEM

## Status

Canonical

This chapter defines how NPCs recall past experiences when making decisions.

If Chapter 12 defines what memories exist, and Chapter 27 defines how NPCs choose actions, Chapter 28 defines which memories are retrieved to influence those choices.

Memory is not a database.

Memory is not a video recording.

Memory is a retrieval process.

An NPC does not remember everything they ever experienced. They remember what is **relevant**, **recent**, **emotional**, and **cued** by the current situation.

The Memory Retrieval System determines:

- Which memories enter working memory for decision‑making.
- How strongly each retrieved memory influences utility calculations.
- How retrieval probability decays over time.
- How emotional weight and trauma bias recall.

This chapter is essential for realistic, non‑omniscient NPCs.

---

# 28.1 Core Doctrine

**An NPC remembers what matters to them, right now.**

Memory retrieval is not random. It is a function of:

- **Recency** – How recently the event occurred.
- **Emotional weight** – How intense the feeling was (fear, joy, grief, anger).
- **Relevance** – How similar the current situation is to the original event.
- **Repetition** – How many times similar events have occurred.
- **Personality** – Some NPCs dwell on the past; others live in the present.

The engine does not simulate perfect recall. It simulates **biased, context‑sensitive remembering**.

---

# 28.2 Definition

**Memory retrieval** is the process of selecting a subset of an NPC’s stored memories to be active during decision‑making.

Retrieved memories are placed into **working memory** – a temporary buffer that exists only for the current decision cycle.

Working memory size is limited (typically 3–7 memories per decision). This prevents utility calculations from being overwhelmed by irrelevant history.

After the decision is made, working memory is cleared.

---

# 28.3 Retrieval Probability

For each stored memory `m` in an NPC’s memory store, the probability of being retrieved into working memory is:

```
P(m) = (R × E × C × P_base) / Σ(all memories)
```

Where:

- `R` = recency factor (0–1). Exponential decay: `e^(-days_since_event / half_life)`, where half_life depends on memory weight (major memories: 30 days; minor: 3 days).
- `E` = emotional weight (0–1). Directly from Chapter 12 memory weight (Defining=1.0, Major=0.7, Moderate=0.4, Minor=0.1).
- `C` = cue relevance (0–1). Similarity between the current context (location, actors present, activity type, time of day) and the original event’s context. Computed via weighted feature matching.
- `P_base` = base retrieval probability (0.01 for minor memories, 0.5 for major, 0.9 for defining). Ensures even low‑probability memories have a chance.

The sum of `P(m)` over all memories is normalised so that exactly `working_memory_size` memories are retrieved (selected via weighted random sampling).

---

# 28.4 Retrieval Cues

Cues are extracted from the current decision context:

- **Location** – Where the NPC is (e.g., market, forest, castle). Exact location match gives cue = 1.0; nearby or similar location (e.g., any market) gives 0.5.
- **Actors present** – Who the NPC can see. Presence of a person involved in the memory gives cue = 1.0; presence of a member of the same faction gives 0.3.
- **Activity type** – What the NPC is currently doing or considering (e.g., fighting, trading, talking). If the memory’s activity matches, cue = 1.0; similar (e.g., negotiating vs trading) gives 0.6.
- **Time of day / season** – If the memory occurred at a similar time (e.g., both at night), cue = 0.2.
- **Current pressure type** – If the memory involves the same pressure (e.g., hunger), cue = 0.4.

The total cue relevance `C` is the weighted average of all active cues, with location and actors present weighted highest.

---

# 28.5 Emotional Weight and Retrieval Bias

High‑emotional‑weight memories (trauma, love, rage) are retrieved more often than neutrally weighted memories, even if they are older.

The emotional bias multiplier is applied to `E` in the probability formula:

- Defining memories: multiplier 2.0.
- Major memories: multiplier 1.5.
- Moderate: 1.0.
- Minor: 0.5.

This ensures that traumatic events continue to influence behaviour long after they occur – exactly as intended in Chapter 14 (Stress & Breaking Points) and Chapter 21 (Scar Theory).

---

# 28.6 Repetition and Pattern Memory

Multiple similar events are not stored individually. They are **compressed** into a single **pattern memory** (see Chapter 12.13).

Pattern memory retrieval probability is increased by the number of original events compressed:

```
P(pattern) = P_base × (1 + log10(count))
```

Where `count` is how many individual events were summarised. This makes repeated experiences (e.g., being cheated by merchants many times) more influential than a single event.

---

# 28.7 Working Memory and Decision Influence

Once memories are retrieved into working memory, they influence the NPC Decision Engine (Chapter 27) through the **Memory avoidance score** and **Relationship impact score**.

Specifically:

- For each retrieved memory that involves an actor present in the current scene, the Relationship impact score is adjusted (e.g., a memory of betrayal reduces trust).
- For each retrieved memory that involves a similar action or outcome, the Memory avoidance score is calculated (e.g., a memory of being injured while fighting a bear makes “attack bear” less appealing).

The retrieved memories are also available for **narrative rendering** – when an LLM generates dialogue or internal monologue, it can reference the retrieved memories to explain behaviour.

---

# 28.8 Forgetting and Retrieval Failure

Forgetting is **decided** by the Gravity Governance Layer (Chapter 26) and **executed** here. This section defines the mechanism, not an independent authority.

When the Governance Layer's retention score for a memory's originating event falls below 0.2 (per 26.4 and 26.8), the memory is moved to **archived memory** (Chapter 12.14). Chronically low retrieval probability (below 0.01 for 30+ days) is reported to the Governance Layer as a *connectivity signal* – an unretrieved memory accrues no new references, so its retention score falls naturally and archival follows through the standard 26.4 thresholds.

Archived memories are not retrieved unless a specific trigger (e.g., finding a related object) promotes them back, which restores them through the standard promotion path.

There is exactly one forgetting authority in the engine: Chapter 26. This section, 12.19, and 26.8 describe the same pipeline from three vantage points. The world does not remember everything forever – but what is important persists.

---

# 28.9 Memory Retrieval and Actor Resolution

Per Chapter 25 (Actor Resolution Scaling), retrieval depth varies by tier:

| Tier | Working memory size | Retrieval frequency | Cue detail |
|------|---------------------|---------------------|-------------|
| Hero | 7 memories | Every decision | Full cue extraction |
| Active | 5 memories | Every decision | Simplified cues (location, actors only) |
| Relevant | 3 memories | Every decision, but cached for 24h | Only location and primary actor |
| Dormant | 1 memory | Only on promotion to higher tier | N/A |

This ensures that performance scales with relevance. A distant NPC does not waste cycles retrieving memories from decades ago.

---

# 28.10 Memory Retrieval Example

**Scenario:** A guard (NPC) is currently standing at the city gate at night. A stranger (player) approaches.

**Stored memories of the guard:**

1. (Major) – Three months ago, a stranger attacked him at the same gate at night. Emotional weight 0.7.
2. (Moderate) – One month ago, he helped a lost traveller, who thanked him. Emotional weight 0.4.
3. (Minor) – A week ago, he ate a good meal. Emotional weight 0.1.

**Current cues:** Location = city gate (match memory 1 and 2), time = night (match memory 1), actor = stranger (match memory 1 and 2, since both involved strangers).

**Retrieval probability (simplified):**
- Memory 1: high recency (3 months = moderate), high emotional weight, strong cue match → probability 0.6.
- Memory 2: medium recency, lower emotion, medium cue match → probability 0.3.
- Memory 3: high recency, low emotion, no cue match → probability 0.01.

**Working memory (size 2):** Memory 1 and Memory 2 are retrieved.

**Decision influence:** The guard’s utility calculation for “let stranger pass” vs “challenge stranger” is influenced by Memory 1 (fear of attack) and Memory 2 (positive outcome of helping). Depending on stress and personality, fear may dominate.

---

# 28.11 The Memory Retrieval Test

For any NPC making a decision, ask:

- Are retrieved memories limited to working memory size (per tier)?
- Does retrieval probability reflect recency, emotional weight, and cue relevance?
- Are high‑emotional‑weight memories (trauma) retrieved more often than neutral ones?
- Are pattern memories (compressed repeated events) retrieved with appropriate bonus?
- Do retrieved memories correctly influence utility calculations (Memory avoidance, Relationship impact)?

If yes: The Memory Retrieval System is functioning.

---

# 28.12 Final Doctrine

Memory is not a library.

Memory is a lens.

The past does not weigh equally on the present.

What is recent, emotional, and similar to now matters most.

What is old, neutral, or irrelevant fades.

The Memory Retrieval System exists not to store history, but to **apply** history to behaviour.

Without retrieval, memory is useless.

With retrieval, memory becomes the ghost that haunts every decision.

A living world is not defined by what happened.

It is defined by what is remembered, right now, in this moment of choice.

END OF CHAPTER 28

CANONICAL VERSION

# CHAPTER 29

# RELATIONSHIP CALCULUS

## Status

Canonical

This chapter defines how the Dice Reaction Story Engine aggregates shared history into actionable relationship values.

If Chapter 13 defines relationships as histories, and Chapter 28 defines how memories are retrieved, Chapter 29 defines how those histories become **trust**, **loyalty**, **fear**, and **resentment** – the four core relationship dimensions that directly influence behaviour.

A relationship is not a single number.

A relationship is a vector of these four dimensions.

Each dimension has its own calculus, its own decay rate, and its own influence on the NPC Decision Engine (Chapter 27).

This chapter governs:

- Trust calculation from accumulated positive/negative interactions.
- Loyalty calculation from shared identity, duty, and sacrifice.
- Fear calculation from perceived threat and past harm.
- Resentment calculation from unmet expectations and perceived unfairness.
- Dimension decay and reinforcement.
- Relationship resolution (forgiveness, betrayal, collapse).
- Integration with Memory Retrieval (Chapter 28) and NPC Decision Engine (Chapter 27).

Every NPC’s relationship with every other actor (individual, faction, settlement) is represented by these four scores.

---

# 29.1 Core Doctrine

**A relationship is not a number. A relationship is four numbers.**

Trust, loyalty, fear, and resentment are separate dimensions. They can move independently.

An NPC may:

- Trust someone but not be loyal to them.
- Fear someone while respecting them.
- Resent someone they are still loyal to (family, liege).
- Be loyal to someone they do not trust.

The simulation does not reduce relationships to a single “liking” score. That would be false to human experience.

---

# 29.2 Definition of the Four Dimensions

| Dimension | Definition | Range | Behavioural Influence |
|-----------|------------|-------|------------------------|
| **Trust** | Belief that the other actor will act predictably and not harm the NPC’s interests. | –100 (complete distrust) to +100 (complete trust) | Affects cooperation, information sharing, trade. |
| **Loyalty** | Willingness to sacrifice for or remain committed to the other actor, regardless of short‑term interests. | 0 (no loyalty) to 100 (absolute loyalty) | Affects defence of the other, refusal to betray, following orders. |
| **Fear** | Anticipated harm if the NPC does not comply with the other actor’s wishes. | 0 (no fear) to 100 (paralysing terror) | Affects submission, flight, aggression (as pre‑emptive strike). |
| **Resentment** | Accumulated anger or sense of unfair treatment from the other actor. | 0 (no resentment) to 100 (burning hatred) | Affects willingness to harm, betray, or undermine the other. |

Trust and loyalty are **positive‑valence** dimensions (higher is better for the relationship). Fear and resentment are **negative‑valence** (higher is worse).

---

# 29.3 Trust Calculus

Trust is earned through repeated interactions that demonstrate reliability, honesty, and mutual benefit.

Each interaction that is **observed or experienced** generates a delta to trust:

```
ΔTrust = base_value × weight_trust × (1 + emotional_intensity)
```

Where:

- `base_value` = intrinsic impact of the action type (+10 for fulfilling a promise, –15 for breaking a promise, +5 for honest trade, –10 for lying, +20 for saving life, –30 for betrayal).
- `weight_trust` = how much this NPC values trust (personality factor, 0.5–1.5, default 1.0).
- `emotional_intensity` = from the memory’s emotional weight (0–1), increases impact.

Trust decays over time when not reinforced. Decay rates and the canonical decay function for all four dimensions are defined once, in **29.10**. No per-dimension decay constants are defined elsewhere.

Trust is capped at ±100.

---

# 29.4 Loyalty Calculus

Loyalty is not the same as trust. Loyalty emerges from:

- **Shared identity** – family, faction, nationality, religion. Base loyalty from shared identity = 30–70 depending on cultural strength.
- **Shared hardship** – surviving danger together. Each shared hardship event adds +5 to +20.
- **Duty** – formal obligations (oath, contract, employment). Adds +10 to +40.
- **Sacrifice received** – when the other actor sacrifices for the NPC, loyalty increases significantly (+20 to +50).
- **Sacrifice given** – when the NPC sacrifices for the other, loyalty also increases (sunk cost effect, +5 to +15).

Loyalty decays very slowly (0.001 per day) unless a major betrayal occurs. Betrayal (perceived or real) can reduce loyalty by 30–80 points in a single event.

Loyalty is never negative. It ranges 0–100. An NPC with loyalty 0 feels no obligation; an NPC with loyalty 100 would die for the other.

---

# 29.5 Fear Calculus

Fear is based on:

- **Perceived power differential** – How much more powerful the other actor is (combat ability, wealth, political influence). `power_diff = min(1, max(0, (other_power - self_power) / 100))`.
- **Past harm received** – Accumulated damage (physical, financial, social) caused by the other, weighted by recency.
- **Credible threats** – Explicit threats from a source the NPC believes capable of carrying them out.
- **Reputation** – The other’s reputation for violence or cruelty.

Fear formula:

```
Fear = (power_diff × 60) + (past_harm_norm × 30) + (threat_credibility × 10)
```

Capped at 0–100.

Fear decays when no new threatening events occur; the rate is defined in 29.10.

High fear (≥ 70) triggers avoidance, submission, or pre‑emptive aggression depending on personality.

---

# 29.6 Resentment Calculus

Resentment accumulates when an actor perceives **unfair treatment** – when the other actor benefits at the NPC’s expense without justification, or when the NPC’s expectations are violated.

Resentment increase formula:

```
ΔResentment = (unfairness_score × 20) + (expectation_violation × 10) - (apology_quality × 15)
```

Where:

- `unfairness_score` = 0–1, how disproportionate the harm was relative to any justification.
- `expectation_violation` = 0–1, how much the action violated the NPC’s expectations of the relationship (high trust makes violation worse).
- `apology_quality` = 0–1, how sincere and costly the other actor’s apology or recompense was.

Resentment decays slowly (rate defined in 29.10) but can persist for years. High resentment (≥ 70) makes the NPC seek revenge, sabotage, or public shaming.

Resentment and loyalty can coexist (e.g., resentful but loyal family member). When resentment exceeds loyalty, betrayal becomes likely.

---

# 29.7 Relationship State and Behavioural Influence

The NPC Decision Engine (Chapter 27) uses these four dimensions to influence:

- **Cooperation** – Positive weight for trust and loyalty; negative weight for fear and resentment.
- **Aggression** – Positive weight for resentment and fear (pre‑emptive) if NPC is aggressive personality; otherwise fear reduces aggression.
- **Deception** – Negative weight for trust (low trust increases lying), positive weight for resentment.
- **Sacrifice** – Positive weight for loyalty only; trust alone does not cause sacrifice.
- **Defection/Betrayal** – Triggered when resentment > loyalty AND opportunity arises.

The exact influence is defined in Chapter 27’s relationship impact score (dimension).

---

# 29.8 Relationship Events and State Changes

Certain events cause **automatic, large shifts** in relationship dimensions:

| Event | Trust Δ | Loyalty Δ | Fear Δ | Resentment Δ |
|-------|---------|-----------|--------|---------------|
| Save life | +30 | +20 | –10 | –20 |
| Kill friend | –50 | –40 | +20 | +50 |
| Break promise | –20 | –10 | 0 | +15 |
| Keep promise | +10 | +5 | 0 | –5 |
| Public humiliation | –15 | –10 | +10 | +30 |
| Apology accepted | +10 | 0 | –5 | –25 |
| Betrayal (major) | –60 | –50 | +20 | +70 |
| Long service reward | +15 | +20 | –5 | –10 |

These are **base values**; emotional intensity and personality multiply them.

---

# 29.9 Relationship Resolution

When a relationship reaches extreme values, special states can trigger:

- **Betrayal** – When resentment > 70 and opportunity arises, NPC may actively work against the other. Betrayal is not automatic; it is a possible action with high utility (if resentment weight is high).
- **Forgiveness** – When the offending actor makes a sincere, costly apology, resentment can drop by 30–50 points. Forgiveness does not erase memory (Chapter 12). The event remains, but its behavioural influence diminishes.
- **Collapse** – When trust < –50 and loyalty < 20, the relationship effectively ends. The NPC will avoid the other and refuse all cooperation.
- **Reconciliation** – Requires repeated positive interactions over a long period (months). Each positive interaction increases trust and decreases resentment by a small amount.

---

# 29.10 Relationship Decay and Neglect

**This section is the single authority for relationship decay.** Sections 29.3–29.6 define how dimensions *change* through events; this section defines how they *drift* through neglect.

Relationships that are not maintained (no interaction) drift toward neutral exponentially:

```
V(t) = V_last × e^(-r × days_since_last_interaction)
```

The exponential form is mandatory. Linear decay (`V × (1 - r × days)`) is forbidden – it crosses zero and inverts the sign of the dimension at long neglect intervals, which is nonsensical (indifference, not inverted feeling, is the limit of neglect).

| Dimension | Decay rate `r` (per simulation day) | Half-life | Notes |
|-----------|-------------------------------------|-----------|-------|
| Trust | 0.005 | ~139 days | Drifts toward 0 from either direction. |
| Resentment | 0.005 | ~139 days | People forget slights. |
| Fear | 0.010 | ~69 days | Fear fades fastest without reinforcement. |
| Loyalty | 0.001 | ~693 days | Loyalty is sticky. |

Identity‑level relationships (family, lifelong oath) use rates ten times slower (half-lives ~10× longer).

Decay is computed lazily at read time from `days_since_last_interaction`, consistent with gravity decay (20.17) – no per-tick mutation of dormant relationships.

---

# 29.11 Group and Faction Relationships

The same calculus applies to relationships between groups (NPC to faction, faction to faction, settlement to settlement).

For group‑level relationships:

- The relationship vector is the **average** of all member relationships, weighted by influence/power of each member.
- When an individual acts, it affects the group‑level relationship (e.g., a merchant’s dishonesty damages the entire guild’s trust with the city).
- Leaders have higher weight in the average.

This ensures that faction reputation (Chapter 16) is grounded in actual interactions, not arbitrary assignment.

---

# 29.12 Integration with Memory Retrieval

**Authority model:** The stored four-dimension vector (29.2) is the canonical relationship state. It is mutated only by events (29.3–29.8) and neglect decay (29.10). It is **never recomputed from working memory** – working memory holds 3–7 sampled items (28.2), and deriving trust from a per-decision random sample would make relationships swing wildly between decisions, violating State Is Truth (Chapter 3).

Memory retrieval (Chapter 28) instead applies a **situational modifier** on top of the stored vector, for the current decision only:

- Each retrieved memory involving the other actor temporarily amplifies the relevant dimension's influence in the Decision Engine's relationship impact score (27.4.1). A retrieved betrayal memory makes resentment weigh heavier *in this decision*; it does not change the stored resentment value.
- The modifier is bounded: retrieved memories may scale a dimension's effective influence by at most ±50%.
- When the decision cycle ends and working memory clears (28.2), the modifier vanishes. The stored vector is untouched.

This produces the intended realism through a clean mechanism: an NPC standing at the gate where they were attacked *feels* the fear more strongly (retrieval modifier) without the engine pretending their underlying relationship changed. Forgetting still matters – when a memory's originating event is archived by the Governance Layer (26.8), its contribution was already baked into the vector at event time, and it simply stops appearing as a situational amplifier.

When no relationship vector exists for an actor (never interacted), the vector defaults to a **baseline** determined by reputation (Chapter 16) and group membership.

---

# 29.13 The Relationship Calculus Test

For any relationship between two actors, ask:

- Are the four dimensions (trust, loyalty, fear, resentment) tracked separately?
- Do interactions produce delta changes consistent with the action types (e.g., betrayal heavily damages trust and loyalty)?
- Do dimensions decay appropriately over time without interaction?
- Do extreme values trigger special states (betrayal, forgiveness, collapse)?
- Does the NPC Decision Engine correctly use these dimensions to influence behaviour?

If yes: The Relationship Calculus is functioning.

---

# 29.14 Final Doctrine

Relationships are not single numbers.

They are four forces.

Trust says: “I believe you.”

Loyalty says: “I stand with you.”

Fear says: “I yield to you.”

Resentment says: “I want to hurt you.”

These forces can point in different directions.

A living world is not defined by who likes whom.

It is defined by the tension between trust and fear, loyalty and resentment.

The Relationship Calculus gives those tensions numbers.

And numbers can be simulated.

END OF CHAPTER 29

CANONICAL VERSION

# CHAPTER 30

# WORLD GENESIS & BURN‑IN

## Status

Canonical

This chapter defines how a new world is born, seeded with history, and made ready for the player.

If earlier chapters define how a living world *runs*, this chapter defines how a living world *starts*.

No world should begin empty.

No world should begin without scars.

No world should begin without pressure, relationships, factions, or history.

The player must enter a reality already in motion – not a sterile sandbox waiting to be filled.

World Genesis is the process of creating that initial, lived‑in state.

This chapter governs:

- Geography generation
- Resource placement
- Settlement spawning
- Faction emergence
- Initial pressure assignment
- Relationship seeding
- Scar generation
- Burn‑in simulation (accelerated history)
- Player start state selection

Every new world must pass through this genesis process before any player enters.

---

# 30.1 Core Doctrine

**A world without history is not alive.**

The player should never be the first person to do anything significant.

Civilisations should have risen and fallen before the player drew breath.

Wars should have been fought. Alliances should have been broken. Loves should have been lost. Scars should have formed.

World Genesis exists to fabricate that history – not as a script, but as a **generative process** that follows the same causal rules as the main simulation.

---

# 30.2 Genesis Phases

The World Genesis process consists of six phases, executed in order:

```text
1. Geography & Resources
2. Settlement Spawning
3. Faction Emergence
4. Initial Pressure & Relationship Seeding
5. Burn‑In Simulation (Accelerated History)
6. Player Start State Selection
```

Each phase feeds into the next. The output of Phase 5 is a fully realised world state with event log, scars, and active pressures – ready for the player.

---

# 30.3 Phase 1 – Geography & Resources

The engine first generates the physical world.

Inputs (configurable):

- World size (e.g., 1000×1000 km, or number of regions)
- Biome distribution (temperate forest, desert, mountains, etc.)
- Resource density and rarity

Process:

1. Generate heightmap (terrain).
2. Generate water bodies (rivers, lakes, coastlines).
3. Place resource nodes: farmland (fertile soil), mineral deposits (ore, stone, coal), forests (wood), water sources, fishing grounds, etc.
4. Assign each resource a quantity and renewal rate.

Output: A map of terrain tiles, each with coordinates, biome, and resource list.

All geography is stored as state (Chapter 3) and can be modified by future events (e.g., deforestation, mining depletion).

---

# 30.4 Phase 2 – Settlement Spawning

Settlements emerge where resources support them.

Process:

1. Identify **habitable zones** (fresh water, arable land, defensible position).
2. Rank locations by **carrying capacity** (max population supported by local resources).
3. Spawn initial settlements at the highest‑ranked locations, one per region.
4. Assign each settlement:
   - Name (generated or from pool)
   - Population (random within range based on carrying capacity)
   - Core variables (food, wealth, security, stability, influence) calculated from local resources
   - Initial infrastructure (basic: houses, well, maybe a wall if threat exists)

Settlement density is configurable (e.g., one settlement per 50×50 km). Larger worlds have more settlements.

Settlements are stored as state (Chapter 7) and will evolve during burn‑in.

---

# 30.5 Phase 3 – Faction Emergence

Factions arise from settlements and their interests.

Process for each settlement:

1. Identify natural **interest groups** within the population based on profession and wealth: merchants, farmers, guards, nobles (if applicable), religious leaders.
2. Each interest group with sufficient cohesion (population > threshold) becomes a **nascent faction**.
3. Assign each faction:
   - Identity (e.g., “Merchant Guild of Rivertown”)
   - Core drive (profit, power, safety, faith)
   - Initial goals (e.g., expand trade, control local governance)
   - Resources (shared pool from members)
   - Leadership (randomly selected from members)
   - Relationships with other nascent factions (default neutral, but rivalries seeded for factions with competing interests)

Factions are stored as state (Chapter 17). They will act during burn‑in, forming alliances, conflicts, and hierarchies.

---

# 30.6 Phase 4 – Initial Pressure & Relationship Seeding

Before burn‑in, the world needs initial pressures and relationships to avoid starting in a perfect equilibrium.

**Pressure seeding:**

- Assign each settlement a random initial pressure intensity (0–0.3) for each pressure category (food, economic, social, political, etc.), based on local resource scarcity or abundance.
- Assign each faction a random initial internal pressure (0–0.2) for leadership disputes, resource shortages, or ideological splits.
- Assign each NPC a random initial stress level (0–20) based on their faction and settlement pressures.

**Relationship seeding:**

- Family relationships: group NPCs into random family units (2–5 members) with loyalty baseline 60–80.
- Faction relationships: set initial trust, loyalty, fear, resentment between factions based on:
  - Geographic proximity (neighbours have lower trust, higher resentment).
  - Resource competition (overlapping resource needs → lower trust, higher resentment).
  - Shared identity (same settlement or culture → higher loyalty).
- Settlement relationships: trade links (positive trust), rival claims (negative trust).

All seeded values are within a narrow range (±0.2 from neutral) to avoid predetermining history. The burn‑in will amplify or resolve them.

---

# 30.7 Phase 5 – Burn‑In Simulation (Accelerated History)

The most critical phase. The engine runs the full simulation (Chapters 4, 5, 6, etc.) at **accelerated time** for a configurable period – typically 100 to 1000 years.

Acceleration factor: up to 1000x real time (1 simulated year per 8.76 real hours, or faster with summarisation).

Burn‑in steps:

1. **Initial fast‑forward (low resolution)** – For the first 90% of the burn‑in period, run the simulation with:
   - All actors at Relevant resolution (Chapter 25) except for major events.
   - Simplified pressure and consequence chains.
   - Aggressive event summarisation (Chapter 22).
   - This produces broad historical strokes (wars, alliances, collapses) without excessive detail.

2. **Final resolution increase (last 10%)** – For the most recent period (e.g., last 10–20 years), run at higher resolution (Active for key actors, Hero for major faction leaders). This produces the detailed recent history that the player may directly investigate.

3. **Event log management** – During burn‑in, low‑gravity events are summarised or archived immediately. Only events with gravity > 0.4 are retained in full detail. This prevents the event log from exploding.

4. **Scar formation** – The burn‑in naturally generates scars (Chapter 21): destroyed settlements, fallen dynasties, religious schisms, etc. These become part of the world’s identity.

5. **Generational turnover** – NPCs age, die, reproduce, and succeed one another throughout burn‑in per Chapter 33 (NPC Lifecycle & Generational Succession). A 200‑year burn‑in spans roughly 6–8 generations; no NPC present at genesis survives to player entry except through descendants, records, and legends. Inheritance of relationships, grudges, property, and leadership follows 33.6–33.8.

The burn‑in terminates when the configured simulation time is reached, or earlier if a stable equilibrium is detected and no major events have occurred for 10 simulated years.

Output: A complete world state (settlements, factions, NPCs, relationships, scars) and a summarised event log ready for player entry.

---

# 30.8 Phase 6 – Player Start State Selection

After burn‑in, the player chooses where to enter the world.

Options:

- **Random start** – Player placed in a random settlement, with basic starting resources.
- **Origin selection** – Player chooses from a list of available settlements, each with a brief history generated from the burn‑in (e.g., “Rivertown – recently recovered from a flood”).
- **Faction affiliation** – Player starts as a member of an existing faction (or as an outsider).
- **Scenario selection** – Player picks from emergent scenarios generated during burn‑in (e.g., “A famine is spreading. Start as a refugee.”)

The player start state is a **new actor** (the player character) inserted into the world state. All existing history remains unchanged.

---

# 30.9 Burn‑In Configuration Parameters

World creators (developers or players) can configure:

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| Burn‑in duration | 200 years | 0–2000 years | How much history is generated. |
| Acceleration factor | 1000x | 100x–10000x | Simulated years per real hour. |
| Resolution during burn‑in | Relevant | Dormant–Hero | Lower = faster, less detail. |
| Event retention threshold | 0.4 | 0.0–1.0 | Gravity above this kept in full detail. |
| Scar formation sensitivity | 1.0 | 0.5–2.0 | Higher = more scars from events. |
| Random seed | (time) | any | Deterministic world generation. |

These parameters allow rapid prototyping (10‑year burn‑in) or deep, epic history (1000‑year burn‑in).

---

# 30.10 Deterministic vs Stochastic Genesis

For reproducibility (debugging, multiplayer, shared worlds), the entire genesis process must be **deterministic** given a random seed.

All random decisions (settlement placement, faction emergence, pressure seeding) use the same seeded random number generator. The burn‑in simulation itself is deterministic (same inputs → same events).

This allows:

- Re‑generating the exact same world from a seed.
- Sharing world seeds between players.
- Debugging historical events by replaying the burn‑in from the seed.

---

# 30.11 Genesis Without Burn‑In (Zero‑History Worlds)

For testing or custom scenarios, the burn‑in phase can be skipped (duration = 0). The world then starts with only seeded pressures and relationships, no accumulated history.

This is **not recommended** for normal play, as it violates the “world already in motion” doctrine. But it is permitted for developer debugging or players who want a blank slate.

---

# 30.12 Post‑Genesis Validation

After genesis and burn‑in, the world must pass the **Dead World Test** (Chapter 1.13):

- Do settlements have distinct characteristics (population, wealth, stability)?
- Do factions have active goals?
- Are there scars visible (ruins, memorials, distrust)?
- Are there active pressures (food shortages, political tension)?
- Would the world continue changing if the player never arrived?

If the world fails any of these, the genesis process is repeated with a different random seed or adjusted parameters.

---

# 30.13 The World Genesis Test

For any newly generated world, ask:

- Does geography plausibly support the locations of settlements?
- Did factions emerge from settlement interest groups, not arbitrary assignment?
- Were initial pressures and relationships seeded within a neutral range (±0.2)?
- Did the burn‑in simulation produce a plausible history (wars, alliances, collapses)?
- Are there scars and active pressures at the end of burn‑in?
- Can the player start in a world that feels already in motion?

If yes: World Genesis is functioning.

---

# 30.14 Final Doctrine

A living world is not born empty.

It is born with mountains and rivers.

It is born with villages and cities.

It is born with merchants and guards, kings and beggars.

It is born with old grudges and ancient loves.

It is born with scars that will never fully heal.

World Genesis is the art of creating that birth – not through scripted history, but through simulation accelerated.

The player enters not at the beginning of time.

The player enters in the middle of the story.

That is the only way a living world can feel real.

END OF CHAPTER 30

CANONICAL VERSION

# CHAPTER 31

# LLM ARCHITECTURE & INTEGRATION

## Status

Canonical

This chapter defines how Large Language Models (LLMs) are used within the Dice Reaction Story Engine – **without violating simulation‑first principles**.

LLMs are powerful tools for generating natural language, dialogue, descriptions, and narrative summaries. But they are also capable of hallucination, contradiction, and forgetting.

Therefore: **The LLM writes prose. The engine writes truth.**

The LLM never modifies state. The LLM never creates events. The LLM never decides outcomes. The LLM only **describes, explains, or narrates** what the simulation has already determined.

This chapter governs:

- LLM role boundaries
- Prompt construction
- Context packet (state snapshot, event summary, NPC state)
- Output validation (anti‑hallucination)
- Integration with NPC Decision Engine (Chapter 27) – LLM does *not* choose actions
- Dialogue generation
- Narrative rendering (Chapter 4.25)
- Event summarisation (Chapter 22)
- Legend formation (Chapter 23)
- Performance and cost management
- LLM caching and tiered use per Actor Resolution (Chapter 25)

All LLM outputs are ephemeral. They are not stored as truth. Only events and state persist.

---

# 31.1 Core Doctrine

**The LLM writes prose. The engine writes truth.**

This is the absolute, non‑negotiable boundary.

- **Truth** – what happened, what exists, what changed – is stored in state and events.
- **Prose** – dialogue, description, internal monologue, narrative summary – may be generated by LLM.

The LLM may interpret truth. It may elaborate on truth. It may add emotional colour to truth. It may never **contradict** truth or **invent** truth that does not exist in state.

If the LLM says “the bridge is broken” but the state says the bridge is intact, the LLM has hallucinated. That output must be rejected or corrected.

---

# 31.2 LLM Role Boundaries

The LLM is permitted to perform only the following tasks:

| Task | Description | Input | Output |
|------|-------------|-------|--------|
| **Dialogue generation** | NPC speech in response to player or other NPCs | NPC state, relationship scores, current context, memory retrieval | Natural language dialogue line(s) |
| **Narrative rendering** | Describing state changes, actions, and consequences to the player | Event delta, before/after state, context | Prose description of what happened |
| **Internal monologue** | NPC reasoning (optional, for immersion) | NPC decision utility scores, retrieved memories | “I think…” style text |
| **Event summarisation** | Compressing low‑gravity event sequences | Sequence of events, gravity score | Short paragraph summary |
| **Legend formation** | Transforming ancient history into myth | Archived event summary, cultural context | Legendary narrative (may include symbolic distortion) |
| **Scene description** | Describing a location or actor the player observes | State snapshot (location, actors, objects, scars) | Descriptive prose |

The LLM is **forbidden** from:

- Choosing an NPC’s action (that is Chapter 27’s Utility AI).
- Determining the outcome of a resolution (that is Chapter 4’s hidden D20).
- Creating new events or modifying state.
- Deciding that an NPC knows something not in their memory/knowledge state.
- Generating quests or objectives (goals emerge from simulation).
- Speaking for the player character.

---

# 31.3 Context Packet Structure

Every LLM call receives a **context packet** – a structured JSON object containing only information the LLM is permitted to use.

Example packet for dialogue generation:

```json
{
  "npc": {
    "name": "Hilda",
    "role": "innkeeper",
    "drive": "safety",
    "current_stress": 45,
    "current_mood": "worried",
    "retrieved_memories": [
      {"summary": "Player helped clear bandits from the road last week", "emotional_weight": 0.7}
    ],
    "relationship_to_player": {
      "trust": 35,
      "loyalty": 10,
      "fear": 5,
      "resentment": 0
    }
  },
  "context": {
    "location": "The Rusty Nail tavern",
    "time": "evening",
    "recent_events": ["The town crier announced a tax increase"],
    "active_pressures": ["food shortage", "bandit activity"]
  },
  "player_recent_actions": ["Asked about the bandits"],
  "simulation_truth": {
    "bandits_are_nearby": true,
    "tax_increase_is_real": true
  }
}
```

The packet explicitly includes **simulation truth** so the LLM does not hallucinate facts. It also includes **relationship scores** and **retrieved memories** so the LLM can generate consistent, personalised dialogue.

**Important:** The packet excludes anything the NPC does not know (e.g., distant events, player secrets). The LLM must not imply knowledge the NPC lacks.

---

# 31.4 Prompt Templates

Each task has a dedicated prompt template. Templates are stored as configuration, not hardcoded.

**Dialogue generation template (simplified):**

```
You are {npc_name}, a {role} in {location}. 
Your core drive is {drive}. 
Current stress level: {stress}/100.

Relationship to the person you are speaking to:
- Trust: {trust}/100
- Loyalty: {loyalty}/100
- Fear: {fear}/100
- Resentment: {resentment}/100

You remember: {retrieved_memories_summary}

Current situation: {context_description}

The player just said/did: {player_action}

Based on your personality and the situation, what do you say? 
Keep it brief (1-2 sentences). 
Do not reveal information you don't have. 
Do not invent facts not in the simulation truth below.

Simulation truth (for consistency only - you may refer to it but not quote it): {truth_summary}
```

**Narrative rendering template (for event description):**

```
The following change just occurred in the simulation:

{event_description}

Before: {before_state_summary}
After: {after_state_summary}

Write a single paragraph (2-4 sentences) describing this change as the player would experience it. 
Use immersive, sensory language. 
Do not add events that did not occur. 
Do not change causality.
```

All templates include an explicit **anti‑hallucination clause** at the end.

---

# 31.5 Output Validation

Every LLM output is validated before being presented to the player or stored (if stored – most LLM output is ephemeral).

Validation checks:

1. **Factual consistency** – Does the output contradict any known truth in state? (e.g., says “bridge is broken” when state says intact).
2. **Knowledge boundary** – Does the output imply the NPC knows something not in their memory/knowledge state?
3. **Action assertion** – Does the output claim an action occurred that is not in the event log? (Forbidden.)
4. **Prohibited content** – Does the output attempt to give a quest, decide an outcome, or speak for the player?

If any check fails, the output is **rejected**. The engine may:

- Retry with a different random seed or temperature.
- Fall back to a generic template response (e.g., “Hilda grunts noncommittally.”).
- Log the failure for developer review.

Validation occurs in a dedicated **LLM Gateway** service that sits between the simulation and the LLM.

---

# 31.6 LLM and NPC Decision Engine – Separation of Concerns

The NPC Decision Engine (Chapter 27) is **Utility AI, not LLM**.

This is deliberate.

- Utility AI is deterministic, fast, explainable, and cheap.
- LLM is stochastic, slow, opaque, and expensive.

Using an LLM to choose NPC actions would:
- Introduce unacceptable latency (seconds per decision).
- Make behaviour unreproducible.
- Cost a fortune at scale.
- Risk hallucinated actions that violate simulation rules.

Therefore:

- **What** the NPC does → Utility AI.
- **Why** the NPC does it (dialogue, internal monologue) → LLM (optional, for immersion).

The LLM may receive the utility scores and retrieved memories to generate an explanation (“I’m helping you because I remember you saved my brother”), but it does not choose the help action.

---

# 31.7 LLM and Actor Resolution Scaling

Per Chapter 25, LLM calls are **tiered** to manage cost and latency:

| Tier | LLM Use | Frequency | Max tokens per call |
|------|---------|-----------|---------------------|
| Hero | Full LLM (dialogue, narrative, monologue) | Every interaction | 500 |
| Active | Dialogue only (no internal monologue) | When player initiates | 300 |
| Relevant | Pre‑generated or cached responses only | Never real‑time | N/A |
| Dormant | No LLM | Never | N/A |
| Archived | No LLM | Never | N/A |

For Relevant and lower tiers, dialogue uses **cached templates** (e.g., “Good day, traveller”) or simple rule‑based responses. This prevents runaway API costs.

---

# 31.8 LLM Caching

Many LLM outputs are reusable.

Cache keys are derived from:

- NPC role + drive + stress tier + relationship bracket + context type.

Example: `innkeeper_safety_stressed_trust_medium_greeting` → cached greeting text.

Cache lifetime: until the NPC’s state changes significantly (stress tier, relationship bracket, or location). When a change occurs, the cache for that NPC is invalidated.

Caching reduces LLM calls by 70–90% in typical gameplay.

---

# 31.9 Event Summarisation and Legend Formation (LLM‑Assisted)

When the Gravity Governance Layer (Chapter 26) decides to summarise a sequence of low‑gravity events, the LLM may generate the summary text.

Procedure:

1. Gather the event sequence (IDs, timestamps, brief descriptions).
2. Construct a summarisation prompt with the event list and a target length (e.g., 50 words).
3. LLM generates a paragraph.
4. Validate that the summary does not contradict any event fact (e.g., “the merchant sold apples” not “the merchant sold oranges”).
5. Store the summary as a **compressed event** (Chapter 22), with a link to the original event IDs.

For legend formation (deep time, Chapter 23.15), the LLM may introduce **symbolic distortion** – names become archetypes, numbers become rounded, causality becomes moralised. This is permitted because legends are explicitly **not** objective truth. The original events remain archived.

---

# 31.10 Performance and Cost Management

LLM calls are expensive in both time and money. The engine must:

- **Rate limit** – No more than N LLM calls per second (configurable, default 10).
- **Queue** – Non‑critical calls (e.g., internal monologue for non‑Hero NPCs) are queued and processed when bandwidth available.
- **Timeout** – If an LLM call exceeds 5 seconds, it is cancelled and falls back to template.
- **Budget tracking** – Log per‑session LLM token usage and cost. Alert if exceeding threshold.

For large worlds, the engine may run its own small, fine‑tuned model locally (e.g., Llama 3 8B) for low‑latency, free generation, reserving cloud LLMs for complex narrative rendering.

---

# 31.11 The Anti‑Hallucination Gateway

All LLM traffic passes through an **Anti‑Hallucination Gateway** that:

1. Injects simulation truth into the prompt (as “facts you must not contradict”).
2. Receives LLM output.
3. Runs validation checks (31.5).
4. If validation fails, attempts a correction by re‑prompting with “You made a mistake: {error}. Please correct.”
5. After 2 failures, falls back to template.

This gateway is the only code that calls the LLM. The rest of the simulation never interacts with the LLM directly.

---

# 31.12 LLM and Player Discovery

The LLM may assist with Discovery Architecture (Chapter 24) by:

- Generating natural‑language descriptions of evidence (“You find a bloodstained dagger with an eagle pommel”).
- Creating witness statements that reflect the witness’s knowledge and personality.
- Describing the player’s synthesis of clues (“The ledger and the letter both mention the same date…”).

However, the LLM **never** tells the player the solution. The player must connect the dots themselves.

---

# 31.13 The LLM Integration Test

For any LLM call, ask:

- Does the prompt include all necessary simulation truth?
- Does the prompt explicitly forbid hallucination?
- Is the LLM’s role limited to prose (dialogue, description, narrative)?
- Is the output validated against state before use?
- If validation fails, is there a fallback (retry or template)?
- Are LLM calls tiered by actor resolution to manage cost?
- Does the LLM never modify state, create events, or decide outcomes?

If yes: LLM Integration is functioning.

---

# 31.14 Final Doctrine

The LLM is a guest in the simulation.

It is powerful, but it is not trusted.

It writes prose. It does not write truth.

Truth lives in state and events – immutable, verifiable, causal.

The LLM may describe truth. It may colour truth. It may summarise truth.

But if the LLM ever contradicts truth, the engine rejects it.

This is not negotiable.

A living world cannot survive hallucination.

The LLM serves the world. The world does not serve the LLM.

END OF CHAPTER 31

CANONICAL VERSION

# CHAPTER 32

# SIMULATION TESTING FRAMEWORK

## Status

Canonical

This chapter defines how the Dice Reaction Story Engine is verified, validated, and tested.

A simulation of this complexity cannot be debugged manually. It requires an automated testing framework that runs continuously, simulating worlds without players, and asserting that core doctrines hold.

The Testing Framework exists to answer one question:

**Is the world alive, consistent, and causal?**

It does not test for “fun” or “balance”. Those are game design concerns. The Testing Framework tests for **correctness** of simulation mechanics.

This chapter governs:

- Unit tests for simulation components (Utility AI, Relationship Calculus, Memory Retrieval, etc.)
- Integration tests for systems working together
- The Dead World Test (Chapter 1.13) – automated
- The Living World Test (Chapter 1.14) – automated
- The Event Sourcing Test (Chapter 22.18) – automated
- The Actor Resolution Test (Chapter 25.10) – automated
- The Governance Test (Chapter 26.11) – automated
- The Decision Engine Test (Chapter 27.9) – automated
- The Memory Retrieval Test (Chapter 28.11) – automated
- The Relationship Calculus Test (Chapter 29.13) – automated
- The World Genesis Test (Chapter 30.13) – automated
- The LLM Integration Test (Chapter 31.13) – automated
- Performance benchmarks
- Regression testing (ensuring changes don’t break existing behaviour)

All tests must be reproducible (deterministic random seeds). Test worlds are small (e.g., one settlement, 20 NPCs) to run quickly.

---

# 32.1 Core Doctrine

**A simulation that cannot be tested cannot be trusted.**

If a doctrine cannot be automatically verified, it is not an engineering requirement – it is wishful thinking.

The Testing Framework transforms every major doctrine from prose into executable assertions.

Every change to the engine must pass the full test suite before deployment.

---

# 32.2 Test Categories

| Category | Purpose | Frequency |
|----------|---------|-----------|
| **Unit tests** | Verify individual functions (utility calculation, trust delta, retrieval probability) | Every build |
| **Integration tests** | Verify interactions between systems (e.g., Utility AI reading from Memory Retrieval) | Every build |
| **World tests** | Run short simulations (e.g., 1 simulated year) and assert world properties | Every build (fast) |
| **Long‑haul tests** | Run extended simulations (e.g., 100 simulated years) and assert historical properties | Nightly |
| **Performance tests** | Measure tick time, memory usage, LLM call latency | Every build (warning only) |
| **Regression tests** | Ensure fixes don’t reintroduce old bugs | Every build |

---

# 32.3 Unit Test Examples

Each core component must have a suite of unit tests.

**Utility AI (Chapter 27):**

```python
def test_starving_npc_prioritises_eating():
    npc = create_test_npc(hunger_pressure=0.9, food_available=True)
    actions = npc.possible_actions()
    utilities = {a: utility_ai.compute_utility(a, npc) for a in actions}
    assert utilities["eat"] > utilities["work"]
    assert utilities["eat"] > utilities["rest"]
```

**Relationship Calculus (Chapter 29):**

```python
def test_betrayal_damages_trust_and_loyalty():
    rel = Relationship(trust=80, loyalty=70, fear=10, resentment=0)
    rel.apply_event("betrayal", emotional_intensity=0.8)
    assert rel.trust < 30
    assert rel.loyalty < 30
    assert rel.resentment > 50
```

**Memory Retrieval (Chapter 28):**

```python
def test_recent_emotional_memory_retrieved_over_old_neutral():
    memories = [
        Memory(days_ago=1, emotional_weight=0.9, context_match=0.8),
        Memory(days_ago=100, emotional_weight=0.1, context_match=0.2)
    ]
    retrieved = memory_retrieval.select_working_memory(memories, working_memory_size=1)
    assert retrieved[0] == memories[0]
```

---

# 32.4 Integration Tests

Integration tests verify that systems work together correctly.

**Example: Utility AI + Memory Retrieval**

```python
def test_traumatic_memory_affects_action_utility():
    npc = create_test_npc()
    # Add a traumatic memory of being attacked by a wolf
    npc.add_memory(event_type="attacked_by_wolf", emotional_weight=0.9)
    # Current context: wolf present
    npc.set_current_context(actor_type="wolf")
    # Retrieve memories
    memory_retrieval.update_working_memory(npc)
    # Compute utility for "approach" vs "flee"
    utility_approach = utility_ai.compute_utility("approach_wolf", npc)
    utility_flee = utility_ai.compute_utility("flee", npc)
    assert utility_flee > utility_approach
```

**Example: Relationship Calculus + Memory Retrieval + Utility AI**

```python
def test_resentment_leads_to_betrayal_when_opportunity_arises():
    npc = create_test_npc(personality_aggressive=True)
    # Build high resentment
    for _ in range(5):
        npc.relationship_with("target").apply_event("broken_promise")
    # Target is vulnerable (low health, isolated)
    npc.set_context(target_vulnerable=True)
    utility_betray = utility_ai.compute_utility("betray_target", npc)
    utility_help = utility_ai.compute_utility("help_target", npc)
    assert utility_betray > utility_help
```

---

# 32.5 Dead World Test (Automated)

From Chapter 1.13: Remove the player, run simulation, observe if world changes.

**Automated version:**

```python
def test_dead_world_test():
    world = generate_test_world(settlements=3, npcs=50, years_of_history=0)
    # Remove player (no player actor)
    world.player = None
    # Run simulation for 1 simulated year
    for _ in range(365):  # days
        world.tick()
    # Assert world changed
    assert world.settlement_population_variance() > 0.01  # populations moved
    assert world.total_event_count() > 0  # events occurred
    assert any(f.goal_changed() for f in world.factions)  # factions adapted
    # Also assert not everything collapsed (optional)
    assert len(world.settlements) >= 2  # not all destroyed
```

If this test fails, the world is dead – simulation components are not generating independent motion.

---

# 32.6 Living World Test (Automated)

From Chapter 1.14: A living world demonstrates motion, persistence, causality, etc.

**Automated version:**

```python
def test_living_world_test():
    world = generate_test_world(settlements=5, npcs=200, years_of_history=10)  # with burn‑in
    snapshot_before = world.snapshot()
    # Run for 1 month
    for _ in range(30):
        world.tick()
    # Assert motion
    assert world.scar_count() > snapshot_before.scar_count() or world.has_new_events()
    # Assert persistence – scars from before still exist (unless healed)
    for scar in snapshot_before.scars:
        assert world.scar_exists(scar.id) or world.scar_healed(scar.id)  # healing is allowed
    # Assert causality – each new event has a cause
    for event in world.events_since(snapshot_before):
        assert event.caused_by is not None or event.is_initial_condition()
```

---

# 32.7 Event Sourcing Test (Automated)

From Chapter 22.18: Can every state change be traced to an event? Can state be reconstructed?

```python
def test_event_sourcing():
    world = generate_test_world()
    # Run for 10 days
    for _ in range(10):
        world.tick()
    # Capture state after
    state_after = world.snapshot()
    # Reconstruct state from event log starting from initial snapshot
    reconstructed = reconstruct_state(world.initial_snapshot, world.event_log)
    # Assert identical
    assert state_after == reconstructed
    # Also test that any event can be traced to a cause
    for event in world.event_log:
        if not event.is_initial:
            assert event.caused_by is not None
            assert event.caused_by[0] in world.event_log  # referenced event exists
```

---

# 32.8 Actor Resolution Test (Automated)

From Chapter 25.10: Actors are in correct tier, demote/promote correctly.

```python
def test_actor_resolution_scaling():
    world = generate_test_world()
    # Player starts in Settlement A
    world.player.location = settlement_A
    # NPC in same settlement should be Hero or Active
    npc = settlement_A.npcs[0]
    assert world.actor_resolution.get_tier(npc) in ["Hero", "Active"]
    # Player travels far away
    world.player.location = distant_settlement
    world.tick()  # allow demotion check
    # Same NPC should now be Relevant or Dormant
    assert world.actor_resolution.get_tier(npc) in ["Relevant", "Dormant"]
    # Player returns
    world.player.location = settlement_A
    world.tick()
    assert world.actor_resolution.get_tier(npc) in ["Hero", "Active"]
```

---

# 32.9 Governance Test (Automated)

From Chapter 26.11: Retention scores match gravity, thresholds trigger actions.

```python
def test_gravity_governance():
    world = generate_test_world()
    # Create a low‑gravity event
    event_low = world.create_test_event(gravity=0.05, age_days=100)
    # Run governance (should compress or archive)
    world.governance_layer.update()
    assert event_low.retention_score < 0.4
    assert event_low.is_archived or event_low.is_compressed
    # Create a high‑gravity event
    event_high = world.create_test_event(gravity=0.9, age_days=1)
    world.governance_layer.update()
    assert event_high.retention_score > 0.8
    assert not event_high.is_archived
    assert not event_high.is_compressed
```

---

# 32.10 LLM Integration Test (Automated)

From Chapter 31.13: LLM outputs validated, anti‑hallucination works.

```python
def test_llm_anti_hallucination():
    # Simulate an LLM call for dialogue
    npc = create_test_npc()
    context = {
        "simulation_truth": {"bridge_status": "destroyed"},
        "npc_knowledge": {"bridge_status": "unknown"}  # NPC doesn't know
    }
    # Malicious LLM output that contradicts truth
    bad_output = "The bridge is intact."
    validated = llm_gateway.validate_output(bad_output, context)
    assert validated is False  # rejected
    # Good output
    good_output = "I haven't seen the bridge lately."
    validated = llm_gateway.validate_output(good_output, context)
    assert validated is True
```

---

# 32.11 World Genesis Test (Automated)

From Chapter 30.13: Generated world has plausible history, scars, pressures.

```python
def test_world_genesis():
    world = WorldGenesis.create(seed=12345, burn_in_years=100)
    # Should have at least 3 settlements
    assert len(world.settlements) >= 3
    # Should have at least 2 factions
    assert len(world.factions) >= 2
    # Should have scars (ruins, memorials, etc.)
    assert world.scar_count() >= 1
    # Should have active pressures
    assert any(s.has_active_pressure() for s in world.settlements)
    # Should have some relationships with non‑zero values
    assert any(r.trust != 0 or r.loyalty != 0 or r.fear != 0 or r.resentment != 0 
               for r in world.relationship_list())
```

---

# 32.12 Performance Benchmarks

Performance tests do not assert pass/fail (because hardware varies). They log metrics and warn if thresholds are exceeded.

Example metrics:

- Tick time for 1000 NPCs with 50% Active, 30% Relevant, 20% Dormant: target < 50ms.
- Memory usage per NPC: target < 10KB for Dormant, < 100KB for Relevant, < 1MB for Active.
- LLM call latency (p95): target < 3 seconds for cloud LLM, < 500ms for local.
- Event log growth rate: target < 1MB per simulated year for a small world (100 NPCs).

These benchmarks are run nightly. Regressions trigger alerts.

---

# 32.13 Regression Testing

Each bug fix must include a regression test that fails without the fix.

Example:

```python
def test_regression_bug_1234_npc_starvation_not_eating():
    # Bug 1234: NPC with food available would work instead of eat when starving.
    npc = create_test_npc(hunger_pressure=0.9, food_available=True)
    # Prior to fix, this would fail. After fix, passes.
    assert utility_ai.compute_utility("eat", npc) > utility_ai.compute_utility("work", npc)
```

Regression tests are stored alongside the code. All regression tests must pass before merge.

---

# 32.14 Test Worlds

All tests use **test worlds** – minimal configurations that run quickly:

- Small world: 1 settlement, 20 NPCs, 2 factions.
- Medium world: 5 settlements, 100 NPCs, 5 factions (for integration tests).
- Large world: 20 settlements, 500 NPCs, 10 factions (for long‑haul and performance tests).

Test worlds are generated deterministically from a fixed seed (e.g., 42). This ensures reproducibility.

---

# 32.15 Continuous Integration

The full test suite runs automatically on:

- Every pull request (unit, integration, world tests, regression, LLM integration).
- Every merge to main (adds long‑haul and performance tests).
- Nightly (full suite including long‑haul with longer burn‑in).

Test failures block merging.

---

# 32.16 The Testing Framework Test

For the framework itself, ask:

- Does every core doctrine have at least one automated test?
- Are tests deterministic (same seed → same result)?
- Can tests run in under 5 minutes for the fast suite?
- Do performance benchmarks produce actionable metrics?
- Does the framework detect regressions before they reach production?

If yes: The Simulation Testing Framework is functioning.

---

# 32.17 Final Doctrine

A simulation that cannot be tested cannot be trusted.

Every doctrine must become an assertion.

Every change must be verified.

Every bug must leave a test behind.

The Testing Framework is not an afterthought.

It is the only way to know if the world is truly alive.

Without tests, the Bible is just philosophy.

With tests, it becomes engineering.

END OF CHAPTER 32

CANONICAL VERSION

# CHAPTER 33

# NPC LIFECYCLE & GENERATIONAL SUCCESSION

## Status

Canonical

This chapter defines how NPCs are born, age, die, and pass their place in the world to others.

If Chapter 10 defines what an NPC is, Chapter 25 defines how much of one is simulated, and Chapter 30 defines worlds that begin with centuries of history, this chapter defines the mechanism that makes multi‑generational time possible at all.

Without a lifecycle:

- Burn‑in produces 200‑year‑old immortals.
- Factions never change leadership except by violence.
- Family, inheritance, and legacy are empty words.
- Historical layering (Chapter 23) has no human texture.

A living world is not populated by fixtures.

It is populated by mortals.

This chapter governs:

- Aging and life stages
- Natural and unnatural death
- Birth and family formation
- Inheritance of property, relationships, and grudges
- Leadership and role succession
- Lifecycle processing per resolution tier
- Lifecycle during burn‑in

---

# 33.1 Core Doctrine

**Every NPC is mortal.**

**Every role outlives its holder.**

**Every death transfers something: property, position, memory, or grievance.**

Death is not deletion. A dead NPC is demoted to Archived (Chapter 25) with their historical record intact. Their relationships, debts, and grudges do not vanish – they transfer, fade, or scar, according to the rules below.

---

# 33.2 Aging and Life Stages

Every NPC has a birth date in simulation time and ages continuously.

| Life Stage | Age Range (default human) | Simulation Effects |
|-----------|---------------------------|--------------------|
| Child | 0–15 | Not independently simulated below Active tier. Attached to family unit. No profession. |
| Adult | 16–49 | Full simulation. Can hold roles, form families, lead factions. |
| Elder | 50–69 | Physical capability declines (modifier on relevant resolutions). Social influence often rises. Succession planning pressure (33.7) begins. |
| Venerable | 70+ | Annual natural‑death probability rises steeply (33.3). |

Age ranges are species/setting configuration, not hard‑coded. The structure is canonical; the numbers are parameters (Appendix A).

Aging is processed at the macro heartbeat (Chapter 5) for all tiers. Aging is one of the few processes that touches Dormant actors: their age advances even while nothing else about them is simulated.

---

# 33.3 Natural Death

Each macro heartbeat, every living NPC is evaluated against an age‑dependent mortality curve:

```
P(death this year) = base_mortality × age_factor × health_factor × pressure_factor
```

Where:

- `base_mortality` = 0.5% per year for adults (configurable, Appendix A).
- `age_factor` = 1.0 through adulthood, rising exponentially after the Elder threshold (doubling roughly every 8 years past 50).
- `health_factor` = 1.0 healthy, up to 5.0 for chronic injury, disease, or starvation (Chapter 8 survival resources).
- `pressure_factor` = 1.0 to 2.0 based on sustained survival pressure on the NPC's settlement (Chapter 6).

Mortality rolls use the seeded simulation RNG (30.10). Deaths are deterministic per seed.

Natural death generates an event (Chapter 22) with gravity proportional to the NPC's connectivity and role – a beggar's death is Negligible; a beloved monarch's death may be Major and a turning point (23.9).

---

# 33.4 Unnatural Death

NPCs may die from violence, accident, starvation, disease, or execution, resolved through the standard Simulation Loop (Chapter 4).

Unnatural death typically carries higher gravity than natural death at the same connectivity, because it generates injustice, fear, and grievance pressure. A murder is never just a state change – it is a pressure source (Chapter 6) and a likely scar (Chapter 21).

---

# 33.5 Birth and Family Formation

NPCs form partnerships through the same Utility AI that governs all behaviour (Chapter 27) – companionship and family are goal types (Chapter 11), not scripts.

Birth mechanics:

- Partnered adult NPCs in a settlement with positive food security have a per‑year birth probability (configurable, default tuned so settlement birth rates roughly track carrying capacity per Chapter 7).
- A birth creates a new Child NPC attached to the family unit, inheriting family identity, faction affiliation, and a seeded personality derived from the parents (with variation from the seeded RNG).
- Births are events with Negligible–Minor gravity (royal or prophesied births configurable upward).

Population dynamics (7.24) are thereby grounded in individual lifecycle events at Active resolution and statistically batched at lower resolutions (33.9).

---

# 33.6 Inheritance

Death transfers. The transfer rules:

**Property** – Passes by local custom (configuration per culture): primogeniture, partible inheritance, or communal reversion. Disputed inheritance is a pressure source and a common emergent conflict seed.

**Relationships** – Do not transfer wholesale. Identity‑level bonds generate **inherited dispositions** in heirs: a child of the player's sworn ally starts with a loyalty baseline toward the player (+10 to +30), a child of the player's victim starts with resentment (+20 to +50). Inherited dispositions are baselines (29.12), not full relationship vectors – the heir's own history then builds on top.

**Grudges** – High‑resentment relationships (≥ 70) at death convert to **family or faction grudges**: a persistent disposition modifier carried by the bloodline or group, decaying at one tenth the standard resentment rate (29.10). Generational feuds are this rule operating over centuries.

**Memory** – The dead NPC's defining memories survive as records, testimony given before death, and the memories other NPCs hold of them (Chapter 12). Beyond living memory, they become legend material (23.15).

---

# 33.7 Succession

Every formal role (faction leader, settlement official, guild master, head of family) has a **succession rule** defined at role creation: hereditary, elective, appointive, seniority, or contest.

Succession mechanics:

- When a role‑holder enters Elder stage, succession pressure begins accumulating on the role (Chapter 6, political pressure). Ambitious NPCs (goal systems, Chapter 11) position themselves.
- On death or removal, the succession rule resolves through the Simulation Loop. Contested successions are among the most reliable emergent‑conflict generators in the engine – they are pressure collisions (6.14) by construction.
- Succession events carry gravity proportional to the role's influence. A monarch's succession is a candidate turning point (23.9).

No role may be defined without a succession rule. A role without succession is a future null‑pointer in the simulation.

---

# 33.8 Death and the Player

The player's relationships die with their holders – but per 33.6, dispositions echo in heirs.

The player may cause deaths, inherit grudges, witness successions, and outlive allies. None of this is scripted. All of it follows from this chapter operating inside the standard loop.

NPC death during player absence is normal and is discovered, not announced (Chapter 24). Returning to a settlement after twenty years should feel like returning after twenty years.

---

# 33.9 Lifecycle and Actor Resolution

Per Chapter 25:

| Tier | Lifecycle Processing |
|------|----------------------|
| Hero / Active | Full individual processing: aging effects, partnership decisions, mortality rolls, succession participation. |
| Relevant | Mortality and aging rolled individually at the regional heartbeat; partnerships and births simplified to probabilistic family‑unit updates. |
| Dormant | Batch statistical processing at the macro heartbeat: cohort aging, aggregate mortality, aggregate births assigned to family units. Individual deaths still generate (low‑gravity) events for traceability. |
| Archived | No processing. The dead remain dead. |

Statistical batching must remain event‑sourced: every batched death or birth writes an event (Chapter 22), so history reconstruction never encounters population that appeared or vanished without cause.

---

# 33.10 Lifecycle During Burn‑In

Burn‑in (30.7) runs lifecycle at Dormant‑tier batch processing for the fast‑forward phase, raising to per‑tier processing in the final high‑resolution period.

Requirements:

- Generational turnover must occur: a 200‑year burn‑in must end with no living NPC who was alive at genesis (absent configured long‑lived species).
- Succession rules must resolve throughout, so factions at player entry are led by plausible heirs and successors of genesis leadership, with the succession chain traceable in the event log.
- Inherited grudges and dispositions (33.6) must propagate, so the world at player entry contains generational feuds with discoverable roots.

A burn‑in that produces a world still led by its founders has failed this chapter.

---

# 33.11 The Lifecycle Test

Ask:

- Does every NPC have a birth date, life stage, and mortality evaluation?
- Does every formal role have a succession rule?
- Does death transfer property, dispositions, and grudges per 33.6?
- After a long burn‑in, has full generational turnover occurred?
- Is every birth and death traceable as an event?

If yes: the lifecycle is functioning.

---

# 33.12 Final Doctrine

A living world is not a terrarium of immortals.

It is a procession of generations.

People are born into pressures they did not create.

They inherit loves and hatreds they did not earn.

They hold roles for a while, and then they pass them on.

The player walks among mortals.

And one day, the people the player knew are gone – and their children remember.

That is what it means for a world to be alive across time.

END OF CHAPTER 33

CANONICAL VERSION

# APPENDIX A

# CONSTANTS REGISTRY

## Status

Canonical

This appendix is the **single authoritative location** for every numeric constant, threshold, rate, and formula parameter in the Bible. Chapters state mechanisms; this registry states numbers. Where a chapter and this registry disagree, the registry is correct and the chapter must be amended.

**Amendment rule:** No new constant may be introduced in chapter prose. New constants are added here first, then referenced. This rule exists because every contradiction found in versions 1.0–1.1 traced to the same root cause: the same quantity defined in two places.

All durations are simulation time (25.6).

## A.1 Gravity (Chapter 20)

| Constant | Value |
|----------|-------|
| Gravity scale | 0.0 – 1.0 continuous |
| Tier ranges (Negligible / Minor / Significant / Major / Defining) | 0–0.2 / 0.2–0.5 / 0.5–0.7 / 0.7–0.9 / 0.9–1.0 |
| Decay function | G(t) = G_peak × 0.5^(t / half_life) |
| Half-lives by peak tier | 3 d / 30 d / 1 y / 10 y / 100 y |
| Connectivity decay-clock reset | 25% of time since last reference |

## A.2 Retention (Chapter 26)

| Constant | Value |
|----------|-------|
| Retention formula | R = G × (1 + 0.5C) × (1 + 0.5P) × D / 2.25, clamped 0–1 |
| Player relevance P | e^(−days_since_encounter / 7); P = 0 if no player or never encountered |
| Duration factor D | G ≥ 0.7: min(1.2, 1 + years/500); G < 0.7: max(0.8, 1 − years/200) |
| Action thresholds | ≥0.8 fully active / 0.6–0.8 light summarisation / 0.4–0.6 compress / 0.2–0.4 archive / <0.2 deletable if causally unlinked |
| Summary gravity on compression | original × 0.8 |
| Player-event minimum retention | 0.5 for 30 days |
| Active-investigation boost | retention ≥ 0.6 until investigation closes |
| Recalculation frequency | G>0.6 daily / 0.3–0.6 weekly / <0.3 monthly or on reference |

## A.3 Actor Resolution (Chapter 25)

| Constant | Value |
|----------|-------|
| Tier ceilings | Hero 16 / Active 200 / Relevant 2000 / Dormant unlimited / Archived unlimited |
| Demotion grace periods | Hero→Active 5 min / Active→Relevant 24 h / Relevant→Dormant 7 d / Dormant→Archived 30 d (90 d total inactivity) |
| Retention→tier eligibility | >0.7 Hero / >0.5 Active / >0.3 Relevant / ≤0.3 Dormant–Archived |
| Gravity→tier eligibility | >0.8 Hero / >0.5 Active / >0.2 Relevant |

## A.4 Utility AI (Chapter 27)

| Constant | Value |
|----------|-------|
| Utility formula | U(a) = Σ(score × weight) / Σ(weight), bounded 0–100 |
| Base weights | Survival 100 / Goal 50 / Pressure relief 30 / Stress 20 / Relationship 40 / Resource 25 / Memory avoidance 15 (state modifiers per 27.4.2) |
| Whim noise | ±0.5, seeded RNG, applied before comparison |
| Tie window | 0.01 after noise |
| SVU definition | value of one day of basic food for one adult at local scarcity |

## A.5 Memory Retrieval (Chapter 28)

| Constant | Value |
|----------|-------|
| Working memory size | Hero 7 / Active 5 / Relevant 3 (cached 24 h) / Dormant 1 (on promotion) |
| Recency half-lives | major memories 30 d / minor 3 d |
| Base retrieval probability | defining 0.9 / major 0.5 / minor 0.01 |
| Emotional bias multipliers | defining 2.0 / major 1.5 / moderate 1.0 / minor 0.5 |
| Pattern memory bonus | P_base × (1 + log10(count)) |
| Low-retrieval connectivity signal | P < 0.01 for 30 d |

## A.6 Relationships (Chapter 29)

| Constant | Value |
|----------|-------|
| Dimensions and ranges | Trust −100..+100 / Loyalty 0..100 / Fear 0..100 / Resentment 0..100 |
| Decay function | V(t) = V_last × e^(−r × days); exponential mandatory |
| Decay rates r (per day) | Trust 0.005 / Resentment 0.005 / Fear 0.010 / Loyalty 0.001; identity-level bonds ×0.1 |
| Retrieval situational modifier bound | ±50% of dimension influence, current decision only |
| Event deltas | per table 29.8 |
| Special-state thresholds | Betrayal: resentment > 70 and > loyalty, with opportunity / Collapse: trust < −50 and loyalty < 20 / Forgiveness: −30 to −50 resentment on costly apology |

## A.7 Lifecycle (Chapter 33)

| Constant | Value |
|----------|-------|
| Life stages (default human) | Child 0–15 / Adult 16–49 / Elder 50–69 / Venerable 70+ |
| Base adult mortality | 0.5% per year |
| Age factor | doubles approximately every 8 years past 50 |
| Health factor / Pressure factor | 1.0–5.0 / 1.0–2.0 |
| Inherited dispositions | ally heir loyalty +10..+30 / victim heir resentment +20..+50 |
| Grudge decay | standard resentment rate × 0.1 |

## A.8 Discovery & Evidence (Chapter 24)

| Constant | Value |
|----------|-------|
| Discovery windows by gravity | >0.8 decades–centuries / 0.5–0.8 years / 0.2–0.5 weeks–months / <0.2 days |

## A.9 LLM Integration (Chapter 31)

| Constant | Value |
|----------|-------|
| Max tokens per call | Hero 500 / Active 300 / lower tiers cached only |
| Rate limit / Timeout / Validation retries | 10 calls/s default / 5 s real time / 2 then template fallback |
| Expected cache hit reduction | 70–90% |

## A.10 Burn-In (Chapter 30)

| Constant | Value |
|----------|-------|
| Default duration | 200 years (configurable 0–2000) |
| Acceleration | 1000× default (100×–10000×) |
| Event retention threshold during burn-in | gravity > 0.4 |
| Equilibrium early-stop | 10 years without major events |
| High-resolution tail | final 10% of burn-in period |

END OF APPENDIX A

CANONICAL VERSION
