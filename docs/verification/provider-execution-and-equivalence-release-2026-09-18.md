# Provider Execution and Fallback Equivalence Release Verification

This verification covers the two remaining Capability-driven, fail-closed gaps: real
installed-Skill Provider execution and enforceable `FULL` fallback equivalence. The
implementation was developed without invoking the target `skill-engineering:skill-engineer`
Plugin. The target Plugin was invoked only after packaging and installation, from a new
independent Codex session.

## Implemented boundaries

- `engine/host_adapters.py` discovers configured installed Skills and invokes them through
  an ephemeral, read-only `codex exec` session. Availability is discovery only.
- Provider evidence is selectable only when `provider_available=true`,
  `provider_execution=EXECUTED`, `fallback_used=false`, and `evidence_valid=true`.
  The adapter binds output to the expected Provider ID/capability, an invocation nonce,
  and the discovered Provider Skill digest before the Engine can promote it.
- A schema error, timeout, crash, invalid marker, self-reported fallback, or Provider-owned
  coverage limitation records failed execution and enters ordinary fallback resolution.
  `FULL/ALTERNATIVE` may execute; `PARTIAL/NONE` remains `BLOCKED` and yields
  `INCOMPLETE`.
- `engine/equivalence_contracts.py` keeps required dimensions, required evidence,
  failure semantics, and implementation coverage as independent declarations. Runtime
  preflight derives `FULL`; it does not trust the configuration label. Adding a required
  dimension without separately adding implementation coverage downgrades the fallback
  to `PARTIAL`.
- Dynamic domain capabilities continue to use `NONE` unless they acquire a separate,
  proven equivalence contract.

## Dogfood A: real installed `skill-creator` Provider

The repository CLI inspected a disposable Skill in `MODIFY` mode with
`--provider-skill skill-creator`. The production adapter discovered
`C:\Users\28320\.codex\skills\.system\skill-creator`, launched a real isolated Codex
session, and validated schema, identity, digest, and nonce markers.

The first target intentionally contained a trigger/runtime mismatch and underspecified
normalization semantics. The Provider returned two findings with:

```text
provider_available=true
provider_execution=EXECUTED
fallback_used=false
evidence_valid=true
provider status=FAIL
```

Those findings became required failures for
`skill_creation_or_restructure`, `skill_instruction_design`, and
`skill_trigger_and_description`; confirmation failed and publication was denied.

After correcting the disposable target, a fresh real invocation returned no findings or
limitations. The same three required capability checks were emitted from
`provider:openai.skill-creator` with `PASS` and retained the exact execution fields above.
Digest-bound confirmation then produced:

```text
verdict=PASS
outcome=READY_TO_PUBLISH
publish_authorized=true
```

No publication command was run. Unit/integration coverage separately proves that a crash
or invalid schema uses a proven `FULL` fallback, while the same failure with `NONE`
produces `BLOCKED / INCOMPLETE` and publication denial.

## Dogfood B: Providers absent

The production CLI was invoked with the explicitly configured but absent
`agent-skills-creator`, `agents-md`, and `validate-skills` Provider names. Discovery returned
unavailable adapter descriptors instead of aborting before capability resolution. All four
Provider evidence records were explicit:

```text
provider_available=false
provider_execution=NOT_STARTED
fallback_used=false
evidence_valid=false
status=NOT_EXECUTED
```

On a valid audit target, all 13 applicable core Required Capabilities selected independent
`FULL` internal fallbacks, emitted matching `capability.<name>` execution records, and
passed. Final audit state was `PASS / COMPLETE` with `publish_authorized=false`, as required
for Audit Only. The defective dogfood fixture separately exercises duplicate/conflicting
rules, cross-layer instruction ownership, broken references, missing scripts, and an
unsupported dynamic capability; the dynamic capability retains `NONE` and forces
`INCOMPLETE`.

## Equivalence contract coverage

The behavioral contract suite covers the full declared fallback scope:

- `skill-creator`: structure, frontmatter/name/description/trigger design, instruction
  design, directory layout, references/scripts/resources, responsibility boundary, and
  progressive disclosure;
