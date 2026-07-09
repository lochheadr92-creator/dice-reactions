# Grok Build Instructions

Project: Dice Reactions

Core rules:
- State is truth.
- Narrative is derived from state.
- Player choice drives direction.
- World systems may move independently.
- Replayability, determinism, and causality are mandatory.
- Do not use simulation-kernel research.
- Do not redesign unrelated systems.
- Preserve existing runtime behaviour unless this task explicitly changes it.

Before editing:
- Read docs/current-state.md
- Read docs/next-work.md
- Read docs/system-doctrine.md
- Read only files directly related to the task after that.

During work:
- Make small, surgical changes.
- Keep changes behind flags if behaviour changes.
- Update tests for changed behaviour.
- Do not broaden scope.

Completion proof:
- Show files changed.
- Show tests run.
- Show whether replay output changed.
- Explain any behaviour change.
