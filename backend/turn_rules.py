"""
Always-on rules sent with every turn request, opening included.

These are not player settings. A turn the player cannot follow, or a turn in
which nothing happens, is a defect whatever the story's tone or mystery level.
They were added after a live story spent three turns at one table on one
question, in invented terms nobody explained (2026-11-23).

Pure text. No I/O, no engine state.
"""

from __future__ import annotations

TURN_CLARITY_RULES = (
    "[TURN RULES — always required. Where these conflict with atmosphere, mystery, "
    "implication or any instruction to withhold, these win.]\n"
    "1. Plain stakes. Before the choices, the narrative says in plain words what the "
    "player must decide right now, and what they stand to lose or gain. A reader who "
    "skims must still know it. Facts the character cannot know may stay hidden; what "
    "is happening in front of them may not.\n"
    "2. Plain words. Use everyday words. The first time a made-up or specialist term "
    "appears (an object, title, place or custom), the same sentence says what it is. "
    "Dialogue may be terse, never a riddle.\n"
    "3. Movement. This turn changes the situation: something is gained, lost, learned, "
    "moved or decided. Do not end where the previous turn ended with the same question "
    "still open. A scene that has run three turns must be resolved or left.\n"
    "4. Choices. Each choice is an action that could change the situation. Never offer "
    "a choice that repeats what the player just did. Watching or waiting is a choice "
    "only when the choice says what it is for. A choice never states a number, a name "
    "or an agreement between people that the story has not already shown."
)
