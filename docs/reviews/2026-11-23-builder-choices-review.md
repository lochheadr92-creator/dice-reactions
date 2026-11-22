# Builder choices review, 2026-11-23

Scope: the three ways to start a story (Quick Start, Guided, Advanced), the wording of every choice, and whether each answer reaches the engine. Read from code on branch `emergent` at `47a4d41`. The app was not clicked through, so layout and feel are not covered.

## Findings

| # | Finding | Evidence |
|---|---|---|
| 1 | Advanced hid descriptions that were already written. 46 options under want, fear, who matters, past, talent, flaw and line showed a one-word label. | `AdvancedBuilder.tsx` mapped `options.ts` copy to `{ value, label }` only |
| 2 | 64 options had no description anywhere: world type, world strain, recent change, real or strange, role, story feel, harshness, and all 28 content levels. | Option lists in `AdvancedBuilder.tsx` |
| 3 | Helper lines were written in builder shorthand and said what a setting was not. | "Compact world type, not a scenario card." and similar |
| 4 | No place for a premise. A story idea typed into the world type box became the title and was cut at 120 characters in the stored frame. | Sessions `09db17b9`, `e1c927ad` |
| 5 | No time period question. A typed world has no era, so the model chose one. | Session `e1c927ad` opened in a pre-industrial hamlet |
| 6 | The opening situation was rolled without looking at the player's answers. | "opportunities arising" rolled `debt_called` and `locked_in` |
| 7 | Preset answers applied silently. | `DEFAULT_SETUP` |
| 8 | Three vocabularies for one engine value (difficulty). Tone also set difficulty in Guided without saying so. | `options.ts`, `GuidedStart.tsx`, `AdvancedBuilder.tsx` |
| 9 | World strain, recent change and Guided pressure overlapped with no explanation. | Step helpers |
| 10 | Quick Start cards fixed a role and a difficulty and showed neither. | `QuickStart.tsx` |
| 11 | Prose style and basic or advanced mode have no control. | No frontend reference to `prose_mode` |

## Resolution, 2026-11-23

| Finding | Change |
|---|---|
| 1 | Advanced and Guided show both lines (what it means, what to expect) for every hook option. |
| 2 | Two-line descriptions written for every bare option. The 18+ panel has a help line per row and one line per level. |
| 3, 9 | Helper lines rewritten in plain words. World strain and recent change each say how they differ. |
| 4 | New optional question "What is this story about?" (`premise`, up to 600 characters). It goes into the opening request and every later turn. The title is a short version of the world type. The typed world type is stored up to 320 characters. |
| 5 | New question "When is this set?" (`timePeriod`: present day, the past, the future, or let the world type decide). It sets `world_frame.era`. |
| 6 | `opening_state.opening_archetype_pool` narrows the opening roll to archetypes that fit the recent change or Guided pressure. A typed change cannot be mapped, so the opening request now says the situation must not contradict it. |
| 7 | Preset answers carry a visible marker on the question and on the review page until the player chooses. |
| 8 | One set of words everywhere: Forgiving, Balanced, Severe, Brutal (`HARSHNESS_LABELS`). Guided states that one choice sets mood and consequences. |
| 10 | Quick Start cards show "You are: <role>. Consequences: <label>." |
| 11 | Not changed. Belongs with the Settings screen rework. |

Also changed: the Advanced builder is four pages (World, Character, People and past, Experience) plus the review, down from 19 single-question screens.

## Not verified

- No click-through in a browser. Page length on the World page (9 questions) and Quick Start card text fit are unchecked.
- No live story generated with the premise or time period fields.
- The level descriptions in the 18+ panel describe the labels in plain words. They were not checked line by line against the mature content policy code.
