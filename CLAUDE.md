# Development Rules

## General Philosophy

Write code that is simple, maintainable, and easy to reason about.

Optimize first for correctness, then readability, then performance. Optimize performance early only when there is clear evidence that it matters.

Prefer improving existing code over introducing new abstractions.

Avoid unnecessary complexity.

---

## Before Writing Code

Understand the problem before proposing a solution.

Read the relevant code before modifying it.

Trace data flow from input to output.

Identify constraints, assumptions, and potential side effects before making changes.

If requirements are ambiguous, ask for clarification rather than guessing.

---

## Planning

For non-trivial work:

* Explain the problem.
* Describe the proposed approach.
* Identify affected files.
* Mention potential risks.
* Outline how the change will be verified.

Do not begin implementation until the approach is coherent.

---

## Implementation

Prefer small, focused changes over large refactors.

Modify existing code where appropriate instead of rewriting it.

Avoid changing unrelated code.

Keep functions cohesive and focused on a single responsibility.

Use descriptive names rather than clever ones.

Reduce duplication, but do not abstract prematurely.

Avoid hidden side effects.

Do not introduce dependencies without a clear benefit.

---

## Code Quality

Write code that another engineer can understand months later.

Prioritize explicitness over cleverness.

Prefer deterministic behavior.

Handle errors intentionally.

Fail loudly when assumptions are violated rather than silently masking problems.

Leave code cleaner than you found it.

---

## Testing

Treat tests as part of the implementation.

When changing behavior:

* Update or add relevant tests.
* Run the smallest meaningful test scope first.
* Expand testing only as necessary.

Never remove or weaken tests simply to make them pass.

If a bug is fixed, add a regression test whenever practical.

---

## Debugging

Find the root cause before implementing a fix.

Do not stack speculative fixes together.

Use evidence from logs, traces, tests, or debugging output.

Explain why the issue occurred, not just how it was fixed.

---

## Documentation

Keep documentation synchronized with implementation.

Update comments only when they improve understanding.

Do not leave stale documentation behind.

Prefer self-explanatory code over excessive comments.

---

## Git

Make logical, atomic changes.

Keep commits focused on a single purpose.

Write clear, descriptive commit messages.

Do not commit or push unless explicitly requested.

Never hide failing tests or broken behavior inside unrelated commits.

---

## Communication

Be direct and technically precise.

State assumptions explicitly.

If uncertain, say so.

Distinguish facts from hypotheses.

Highlight trade-offs rather than presenting a single solution as universally correct.

When reviewing code, explain both strengths and weaknesses.

Recommend the simplest solution that satisfies the requirements.

---

## Continuous Improvement

Continuously look for opportunities to improve readability, reliability, maintainability, and developer experience.

Prefer evolutionary improvements over unnecessary rewrites.

Respect existing architecture unless there is a strong technical reason to change it.
