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
- **Audit Only** - inspect without writing the source; execute commands only in an Engine-owned disposable snapshot and return separate execution and target-quality states.
- **Audit + Optimize** - audit first, then stage an isolated optimization copy only when a change is needed and authorized.

For Audit Only and advice requests, keep the target tree byte-for-byte unchanged throughout the run. The Engine records a recursive baseline snapshot, gives executable checks a disposable copy, and verifies the source after every command and before the final result. Still prefer `python -B` with `PYTHONDONTWRITEBYTECODE=1` so the disposable evidence reflects the intended check rather than cache artifacts. Do not run `py_compile` or any command that writes caches, coverage data, or test artifacts against the source target. When a check cannot run safely, record the limitation instead of writing and cleaning up afterward. A source mismatch makes the audit `INCOMPLETE / UNKNOWN`; never restore the source automatically because that could overwrite a legitimate concurrent change.

## Workflow

1. Determine the explicit mode and call `inspect` before making governance decisions.
2. Review the returned baseline, signals, stable finding IDs, and optional Provider evidence. Perform RCA, classification, mechanism selection, and any `KEEP / MERGE / MOVE / DELETE` decisions. Treat scanner and Provider outputs as evidence only.
4. Disclose only the references relevant to the current phase:
   [pipeline](references/pipeline.md),
   [issue classification](references/issue-classification.md),
   [mechanism selection](references/mechanism-selection.md),
   [rule governance](references/rule-governance.md),
   [Provider contracts](references/provider-contracts.md), and
   [quality gate](references/quality-gate.md).
5. Create or edit a complete isolated candidate. Do not let the Engine generate semantic Skill content.
6. Call `validate` with the `InspectionBundle`, `DecisionRecord`, complete `GovernanceDecisions`, candidate, and applicable test runners. Review `deterministic_evidence` separately from `advisory_evidence`.
7. After validation reaches `VALIDATED_PENDING_CONFIRMATION`, review the current artifact and evidence, then call `confirm` with Codex semantic confirmation for that exact digest.
8. Call `publish` separately only when the confirmed outcome is `READY_TO_PUBLISH` and publication was explicitly requested.

## Result boundary

Change-mode results are `VALIDATED`, `READY_TO_PUBLISH`, or a blocked Gate result. Audit results combine `AuditExecution.COMPLETE | INCOMPLETE` with `ArtifactAssessment.VALID | FINDINGS | BLOCKING_FINDINGS | UNKNOWN`. A complete audit that discovers a serious defect is successful execution with `BLOCKING_FINDINGS`; only an incomplete audit is untrusted. Providers supply evidence or candidate material; detectors emit signals; neither may classify the task, govern rules, confirm semantics, or authorize publication.
