# Adversarial review, 20 November 2026

Reviewer: Claude (Fable 5.2), read only session requested by Ryan.
Scope: the whole repository as found on disk, meaning HEAD plus the uncommitted reliability work described in `docs/reliability-release.md`.
Repo state at review: `C:\dev\dice-reactions`, branch `emergent`, HEAD `d670da33b07a6b49352b888d218994b7a3c725f0`, 49 dirty entries, level with `origin/emergent` by local refs (no fetch was run).

This is a dated review record. Line numbers refer to the working tree on 20 November 2026 and will drift after edits.

## Evidence labels

- VERIFIED: reproduced in this session by a test run or a probe.
- LIKELY: supported by evidence, cause or impact not fully proven.
- UNKNOWN: not checked or not checkable from this session.

## Method and limits

- All tests and probes ran on a copy of the tree in a sandbox, against a throwaway MongoDB 7.0.16 single node replica set. Nothing ran against the real `backend/.env` database. No paid provider call was made.
- Backend ran on Python 3.10.12 with unpinned compatible packages. CI and the reliability report use Python 3.12 with `constraints.txt`.
- Frontend ran on Node 22. CI uses Node 20.
- The engine modules (about 45,000 lines) were sampled, and were not audited line by line. Utility AI, pressure graph, information engine, goal engine and world event engine received no deep read.
- Mature content policy was not reviewed. The UI was not driven in a browser. The Emergent deployment was not inspected.
- The probe scripts were not saved into the repo. They import the test fixtures that delete sessions and turns (finding 1), so keeping them here would add to that hazard. Each finding below states how it was reproduced.

## Verification results

| Check | Result | Label |
|-------|--------|-------|
| Backend `pytest -m "not live"` | 1386 passed, 1 failed, 36 deselected | VERIFIED |
| Reliability report figure | 1387 passed | Docs claim, differs by the flaky test in finding 13 |
| Frontend Jest | 8 suites, 70 tests passed | VERIFIED |
| Frontend `tsc --noEmit` | clean | VERIFIED |
| Frontend `expo lint --max-warnings=0` | exit 0 | VERIFIED |
| `yarn install --frozen-lockfile` | succeeded | VERIFIED |
| Web export | not run | UNKNOWN |

## Findings, high severity

### 1. Running the backend tests deletes the local game database (VERIFIED)

Verdict: a bare `pytest` run in `backend` wipes every saved chronicle on this machine.

Why: `backend/tests/conftest.py` line 7 loads `backend/.env`. That file names `DB_NAME=dice_reaction` on `127.0.0.1:27017`, the same database the Windows launcher uses for saved stories. Line 11 uses `setdefault`, so the test database name never replaces the real one. Four fixtures then delete all sessions and turns in that database: `tests/reliability_support.py` lines 76 to 77, `tests/test_action_concurrency.py` 105 to 106, `tests/test_secret_reveal.py` 451 to 452, `tests/test_replayability_integration.py` 1071 to 1072. The documented command in `docs/development.md` sets `DB_NAME` by hand, which hides the hazard. `AGENTS.md` lets agents run tests without asking.

Reproduction: sandbox copy with a `.env` naming a stand in database holding 3 sessions and 40 turns, no `DB_NAME` in the shell. One stock test (`tests/test_action_idempotency.py -k sequential_duplicate`) left 0 sessions and 0 turns.

Alternative: in `conftest.py`, set the test database name outright, refuse to start unless the name ends in `_test`, and stop loading the real `.env`.

### 2. Creation size limits fail to bound the prompt (VERIFIED)

Verdict: the report's claim that input size limits return 422 before any paid work is false for `custom_world_setup`.

Why: `_measure_text` (`backend/server.py` line 3685) counts string values only. Keys, numbers, booleans and empty strings cost nothing. `normalize_custom_world_setup` (`backend/creation_contract.py` line 281) keeps unknown top level keys and passes nested dicts through unchanged. `_clean_setup` (`server.py` line 1048) caps string and list lengths, and does not cap key count. No request body size limit exists.

Reproduction: a setup holding 40,000 numeric keys returned 200. The opening prompt grew from 40,493 characters to 778,249 characters and the stored session reached 976,287 bytes. A nested dict of 40,000 empty strings gave 749,396 characters. A single 2,001 character string returned 422. At 4 characters per token (an estimate) each provider attempt carries roughly 200,000 tokens, and the figure scales with key count.

