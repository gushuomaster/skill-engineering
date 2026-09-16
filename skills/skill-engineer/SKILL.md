---
name: skill-engineer
description: Help Codex create, modify, repair, audit, and optimize Skills with isolated workspaces, deterministic evidence, and guarded publication.
---

# Skill Engineer

Use this single entry for Skill engineering work. Codex is the decision-maker and author: understand the user's outcome, diagnose root causes, select the mode and mechanism, create the candidate, evaluate rule-governance signals, and confirm whether the current artifact satisfies the semantic goal. The Plugin supplies deterministic inventory, isolation, validation, evidence, diff, and atomic-publication safeguards through `scripts/skill_engineering.py` and `engine/`.

## Scope and input

Accept a target Skill path, the requested requirement or defect, available evidence, environment facts, and explicit authorization. Treat a request to inspect as read-only. Do not infer permission to modify or publish from an audit request.

Select exactly one mode from the request and context. Pass it explicitly to the Engine; never ask the Engine to infer intent from keywords.

- **Create** - build a complete candidate Skill in an independent directory; use `skill-creator` when its structure and authoring guidance helps.
- **Modify** - change an existing Skill only for a stable capability or requirement; task-local preferences are not persisted.
- **Fix** - repair an evidenced defect after root-cause analysis, classification, mechanism selection, and regression disposition.
- **Audit Only** - inspect without copying or writing; return the unchanged validated Skill or minimal blocking findings.
- **Audit + Optimize** - audit first, then stage an isolated optimization copy only when a change is needed and authorized.

For Audit Only and advice requests, keep the target tree byte-for-byte unchanged throughout the run. Record its digest before executable checks and verify the same digest afterward. Use non-writing commands; for Python, prefer `python -B` with `PYTHONDONTWRITEBYTECODE=1`. Do not run `py_compile` or any command that creates caches, coverage data, test artifacts, or temporary files below the target. When a check cannot be made read-only, report that evidence limitation instead of writing and cleaning up afterward.

## Workflow

1. Load context and inventory the target.
2. Determine intent and authorization, then record them explicitly.
3. Perform RCA, classification, mechanism selection, and any `KEEP / MERGE / MOVE / DELETE` decisions. Treat scanner and Provider outputs as evidence only.
4. Disclose only the references relevant to the current phase:
   [pipeline](references/pipeline.md),
   [issue classification](references/issue-classification.md),
   [mechanism selection](references/mechanism-selection.md),
   [rule governance](references/rule-governance.md),
   [Provider contracts](references/provider-contracts.md), and
   [quality gate](references/quality-gate.md).
5. Create or edit a complete isolated candidate. Do not let the Engine generate semantic Skill content.
6. Invoke `scripts/skill_engineering.py` with the explicit mode, `DecisionRecord`, candidate, and applicable test runners.
7. Review the staged artifact and its digest, then provide Codex semantic confirmation for that exact digest.
8. Publish only through a separate explicit atomic publication action after the Gate reports the candidate ready.

## Result boundary

The external result is either **Validated Complete Skill** or **Unchanged Skill + Minimal Blocking Findings**. A Gate failure never authorizes publication. Passing deterministic checks without Codex semantic confirmation is also a failure. Providers supply evidence or candidate material; detectors emit signals; neither may classify the task, govern rules, confirm semantics, or authorize publication.