- `agent-skills-creator`: duplication, conflict, obsolescence, enforceability, placement,
  responsibility overlap, unconditional Provider orchestration, rule bloat, repeated
  constraints, and instruction-quality defects;
- `agents-md`: `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, project/directory scope, inheritance,
  precedence, ownership, duplication, conflict, and misplaced governance;
- `validate-skills`: missing/invalid Skill structure and metadata, broken references and
  path escapes, declared scripts/resources, and manifest/metadata/entrypoint mismatch.

Contract mutation tests remove an existing coverage dimension and add a new required
dimension. Both cases break completeness; the latter changes runtime equivalence from
`FULL` to `PARTIAL`.

## Test and package results

```text
focused Provider/equivalence suite: 21 passed
unit suite:                         248 passed, 2 skipped
integration suite:                  102 passed
full repository suite:              374 passed, 2 skipped
isolated current-build suite:        374 passed, 2 skipped
Skill quick validation:              PASS
Plugin validation:                   PASS
git diff --check:                    PASS (line-ending warnings only)
```

The two skips are Windows symlink tests; the current token lacks symlink creation privilege
(`WinError 1314`). The isolated runtime candidate initially omitted project `AGENTS.md`, so
one development-only configuration test failed while 372 tests passed. Adding `AGENTS.md`
to the isolated source-test copy produced the clean result above; the installable Plugin
allowlist intentionally continues to exclude project governance files.

The final official cachebuster flow produced
`1.0.2+codex.20260918020459`. The repository runtime allowlist, personal Marketplace
source, and installed cache each contained 139 files with zero missing or changed hashes:

```text
C:\Users\28320\plugins\skill-engineering
C:\Users\28320\.codex\plugins\cache\personal\skill-engineering\1.0.2+codex.20260918020459
```

Both the Marketplace source and installed cache passed Plugin validation; the installed
Skill passed `quick_validate.py`.

## Independent installed-Plugin acceptance and final-version blocker

A new `codex exec --ephemeral` session explicitly invoked the installed
`$skill-engineering:skill-engineer` Plugin from a temporary workspace at the immediately
preceding build `1.0.2+codex.20260917085648`. It ran the real phased Audit Only workflow:

```text
inspect -> Codex decision/governance -> validate -> Codex confirmation -> confirm
```

The session imported `engine.capabilities`, `engine.equivalence_contracts`, and
`engine.host_adapters` from the installed cache; none came from
`D:\project\skill-engineering`. Provider states were unavailable/`NOT_STARTED`, 13/13
required fallback execution records passed, all nine dynamic domain capabilities retained
`NONE`, and the result was:

```text
Gate verdict=PASS
outcome=AUDIT_COMPLETE_VALID
audit_execution=COMPLETE
artifact_assessment=VALID
publish_authorized=false
target_hash_unchanged=true
```

The target recursive SHA-256 before and after was
`b23a855d39026bdbeeb322cd47e866a5bcbae7f215f3c42f279d39334fe48b5e`.
The independent session first encountered the inaccessible WindowsApps `python.exe` alias,
retained that error, selected the actual Python installation, and completed without using
the repository or weakening the Gate.

The only code change after that successful session was the fail-closed representation of
an explicitly configured but undiscovered Provider plus its regression test. The final
installed build was exercised directly from its cache with all three absent Provider names;
discovery completed, all three were `unavailable / NOT_STARTED`, and all 13 required core
capabilities selected `FULL` fallback. Repository and fresh isolated-source suites both
passed at `374 passed, 2 skipped`.

An exact-final-version independent-session recheck was attempted three ways and could not
start model work because of external account state:

- configured CLI Provider: `Quota exceeded` after 401/service retries;
- default OpenAI CLI Provider: invalid API key after transport retries;
- new desktop Codex task: access token refresh rejected because the host had been logged
  out or switched to another account.

All three attempts failed before reading the installed Skill or running the workflow. This
is not recorded as a Plugin PASS or Plugin defect. The exact-final-version independent
acceptance remains pending a host sign-in/credential repair; the earlier successful
independent run and the final installed-cache deterministic checks remain separate evidence.

No Git commit was created.
