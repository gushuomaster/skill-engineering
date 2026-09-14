---
name: skill-engineer
description: Create, repair, audit, and validate maintainable Skills through the internal engineering quality gate.
---

# Skill Engineer

Use this single entry for Skill engineering work. Discover the target Skill and the user's requested outcome, identify the intent and authorization, then route execution to `scripts/skill_engineering.py`. The script and engine modules own mutation, validation, classification, Provider calls, evidence, and Gate adjudication; do not reproduce those rules in this document.

## Scope and input

Accept a target Skill path, the requested requirement or defect, available evidence, environment facts, and explicit authorization. Treat a request to inspect as read-only. Do not infer permission to modify or publish from an audit request.

Select exactly one mode:

- **Create** - build a new Skill from the requirement, with capability and risk analysis.
- **Modify** - change an existing Skill only for a stable capability or requirement; task-local preferences are not persisted.
- **Fix** - repair an evidenced defect after root-cause analysis, classification, mechanism selection, and regression disposition.
- **Audit Only** - inspect without copying or writing; return the unchanged validated Skill or minimal blocking findings.
- **Audit + Optimize** - audit first, then stage an isolated optimization copy only when a change is needed and authorized.

## Workflow

1. Load context and inventory the target.
2. Detect intent and authorization; stop before any unauthorized write.
3. Select the mode and follow its isolation rules.
4. Disclose only the references relevant to the current phase:
   [pipeline](references/pipeline.md),
   [issue classification](references/issue-classification.md),
   [mechanism selection](references/mechanism-selection.md),
   [rule governance](references/rule-governance.md),
   [Provider contracts](references/provider-contracts.md), and
   [quality gate](references/quality-gate.md).
5. Invoke the Pipeline Orchestrator through `scripts/skill_engineering.py`.
6. Present only a legal external result after evidence collection and the internal Quality Gate.

## Result boundary

The external result is either **Validated Complete Skill** (with publication only when `publish_authorized` is true and workspace preconditions hold) or **Unchanged Skill + Minimal Blocking Findings**. A Gate failure never authorizes publication. Providers supply evidence or candidate material; they cannot emit a final verdict.
