# Independent adversarial review — 23 November 2026

Reviewer: Codex, fresh review of the supplied packet and current working tree.

## Repository and scope

Verified first: `C:\dev\dice-reactions`, branch `emergent`, HEAD `014b1a28280edf70d36f4b4f52a66a6fe8acc889`; local `origin/emergent` remained `fff8095`. Eight commits are ahead. No fetch, branch change, commit, push, pull, or tracked-file edit was made. The untracked packet was preserved. The only file created by this review is this report. I read the packet, repo instructions/doctrine, the prior review and its resolution table, and inspected the eight-commit diff (30 tracked paths; 2,426 additions, 276 deletions), focusing on builder flow, prompts/turn rules, settings, creation limits, mature rendering, tests and docs. A whole-repository line-by-line audit is not claimed.

## Verification

| Check | Result | Evidence |
|---|---|---|
| Repo identity / clean baseline | VERIFIED | Branch and HEAD match packet; working tree had only the pre-existing untracked packet. |
| Backend deterministic suite | VERIFIED | `pytest -m "not live" -q -p no:cacheprovider`: 1,605 passed, 36 deselected, 6 warnings, 54.39s. Test guard inspected: `tests/conftest.py` sets and enforces a `_test` database before server import. No live tests/eval were run. |
| Frontend unit tests | VERIFIED | Node 20 Jest: 9 suites, 90 tests passed. `NODE_ENV=test` set for Jest. |
| TypeScript / lint | VERIFIED | `tsc --noEmit` and Expo lint `--max-warnings=0` exited 0. |
| Local service | VERIFIED | App returned HTTP 200; `/api/health` returned `status=ok`, `llm_configured=true`. No services were started. |
| Browser creation flow | VERIFIED | Advanced builder completed; selected custom world, premise, present day, crowded city, route failure, speculative, character/relationship/experience options; review screen showed selections and an explicit preset marker for the untouched condition. Created story successfully. |
| Live AI turns | VERIFIED / UNKNOWN | Opening and three subsequent responses arrived. A fourth subsequent action remained at “the dice fall…” on repeated observations; no final response or error was observed before I stopped. Exact elapsed time for this pending action was not captured reliably, so no latency number is asserted. One story only; 18+ stayed off. |
| Browser console | UNKNOWN | Could not obtain reliable per-screen console evidence. |
| Security / real deployment / provider behavior | UNKNOWN | No deployment inspected; no live-provider validation beyond the authorized story play. |

## Findings, ordered by severity

### 1. Prompt rules do not enforce clear, advancing turns — LIKELY, medium

**Verdict:** The “always required” turn rules can improve model behavior, but the application does not make them a hard acceptance condition. A generated response that omits a clear cost or repeats an action can still be shown if it passes the existing structural/game-state validator.

**Why:** `backend/turn_rules.py:15-30` supplies prose instructions (including movement, choice freshness and consequence clarity). Tests check the rule text is included; they do not establish an output validator for these qualities. During play, the first response gave a concrete clue and the next turn advanced crowd pressure, but the game then offered “Tell Sera to stay off the boat” while the existing pressure already said Sera needed a boat-or-stay answer. That is close to re-asking the same decision without new information. The following response again framed the same unresolved choice. This is evidence of a live near-loop, not proof of a general defect or exact semantic duplicate.

**Alternative:** Treat this as a known probabilistic limitation: the sample mostly advanced, the options offered different actions, and the existing scene remained coherent. I did not force a repeated-action exploit or inspect the full validator path for every possible loophole.

**Reproduction:** In the local browser, create a custom floodplain-refuge story with an endangered dependent and a forged evacuation order; take the order-inspection choice, then the choice that calls for holding the boat. Compare the subsequent pressure and choices. For a fix, add a regression test that feeds a structurally valid but looping reply through the actual acceptance path and verify rejection or repair.

### 2. Play-settings API is absent from API reference — VERIFIED, low

**Verdict:** `docs/api.md` does not document the new play-settings route or the new story fields/settings identified in the packet. Its creation schema still documents `custom_premise`; the new builder also stores premise/time-period values under `custom_world_setup`.

**Why:** The route exists at `backend/server.py:5127` and writes story presentation settings; grep of `docs/api.md` found no play-settings, `prose_style`, `thinking_effort`, `timePeriod`, or new `premise` setup key. This is a concrete contract/documentation drift for API users and maintainers.

**Alternative:** The frontend may be the only intended caller and its TypeScript types are current; the route can still function. The gap is in the published API reference, not runtime behavior.

**Reproduction:** Compare `POST /story/session/{id}/play-settings` and request models in `backend/server.py` with `docs/api.md` creation and session sections.

### 3. Advanced setup concentrates nine questions on one page — VERIFIED observation, low

**Verdict:** The Advanced World page is a long form and makes the first step visually dense. In the browser it contained nine prompts, including world type, premise, era, place, strain, recent change, speculative/real, what belongs, and what must not. The page required substantial scrolling before advancing.

**Why:** `frontend/src/newstory/AdvancedBuilder.tsx` groups the entire World section on page 1 of 4. In the browser, headings and controls were readable and no clipped or overlapping control was observed; the issue is page length and scan burden, not broken layout.

