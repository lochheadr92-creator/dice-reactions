# ADR-026: Research/runtime isolation boundary — `Simulation-Kernel-Research` is non-authoritative

**Status:** Accepted 2026-07-08; **amended 2026-07-08** — the guard test and
doctrine boundary described below remain in force, but the original
"retain the gitlink, contain it in place" position has been reversed. See
§8 Amendment. No runtime behaviour changed by either the original decision
or this amendment.
**Date:** 2026-07-08
**Deciders:** Ryan
**Branch target:** `research/simulation-kernel-constitution-v1` (docs + new test only; no production code changes)
**Relates to:** `docs/system-doctrine.md` Architectural constraints (AC12)

---

## 1. Context

The `Simulation-Kernel-Research` git submodule (architecture audits, a draft
"simulation kernel" constitution, brainstorms, and a proposed Source-of-Truth
v2) was added to the repository on `research/simulation-kernel-constitution-v1`
as future-facing material — three commits (`bb3075c`, `d3049de`, `9349032`)
add the submodule, bump its pointer twice, and add a two-line `.gitignore`
entry. It is explicitly not yet approved to replace or influence the current
deployed application, which remains governed by `Source_of_Truth_v1.2.md` and
`docs/system-doctrine.md`.

Nothing today requires research material to stay inert — that has held only
by convention. As the research tree grows (more documents, more drafts, more
submodule commits), a future change could accidentally wire it into runtime
(a prompt that reads a doc, a build step that bundles it, a script that
copies a draft into a config file) without anyone deciding that should
happen. This ADR makes the boundary explicit and durable.

## 2. Decision

1. Everything under the research locations named in `RESEARCH_MARKERS` (see
   §4) is **non-runtime documentation**. It may inform future development
   but carries no authority over the current application.