Alternative: allowlist known setup keys in the normaliser, cap key count and serialised JSON size, and add a request body size limit.

### 3. A failed story creation leaves a permanently stuck shell (VERIFIED)

Verdict: the creation path lacks the crash recovery the action path received.

Why: `server.py` line 4076 inserts a provisional session before generation. Lines 4111 to 4209 then run about fifteen engine steps on the model output with no error handling. An exception, a cancellation or a process kill there leaves a session at turn count 0. `_build_existing_creation_response` (line 3784) answers every retry with the same creation id with 409 "Story creation already in progress". The frontend reuses the id while the payload is unchanged (`frontend/app/new-story.tsx` line 173). `list_sessions` returns the shell, so the home list shows a T·000 entry. `CommitOutcomeUnknown` (line 4227) leaves the same shell when the commit did not land.

Reproduction: forced an exception in `hud.shape_hud` during creation. First request 500, retry with the same id 409, shell listed with turn count 0.

Alternative: wrap the post generation steps with cleanup, handle `asyncio.CancelledError`, and let a retry take over a provisional session older than the lease time.

### 4. The generation deadline is no wall clock limit (VERIFIED)

Verdict: the report's "one total deadline" claim fails, and its review fix F1 (lease floor of deadline plus 60 seconds) rests on that claim.

Why: `backend/ai_service.py` lines 286 to 291 pass the remaining time as the httpx timeout. That value limits each wait between bytes, and sets no limit on the whole call. A slow response outlives the lease, a retry takes over, and a second generation is paid for. The commit precondition still blocks a double turn. The provider concurrency slot also expires while still in use.

Reproduction: a local server sending one byte every half second. `_call_model_once` with `timeout_seconds=1.0` returned after 8.1 seconds. `chat_completion_with_meta` under a 2.0 second budget deadline returned after 8.1 seconds.

Whether the real provider sends bytes this way is UNKNOWN.

Alternative: wrap the call in `asyncio.wait_for` with the remaining time.

### 5. Standalone MongoDB turns every write into 503 (design verified, exposure UNKNOWN)

Verdict: pushing this tree to a host without a replica set stops story creation, actions, reset and delete.

Why: the behaviour is deliberate and documented in `docs/development.md`. `.emergent/emergent.yml` names the image `expo_mongo_base_image_cloud_arm`, which bundles its own MongoDB. Its mode was not checkable from this session.

Alternative: on the Emergent environment, check `db.hello()` for `setName` before pushing, or call `GET /api/admin/consistency` after deploy and read `transaction_support_error`.

## Findings, medium severity

### 6. IP rate limiting collapses behind a proxy (VERIFIED)

Verdict: honest players share one bucket and a client sending a fake header gets a private one.

Why: `backend/rate_limit.py` line 98 rejects a forwarded chain whose length equals `TRUSTED_PROXY_COUNT`. With N trusted proxies each appending one entry, an honest chain has exactly N entries. `tests/test_rate_limit.py` encodes the fault as expected behaviour (`test_spoofed_only_chain_falls_back_to_peer`). `docs/api.md` line 87 documents the same condition.

Reproduction: with one trusted proxy, the chain `203.0.113.9` resolved to the proxy address `10.0.0.5`. The chain `1.2.3.4, 203.0.113.9` resolved to `203.0.113.9`. All honest players then share 10 creations per hour.

Alternative: change `<=` to `<` and correct the tests and `docs/api.md`.

### 7. Invalid requests burn creation quota (VERIFIED)

Verdict: quota is reserved before cheap validation runs.

Why: `new_story` reserves the global, IP and device buckets at `server.py` line 3810. Scenario resolution (line 3879) and mature content validation (line 3922) run later inside `_create_new_story`, and a 422 there triggers no rollback.

Reproduction: three requests with an unknown `scenario_id` returned 422. The next valid request returned 429 with zero provider calls. Buckets read global 3, ip 3, device 3.

Alternative: run validation before reserving, or roll back the buckets on a 4xx.

### 8. A crash mid action locks the chronicle for 10 minutes (VERIFIED)

Verdict: the lease outlasts what the deadline needs, and nothing clears a dead worker's lease.

Why: `resolve_lease_seconds()` returns 600 (`backend/action_concurrency.py` line 41, floor 300 from the 240 second deadline). The startup handler creates indexes only. No heartbeat exists. `uvicorn --reload` restarts the process on every file save during development.

