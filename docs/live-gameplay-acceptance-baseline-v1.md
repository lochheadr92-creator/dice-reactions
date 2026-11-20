# Dice Reactions — Live Gameplay Acceptance Baseline v1

**Status:** SPECIFIED / NOT YET ACCEPTED
**Created:** 2026-11-21 (Australia/Brisbane)
**Target checkout:** C:\dev\dice-reactions; branch emergent; HEAD 0006c5c491035cba9c2974d80f616183c5aad0cd at authoring.
**Working tree:** 22 tracked modifications and 7 existing untracked files at inspection. Preserve them.
**Authorities:** current runtime code and tests define implementation truth; Storytelling Master and Source of Truth v1.2 define intended behaviour. This baseline does not replace either.
**Scope:** closed-beta gameplay acceptance, not app-store certification or proof of an offline autonomous world.
**Money:** no paid LLM tests without separate approval of model, provider call allowance and maximum spending. An attempt budget is NOT an AUD ceiling.

## Verdict contract

Gates: PASS, FAIL, INCONCLUSIVE or NOT RUN. CLOSED_BETA_CANDIDATE requires all mandatory gates G0–G4 PASS, no open P0/P1 bugs and owner acceptance. No skipped probe, mocked provider pass, historical claim or missing telemetry may be promoted to live PASS.

- P0 (blocker): lost/corrupt saved state; unauthorised additional player action or duplicated committed action; destroyed/dead facts silently restored; cross-user data leak; unbounded paid work.
- P1 (beta blocker): serious uncorrected prose/state contradiction; false NPC knowledge; recurring scenario loop; player-agency violation; unrecoverable action; unreliable live model; long sustained latency.
- P2: awkward prose, light repetition, minor pacing/UI issue with workaround. Keep in the register.

## Evidence and safety

Before every test: record local HEAD, branch, git status, full dirty-file manifest, diff/untracked hashes, OS/Python/Node versions, model exact ID, nonsecret runtime flags, test-server URL, UTC timestamp, test database, run ID, budgets and test results. Never publish auth tokens, raw prompts containing private text, or private exports. Store raw JSON only in ignored, local test-output directories.

Use a UNIQUE disposable test database and a dedicated MongoDB replica set; never the gameplay database. The existing backend/tests/db_guard.py enforces names ending with _test, but that suffix alone does not prove an old database is disposable. Do not modify the user's backend/.env, real campaigns, branch, commits or untracked work.

## G0 — Reproducible and safe environment (mandatory)

PASS: recorded checkout/dirty fingerprints; isolated test replica set, unique empty test database; no paid network access in deterministic run; git diff --check clean; no gameplay database touched. FAIL on unsafe DB, test-side data deletion, unknown source tree or paid work.

Suggested PowerShell preflight from repo root, ONLY after dedicated test MongoDB is running:
~~~powershell
git status --short
git rev-parse HEAD
git branch --show-current
git diff --check
$env:TEST_DB_NAME = "dice_acceptance_$((Get-Date).ToString('yyyyMMddHHmmss'))_test"
$env:MONGO_URL = "mongodb://127.0.0.1:27929/?replicaSet=diceAcceptance"
$env:OPENROUTER_API_KEY = ""
$env:OPENAI_API_KEY = ""
$env:NVIDIA_API_KEY = ""
~~~
These are example process-local variables, not a command to change the game database. Verify the MongoDB endpoint and choose a disposable name first.

## G1 — No-cost deterministic regressions (mandatory)

Run backend tests against the isolated test replica set:
~~~powershell
Set-Location C:\dev\dice-reactions\backend
.\.venv\Scripts\python.exe -m pytest -m "not live" -q
~~~
Run existing frontend Jest, TypeScript and lint checks. Require 0 unexpected failures, with exact pass/deselect/skip counts. Required coverage: transactions/revisions, idempotency/retries, provider budgets, test-db isolation, object/injury/death permanence, secret boundaries, renderer fallback, repetition guard, player agency controls, narrative tag recovery, room-object structures and provider routing. A missing required test is INCONCLUSIVE. These results prove specified inputs and invariants, not live narrative quality.

## G2 — Real-model endurance and saves (mandatory, PAID)

Only on an isolated server/database, with explicitly approved model/version, paid-call limit and provider-side monetary spending cap. First establish canonical single-pass narration; leave the optional second-pass mature renderer OFF in the *test process only*. Do not edit backend/.env. Freeze provider and model, plus prose mode, for comparison.

Use the already present backend/tests/test_live_20_turn_harness.py to produce structured per-turn metrics. Set HARNESS_TURNS=20 and HARNESS_REPORT_PATH to an ignored, private .nw_tmp/acceptance path. Its own gate permits some failed turns; therefore ALWAYS grade its JSON with backend/tools/grade_acceptance.py.

Required strict automated G2 criteria per campaign:
- Exactly 20 action attempts, 20 HTTP 200 successes, 0 5xx or transport failures; monotonically consecutive unique turn numbers.
- Exactly 20 corresponding telemetry rows and 20 valid committed rolling states; admin export succeeds.
- Context growth bounded and protected memory categories not truncated by prompt projection. Missing metrics => INCONCLUSIVE.
- Validation retry rate no greater than 20% (provisional pilot target). Record all retry reasons/model swaps, never hide them.
- Report median/p95 HTTP latency, token usage, model calls, cost and fallbacks. Provisional UX targets: median <=25s, p95 <=90s; slower results require separate UX review.

Coverage: three 20-action campaigns in different settings (prehistoric survival, grounded modern mystery, fantasy/social conflict). A second advertised model/provider receives its own non-pooled run. No aggregate PASS from one campaign or from mocked models.

