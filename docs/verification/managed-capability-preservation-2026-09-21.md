# Managed Capability Preservation Verification

Date: 2026-09-21

## Root Cause

The previous workflow validated only the candidate's self-consistent current state. It did not preserve an immutable semantic capability baseline, compare that baseline with the staged candidate, or require exact authorization for removed and narrowed public capabilities. A repair could therefore delete declarations, implementation, templates, schemas, and tests together and still pass because the candidate no longer contained evidence of the removed contract.

## Architecture Change

- Added Provider-owned, digest-bound Capability Manifests for baseline and candidate artifacts.
- Added deterministic structured capability diff classifications: `ADDED`, `PRESERVED`, `MODIFIED`, `REMOVED`, `NARROWED`, `BROKEN`, and `UNVERIFIABLE`.
- Added Codex-authored capability change decisions with exact removed/narrowed IDs, user authorization evidence, compatibility impact, migration plan, and deprecation plan.
- Added a packaged read-only `CAPABILITY_CONTRACT` / `DELIVERABLE_CONTRACT` Provider profile.
- Added structured deliverable applicability from operation mode, audit dimensions, and validated public-output status; no keyword inference is used.
- Added semantic workspace evidence and Capability Preservation Gate states.
- Added digest-chained `ManagedCompletionReceipt`, `status`, and `UNMANAGED_CHANGE` reporting.
- Apply now requires an explicit receipt matching the current validated outcome.

## Capability Preservation Gate

| State | Gate effect |
| --- | --- |
| `CAPABILITY_PRESERVED` | May proceed when every other required check passes. |
| `AUTHORIZATION_REQUIRED` | Fails; Apply is not authorized. |
| `CAPABILITY_REGRESSION` | Fails even when a user authorized an unrelated removal. |
| `CAPABILITY_UNVERIFIABLE` | Incomplete; full coverage cannot be claimed. |

## Dogfooding Result

The isolated baseline fixture exposes `SRS`, `SDD_DETAIL`, `STP`, `STD`, and `STR`. The isolated candidate exposes only `SRS` and passes its own pytest suite.

- Without exact authorization, the engine identifies `SDD_DETAIL`, `STD`, `STP`, and `STR` as removed and blocks Apply with `AUTHORIZATION_REQUIRED`.
- With authorization naming the exact four IDs plus compatibility, migration, and deprecation evidence, the otherwise valid candidate reaches `PASS / READY_TO_APPLY`.
- No real external Skill directory is used for dogfooding.

## Verification

Commands and results:

```text
python -m pytest -q
438 passed, 2 skipped
```

The two skips are existing Windows symlink privilege limitations in `tests/unit/test_inventory.py`.

```text
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\skill-engineer
Skill is valid!

python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py providers\capability-contract-provider
Skill is valid!

git diff --check
No diff errors; only Git LF-to-CRLF working-copy warnings.
```

External target protection:

```text
git -C D:\project\skills status --short
<empty>

git -C D:\project\skills rev-parse HEAD
affc52ac74a069113682a86013300d7b00fc3fa3

git -C D:\project\skills diff --name-only -- test3/.hypercode/skills/gjb438c-document-engineering
<empty>
```

## Known Boundary

The plugin cannot intercept every out-of-band filesystem write. It detects whether a result is managed through inspection, digest, Provider, Gate, confirmation, and receipt bindings. A changed artifact without a matching receipt is reported as `UNMANAGED_CHANGE`; this is not a platform-level write hook.

## Installation Status

Not installed. No commit, push, tag, release, publication, or installation was performed in this work.