Alternative: default the lease to deadline plus 60 seconds, and clear leases at startup on single process deployments. A heartbeat is the fuller fix and costs more code.

### 9. Reset leaves a dead chronicle and contradictory answers (VERIFIED)

Verdict: reset has no coherent end state.

Why: after reset the session stays listed at turn count 0 and `/latest` returns 404. A replay of a completed request id returns 404 "Turn not found" (`server.py` line 4254) while the status endpoint returns failed with `superseded` (line 4654). `/admin/consistency` counts the session under `completed_without_turn` and under provisional sessions, both false alarms. An action on the shell commits turn 1 through the action path with no opening seed and `replayability_state` of None. The UI routes to the new story screen and leaves the shell on the home list.

Alternative: the simplest option is the UI calling delete in place of reset. The other option is reset rerunning the opening turn, which costs a provider call and more code.

### 10. Model output overwrites a creation fact the code calls protected (VERIFIED)

Verdict: `restore_creation_surfaces` keeps the model's value whenever one is present.

Why: `backend/creation_contract.py` lines 850 to 855 restore a hook only when the model left it empty. Only `desire` and `fear` are always restored. The root cause sits in `consolidate_rolling_state` (`backend/memory.py` line 246), which lets model output replace every top level key. The engine then restores chosen keys one at a time, so any engine owned key without a restore step is writable by the model.

Reproduction: a model reply changed `character_hooks.relationship_archetype` from `sibling` to `sworn_enemy` and the change persisted. In a wider probe, 8 of 15 top level keys were restored (`active_goals`, `active_pressures`, `active_situations`, `active_world_events`, `actor_stress`, `known_rooms`, `pressure_graph`, `secret_registry`). `world_frame` kept its contract values and accepted extra keys. Relationship numbers resisted direct edits.

Alternative: assign contract values unconditionally for contract owned keys now. Longer term, switch the merge to an allowlist of keys a model is permitted to write.

### 11. Chronicles past 500 turns lose their newest turns on reload (VERIFIED)

Verdict: the cap cuts the wrong end.

Why: `server.py` lines 4780, 4705 and 4692 sort ascending with `to_list(length=500)`. `docs/feature-status.md` notes the cap and omits the effect. The same endpoints fetch full turn documents, including `rolling_state` and `raw`, before trimming to player fields.

Reproduction: with 503 stored turns, the session endpoint returned turns 1 to 500. Export returned 500 turns and reported a turn count of 500.

Alternative: page from the newest turn and project only the fields the player payload needs.

### 12. A non ASCII header returns 500 from the auth check (VERIFIED)

Verdict: `hmac.compare_digest` raises `TypeError` on non ASCII strings.

Why: `backend/security.py` lines 41 and 75, `backend/action_concurrency.py` line 111, `backend/action_requests.py` line 120.

Reproduction: `X-Admin-Api-Key: é` returned 500, where a wrong ASCII key returned 401. `X-Device-Id: é` on a session read returned 500.

Alternative: encode both sides to UTF-8 bytes before comparing.

## Findings, low severity

### 13. Flaky rate limit test (flake VERIFIED, cause LIKELY)

`tests/test_rate_limit.py::TestStoryCreationRateLimit::test_ip_limit_throttles_rotating_devices` failed in the full run (200 where 429 was expected). The file failed once more in about 17 reruns. The limiter keys its 60 second windows on the wall clock. Shifting the clock 60 seconds before the fourth request reproduced the same symptom. CI will fail at random. Freeze the bucket clock in these tests.

### 14. One request id to one turn has no database guarantee (VERIFIED)

`turns_action_request_key` is a non unique partial index (`backend/action_requests.py` line 111). The invariant rests on claim logic alone. Make the partial index unique.

### 15. A stray scratch file with an explicit adult prompt is tracked and on origin (VERIFIED)

`completion = client.chat.completion.txt` at the repo root, added in commit `c918e8c` on 10 July 2026. No key inside. The sibling export was ignored on 22 July. Repo visibility is UNKNOWN. Untrack the file, and rewrite history before sharing the repo.

### 16. Dependencies (VERIFIED unless noted)

