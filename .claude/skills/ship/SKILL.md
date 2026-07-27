---
name: ship
description: Use when the user asks to /ship, build, or implement a specific piece of work end to end. Plans first, delegates implementation to the builder subagent, loops code-reviewer until it passes, then reports what changed.
---

Follow this sequence for the task described. Do not skip or collapse steps.

## 1. Plan
Read CLAUDE.md and the relevant docs/superpowers/plans file. Confirm which
task is next. If no plan task fits, stop and ask rather than improvising.

## 2. Build
Delegate implementation to the `builder` subagent, one task at a time, with
that task's exact acceptance criteria.

## 3. Review loop
After each task, delegate to `code-reviewer`. If FAIL, send its exact feedback
back to `builder` and repeat. Do not proceed on an assumed pass.

## 4. Stop condition
If code-reviewer cannot reach PASS after 3 rounds on the same task, stop and
ask the user, reporting exactly what's still failing.
