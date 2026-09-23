# Required Capability Model

The Engine plans checks from the target Skill before it considers Provider availability. The invariant is:

> Providers are replaceable implementations. Applicable Required Capabilities are mandatory. A missing or failed Provider must use an equivalent fallback or block PASS and publication.

Installed/discoverable and invocable are different states. The Engine records a Provider as executed only when a registered adapter returns schema-valid evidence during the run. Merely finding a Skill on disk never fabricates Provider success.

## Fallback equivalence

| Level | Meaning | May satisfy a Capability? |
|---|---|---|
| `FULL` | Internal implementation covers the maintained Provider responsibility and emits the required evidence contract. | Yes |
| `ALTERNATIVE` | Another executed Provider fully covers the same Capability. | Yes |
| `PARTIAL` | Some checks exist, but the maintained responsibility/evidence contract is incomplete. | No; status is `BLOCKED` |
| `NONE` | No substitute exists. | No; status is `BLOCKED` |

Preflight states are `READY` (preferred Provider executed), `FALLBACK` (a `FULL` internal or `ALTERNATIVE` Provider implementation was selected), `NOT_APPLICABLE`, and `BLOCKED`. Preflight selection is not execution proof: validation must also emit `capability.<name>` evidence. A selected implementation with no matching execution record becomes required `NOT_EXECUTED` evidence.

Provider execution has its own state. Discovery sets availability only; it does not select or complete a Capability. The production `codex-exec` host adapter records `EXECUTED` only after a real read-only Codex invocation returns schema-valid identity-bound evidence containing the per-run nonce and installed Provider Skill digest. Failures record `FAILED` and resolve through the same fallback path.

## Equivalence Contracts

Every declared `FULL` fallback has an executable contract in `engine/equivalence_contracts.py`: Capability, preferred Provider, fallback implementation identity, required dimensions, evidence contract, and required failure semantics. Production preflight intersects the declaration with its proof. Missing coverage automatically changes effective equivalence from `FULL` to `PARTIAL`; tests also fail. Adding a required dimension without updating implementation coverage therefore cannot silently preserve `FULL`.

## Standard matrix

| Required Capability | Preferred Provider | Fallback | Equivalence |
|---|---|---|---|
| `skill_creation_or_restructure` | `skill-creator` | isolated Codex-authored candidate plus structure, frontmatter, references, scripts, resources, and responsibility-boundary rubric | `FULL` |
| `skill_structure` | `validate-skills` | deterministic structure validator | `FULL` |
| `skill_trigger_and_description` | `skill-creator`; `validate-skills` is an alternative | frontmatter and trigger/description validator | `FULL`; alternate Provider is `ALTERNATIVE` |
| `skill_instruction_design` | `skill-creator` | trigger, instruction-quality, and ownership rubric | `FULL` |
| `skill_audit_and_simplification` | `agent-skills-creator` | evidence-backed instruction, governance, duplication/conflict/bloat, ownership, stale-rule, and Provider-orchestration rubric | `FULL` |
| `skill_instruction_quality` | `agent-skills-creator` | executable-instruction, stale-rule, and unconditional-orchestration checks | `FULL` |
| `skill_rule_governance` | `agent-skills-creator` | complete governance-decision coverage for actionable findings | `FULL` |
| `skill_duplication_and_bloat` | `agent-skills-creator` | duplicate, conflict, overlap, ownership, repeated-constraint, over-explanation, and bloat rubric | `FULL` |
| `skill_resource_integrity` | `validate-skills` | deterministic reference/path validator | `FULL` |
| `skill_script_integrity` | `validate-skills` | deterministic declared-script and executable validator | `FULL` |
| `skill_conformance` | `validate-skills` | deterministic frontmatter, name, directory, reference, path, script, asset, dependency, and entrypoint suite | `FULL` |
| `agent_instruction_governance` | `agents-md` | direct `AGENTS.md`, `CLAUDE.md`, and `SKILL.md` scope/inheritance/ownership/conflict inspection | `FULL` |
| `regression_validation` | internal | regression-disposition enforcement and required runner evidence | `FULL` |
| `evidence_collection` | internal | typed evidence collector | `FULL` |
| `quality_gate` | internal | fail-closed Gate | `FULL` |

The audit/simplification fallback is classified `FULL` because it is a maintained fixed rubric with a stable evidence contract: every finding carries `file`, `line`, `finding`, `severity`, `reason`, and `remediation`. This is not a claim that arbitrary LLM reading is equivalent. If any rubric branch or evidence field is removed, its configured level must be reduced to `PARTIAL` until restored.

## Dynamic domain matrix

The Engine narrowly infers domain capabilities from target metadata and files, and also honors open-ended `required_capabilities` frontmatter. Known routing hints are:

| Capability | Preferred Provider(s) | Internal fallback |
|---|---|---|
| `security_review` | `security-best-practices` | `NONE` |
| `plugin_manifest_validation` | `plugin-creator` | `NONE` |
| `pdf_validation` | `pdf` | `NONE` |
| `document_validation` | `documents` | `NONE` |
| `spreadsheet_validation` | `spreadsheets` | `NONE` |
| `presentation_validation` | `presentations` | `NONE` |
| `frontend_validation` | `vite`, `vue-best-practices` | `NONE` |
| `github_ci_validation` | `gh-fix-ci` | `NONE` |
| `visual_asset_validation` | `imagegen`, `diagram-design` | `NONE` |

These are routing hints, not a closed whitelist. A host may register any nonblank Capability. Triggering must still respect each Provider Skill's own scope. An applicable domain Capability without an executed Provider or a `FULL/ALTERNATIVE` fallback is `BLOCKED`; non-applicable known domains remain visible as `NOT_APPLICABLE`.

## Failure and Gate semantics

Missing, unavailable, unpinned, degraded, timed-out, crashing, incompatible, or malformed Providers all enter the same resolution path. A schema-valid Provider finding is promoted to required Capability `FAIL`; it is not discarded in favor of a passing fallback. A failed Provider may use a `FULL/ALTERNATIVE` fallback. Fallback execution failure leaves the Capability incomplete, and an Engine exception is additionally classified `ERROR`.

Verdict precedence is `ERROR`, then `INCOMPLETE`, then `FAIL`, then `PASS`. `PASS` requires every applicable Capability to have execution evidence and every required result to pass. Only `PASS` can lead to `READY_TO_PUBLISH`, and that still requires an explicit publish request, a publishable staged workspace, and digest-bound Codex confirmation.
