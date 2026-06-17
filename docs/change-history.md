# Change History

Lightweight log of documentation and operational changes. One entry per meaningful doc or release pass.

---

## 2026-06-17 — Operational and architectural documentation spine (pass 2)

| Field | Detail |
|-------|--------|
| **Change** | Added project-control documents: `current-state.md`, `system-doctrine.md`, `feature-status.md`, `decision-log.md`, `failure-modes.md`, `release-checklist.md`, `next-work.md`, `change-history.md`. Updated `README.md` with grouped index. Minimal `api.md` correction for export/reset schemas. |
| **Reason** | First pass (`overview`, `architecture`, `api`, `development`, `story-engine`, `frontend`, `verification`) provided technical reference but lacked operational spine, evidence tagging, and ADR-style decision record. |
| **Files affected** | `docs/*.md` (8 new + `README.md` modified + `api.md` minor fix) |
| **Tests run** | `python tests/verify_p0_object_permanence.py` ✅; `verify_p1_immersion_integrity.py` ✅; `verify_p15_microfixes.py` ✅; `pytest tests/test_custom_world_system.py` ❌ (server not running) |
| **Documentation updated** | All `/docs` files indexed in `README.md` |
| **Decision-log entry** | None new accepted — documented existing decisions as ADR-001–008 from code evidence |
| **Remaining risks** | Admin/export unauthenticated; integration tests require manual server; PRD verification claims remain Docs-claimed |

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