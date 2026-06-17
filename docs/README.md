# Dice Reaction — Documentation

Dice Reaction is a hidden-systems narrative app: a persistent causal D20 story simulation with an Expo mobile/web frontend and a FastAPI backend backed by MongoDB and OpenRouter.

**Canonical runtime branch:** `emergent` (includes `gateway.py`, `relationships.py`, `hud.py`). The `main` branch lacks these modules.

## Core principle

**State is truth. Narrative is output.**

Mechanics drive outcomes in backend state (`rolling_state`, `ledger`, guards). Prose is generated output. All LLM calls route through `gateway.invoke_llm`. Player-facing views must not invent facts that are not in state, and internal mechanics must stay concealed unless developer mode is explicitly enabled.

**Canonical operational snapshot:** [current-state.md](./current-state.md) (date-stamped, evidence-tagged, `emergent` branch).

**Planning tracker (not runtime truth):** [memory/PRD.md](../memory/PRD.md) — Source-of-Truth conformance checklist and historical verification claims. Treat PRD dates as **Docs-claimed** until re-run against code.

---

## 1. System reference

Technical reference derived from the `emergent` codebase.

| Document | Contents |
|----------|----------|
| [overview.md](./overview.md) | Product purpose, repo layout, tech stack, player flows |
| [architecture.md](./architecture.md) | Components, gateway/relationship/HUD, data flow, persistence |
| [api.md](./api.md) | REST endpoints, request/response shapes |
| [story-engine.md](./story-engine.md) | Turn format, gateway, guards, memory, HUD, validation |
| [frontend.md](./frontend.md) | Expo structure, screens, DNG/MOM/PRS, sanitization |

---

## 2. Architecture and doctrine

Rules, invariants, and failure analysis.

| Document | Contents |
|----------|----------|
| [system-doctrine.md](./system-doctrine.md) | Hard invariants, architectural constraints, enforcement status |
| [failure-modes.md](./failure-modes.md) | Failure catalogue with detection, prevention, recovery |
| [decision-log.md](./decision-log.md) | ADR-style decisions (ADR-001–011) and candidates |

---

## 3. Development and verification

Setup, testing, and release discipline.

| Document | Contents |
|----------|----------|
| [development.md](./development.md) | Local setup, environment variables, commands |
| [verification.md](./verification.md) | 47-test bundle, live-unverified inventory, backlog |
| [release-checklist.md](./release-checklist.md) | Before implementation / merge / release / after release |

---

## 4. Project state and planning

What is true now and what to do next.

| Document | Contents |
|----------|----------|
| [current-state.md](./current-state.md) | Canonical `emergent` snapshot with evidence tags |
| [feature-status.md](./feature-status.md) | Feature table: status, files, tests, risks |
| [next-work.md](./next-work.md) | P0–P2 backlog with acceptance criteria |

---

## 5. Decisions and change history

| Document | Contents |
|----------|----------|
| [decision-log.md](./decision-log.md) | Accepted ADRs and candidates |
| [change-history.md](./change-history.md) | Documentation and ops change log (incl. branch-error correction) |

---

## Related project files (outside `/docs`)

| Path | Role |
|------|------|
| `AGENTS.md` | Agent/coding guidelines for this repository |
| `memory/PRD.md` | **Planning and conformance tracker** — not runtime truth |
| `frontend/README.md` | Default Expo starter readme |
| `backend/server.py` | Story engine, routes, guards, system prompt |
| `backend/gateway.py` | Anti-Hallucination Gateway + `invoke_llm` chokepoint |
| `backend/relationships.py` | NPC→player relationship calculus |
| `backend/hud.py` | DNG/MOM/PRS HUD shaping |

## Quick start

```bash
# Backend (from backend/)
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# Frontend (from frontend/)
yarn install
yarn start
```

Set `OPENROUTER_API_KEY` in `backend/.env` and `EXPO_PUBLIC_BACKEND_URL` in `frontend/.env` before running story turns.

Deterministic verification (no server, `emergent` branch):

```bash
cd backend
pytest tests/test_security.py \
       tests/test_anti_hallucination_gateway.py \
       tests/test_relationship_calculus.py \
       tests/test_hud.py \
       tests/test_gateway_e2e.py \
       tests/verify_p0_object_permanence.py \
       tests/verify_p1_immersion_integrity.py \
       tests/verify_p15_microfixes.py -q
# Expected: 67 passed (set ADMIN_API_KEY in env)
```