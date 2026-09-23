# Pipeline Contract

Codex controls `inspect`, `validate`, `confirm`, `status`, and `apply`.

1. `inspect --target ... --mode AUDIT|AUDIT_REPAIR|TARGETED_REPAIR` records the immutable source baseline, per-run nonce, provenance, and a bundled Provider-owned baseline Capability Manifest. Codex supplies structured audit dimensions; the Engine never infers semantic scope from keywords or file suffixes.
2. Codex performs RCA and authors the decision, governance records, and any complete isolated candidate.
3. `validate` rejects stale inspection data, stages the candidate, runs the same bundled Provider against that staged artifact, computes a structured Capability Diff, validates authorization scope, executes applicable checks, and returns `VALIDATED_PENDING_CONFIRMATION`.
4. `confirm` binds Codex's semantic decision to the exact artifact digest and computes `PASS`, `FAIL`, `INCOMPLETE`, or `ERROR`.
5. A formal result includes a digest-chained `ManagedCompletionReceipt`. `status` reports `UNMANAGED_CHANGE` when no matching receipt exists.
6. `apply` requires the matching receipt and is available only to an authorized repair at `PASS / READY_TO_APPLY`; it atomically replaces the source with digest and concurrent-change protection.

`AUDIT` runs commands in a disposable snapshot and verifies no source change. `AUDIT_REPAIR` requires a candidate and full-audit evidence. `TARGETED_REPAIR` requires evidence that the stated problem existed and targeted regression covering the necessary impact chain.

For a Codex-selected standard dependency, use `--require-standard-skill NAME|RESPONSIBILITY|GAP`. A missing dependency stops before validation and returns action-required status. Only an explicit `--continue-limited` proceeds, and its Gate result is `INCOMPLETE`.

The plugin cannot intercept every out-of-band write. It detects unmanaged state through receipt and digest comparison and must not claim a platform-level write hook.
