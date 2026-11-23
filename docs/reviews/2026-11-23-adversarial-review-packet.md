# Adversarial review packet, whole repository, 23 November 2026

Prepared by Claude (Fable 5.2) at Ryan's request for an independent reviewer. The reviewer should be a different model or a fresh session with no memory of the work described here.

This packet is a briefing. It is written by the party whose work is under review, so treat every statement in it as a claim to test. Where it conflicts with the code, the code wins.

## 1. Repository identity

| Item | Value |
|---|---|
| Path | `C:\dev\dice-reactions` |
| Branch | `emergent` |
| HEAD | `014b1a28280edf70d36f4b4f52a66a6fe8acc889` |
| `origin/emergent` (local ref, no fetch run) | `fff8095` |
| Unpushed local commits | 8 (`cfc2cd2` through `014b1a2`) |
| Working tree at packet time | clean apart from this file |
| Tracked files | 375 |
| Backend | Python, FastAPI, MongoDB replica set `rs0`. About 46,300 lines in `backend/*.py`; `server.py` is 5,421 lines |
| Backend tests | 117 files in `backend/tests` |
| Frontend | Expo React Native, web target, 9 Jest suites |
| CI | `.github/workflows/deterministic-ci.yml`: Python 3.12, Node 20, MongoDB 7 replica set, web export |

CI has not run on the 8 unpushed commits.

## 2. What the system is

An AI-assisted story game. The player builds a story, a language model writes each turn, and the engine validates and stores it.

Doctrine (`docs/system-doctrine.md`): state is truth and narrative is output (H1); the model cannot be the sole author of simulation truth (H2); engine-only state must not leak into player text (H3); persisted turn events are append-only (H4); narrative passes through the gateway and sanitisation path (H5); developer-only information stays hidden from normal players (H7).

Read before judging: `AGENTS.md`, `CLAUDE.md`, `docs/system-doctrine.md`, `docs/failure-modes.md`, `docs/verification.md`, `docs/current-state.md` (contains superseded sections), `docs/reviews/2026-11-20-adversarial-review.md`, `docs/reviews/2026-11-23-builder-choices-review.md`.

## 3. Scope and where to spend depth

Scope is the entire repository. Depth should follow risk.

**Tier 1: the 8 unpushed commits.** 30 files, 2,426 insertions, 276 deletions, written in one overnight session between about 22:00 and 05:40. No browser click-through was done at any point. Several changes were made in direct reply to live play and shipped to the running engine within minutes.

| Commit | Claim |
|---|---|
| `cfc2cd2` | A typed world type gets its own world frame; it no longer falls back to the Modern frame |
| `4cca2b0` | Every opening request ends with an orientation rule |
| `47a4d41` | The scarcity roll fits the world; ammo only in genres with guns; typed worlds roll five neutral axes |
| `7bc24d5` | Premise and time period reach the engine; short titles; the opening roll is narrowed by builder answers |
| `ee9a2b4` | Builders describe every choice; Advanced is four pages; presets are marked |
| `bd571ef` | Docs only |
| `6cdc578` | Always-on turn rules; prose mode ranges; writing style; per-story thinking effort; `play-settings` endpoint; mature renderer keeps paragraphs |
| `014b1a2` | Settings page: text size, turn length, writing style, speed, story defaults |

**Tier 2: areas the 20 November review did not audit.** It sampled the engine and did not read these in depth: `utility_ai.py`, `pressure_graph.py`, `information_engine.py`, `goal_engine.py`, `world_event_engine.py`. It did not review the mature content policy (`mature_content.py`, `mature_rendering.py`), did not drive the UI in a browser, and did not inspect any deployment.

**Tier 3: regression check on the 16 fixes from 20 November.** The resolution table is at the end of that review. Confirm each still holds after tonight's changes, in particular fix 14 (creation facts win over model output) and fixes 2 and 3 (creation size limits, creation recovery), which share code with `7bc24d5`.

## 4. Claims to attack, with the weakest point of each

