# Required Capability Dogfooding — 2026-09-17

This run used the repository CLI directly and did not invoke the installed `skill-engineering:skill-engineer` Plugin. The host exposed `skill-creator`, but the CLI had no registered host adapter, so it truthfully recorded `CREATE_CANDIDATE=NOT_EXECUTED`; installation was not misreported as execution. `agent-skills-creator`, `agents-md`, and `validate-skills` were absent and were likewise `NOT_EXECUTED`.

## Defective audit

The target `tests/fixtures/skills/capability-dogfood` intentionally contains:

- exact duplicate and opposing rules;
- an `AGENTS.md` / `SKILL.md` ownership conflict and a repository-wide rule misplaced in `SKILL.md`;
- a broken `references/missing.md` link;
- a declared but missing `scripts/run.py`;
- required `domain_x` with no Provider or fallback (`NONE`).

The phased CLI commands were `inspect`, `validate`, `confirm`, then an independent `publish` attempt. Validation emitted:

| Evidence | Result |
|---|---|
| `capability.skill_duplication_and_bloat` | `FAIL`; exact duplicate plus three conflicts, each with `file`, `line`, `finding`, `severity`, `reason`, and `remediation` |
| `capability.agent_instruction_governance` | `FAIL`; duplicate ownership, cross-layer conflict, and misplaced project-wide rule |
| `capability.skill_resource_integrity` | `FAIL`; missing reference |
| `capability.skill_script_integrity` | `FAIL`; missing declared script |
| `capability.domain_x.preflight` | `NOT_EXECUTED`; `BLOCKED`, equivalence `NONE` |

All applicable standard capabilities selected `FULL` internal fallbacks; no missing Provider was treated as passed or silently skipped. Because verdict precedence is fail-closed, the blocked domain capability produced:

```text
confirm exit=2
verdict=INCOMPLETE
outcome=AUDIT_INCOMPLETE
audit_execution=INCOMPLETE
artifact_assessment=UNKNOWN
publish_authorized=false
```

The independent `publish` command exited `2` with `outcome has no publication-ready workspace`. This proves `BLOCKED` cannot be converted into publication even when other fallback checks execute and find defects.

## Repaired audit

A disposable copy of the same target was repaired by consolidating the rules, moving repository ownership to `AGENTS.md`, adding `references/operating.md` and `scripts/run.py`, and removing the unsupported `domain_x` declaration because that Capability was not actually required by the repaired text-only workflow.

Re-running all three audit phases produced no blocked capabilities, no non-passing required evidence, and:

```text
confirm exit=0
verdict=PASS
outcome=AUDIT_COMPLETE_VALID
audit_execution=COMPLETE
artifact_assessment=VALID
publish_authorized=false
```

The final `publish_authorized=false` is expected because Audit Only is never a publication request. Change-mode publication remains separately guarded by `PASS`, `READY_TO_PUBLISH`, explicit authorization/request, a publishable staged workspace, and digest-bound confirmation.

## Current Skill self-audit

The modified `skills/skill-engineer` was then audited directly with the repository Engine. Digest `a2fe2e5f8a09891ef7471683e434d71b1a3715ae0581bd424217315a5c3aee81` produced `PASS / AUDIT_COMPLETE_VALID`, `AuditExecution.COMPLETE`, `ArtifactAssessment.VALID`, zero blocked capabilities, and zero non-passing required checks. No installed copy of the target Plugin was invoked.