Thirteen declared backend packages are never imported: boto3, pandas, numpy, python-jose, passlib, bcrypt, pyjwt, jq, typer, cryptography, requests-oauthlib, email-validator, python-multipart. Dev tools (pytest, black, isort, flake8, mypy) sit in the runtime requirements. `motor==3.3.1` is pinned. The Motor documentation states Motor reached end of life on 14 May 2026 with critical fixes until 14 May 2027, and recommends the PyMongo Async API. The pins for fastapi 0.110.1, uvicorn 0.25.0 and pymongo 4.5.0 were not checked against security advisories (UNKNOWN).

### 17. Documentation drift (VERIFIED)

- `README.md` is a one line placeholder.
- `docs/development.md` lists `anthropic/claude-haiku-4.5` as the `DEFAULT_MODEL` default. `backend/ai_config.py` lines 45 to 52 treat Haiku as deprecated and silently map it to Sonnet 4.5, a cost surprise.
- `docs/development.md` "Developer unlock flow" says the client posts admin settings. The code requires the admin key, and `frontend/app/settings.tsx` asks for it.
- `docs/current-state.md` carries a 22 July 2026 header above later corrections.
- `docs/reliability-release.md` marks as PASS three areas contradicted by findings 2, 3 and 4.

### 18. Smaller items (VERIFIED by reading)

- `device_id` in the `/story/new` body has no length limit (`_validate_creation_input` omits it).
- `ensure_action_concurrency_indexes` skips every index when duplicate turn rows exist, logs only, and scans the whole turns collection at each startup.
- `/admin/consistency` caps `completed_without_turn.count` at the sample size.
- Provider error text is stored in the session `model_switches` list.
- `developer_mode` is one server wide switch. Any player sending `debug_mode: true` then receives debug payloads for their own sessions.
- No `.gitattributes` exists. The working tree holds CRLF on every line while the index holds LF, and both Windows and Linux agents touch this repo.
- `@app.on_event` is deprecated in FastAPI in favour of lifespan handlers.

## What held up

- The transactional commit, the lease plus turn count plus revision precondition, replay of completed requests, and the atomic concurrency pool behaved as claimed in every test and probe.
- Turns are insert only. No code path updates a committed turn.
- Engine modules use no random calls and no clock calls. The run seed is stored once per story.
- A scan of git history for six key patterns (OpenRouter, OpenAI, NVIDIA, GitHub, AWS, MongoDB credentials) found nothing. `.env` files are ignored.
- Device ids come from the platform secure random source.
- Player facing payloads pass through allowlist serialisers.

## Necessary fixes, in order

Before the next backend test run:

1. Finding 1. Guard `conftest.py` so tests never touch a database whose name does not end in `_test`.

Before committing the reliability work:

2. Finding 2. Bound `custom_world_setup` by allowlist, key count and serialised size. Add a request body limit.
3. Finding 3. Clean up or take over provisional sessions after a failed creation.
4. Finding 4. Enforce the generation deadline with `asyncio.wait_for`.
5. Finding 13. Freeze the clock in the rate limit tests so CI results mean something.
6. Finding 17, last bullet. Correct the three PASS rows in `docs/reliability-release.md`.

Before pushing to `emergent` or any hosted deployment:

7. Finding 5. Confirm the host MongoDB is a replica set.
8. Finding 6. Fix the forwarded chain length check.
9. Finding 7. Validate before reserving quota.
10. Finding 15. Untrack the scratch file.

Necessary, lower urgency:

11. Finding 12. Byte encode before `compare_digest`.
12. Finding 14. Make the request key index unique.
13. Finding 8. Shorten the lease and clear dead leases at startup.
14. Finding 10. Assign contract values unconditionally.
15. Finding 9. Decide what reset means, then make the server and UI agree.
16. Finding 11. Page turns from the newest end.

Optional: findings 16 and 18, and the remaining bullets of 17.

No fix in this list has been authorised or started. Each needs Ryan's approval.

## Resolution, 20 November 2026 (same day)

Ryan authorised all 16 fixes in the Claude chat on 2026-11-20 ("lets begin working through all 16 fixes"). Changes sit in the working tree, uncommitted. Previous versions of the 22 modified files are kept in `.nw_tmp/review-fixes-2026-11-20/before/` (git-ignored).

