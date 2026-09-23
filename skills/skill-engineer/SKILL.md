---
name: skill-engineer
description: Audit, diagnose, repair, and validate Codex Skills with Codex-led reasoning, isolated candidates, evidence-backed checks, and safe apply.
---

# Skill Engineer

Use this Skill when the user asks to audit a Skill, audit and repair it, or repair a specific evidenced problem. Codex owns intent, diagnosis, root-cause analysis, professional-Skill selection, repair decisions, semantic confirmation, and the final explanation. The Engine supplies inventory, read-only audit isolation, deterministic checks, evidence integrity, regression enforcement, and atomic safe apply. It does not decide what the user's problem means.

Do not use this Skill for Marketplace publishing, Plugin release, distribution, installation, deployment, or release management.

## Choose one user mode

- `AUDIT`: inspect the complete baseline, run executable checks only in an Engine-owned disposable snapshot, report RCA/findings/evidence, and prove the source tree did not change.
- `AUDIT_REPAIR`: run the complete audit, create an isolated repaired candidate, validate it, then safely apply it when authorized.
- `TARGETED_REPAIR`: first prove the reported problem, trace its necessary impact chain, repair only that scope, and run targeted regression before safe apply.

Do not expose older create/modify/fix/audit-optimize lifecycle labels as user modes. Do not expand a targeted repair into unrelated cleanup.

## Codex-led workflow

1. Read the target Skill and applicable `AGENTS.md` / `CLAUDE.md` instructions. Select the mode from the user's meaning; never let a static classifier choose it.
2. For a full audit, cover all eight baselines: goal/responsibility, trigger/description, instructions, rule governance, engineering structure, agent-instruction relationships, actual implementation, and behavioral validation.
3. Decide which professional Skills, validators, or tools are genuinely needed. Domain Skills are open-ended and selected from the target and findings; there is no closed domain catalog.
4. Before work that genuinely requires a standard professional Skill, run dependency preflight. If it is missing, tell the user its name, responsibility, affected checks, and coverage gap, then ask whether to install/connect it or continue with a limited audit. Never install without consent.
5. If the user declines, continue only with explicit limited scope. Preserve `standard-dependency.* = NOT_EXECUTED` evidence; the Gate must return `INCOMPLETE`, never a full `PASS`.
6. Treat an installed Provider runtime failure separately. A validated `FULL`/`ALTERNATIVE` fallback may handle crash, timeout, invalid output, or temporary invocation failure, and evidence must record the failed Provider and fallback path.
7. Codex performs RCA, classification, mechanism selection, and every `KEEP / MERGE / MOVE / DELETE` decision. Provider and scanner output is evidence or implementation help, never the final diagnosis or repair authority.
8. For repair, author a complete candidate outside the source. The Engine must extract baseline and staged-candidate Capability Manifests, compute their structured diff, and require an exact Codex-authored capability decision plus user authorization for every removal or narrowing. Run structural/reference checks, actual implementation checks, applicable behavior checks, and required regression. Bind confirmation to the current candidate digest.
9. Use `apply` only for a confirmed `PASS / READY_TO_APPLY` repair with a matching `ManagedCompletionReceipt` when modification was authorized. Safe apply preserves staging, digest checks, concurrent-source protection, backup, atomic replacement, and recovery.

Read phase-specific details only when needed:
[pipeline](references/pipeline.md),
[issue classification](references/issue-classification.md),
[mechanism selection](references/mechanism-selection.md),
[rule governance](references/rule-governance.md),
[required capabilities](references/required-capabilities.md),
[Provider contracts](references/provider-contracts.md), and
[quality gate](references/quality-gate.md).

## Result boundary

The Gate returns only `PASS`, `FAIL`, `INCOMPLETE`, or `ERROR` for the requested audit/repair/validation work. `PASS` means the requested scope and required evidence completed. `FAIL` means a known defect remains or repair validation failed. `INCOMPLETE` means a required Skill, tool, permission, environment, or execution record is missing. `ERROR` means the framework itself failed.

A formal completion claim contains the inspection ID, `ManagedCompletionReceipt`, Gate verdict, coverage status, and capability-preservation status. `target pytest cannot replace the Quality Gate`. If the current artifact has no matching Engine receipt, report `UNMANAGED_CHANGE`; do not represent it as a completed audit or repair.
