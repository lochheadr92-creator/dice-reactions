#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Replace the current AI provider (Claude via Emergent LLM Key) with OpenRouter.
  - Use OpenRouter chat completions API (https://openrouter.ai/api/v1/chat/completions)
  - Store API key securely in env (OPENROUTER_API_KEY)
  - Add support for switching models later
  - Keep all existing UI and story systems unchanged
  - Preserve memory, character state, and world continuity
  - Increase token/context handling for long-form story generation
  - Add retry handling for failed completions
  - Add adjustable temperature and max token controls in admin settings
  - Default model: gryphe/mythomax-l2-13b
  - All AI requests route through a centralized aiService layer

backend:
  - task: "Centralized aiService layer (OpenRouter chat completions)"
    implemented: true
    working: true
    file: "/app/backend/ai_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          New module exposes async chat_completion(messages, model, temperature, max_tokens, max_retries).
          - Calls https://openrouter.ai/api/v1/chat/completions with proper headers (Auth, HTTP-Referer, X-Title)
          - Retries on 5xx / 408 / 429 / transport errors with exponential backoff (3 attempts)
          - Non-retryable 4xx fails fast with AIServiceError including provider response excerpt
          - Curated SUPPORTED_MODELS list (Mythomax default + Claude/GPT-4o/Llama/Gemini/Mistral + free tiers)
          - Defaults read from env: DEFAULT_MODEL, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS, DEFAULT_HISTORY_WINDOW
          - Manual smoke test: confirmed 402 on paid models (account no credits), 200 OK on
            openai/gpt-oss-120b:free and google/gemma-4-31b-it:free.
      - working: true
        agent: "testing"
        comment: |
          Verified via /app/backend_test.py + /app/_retry_story.py (public URL https://dice-story-engine.preview.emergentagent.com/api).
          - chat_completion exercised end-to-end through /api/story/new and /api/story/action against
            openai/gpt-oss-120b:free. Both calls returned 200 OK with valid <narrative>/<choices>/
            <state>/<ledger>/<debug> blocks (paragraphs=4 and 3, choices=6/6, debug present).
          - Retry/backoff path observable in logs (no transient failures hit during testing).
          - is_configured() returns true (key present in env), provider_configured reflected on
            /api/admin/settings.
          - get_supported_models() returns 15 entries including default gryphe/mythomax-l2-13b.
          - Observation (not a defect): free-tier completions take 55-65s; the preview ingress
            occasionally returns 502 when paired with the default max_tokens=2048. Reducing
            max_tokens (e.g. 768) consistently returns within the ingress window. This is a
            provider/edge latency artifact, not a backend bug — backend logs show 200 OK.

  - task: "Story endpoints refactored to use aiService + proper messages array"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          Removed emergentintegrations import path. New _generate_turn() builds an OpenAI-style
          messages[] with system prompt + replay of last N turns as user/assistant pairs
          (reconstructed from stored narrative/choices/state/ledger blocks). This preserves
          memory, character state, and world continuity while being far more token-efficient
          than the old "history block" approach. history_window is admin-configurable.
          /api/story/new and /api/story/action both flow through _generate_turn.
          Manual e2e test with openai/gpt-oss-120b:free returned 4 paragraphs, 5 choices,
          full <state>/<ledger>/<debug> blocks parsed correctly. Turn 2 also passed with
          proper continuity (door/generator/red glow carried forward).
      - working: true
        agent: "testing"
        comment: |
          End-to-end verified through public ingress:
          - POST /api/story/new (genre=post-apocalyptic survival, debug_mode=true, free model):
            200 OK, session_id returned, turn.turn_number=1, player_action=None, paragraphs=4,
            choices=6, state populated (Health/Stress/Fatigue/Position/Objective/...), ledger
            populated (Carried/Worn/Stored/Weapons/Supplies/Uncertain/Load), debug block present.
          - Session persisted: GET /api/story/sessions?device_id=… returns the new session.
          - POST /api/story/action with first choice text: 200 OK, turn.turn_number=2,
            player_action matches submitted text, 3 paragraphs, 6 choices.
          - Continuity check: 23 distinctive keywords shared between turn 1 and turn 2 narratives
            (e.g. "doorway", "concrete", "metal", "debris", "battered") — prior scene elements
            carried forward.
          - GET /api/story/session/{id}: 200, returns {session, turns:[t1,t2]} sorted by turn_number.
          - GET /api/story/session/{id}/latest: 200, latest_turn_number=2.
          - DELETE /api/story/session/{id}: 200 {"deleted":true}; subsequent GET returns 404.

  - task: "Admin AI settings (model / temperature / max_tokens / history_window)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          New endpoints:
          - GET /api/admin/settings: returns {settings, models, limits, defaults, provider_configured}
          - POST /api/admin/settings: validates model is in supported list, applies pydantic
            range checks (temperature 0.0-2.0, max_tokens 256-16384, history_window 4-200)
          - GET /api/admin/models: list of curated model options
          Settings persisted in MongoDB collection admin_settings (key=ai_settings).
          /api/health now reports {provider, model, temperature, max_tokens, history_window}.
          Manual test: POST switched model to free tier, story_new used the override, then
          reset back to gryphe/mythomax-l2-13b successfully.
      - working: true
        agent: "testing"
        comment: |
          Validated via /app/backend_test.py:
          - GET /api/health: provider="openrouter", llm_configured=true, model/temperature/
            max_tokens/history_window all present and reflect current settings.
          - GET /api/admin/settings: returns all 5 expected keys (settings, models, limits,
            defaults, provider_configured=true); 15 models returned.
          - GET /api/admin/models: 15 entries returned, default gryphe/mythomax-l2-13b present.
          - POST /api/admin/settings valid patch {"temperature":0.7,"max_tokens":1024} → 200,
            persistence confirmed via follow-up GET (values survive in MongoDB).
          - POST /api/admin/settings {"model":"fake/model"} → 400 "Unsupported model".
          - POST /api/admin/settings {"temperature":3.0} → 422 (pydantic le=2.0).
          - POST /api/admin/settings {"max_tokens":50} → 422 (pydantic ge=256).
          - POST /api/admin/settings {"history_window":1} → 422 (pydantic ge=4).
          - Model switch to "openai/gpt-oss-120b:free" succeeded and was honored by /story/new
            and /story/action.
          - After tests, model restored to gryphe/mythomax-l2-13b (default state clean).

  - task: "Environment variables for OpenRouter"
    implemented: true
    working: true
    file: "/app/backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: |
          Added OPENROUTER_API_KEY, OPENROUTER_BASE_URL, DEFAULT_MODEL, DEFAULT_TEMPERATURE,
          DEFAULT_MAX_TOKENS, DEFAULT_HISTORY_WINDOW, DEFAULT_TIMEOUT_SECONDS, APP_PUBLIC_URL,
          APP_TITLE. MONGO_URL, DB_NAME, CORS_ORIGINS preserved.
          NOTE: Provider currently returns HTTP 402 on Mythomax (paid) because the account
          has no purchased credits. Free-tier models work. The user must add OpenRouter
          credits to use the paid default model.

frontend:
  - task: "Admin AI controls in Settings screen"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/settings.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Added "ADMIN · AI ENGINE" section to existing Settings screen (existing UI preserved).
          - Provider status indicator (CONFIGURED / MISSING KEY)
          - Model picker (top 4 + "show more" toggle reveals all curated models)
          - Temperature stepper with progress bar (0.0–2.0, step 0.05)
          - Max output tokens stepper (256–16384, step 128)
          - Context history stepper (4–200 turns, step 2)
          - RESET / SAVE actions with dirty-state detection and saved-flash feedback
          Fetches from GET /api/admin/settings and persists via POST /api/admin/settings.
          Awaiting user permission before invoking frontend testing agent.

  - task: "Frontend API client extension"
    implemented: true
    working: "NA"
    file: "/app/frontend/src/api.ts"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Added types and helpers: AISettings, ModelOption, AdminSettingsBundle, HealthResponse.
          Added getAdminSettings(), saveAdminSettings(patch), getHealth().
          Existing story APIs unchanged.

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      OpenRouter migration is complete. All AI requests now route through /app/backend/ai_service.py
      (centralized chat_completion). The Claude-via-Emergent path is fully removed.

      IMPORTANT testing notes:
      1. The provided OPENROUTER_API_KEY is valid but the account has $0 credits, so the
         default paid model gryphe/mythomax-l2-13b returns HTTP 402 "Insufficient credits".
         When testing the actual story generation, please first switch the active model to
         a confirmed-working free tier via:
            POST /api/admin/settings  body: {"model": "openai/gpt-oss-120b:free"}
         (openai/gpt-oss-120b:free and google/gemma-4-31b-it:free both confirmed responsive)
         After tests, restore default with:
            POST /api/admin/settings  body: {"model": "gryphe/mythomax-l2-13b"}
      2. Validate:
         - GET /api/health reports provider=openrouter, llm_configured=true, model echo
         - GET /api/admin/settings returns settings/models/limits/defaults/provider_configured
         - POST /api/admin/settings validates ranges (reject temperature=3, max_tokens=50,
  - agent: "testing"
    message: |
      Backend OpenRouter migration validated end-to-end against the public ingress
      (https://dice-story-engine.preview.emergentagent.com/api). Tests live in
      /app/backend_test.py and /app/_retry_story.py. Summary:

      PASS — GET /api/health (provider=openrouter, llm_configured=true, all fields present)
      PASS — GET /api/admin/settings (5/5 keys, 15 models, provider_configured=true)
      PASS — GET /api/admin/models (15 entries, default model present)
      PASS — POST /api/admin/settings valid patch (temperature 0.7 + max_tokens 1024 persisted to Mongo)
      PASS — POST /api/admin/settings rejects bogus model with 400
      PASS — POST /api/admin/settings rejects temperature=3.0 with 422
      PASS — POST /api/admin/settings rejects max_tokens=50 with 422
      PASS — POST /api/admin/settings rejects history_window=1 with 422
      PASS — Model switch to openai/gpt-oss-120b:free
      PASS — POST /api/story/new (debug_mode=true): session_id returned, turn_number=1,
             player_action=None, 4 paragraphs, 6 choices, full state/ledger/debug blocks
      PASS — Session persisted (GET /api/story/sessions?device_id=…)
      PASS — POST /api/story/action: turn_number=2, player_action matches, 3 paragraphs,
             6 choices, 23 distinctive keyword overlap with turn 1 (continuity preserved:
             doorway/concrete/metal/debris/etc.)
      PASS — GET /api/story/session/{id} (2 turns sorted)
      PASS — GET /api/story/session/{id}/latest (turn_number=2)
      PASS — DELETE /api/story/session/{id} ({deleted:true}), subsequent GET → 404
      Cleanup — Active model restored to gryphe/mythomax-l2-13b.

      Note (no defect): Free-tier completions take 55-65s. When max_tokens=2048 the upstream
      preview ingress can intermittently 502 on its edge timeout even though the backend
      eventually returns 200 (visible in backend.out.log). Using max_tokens≤1024 with the
      free model consistently completes within the ingress window. The default paid model
      gryphe/mythomax-l2-13b returns HTTP 402 from OpenRouter due to $0 account credits,
      as documented by main agent — add credits before relying on the default in prod.

      No critical issues found. All three focus tasks marked working=true, needs_retesting=false.
           bogus model) and persists valid patches to MongoDB
         - GET /api/admin/models returns curated list
         - POST /api/story/new with debug_mode=true produces parsed narrative/choices/state/
           ledger/debug blocks
         - POST /api/story/action on the same session preserves continuity and increments turn_number
         - GET /api/story/sessions and /api/story/session/{id} still work
         - DELETE /api/story/session/{id} removes session + turns
      3. Skip /api/story tests against gryphe/mythomax-l2-13b unless credits are added;
         use the free model override for any LLM-dependent assertions.

  - agent: "main"
    message: |
      INCREMENT 1 — Anti-Hallucination Gateway (Source of Truth Ch 31). Source of
      Truth 1-32 is now the conformance authority; /app/memory/PRD.md rewritten as a
      chapter-by-chapter tracker. Approach: incremental alignment (no rebuild). Model
      kept as dolphin-mistral:free (currently rate-limited upstream → auto-falls back
      to anthropic/claude-3-5-haiku).

      New module: /app/backend/gateway.py — "The LLM writes prose. The engine writes
      truth." It (1) PREVENTS via build_immutable_truth_block injected into the prompt,
      (2) STRIPS illegal state mutations (terminal-object revival, silent injury
      resolution/improvement without a recovery cue, deceased-NPC revival) on the fresh
      parsed turn before consolidation, (3) DETECTS prose contradictions (destroyed/
      consumed object used as intact, dead NPC speaking) → hallucination correction
      re-prompt, and (4) records clear NPC deaths into engine-owned rolling_state.deceased
      (now a PROTECTED_LIST_KEY). Wired into _build_messages, _generate_validated_turn
      (_full_validate), and both /api/story/new and /api/story/action routes.

      Verified deterministically (no live LLM):
        - tests/test_anti_hallucination_gateway.py — 13 passed (unit: truth extraction,
          strip terminal object/injury/deceased, death registry incl. threat negatives,
          prose detection incl. memory/charred-remains negatives).
        - tests/test_gateway_e2e.py — 1 passed (full route pipeline w/ scripted LLM:
          death recorded turn1, truth block injected turn2, hallucination re-prompt fired
          [validation_retry_kind=hallucination], revived key reverted to destroyed,
          dead NPC forced stance=dead, destroyed key removed from player ledger).
        - tests/test_custom_world_system.py — 7 passed (live regression, no breakage).
      Frontend untouched; home screen smoke-tested OK after expo restart.

      NOT yet done (next Ch 31 sub-increments): knowledge-boundary + action-assertion
      checks; making the gateway the sole LLM caller. Live adversarial e2e (real model)
      not run — deterministic e2e covers the logic.

  - agent: "main"
    message: |
      INCREMENT 1b — Destruction/Consumption Registry (fix for live-probe CRITICAL).
      Live probe (iteration_3) found the real model NEVER emits status=destroyed/consumed;
      it RENAMES destroyed items ("iron lantern"→"lantern fragments") or silently drops
      consumed items, so gateway.build_truth().terminal_objects was empty against the live
      model. Added gateway.update_destruction_registry(): detects (a) rename-shaped
      destruction (husk rows like *fragments/ash/powder or destroyed-style condition whose
      base identity matches a known object) and (b) verb-based destroy/consume in prose with
      an intent/hypothetical guard, then writes a terminal object_locations row under the
      ORIGINAL identity and drops the husk. Wired into both routes after consolidation.
      Added a system-prompt rule telling the model to mark destroyed/consumed under the
      original name. Tests: gateway unit suite now 19 passing (6 new destruction tests),
      e2e 2 passing incl. a 3-turn rename→destroy→revive-blocked pipeline test
      (test_gateway_e2e.py::test_destruction_registry_end_to_end). Re-running live probe
      for object tests 1/2/5 next; model still dolphin-mistral until probe confirms.

  - agent: "main"
    message: |
      INCREMENT 1c — remaining Ch 31 sub-increments + model switch.
      - MODEL: live probe (iteration_4) passed all 5 object/NPC/injury families against the
        real model, so default model switched dolphin-mistral:free -> anthropic/claude-3-5-haiku
        (DB admin_settings.ai_settings.model). Turns now ~14-27s, no more 429 round-trips.
      - SOLE LLM CALLER (Ch 31.11): added gateway.invoke_llm as the single provider entry
        point; server.py no longer imports chat_completion/chat_completion_with_meta; both
        turn call sites route through gateway.invoke_llm.
      - ACTION ASSERTION (Ch 31.5): detect_prose_contradictions now flags prose that claims
        the player acquired a tracked item whose state was NOT updated to a possession status
        -> hallucination correction re-prompt.
      - KNOWLEDGE BOUNDARY (Ch 31.5, partial): flags a dead NPC framed as a future/interactive
        actor ("X will help", "ask X"); excludes referential "ask about X". FULL per-NPC
        working-memory knowledge boundary deferred to P2/P3 (needs Ch 28 memory model).
      - Tests: gateway unit suite 24 passing (added action-assertion + knowledge-boundary +
        negatives), e2e 2 passing, custom-world live regression 7 passing, server imports OK.
      Next: awaiting user choice for P2 (Ch 29 Relationship Calculus vs Ch 26 Gravity
      Governance). Per user, P2 not to start until Ch 31 enforcement confirmed closed.

  - agent: "main"
    message: |
      P2 INCREMENT — Ch 29 Relationship Calculus (NPC->player). New module relationships.py.
      Engine-owned 4-vector per NPC (trust -100..100, loyalty/fear/resentment 0..100) stored
      in rolling_state.relationship_vectors (PROTECTED_LIST_KEY). Each turn: neglect decay
      toward neutral, event detection from action+narrative -> canonical Ch 29.8 deltas
      (betrayal/save_life/help/threaten/attack/lie/gift/reward/keep_promise/break_promise/
      humiliate/apology) with subsumption + hypothetical guard, derived behavioural state,
      coarse stance sync, and a <relationships> prompt block so the LLM renders NPC behaviour
      to match. LLM-injected vectors are ignored (engine reads PRIOR as authority). Wired into
      both routes (after destruction registry) and _build_messages. Deceased NPCs excluded.
      Tests: tests/test_relationship_calculus.py (11) + e2e test_gateway_e2e.py::
      test_relationship_calculus_end_to_end. Full suite 38 passing; custom-world live
      regression 7 passing. About to run a live Ch 29 probe (vectors evolve + influence
      NPC behaviour in real play). Deferred: NPC<->NPC/faction calculus (Ch 29.11),
      emotional-intensity/personality multipliers, memory-weighting (Ch 28).

  - agent: "main"
    message: |
      Ch 29 VERIFIED LIVE (iteration_5). Testing agent ran an 11-unit suite + 2 live e2e
      (new test_relationship_calculus_live.py): full 9-turn arc help+gift->save->threaten->
      attack->betray->3 neutral decay turns. Final live vector trust=-39 loyalty=0 fear=58
      resentment=88 -> state betrayal_risk; debug carried rel:<name>:<events> markers; decay
      worked; no 500s/regressions. Ch 29 (NPC->player) complete. Next per user order: Ch 27
      Utility AI, then Ch 26 Gravity Governance, then Ch 28.
