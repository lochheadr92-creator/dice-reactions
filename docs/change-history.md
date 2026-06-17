# Change History

Lightweight log of documentation and operational changes. One entry per meaningful doc or release pass.

---

## 2026-06-17 — Reconcile documentation with `emergent` runtime (pass 3)

| Field | Detail |
|-------|--------|
| **Change** | Re-audited all operational docs against `emergent` branch code. Documented `gateway.py`, `relationships.py`, `hud.py`. Corrected branch references from `main` to `emergent`. Re-ran 47-test deterministic bundle. Re-audited security findings. Labeled `memory/PRD.md` as planning tracker only. Removed scoring-equivalence / NaN-ranking from backlog. |
| **Reason** | Pass 1–2 docs were authored against `main` (no gateway/relationship/HUD), committed on `main`, cherry-picked to `emergent` (`a0f2bcc`) without runtime re-audit — causing false claims about missing systems and omitted emergent modules. |
| **Files affected** | `docs/current-state.md`, `system-doctrine.md`, `feature-status.md`, `failure-modes.md`, `decision-log.md`, `architecture.md`, `story-engine.md`, `verification.md`, `next-work.md`, `change-history.md`, `README.md` |
| **Tests run** | `pytest tests/test_anti_hallucination_gateway.py tests/test_relationship_calculus.py tests/test_hud.py tests/test_gateway_e2e.py tests/verify_p0_object_permanence.py tests/verify_p1_immersion_integrity.py tests/verify_p15_microfixes.py -q` → **47 passed** |
| **Documentation updated** | All files listed above |
| **Decision-log entry** | ADR-009 (gateway), ADR-010 (relationships), ADR-011 (HUD) documented from commits `b4a2891`, `a52b66d`, `ff1858d` |
| **Remaining risks** | Admin/export unauthenticated; `device_id` partial; live-server tests unverified; PRD verification claims remain Docs-claimed |

---

## 2026-06-17 — Operational and architectural documentation spine (pass 2)

| Field | Detail |
|-------|--------|
| **Change** | Added project-control documents: `current-state.md`, `system-doctrine.md`, `feature-status.md`, `decision-log.md`, `failure-modes.md`, `release-checklist.md`, `next-work.md`, `change-history.md`. Updated `README.md` with grouped index. Minimal `api.md` correction for export/reset schemas. |
| **Reason** | First pass provided technical reference but lacked operational spine, evidence tagging, and ADR-style decision record. |
| **Files affected** | `docs/*.md` (8 new + `README.md` modified + `api.md` minor fix) |
| **Tests run** | `verify_p0` ✅; `verify_p1` ✅; `verify_p15` ✅; `pytest test_custom_world_system.py` ❌ (server not running) |
| **Documentation updated** | All `/docs` files indexed in `README.md` |
| **Decision-log entry** | ADR-001–008 from code evidence |
| **Remaining risks** | **Pass 2 described `main` runtime** — corrected in pass 3; gateway/relationship/HUD omitted |

**Branch error:** Pass 2 committed on `main` (`791824b`), cherry-picked to `emergent` (`a0f2bcc`), docs reverted on `main` (`fc9b6e3`). Pass 2 never re-audited `emergent`-only modules.

---

## 2026-06-17 — Initial technical documentation (pass 1)

| Field | Detail |
|-------|--------|
| **Change** | Created eight system reference documents under `/docs`. |
| **Reason** | Establish codebase-derived technical reference for Dice Reaction. |
| **Files affected** | `docs/README.md`, `overview.md`, `architecture.md`, `api.md`, `development.md`, `story-engine.md`, `frontend.md`, `verification.md` |
| **Tests run** | Not run during pass 1 |
| **Documentation updated** | New `/docs` tree |
| **Decision-log entry** | — |
| **Remaining risks** | Export/reset marked Unknown in `api.md` until pass 2 |

---

## Template for future entries

```markdown
## YYYY-MM-DD — Short title

| Field | Detail |
|-------|--------|
| **Change** | What changed |
| **Reason** | Why |
| **Files affected** | Paths |
| **Tests run** | Commands and results |
| **Documentation updated** | Which docs |
| **Decision-log entry** | ADR-XXX or — |
| **Remaining risks** | Open items |
```