| # | Claim | Evidence offered | Where it is weakest |
|---|---|---|---|
| 1 | Turn rules make turns clear and make every turn move | `tests/test_turn_rules.py` checks the text is sent | The rules are prompt text. No validator rejects a turn that ignores them. No live turn was generated under them before commit |
| 2 | The orientation rule orients the player | Two live openings read correctly (sessions `09db17b9`, `e1c927ad`) | Two samples, both Grok 4.7. The rule was loosened once at Ryan's request before either sample |
| 3 | Builder answers narrow the opening | `tests/test_builder_answers_reach_engine.py` | The mapping tables in `opening_state.py` are judgement. A typed recent change cannot be mapped and relies on one sentence in the prompt |
| 4 | A story's thinking effort is isolated per request | `test_story_effort_does_not_leak_between_requests` uses separate `asyncio.run` calls | `ai_service.use_story_reasoning_effort` sets a context variable and never resets it. The test does not model one event loop serving concurrent requests, or work spawned from a request |
| 5 | `play-settings` is presentation only | Endpoint tests in `test_security.py` | The play screen calls it on every screen focus. It writes `updated_at` on each call. Interaction with the action lease, the turn commit transaction and list ordering is untested |
| 6 | The mature renderer keeps paragraphs | `test_mature_rendering_keeps_paragraph_breaks`, with the renderer faked | Not run against the real renderer. The renderer's size limit and paragraph-count check now see different input from before |
| 7 | Prose mode changes are safe for stories in progress | Unit tests on ranges | A story created under one range now gets another. Trimming and the format retry note use the new numbers. `cinematic` max dropped from 10 to 8 paragraphs with the same character budget |
| 8 | Story defaults are safe | Jest tests | 18+ levels saved in browser storage are applied when mature content is switched on. Filtering by release capability happens in the client. Confirm the server refuses a level the release does not allow |
| 9 | Typed text is bounded | `MAX_PREMISE_LEN` 600, world type 320 | The premise is repeated in every later-turn request. Check prompt growth and whether typed text can carry instructions to the model |
| 10 | Scarcity and opening pool changes do not disturb existing stories | `derive_run_identity` is called only from `replayability.init_new_story` (checked by grep) | Checked by grep only. Any replay, golden seed or determinism tool that re-derives identity from a seed would now disagree with stored stories |
| 11 | The system prompt edit is harmless | Suite passes | Priority order changed to Readability first and the mystery rule was narrowed. This shifts tone for every story and every model. No eval run was done afterwards |
| 12 | Test counts are accurate | Backend 1,605 passed, 36 deselected; Jest 90 passed; `tsc` and lint exit 0, all run on the repo on 23 November | Local machine only. Two existing Jest tests were edited to press Continue 4 times, not 18. Four existing prose mode assertions were edited to new ranges. Judge whether those edits weakened coverage |

## 5. Weak points already known to the author

1. Nothing in this batch was viewed in a browser. The Settings page and the Advanced World page are long.
2. The Expo dev server did not notice edits made through the Claude tools and served a stale bundle until restarted.
3. The shell used for commands has `NODE_ENV=production`. A frontend server started from it serves a white screen. Jest fails with "actImplementation is not a function" unless `NODE_ENV=test`.
4. A choice that repeats the player's last action is forbidden only by prompt text.
5. The 18+ level descriptions in the builder and Settings describe the labels in plain words. They were not checked against the policy code.
6. Speed setting "Fast" equals the configured effort, so it changes nothing today. "Careful" restores 3 to 4 minute openings.
7. Guided and Quick Start ignore the story feel and harshness defaults.
8. Rejected model replies are not stored, so a slow retried opening cannot be diagnosed after the fact.
9. `docs/api.md` does not describe `POST /api/story/session/{id}/play-settings`, `prose_style`, `thinking_effort`, `timePeriod` or the new `premise` setup key (it mentions the older `custom_premise` only). `docs/frontend.md` and `docs/story-engine.md` were not updated. Checked by grep on 23 November.

## 6. Configuration outside git

`backend/.env` is not tracked. Values that change behaviour, as of packet time (keys and secrets omitted on purpose; do not print them):

