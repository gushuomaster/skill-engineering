# Pipeline Contract

Codex controls the workflow. Use the four explicit phases in order: `inspect`, `validate`, `confirm`, and `publish`. `run()` is a compatibility wrapper around the first three phases and never publishes.

1. `inspect --target ... --mode ... --output inspection.json` captures the source baseline and returns signals, stable finding IDs, Provider capabilities, and optional advisory Provider evidence. It makes no RCA or governance decision.
2. Codex reviews the inspection, optionally consults Providers, authors `DecisionRecord`, `GovernanceDecision` records, and a complete candidate when the mode allows changes.
3. `validate --inspection ... --decision-record ... --governance-decisions ... --candidate ... --output validation.json` rejects stale inspection data and incomplete finding coverage. It stages the candidate, runs checks, and returns separate `deterministic_evidence` and `advisory_evidence` in `VALIDATED_PENDING_CONFIRMATION`.
4. Codex reviews that exact artifact and its evidence, then submits `confirm --validation ... --semantic-confirmation ... --output outcome.json`. Only this phase computes the final Gate.
5. `publish --outcome outcome.json` is an independent call and works only for a current `READY_TO_PUBLISH` outcome.

Create uses a complete Codex-authored candidate in an independent directory. Modify and Fix use a candidate separate from the source and the Engine stages it again before validation. Audit Only remains read-only. Audit + Optimize audits first and stages only an authorized candidate. Modification authorization permits staging; it does not authorize publication. Without an explicit publish request, a valid candidate can pass the Gate while `publish_authorized` remains false. Gate readiness and atomic publication are separate operations.

For CLI execution, pass real behavior and regression commands as JSON string arrays through `--behavior-command-json` and `--regression-command-json`. Change-mode commands run in the staged artifact. Audit Only commands run in an isolated disposable snapshot. The Engine records command, exit status, stdout, and stderr and rechecks the source after each external command. Missing required commands remain `NOT_EXECUTED`.

Audit outcomes use two dimensions: `AuditExecution.COMPLETE | INCOMPLETE` and `ArtifactAssessment.VALID | FINDINGS | BLOCKING_FINDINGS | UNKNOWN`. CLI exit code 0 means complete and valid, 1 means complete with findings, and 2 means incomplete or a system/contract error.