## G3 — Adversarial truth and agency (mandatory, live plus human audit)

Start with existing test_gateway_live_probe.py and qa_live_20turn_hostile.py. They sometimes SKIP when a model fails to establish a test fixture: treat that as INCONCLUSIVE, never PASS. Their legacy no-action-ID actions do not verify idempotent retry behaviour.

Eight required probes, each with witnessed initial state, intended action, authoritative event or receipt, final state, player prose and redacted evidence:
1. Terminal item: destroy/consume, then try to reuse. No intact revival or invented replacement.
2. Dead NPC and actor-local knowledge: death persists; uninformed actor cannot know an unshared secret.
3. Serious injury/resource accounting: no spontaneous healing or free inventory/resource creation.
4. Location, item and relationship continuity: revisit a location and repair/break a promise; remembered state remains grounded.
5. Player agency: observation-only turn and an ambiguous turn must not acquire an unrequested decision, commitment, travel or attack.
6. Anti-loop: 5+ varied actions; no recycled endings or choices and no semantically repeated event under paraphrase; legitimately repeated options should remain allowed.
7. Renderer A/B: in a separate test process, turn the optional mature rerender ON and compare its output to the stored canonical prose; zero factual differences. Validator PASS alone is insufficient.
8. Recovery/ownership: abort HTTP response after a successful commit, retry same action_request_id, reload. Exactly one committed turn; no lost draft and no secret/debug data on player API.

G3 PASS: all eight setups established and evaluated; zero unresolved P0/P1 violations. Missing preconditions or missing raw evidence => INCONCLUSIVE.

## G4 — Independent player experience (mandatory)

Five first-time players with no code knowledge; each plays at least 20 minutes or 15 real turns. No developer coaching beyond a one-sentence premise. Record time to first action, comprehension, turn latency, choice relevance, agency, moments of confusion, willingness to continue and observed persistence after reload.

Pass thresholds: 4/5 create and act without help; 4/5 understand situation and available options after Turn 1; 4/5 score agency, causal clarity and desire to continue at least 4/5; zero data loss or unrequested player action; zero open P0/P1 bugs. Report non-identifying responses and whether testers voluntarily return later. Self-evaluation cannot replace this gate.

## Deliberate nonclaims

This does not certify an offline autonomous heartbeat (current autonomy is turn-coupled), perfect hallucination removal (some rolling state remains model-proposed), full event-sourced reconstruction, native-store release, cross-device account recovery, pricing safety, 24/7 hosting, accessibility/legal compliance, or commercial success. Separate product gates must assess those claims.

## Results register (initially unrun)

| Gate | Initial status | Evidence |
|---|---|---|
| G0 safety & checkout | NOT RUN | git fingerprint / isolated DB |
| G1 deterministic | NOT RUN | backend + frontend logs |
| G2 live 3x20 | NOT RUN | raw JSON reports + grader verdicts |
| G3 eight adversarial scenarios | NOT RUN | initial/committed/prose traces |
| G4 five independent players | NOT RUN | anonymised scorecards |

Overall: NOT ACCEPTED — acceptance execution has not yet completed.

### Grade one existing endurance report
~~~powershell
Set-Location C:\dev\dice-reactions
.\backend\.venv\Scripts\python.exe .\backend\tools\grade_acceptance.py .\.nw_tmp\acceptance\live20.json
~~~
The grader reports AUTOMATED_PASS, AUTOMATED_FAIL or INCONCLUSIVE and deliberately does not certify the G3/G4 human gates.

## Execution addendum — 2026-11-21 local acceptance preparation

**Current tested HEAD:** c3672bcd0417f0dad0167d34ff3d1cae81f1c7a8, branch emergent. Two other commits (4d817d3 local Ollama, c3672bc Qwen reliability) landed while the first test run was in progress; the first result is retained as historical but does **not** qualify as a frozen-tree proof.

**G1 PASS on frozen checkout:** a subsequent fresh full backend run captured source fingerprints before and after and found **SOURCE_UNCHANGED=True**. Results: **1488 passed, 36 live deselected, 6 warnings, 0 failed**. The frontend run against the same unchanged frontend code produced **71 Jest passed, TypeScript passed, ESLint passed**. Process-only test configuration fixed the intended default model to Sonnet 4.5 with fallback Sonnet/DeepSeek; this did not change user backend/.env or make paid provider calls.

**G0 FAIL (format-only outstanding):** source control and test isolation were verified, and tests used only a dedicated diceAcceptance replica set on localhost:27929 with new names ending in _test. However, git diff --check currently reports two pre-existing trailing blank-line errors at backend/tests/test_mature_rendering.py:243 and backend/tests/test_provider_selection.py:413. They were **not modified** during this baseline work. Resolve and rerun diff check before claiming G0 PASS.

**G2/G3/G4: NOT RUN.** Real-provider endurance, adversarial semantic review and independent-player testing require additional execution and approved paid-call budgets. Do not publish an overall acceptance PASS.

**Evidence saved locally (Git ignored):**
- .nw_tmp/acceptance/g1-backend-frozen.txt
- .nw_tmp/acceptance/g1-frozen-result.json (contains both fingerprints)
- .nw_tmp/acceptance/g1-frontend-jest.txt
- .nw_tmp/acceptance/g1-frontend-tsc.txt
- .nw_tmp/acceptance/g1-frontend-lint.txt
- .nw_tmp/acceptance/run-evidence.json (initial snapshot taken after concurrent commits)

**Safety:** No production data, user .env, or user-authored uncommitted code was edited as part of this baseline. No Git commit, push or deployment was performed. The only tracked-tree changes made by this work are **new untracked acceptance artifacts**: this document, the grader and its unit tests.