**Alternative:** Grouping the questions may help people see the world as a coherent whole; the user can skip optional fields and the page progress remains clear. This is a usability concern from one desktop viewport, not a demonstrated failure.

**Reproduction:** Start Advanced creation in the local web UI at desktop size and scroll World page 1. Mobile and accessibility behavior were not comprehensively checked.

## What held up

- The submitted premise, present-day selection, location, and recent route failure appeared in the opening in a way that tied the immediate choice to the setup. The opening identified who the player was, where they were, why they were there, and the urgent decision.
- The custom-world flow visibly required a typed world name; the review summary distinguished chosen answers from an untouched preset. Settings defaults for Dark/Severe carried into the Advanced review; the saved option labels were understandable in this sample.
- The first two story turns produced concrete, causally related changes (double stamp; Kade retrieving the page; horn; crowd/crew pressure). No system prompt or hidden game mechanics appeared in the sampled narration. No unexplained invented term was noticed.
- Backend creation guards include per-field, aggregate text, serialized JSON and request-body limits; the earlier dangerous large-key issue is not present in this HEAD's documented/implemented guards. This is supported by inspected current code/docs and passing tests, not a new adversarial oversized-input probe.
- The old test-count claim matched this run. The edits from 18 Continue presses to four track the redesigned four-page builder and new tests assert page/question behavior; they do not appear to be a simple test bypass. Prose-mode assertions were changed with the configured ranges and prompt strings; they still assert the intended ranges, though they now validate the new contract rather than compatibility with the old one.
- Mature-rendering code checks paragraph count and policy boundaries before serving rewritten prose; unit tests passed. The real provider renderer was not independently exercised.

## Live play sample

| Item | Observation |
|---|---|
| Story | “Review Test Floodplain Refuge”; created from the Advanced builder. |
| Opening | Two paragraphs, with clear protagonist/place/problem/stakes and six actionable choices. The review-test prefix appeared in the world name as expected. |
| Completed follow-up turns | Three. Each kept the forged order, Kade, Sera and boat pressure active; the scene gained evidence, public dispute, a one-minute hold and social cost. |
| Pending turn | The next action remained on the loading indicator. I stopped without retrying or creating another story. No error message was visible. |
| Choice quality | Choices were concrete actions and varied between inspection, public challenge, protecting Sera, and asking/negotiating. At the third response, the player was again asked to decide whether Sera would take the boat after that had already been the central pressure. This is the near-loop described above. |
| Unexplained terms / system leakage | None noticed in sampled narration. Status HUD showed health/stress/fatigue/danger/momentum as UI chrome; it was not narrated as hidden mechanics. |
| Timing | Opening was visible within a later check under one minute after submission, but exact latency is unknown. Early turns appeared in roughly the same under-a-minute observation cadence; exact measurements were not preserved. The fourth action was still pending on stop; exact duration unknown. |
| Console | Not checked reliably. |
| 18+ | Remained off; no mature content was requested or tested. |

## Not checked / limits

- I did not exhaust the 3-story / 6-turn allowance: one story was created; three subsequent turns completed and the next remained pending. I stopped there, so the second and third stories were not started.
- No forced timeout/retry, concurrent-request, same-event-loop ContextVar, stale settings/list ordering, or turn-lease race probe was run. The `ContextVar` setter in `backend/ai_service.py:100` has no explicit reset; ordinary request task isolation may contain it, so I cannot substantiate the packet's hypothesized cross-request leak from code inspection alone.
- No direct provider test of mature rendering, no 18+ content review, no true prompt-injection challenge, no replay/golden-seed determinism audit, and no deployment/CI run on these eight commits.
- I did not re-probe each of the 16 prior fixes or deeply audit every Tier 2 engine module (`utility_ai.py`, `pressure_graph.py`, `information_engine.py`, `goal_engine.py`, `world_event_engine.py`). Passing the full deterministic suite is not proof of those broader claims.
- Existing project configuration includes a provider credential in the untracked local environment file. Its value was not read or printed in this review. Separately, the packet reports a previously exposed provider key that still needs rotation; I did not validate whether it remains active.
- Two archived ChatGPT records were marked partial by the local prompt-archive refresh because their Codex thread host could not be reached. The refresh completed; no local prompts were added at end-of-turn.

## Push assessment and top fixes

**Not ready to push on this evidence.** The deterministic suites pass, but the live sample ended with a still-pending action and showed a near-repeat at a central decision point; the unpushed branch also has no CI evidence. This is a hold for targeted verification, not a claim that the branch is generally broken.

1. Capture response lifecycle timing and failure state for the pending-turn case, without retrying paid calls invisibly; surface an explicit timeout/retry status to the player if it is not already handled elsewhere.
2. Add an acceptance-path regression for repeated decision pressure and repeated/semantically equivalent choices; determine whether the observed Sera loop is intentional continuity or unwanted repetition.
3. Update `docs/api.md` for play-settings, per-story style/effort, and the current setup payload; then run CI on the exact eight-commit HEAD.
4. Consider splitting or collapsing optional World questions to reduce the nine-question first page, and check the flow at mobile widths.

No code or settings were changed for these fixes; they are review recommendations. No commits were made.
