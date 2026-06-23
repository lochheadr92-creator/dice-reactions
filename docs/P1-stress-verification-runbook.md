# P1 (Ch 14 Stress) — Verification Runbook

**Goal:** move the ledger from `P1_COMPONENT_VERIFIED — TURN_INTEGRATION_UNVERIFIED`
to `TURN_INTEGRATION_VERIFIED` by compiling and executing the two turn-path files
that could not be run in the authoring sandbox (`replayability.py`, `server.py`).

**Why off OneDrive first:** the authoring environment served *truncated* copies of
large files and reported a corrupt `.git/index`. Verifying on a OneDrive-synced path
risks testing bytes that differ from disk. Run everything below on a **non-synced**
local clone.

Run from a normal PowerShell prompt on Windows. Each step lists the command, the
**expected** result, and what a failure means.

---

## Step 0 — Work on a clean, non-synced copy

```powershell
# Option A: fresh clone (preferred)
git clone "C:\Users\RJLoc\OneDrive\Desktop\dice-reaction\dice-reactions" C:\dev\dice-reactions
cd C:\dev\dice-reactions

# Option B: if there is no remote/clean history, copy the tree out of OneDrive
# robocopy "C:\Users\RJLoc\OneDrive\Desktop\dice-reaction\dice-reactions" C:\dev\dice-reactions /E /XD .git __pycache__
```

- [ ] Repo now lives outside any OneDrive/synced folder.

> If `git clone` fails on a corrupt index, use Option B, then `cd C:\dev\dice-reactions && git init` is **not** needed for testing — you only need a runnable tree.

---

## Step 1 — Git integrity (only if you cloned)

```powershell
git status
git diff --check
```

- **Expected:** `git status` runs without `fatal: index file corrupt`; `git diff --check` prints nothing (no whitespace/conflict errors).
- **If `.git/index` is corrupt:**
  ```powershell
  Remove-Item .git\index.lock -ErrorAction SilentlyContinue
  Remove-Item .git\index -ErrorAction SilentlyContinue
  git reset
  ```
  This rebuilds the index from HEAD; your working files are untouched.
- [ ] `git status` clean of corruption errors.

---

## Step 2 — Environment & dependencies

```powershell
cd C:\dev\dice-reactions\backend
python --version            # expect 3.10+
python -m pip install -r requirements.txt
python -m pip install pytest
```

- [ ] `requirements.txt` installed, `pytest` available.

> If `conftest.py` needs Mongo env vars, the suite sets safe defaults
> (`MONGO_URL`, `DB_NAME`, `ADMIN_API_KEY`); no live Mongo is required for the
> offline tests. The live HTTP/integration suites need their own services — out of
> scope for this runbook.

---

## Step 3 — Compile the four touched files (the gate I could not clear)

```powershell
python -m py_compile stress.py foundation_snapshot.py replayability.py server.py
echo $LASTEXITCODE
```

- **Expected:** no output, `$LASTEXITCODE` = `0`.
- **If it errors:** note the file + line. A `SyntaxError` at the *end* of
  `replayability.py` (~787) or `server.py` (~3550) means the file is still a
  truncated copy — re-fetch from a clean source (Step 0) and retry. Errors at my
  edit sites (`stress.update_actor_stress` in `replayability.py` ~447; the
  `enforce_authoritative_stress` block in `server.py` ~3272) would be real and need
  fixing.
- [x] All four compile, exit code 0.

---

## Step 4 — Full offline test suite

```powershell
python -m pytest tests -q
```

- **Expected:** all collected tests pass (the stress + foundation_acceptance subset
  was 69 green in authoring; full `tests/` adds integration files that may need
  services — see note).
- **Minimum bar (no services):**
  ```powershell
  python -m pytest tests\test_stress.py tests\foundation_acceptance tests\test_utility_dimensions.py tests\test_utility_ai.py tests\test_engine_determinism.py -q
  ```
  Expected: **69 passed**.
- [x] Offline subset green (69).
- [x] Full `tests/` green, or every failure attributable to a missing external
      service (Mongo/httpx), not to stress code.

---

## Step 5 — Add the turn-integration tests

Create `backend/tests/test_stress_integration.py` with this content:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import stress


def test_consolidation_clobber_protection():
    """A model-supplied actor_stress cannot replace engine-owned stress."""
    engine = {"npc-a": {"stress_level": 41.0, "capacity": 1.0, "schema_version": 1}}
    merged = {"actor_stress": {"npc-a": {"stress_level": 0.0}}}  # malicious/LLM value
    notes = stress.enforce_authoritative_stress(merged, engine)
    assert merged["actor_stress"] == engine
    assert "actor_stress_model_mutation_stripped" in notes


def test_prepare_action_turn_emits_stress_before_snapshot():
    """Real turn: stress is updated and reaches the foundation snapshot inputs."""
    import replayability, foundation_snapshot
    run_seed = "seed-itest"
    rolling = {"npcs": [{"npc_id": "npc-a", "name": "Mara"}]}
    replay = {
        "run_seed": run_seed,
        "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 60}]},
        "npc_agendas": {"agendas": [{"npc_id": "npc-a", "goal_kind": "escape_danger"}]},
    }
    state, _dirs, _diag, _thr, working_rolling = replayability.prepare_action_turn(
        replay, turn_number=2, rolling_state=rolling
    )
    assert working_rolling["actor_stress"]["npc-a"]["stress_level"] > 0.0
    snap = foundation_snapshot.FoundationTurnSnapshot.build(
        run_seed=run_seed, turn_sequence=2,
        rolling_state=working_rolling, replayability_state=state,
    )
    ref = next(r for r in snap.utility_input_refs if r["actor_id"] == "npc-a")
    assert ref["stress_level"] == working_rolling["actor_stress"]["npc-a"]["stress_level"]
