# Skill Engineer Product Semantics Alignment — 2026-09-18

## 1. Before / after

The audited pre-change user path was:

```text
request
→ Engine intent/capability inference
→ every fixed Provider port is enumerated
→ fixed provider-name mapping
→ unavailable provider becomes FULL fallback
→ capability matrix
→ Gate
→ READY_TO_PUBLISH
→ publication
```

Digest binding, isolated staging, typed evidence, fail-closed validation, rollback, and concurrent-source protection were valid engineering mechanisms. Fixed names, closed domain inference, automatic provider traversal, release terminology, and publication states had incorrectly become product semantics.

The implemented path is:

```text
user request
→ Codex selects AUDIT / AUDIT_REPAIR / TARGETED_REPAIR
→ Codex reads and reasons about the target
→ Codex explicitly selects any professional help
→ standard-dependency preflight
→ audit / diagnosis / isolated repair
→ behavior and regression validation
→ Codex semantic confirmation
→ PASS / FAIL / INCOMPLETE / ERROR
→ optional safe apply for an authorized repair
```

## 2. Responsibility boundary

`skill-engineer` now owns audit support, diagnosis support, repair isolation, validation, evidence integrity, and safe apply. Codex owns intent, RCA, classification, professional-Skill selection, repair design, rule governance, and semantic confirmation. Marketplace publication, Plugin release, distribution, installation, deployment, and release management are explicitly outside the Skill's scope.

## 3. User modes

- `AUDIT`: read-only full audit with recursive source-integrity evidence.
- `AUDIT_REPAIR`: full audit, complete isolated candidate, behavior/regression validation, and authorized safe apply.
- `TARGETED_REPAIR`: prove the stated defect, trace only its necessary impact chain, repair that scope, and run targeted regression.

Legacy enum/import aliases remain only for pre-4.2 Python callers. CLI, schemas, serialized records, Skill instructions, Gate outcomes, and installed Plugin metadata use the new semantics.

## 4. Full-audit baseline

The required core coverage now records all eight areas:

1. goal and responsibility;
2. trigger and description;
3. instruction quality/design;
4. rule governance, duplication, conflict, bloat, and ownership;
5. engineering structure, resources, paths, metadata, and entrypoints;
6. AGENTS.md / CLAUDE.md / Skill instruction relationships;
7. actual implementation integrity;
8. behavioral validation.

Owned executable assets without an executed behavior/regression record produce required `NOT_EXECUTED`, so a full audit cannot silently claim behavior coverage. Vendor/runtime trees such as `.venv`, `site-packages`, and `node_modules` are excluded from owned implementation requirements.

## 5. Toolchain findings

| Name | Installed | Conclusion |
|---|---:|---|
| `skill-creator` | yes, system Skill | Real and useful for creation/restructuring guidance, but not required for nearly every audit; optional professional help, not a fixed standard dependency. |
| `agent-skills-creator` | no | Historical assumed name; removed from Provider configuration and product semantics. |
| `agents-md` | no | Historical assumed name; instruction hierarchy inspection is a direct core check. |
| `validate-skills` | no | Historical assumed name; structure/conformance validators are direct core implementation. |

Therefore the default external Standard Toolchain has no fixed members. Codex may declare a real professional Skill required for a particular full audit. That decision is open-ended and semantic, not inferred from a closed catalog.

## 6. Dependency and fallback behavior

`StandardSkillRequirement` and `StandardDependencyAssessment` represent only Codex-selected required standards. A missing dependency returns the Skill name, responsibility, affected coverage gap, and an `install_or_connect_or_continue_limited` action. Validation stops until the user chooses. `continue_limited` emits required `standard-dependency.* = NOT_EXECUTED` evidence with `result_scope=LIMITED_AUDIT`, forcing `INCOMPLETE`.

Provider runtime failure is separate: only an installed, available Provider whose execution actually failed can enter the equivalence-validated fallback path. A merely absent optional Provider selects the direct core implementation; it is not described as fallback. Domain Provider selection is explicit with `NAME=CAPABILITY`; the static domain catalog and automatic suffix/keyword inference were removed.

## 7. Gate and safe apply

The Gate verdict is limited to `PASS`, `FAIL`, `INCOMPLETE`, or `ERROR`. It does not express release readiness. Repair application uses `READY_TO_APPLY`, `apply_authorized`, `apply_session`, `ApplyResult`, and `apply_atomic`. Isolated staging, semantic digest binding, source-race checks, backup-before-replace, atomic move, post-apply verification, and rollback remain intact.

Compatibility aliases for the old Python symbols remain internal and serialize to apply semantics; they are not present in the user CLI or JSON contracts.

## 8. Tests and dogfood

New focused product tests are in `tests/integration/test_product_semantics.py`:

- A: broken Skill audit returns findings and preserves the exact source digest;
- B: `AUDIT_REPAIR` validates, safely applies, and preserves unrelated content;
- C: `TARGETED_REPAIR` changes only the required file and runs targeted regression;
- D: a missing required standard Skill raises user-action-required with responsibility and gap;
- E: declined installation continues only as limited audit and returns `INCOMPLETE`;
- F: installed Provider invalid-output/crash uses a proven fallback and records the runtime failure path;
- G: concurrent source change blocks atomic apply.

Repository validation:

```text
379 passed, 2 skipped
```

The two skips are Windows symlink tests blocked by WinError 1314. `quick_validate.py skills/skill-engineer` returned `Skill is valid!`. The installed cache artifact was separately exercised: eight focused dogfood cases passed and its Skill validation passed.

## 9. Installed artifact

The personal marketplace source and cache now contain:

```text
skill-engineering 1.0.2+codex.20260918024731
```

No Git commit was created. The worktree remains intentionally dirty with this task and earlier uncommitted changes; see `git status --short` at handoff.