| Setting | Value |
|---|---|
| `DEFAULT_MODEL`, `FALLBACK_MODELS`, `MATURE_MODEL_ID` | `openai-direct/grok-4.7` on xAI direct |
| `OPENAI_DIRECT_REASONING_EFFORT` | `low` |
| `DEFAULT_PROSE_MODE` | `standard` |
| `DEFAULT_MAX_TOKENS` | `6144` |
| `VALIDATION_RETRY_STYLE` | `fresh` |
| `MATURE_RENDERER_ENABLED` | `true` |
| `PROVIDER_TIMEOUT` | `300` |

An xAI key was pasted into a chat on 21 November and still needs rotating.

## 7. Live evidence

| Session | What it showed |
|---|---|
| `445a3e62` (deleted) | Typed world "Dinosaur Island Survival" opened as a present-day scene. Two Grok calls of 262 s and 198 s |
| `09db17b9` | Typed world on the page; rolled scarcity `ammo`, debt paid in bullets |
| `e1c927ad` | Scarcity `trust`; opening set in a pre-industrial hamlet, no era given; first reply rejected, cause unknown |
| `fd9e697b` | Premise, future era and matched opening reached the engine; three turns at one table on one question; mature renderer stored five paragraphs as one |
| `d460f99c` | Eval story at effort `low`: opening 89 s, turns 55, 43 and 42 s, four real turns |

Eval baselines in `docs/eval/` were all taken on local `dice-qwen36` on 21 November. None exists for Grok or for the code after `fff8095`.

## 8. How to verify, and hazards

Read these before running anything.

1. Backend tests: `cd backend`, then `.\.venv\Scripts\python.exe -m pytest -m "not live" -q`. `tests/conftest.py` and `tests/db_guard.py` force a database whose name ends in `_test`. Confirm that guard yourself before the first run. Before 20 November a bare `pytest` deleted the local game database.
2. Frontend: set `NODE_ENV=test`, then run Jest, `tsc --noEmit` and `expo lint --max-warnings=0` from `frontend`. Node 20 is at `.nw_tmp\node20\node-v20.20.2-win-x64\node.exe`.
3. Services: `scripts\windows_launcher.py --check` starts or reuses the database, engine (port 8000) and frontend (port 8081). Clear `NODE_ENV` first.
4. Paid provider calls cost Ryan's xAI credit. Do not make any without his say-so. `-m "not live"` makes none.
5. The local game database `dice_reaction` holds Ryan's stories. Read only.
6. Scratch scripts from this session are in `.nw_tmp/opening-trace-2026-11-22/` (git-ignored). They read the live database. They are not part of the product.

## 9. Rules for the reviewer

1. Read only. No commits, no pushes, no branch changes, no edits to tracked files, no deletion.
2. Label every finding VERIFIED (reproduced by a run or probe), LIKELY (supported, not proven) or UNKNOWN.
3. Give each finding as Verdict, Why, Alternative, with a severity (high, medium, low), the file and line, and how you reproduced it.
4. Say what you did not check. An unexamined area is a finding about coverage.
5. Look for what held up as well. List it briefly.
6. Never print secrets. Flag them by location.
7. Do not soften a finding because the author flagged it first in section 5.
8. Save the review as `docs/reviews/2026-11-23-adversarial-review.md` only if Ryan asks you to save it. Otherwise return it in chat.

## 10. Prompt to give the reviewer

```
You are an independent adversarial reviewer for the repository at C:\dev\dice-reactions, branch emergent, HEAD 014b1a2.

Read docs/reviews/2026-11-23-adversarial-review-packet.md first. It was written by the party whose work you are reviewing. Treat every statement in it as a claim to test, and trust the code over it.

Scope is the whole repository. Spend depth in this order: (1) the 8 commits after fff8095, (2) the engine modules and mature content policy the 20 November review did not audit, (3) whether the 16 fixes from 20 November still hold.

Follow section 8 of the packet before running anything, and section 9 for how to report. Work read only. Make no paid provider calls. Never print secrets.

Return: a verification table, findings ordered by severity in Verdict / Why / Alternative form with evidence labels and reproduction steps, a short list of what held up, and a plain statement of what you did not check.
```