| # | Finding | Change | Regression test |
|---|---------|--------|-----------------|
| 1 | 1 | `tests/conftest.py` + new `tests/db_guard.py`: forces `TEST_DB_NAME` (default `dice_reactions_test`), refuses names not ending in `_test`, stops loading `backend/.env`, blanks provider keys unless the shell sets them. CI uses `TEST_DB_NAME: dice_reactions_ci_test` | `tests/test_test_database_guard.py` |
| 2 | 2 | `CREATION_SETUP_JSON_MAX_CHARS` (16000) and `MATURE_CONTENT_JSON_MAX_CHARS` (8000) count serialized JSON; new `request_limits.py` body limit `MAX_REQUEST_BODY_BYTES` (262144, 413) | `test_provider_budget.py`: serialized size, body limit |
| 3 | 3 | `_create_new_story` wraps the build: any failure or cancellation before the commit is attempted deletes the provisional session; stale provisional sessions are taken over by a retry; provisional sessions are not listed | `tests/test_creation_recovery.py` (5 tests) |
| 4 | 4 | `asyncio.wait_for` around the provider POST | `test_provider_budget.py`: slow drip returns timeout under 3 s |
| 5 | 13 | `rate_limit._epoch_seconds()` seam; rate limit tests and `relax_rate_limits` freeze it; the window reset test advances the clock instead of sleeping | 14 consecutive clean runs of `test_rate_limit.py` |
| 6 | 17 | `docs/reliability-release.md` corrections section and table rows; `api.md`, `development.md`, `windows-launcher.md` updated | n/a |
| 7 | 5 | Closed by Ryan, 2026-11-20 23:05: the backend was rebuilt to drop the Emergent dependency, so no Emergent host serves it. It runs locally: `backend/.env` names replica set `rs0`, and both the launcher and server startup refuse a standalone server loudly. Mongo was not running at check time, so live topology was not read | n/a |
| 8 | 6 | `len(parts) < N`; tests corrected to the documented deployment model, with prepended-entry tests added | `test_rate_limit.py` proxy tests |
| 9 | 7 | `new_story` refunds creation buckets on any 4xx | `test_review_hardening.py` |
| 10 | 15 | Scratch file untracked (`git rm --cached`, staged only) and ignored; still on disk. History rewrite not done | n/a |
| 11 | 12 | `security.constant_time_equals` compares UTF-8 bytes; used in security, action_concurrency, action_requests | `test_review_hardening.py` |
| 12 | 14 | New unique partial index `turns_action_request_key_unique`; duplicate data logs an error and never blocks startup; the old non-unique index is left in place | `test_review_hardening.py` |
| 13 | 8 | Default lease = deadline + 60 s (300 s, was 600 s); opt-in `CLEAR_LEASES_ON_STARTUP=1` frees session leases, concurrency slots and request claims; the Windows launcher sets it | `test_review_hardening.py`, `test_session_lifecycle.py` |
| 14 | 10 | `restore_creation_surfaces`: contract hook values and `required_elements` always win; model-added extra hooks are kept | `test_creation_enforcement.py` |
| 15 | 9 | App "Reset chronicle" deletes the chronicle and opens New Story; server reset deletes request records and sets `reset_at`; consistency report counts reset shells separately | `test_session_lifecycle.py`, `play-action-idempotency.test.tsx` |
| 16 | 11 | `_newest_turns` keeps the newest `TURN_WINDOW_MAX` turns for session, export and history; player reads project player fields only; export summary adds `turns_included` and `truncated` | `test_session_lifecycle.py` |

Verification, 2026-11-20 (VERIFIED by execution, sandbox, Python 3.10, Node 22, MongoDB 7.0.16 replica set):

- Backend `pytest -m "not live"` on a fresh copy of the repo files, with the real `backend/.env` present and `DB_NAME` unset: 1418 passed, 36 deselected. Only `_test` databases were created.
- Same suite with `TEST_DB_NAME=dice_reaction`: refused at startup with `UnsafeTestDatabase`.
- Frontend: Jest 71 passed, `tsc --noEmit` clean, `expo lint --max-warnings=0` exit 0.
- Launcher `unittest`: 9 passed. pyflakes: no new findings in changed files.

Behaviour changes to know:

- Reset in the app now deletes the chronicle. Existing reset shells created before this change have no `reset_at`, so they no longer appear in the home list.
- Old request ids sent after a server-side reset create a new turn.
- With `CLEAR_LEASES_ON_STARTUP=1` and several backend workers, a restarting worker would free a running worker's lease; keep it off for multi-worker deployments.

Not verified: Python 3.12 / Node 20 (CI versions), the web export, a browser run of the UI, live provider calls, and the Emergent host's MongoDB mode.
