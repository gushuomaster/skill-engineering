# Quality Gate Contract

The Gate answers only whether the requested audit, repair, and validation work completed.

- `PASS`: the requested scope and every required evidence item completed and passed.
- `FAIL`: a known defect remains or repair/regression validation failed.
- `INCOMPLETE`: a required Skill, tool, permission, environment, or execution record is unavailable.
- `ERROR`: the Skill Engineering framework failed.

Codex confirmation for the exact artifact digest is mandatory. Provider output cannot supply it. Missing standard dependencies kept in limited mode remain required `NOT_EXECUTED` evidence and therefore cannot become a full `PASS`. An installed Provider runtime failure may use a contract-proven fallback and must record both paths.

Validation and coverage are separate. `AUDIT_COMPLETE_VALID` requires `coverage_status=FULL`; `OPTIONAL` missing coverage may remain a validation `PASS` with `PARTIAL` coverage, while `REQUIRED` missing coverage is `INCOMPLETE` or `FAIL` and cannot authorize apply. Legacy calls without explicit deliverable applicability report `COMPATIBILITY`, not full audit coverage.

For repairs, `apply_authorized=true` only when validation is `PASS`, modification was authorized, a staged candidate exists, the user requested apply, and the source/candidate digests are current. This is safe modification, not release readiness or publication.

Capability preservation is an independent Gate input. `CAPABILITY_PRESERVED` may proceed; `AUTHORIZATION_REQUIRED` blocks until authorization names the exact removed/narrowed IDs; `CAPABILITY_REGRESSION` always fails; `CAPABILITY_UNVERIFIABLE` is incomplete. Authorization never overrides broken capability evidence or unrelated validation failures.

Apply additionally requires a `ManagedCompletionReceipt` bound to the inspection, validation bundle, semantic confirmation, baseline/candidate capability digests, full coverage, Gate result, and current artifact digest.