```

- [x] File created.

---

## Step 6 — Run the integration tests

```powershell
python -m pytest tests\test_stress_integration.py -q
```

- **Expected:** **2 passed.**
- **`test_consolidation_clobber_protection` fail** → the engine-owned re-assert is
  not protecting stress; check the `stress.enforce_authoritative_stress(...)` call
  sits *after* `consolidate_rolling_state(...)` in `server.py`.
- **`test_prepare_action_turn_emits_stress_before_snapshot` fail:**
  - `actor_stress` empty → the hook isn't running before the snapshot, or
    `replayability_active` gated it off (the helper needs `replay["run_seed"]`).
  - `stress_level` is `None` on the ref → the actor isn't in the interpretation set;
    confirm the agenda `npc_id` equals the registry `actor_id`.
- [x] 2 passed.

---

## Step 7 — Baseline hash equivalence (stress-absent fixtures)

Proves my snapshot-hash change did **not** alter identity for stress-free state.
Needs the **pre-P1** commit checked out side by side.

```powershell
# 7a. Dump current-commit hashes for stress-free snapshots
cd C:\dev\dice-reactions\backend
python - <<'PY'
import json
from foundation_snapshot import FoundationTurnSnapshot
fixtures = [
    {"rolling": {"npcs": [{"npc_id": "npc-a", "name": "Mara"}]},
     "replay": {"run_seed": "s", "pressure_graph": {"nodes": [{"id": "p1", "status": "active", "magnitude": 50}]},
                "npc_agendas": {"agendas": [{"npc_id": "npc-a", "goal_kind": "escape_danger"}]}}},
]
out = {}
for i, f in enumerate(fixtures):
    snap = FoundationTurnSnapshot.build(run_seed="s", turn_sequence=1,
                                        rolling_state=f["rolling"], replayability_state=f["replay"])
    out[i] = snap.source_state_hash
open("hashes_current.json", "w").write(json.dumps(out, indent=2))
print(out)
PY
```

```powershell
# 7b. Check out the pre-P1 commit in a SEPARATE worktree, run the same dump
git worktree add ..\pre-p1 <PRE_P1_COMMIT_SHA>
# copy the same dump script into ..\pre-p1\backend, run it -> hashes_pre.json
# then compare:
python - <<'PY'
import json
cur = json.load(open("hashes_current.json"))
pre = json.load(open(r"..\pre-p1\backend\hashes_pre.json"))
assert cur == pre, f"HASH DRIFT: {cur} != {pre}"
print("EQUIVALENT — stress-free snapshot identity unchanged")
PY
```

- **Expected:** `EQUIVALENT`. Because the fixtures carry no `actor_stress`, the digest
  is omitted and hashes must match the pre-P1 values exactly.
- **If it drifts:** the conditional in `_actor_stress_commitment` is being entered
  when it shouldn't, or another change touched `hash_material`. Investigate before
  promoting.
- [x] Stress-absent hashes identical pre-P1 vs current.

> Skip 7b only if you have no pre-P1 commit. In that case record the limitation
> honestly: historical byte-identity remains unverified.

---

## Step 8 — Promote the ledger (only after 3–7 pass)

In `docs/foundation-canon-deltas.md`:

1. Change the three runtime-status cells from
   `COMPONENT_VERIFIED / TURN_INTEGRATION_UNVERIFIED` to `TURN_INTEGRATION_VERIFIED`.
2. Change the Utility verdict header from
   `P1_COMPONENT_VERIFIED — TURN_INTEGRATION_UNVERIFIED` to
   `UTILITY_STRESS_INPUT_COMPLETE — stress_level is authoritative and snapshot-produced; D_SEL blocked only by any other incomplete required input.`
3. If Step 7b was completed, append: `Baseline hash equivalence confirmed vs <SHA>.`

- [x] Ledger promoted with the evidence line.

---

## Verification record — 2026-06-22

- Python 3.12 compile gate: `stress.py`, `foundation_snapshot.py`, `replayability.py`, and `server.py` passed.
- Focused offline bar: **69 passed**.
- Turn-path integration: **2 passed**.
- Full backend collection: **628 passed**; 34 failures/errors were live HTTP tests with no service listening at `localhost:8000`.
- Stress-free hash: **MATCH** against pre-P1 commit `b4e5fcc` (`7d2825b108b1da752b9fcfbdd10b9916295179d85eb3e9a0b047dfa7c4535134`).
- Ledger promoted to `TURN_INTEGRATION_VERIFIED`.

---

## One open design decision (confirm before P2)

P1 defines the stress "interpretation set" as **alive actors carrying an active
agenda** (`stress.update_actor_stress`). If you want scene-present actors *without*
agendas to also accrue/recover, that is a one-line predicate change in
`update_actor_stress` now — cheaper than after P2 builds on it.

- [ ] Interpretation-set definition confirmed (agenda-based) **or** widened.

---

## Pass criteria (all must hold to call P1 accepted)

- [x] Step 3 — four files compile, exit 0
- [x] Step 4 — offline subset 69 green; full suite green or service-only failures
- [x] Step 6 — 2 integration tests pass
- [x] Step 7 — stress-absent hash equivalence (or limitation recorded)
- [x] Step 8 — ledger promoted
- [ ] Design decision on interpretation set confirmed