2. It is **not current app configuration** and is **not automatically
   canonical** for existing runtime behaviour, however confidently it is
   written (the research tree's own `Source-of-Truth v2` draft included).
3. Adopting any research concept into the running application requires a
   **separate, explicit migration decision** — a dedicated ADR scoped to
   that concept. This ADR is not that approval and does not pre-approve any
   future one.
4. Production runtime code (backend excluding `backend/tests/`, frontend
   `app/` and `src/` excluding `__tests__/`) must never import, open, read,
   or otherwise depend on files under the research locations.
5. Coding agents and contributors must preserve the current deployed
   build's behaviour when the research tree changes. Research updates alone
   are never sufficient reason to alter runtime code, prompts, state
   schemas, event formats, API contracts, model selection, or deployment
   configuration.

## 3. Audit evidence (2026-07-08)

- `git diff --ignore-all-space origin/emergent..HEAD` (and per-commit `git
  show --stat` on `bb3075c`, `d3049de`, `9349032`) — the only non-whitespace
  changes across all three research-adding commits are the
  `Simulation-Kernel-Research` submodule pointer and a two-line `.gitignore`
  addition (`.nw_tmp/`). Zero backend, frontend, or build-config files were
  touched.
- Grepped `backend/` and `frontend/` runtime source for the submodule name,
  its path variants, and generic recursive-file-loading primitives
  (`os.walk`, `.rglob`, `glob.glob`, docx/zip/markdown parsers) — no
  matches.
- The 9 existing `Source_of_Truth_v1.2.md` references in `backend/*.py`
  predate this research effort, are plain-text citations in
  docstrings/constants (e.g. `canon_ref="Source_of_Truth_v1.2.md:L18949-L18956"`),
  and are never opened or read by runtime or test code — confirmed
  unrelated to the new research tree and left untouched.
- Every `open(`/file-read call found anywhere under `backend/` is confined
  to `backend/tests/` (pytest-only, never executed by the deployed app) or
  to standalone dev tools (`backend/tools/simulate_world.py`,
  `backend/verify_hash.py`) that write local output or read a local hash
  cache — none reference the research tree.
- No CI workflow (`.github/workflows/deterministic-ci.yml`), bundler config
  (`frontend/metro.config.js`, `frontend/app.json`), or dependency manifest
  (`backend/requirements.txt`, `frontend/package.json`) references the
  research tree or includes a document-parsing dependency.
- Full findings, classification, and verification commands were produced as
  part of a repository containment/verification pass on 2026-07-08 (recorded
  in this ADR and in the `docs/decision-log.md` ADR-026 entry; not
  separately logged in `docs/change-history.md`, which this repository
  reserves for larger documentation passes rather than individual ADRs).

## 4. Guard test

`backend/tests/test_research_isolation.py` fails deterministically if:

- backend or frontend runtime source references a known research-location
  marker (`Simulation-Kernel-Research` and path-case variants), or
- build/deploy config (`requirements.txt`, `package.json`, `app.json`,
  `metro.config.js`, the CI workflow, `.emergent/emergent.yml`) references
  one, or
- backend runtime source calls a recursive filesystem-walk primitive
  (`os.walk`, `Path.rglob`, `glob.glob`) — none currently do; this keeps a
  future recursive doc-scanner from being introduced unnoticed.

It runs under the existing `pytest -m "not live"` CI job in
`.github/workflows/deterministic-ci.yml` — no CI configuration changes were
required.

## 5. Non-goals

- Not a migration of any research concept into runtime.
- Not a statement about the research's eventual merit or correctness —
  purely a containment boundary.
- Does not change gameplay behaviour, state schemas, event formats,
  persistence behaviour, prompt behaviour, API contracts, model selection,
  frontend behaviour, database contents, or deployment configuration.
- Does not restrict what may be written inside the research submodule
  itself, and does not delete, rewrite, or relocate any research file.
  **(Superseded 2026-07-08 — see §8 Amendment: the gitlink reference itself
  has since been removed from this repository.)**
- Does not address the pre-existing `Source_of_Truth_v1.2.md` citation
  pattern in `backend/*.py` — that predates this research effort, is
  already dev-guidance-only (comments/citations, never opened by runtime),
  and is out of scope here.

## 6. Consequences

- Future research growth (new documents, new drafts, new submodule commits)
  is safe by default — no runtime file changes occur unless someone
  deliberately writes code against the research tree, at which point the
  guard test (§4) fails and forces a conscious decision.
- Adopting a research concept later requires: (1) a dedicated ADR scoped to
  that concept, (2) deliberately relaxing the specific guard assertion it
  needs to cross, (3) normal test/verification discipline for the
  resulting runtime change.
- The guard's file list (§4) is not exhaustive against every conceivable
  future build system — if a new build/deploy path is introduced, extend
  `_CONFIG_FILES` in the guard test deliberately rather than assuming
  coverage.

## 7. Rejected alternatives

- **Do nothing / rely on convention** — rejected: no durable trip-wire
  against future accidental coupling as the research tree grows.
- **Delete, relocate, or rewrite the research** — rejected: out of scope
  for a containment task, and the research remains legitimate future-facing
  material that should not be destroyed.
  **(Reversed 2026-07-08 — see §8 Amendment: the repo-level gitlink
  reference has been removed. This did not destroy any research material —
  see §8 for why.)**
- **Block the submodule from being committed at all** — rejected: research
  work is wanted; only *runtime coupling* is the concern, not the research
  existing in the repository.
- **A broad recursive-file-access lint across the whole backend (any
  `open()` call, any path argument)** — rejected: too broad, high
  false-positive risk against legitimate future file I/O unrelated to
  research, and harder to keep green than a targeted marker + primitive
  check. The narrower guard in §4 was preferred as simpler to maintain.

## 8. Amendment (2026-07-08): research gitlink removed

**Previous accepted position (original decision above, §§1–7):** contain via
guard test only; retain the `Simulation-Kernel-Research` gitlink in the
tree; deletion/relocation explicitly rejected as "out of scope for a
containment task."

**Changed decision:** remove the `Simulation-Kernel-Research` gitlink
reference from the active Dice Reactions repository context rather than
retain it.

**Reason:** prevent the separate simulation-kernel research effort from
influencing Dice Reactions' current app, runtime, or documentation
direction — including the appearance of an actively wired research
submodule — beyond what containment-in-place communicated. Practically,
the gitlink was also confirmed non-functional as a real submodule: no
`.gitmodules` entry exists or ever existed on any branch (`git log --all --
.gitmodules` returns nothing), no local clone was ever initialised (no
`.git/modules` entry), and the working-tree copy was already absent before
this amendment. Removing the reference preserves exactly as much research
content as keeping it did — none was ever fetchable from inside this
repository either way — so reversing the original "do not delete" position
does not destroy anything the original decision was protecting.

**What changed:**
- `git rm --cached Simulation-Kernel-Research` removed the dangling gitlink
  (tree mode `160000`, commit `eaa4bbbdc829398d07d73559d7edef748c6558e7`)
  from the index. No working-tree copy existed to remove.
- No `.gitmodules` file existed to remove.
- `docs/system-doctrine.md` AC12 reworded from "guarded while present" to
  "removed; guard test retained as a regression check against recurrence."

**What did not change (constraints honoured):**
- Runtime behaviour: unchanged. `backend/tests/test_research_isolation.py`
  already proved zero backend/frontend/build-config files reference the
  research tree before this amendment; re-run after the amendment: **4
  passed**. A gitlink never imported by runtime code cannot affect runtime
  behaviour by being removed.
- No broad refactor: only the gitlink removal plus this document,
  `docs/decision-log.md`, and `docs/system-doctrine.md` were touched. A
  pre-existing, unrelated set of whitespace/line-ending-only diffs already
  present across much of the working tree was left untouched and is not
  part of this change.
- No gameplay changes: no gameplay, API, persistence, or frontend behaviour
  file was edited.
- Tests and doctrine preserved: the guard test is unchanged and still
  passes; `system-doctrine.md`'s other invariants (H1–H7) and architectural
  constraints (AC1–AC11) are untouched.

This amendment still does not migrate, promote, or validate any research
concept into the running application — Action item 4 below is unaffected.

## Action items

1. [x] Guard test added and passing: `backend/tests/test_research_isolation.py`
   (re-verified 2026-07-08 after the amendment: 4 passed).
2. [x] `docs/system-doctrine.md` Architectural constraints table updated
   (AC12) to reference this boundary, then reworded 2026-07-08 to reflect
   removal (§8).
3. [x] `docs/decision-log.md` updated with the ADR-026 summary entry, then
   with a follow-up amendment entry 2026-07-08 (§8).
4. [ ] Any future promotion of a specific research concept requires its own
   dedicated ADR — this ADR does not bulk-approve the research tree.
5. [x] Research gitlink removed from the repository index (2026-07-08, §8).
