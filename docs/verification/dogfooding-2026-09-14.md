# Dogfooding Findings

## DOGFOOD-001

- Failure family: `third-party-runtime-placeholder-false-positive`
- Primary Issue Class: `IMPLEMENTATION_DEFECT`
- Control Gaps: `IMPLEMENTATION_GAP`, `REGRESSION_MISSING`
- Regression Disposition: `REQUIRED`
- Root cause: B02 placeholder validation recursively scanned every file under the Skill root and reported only the first token.
- Fix boundary: B02 now scans `SKILL.md`, authoritative directories (`references/`, `scripts/`, `validators/`, `schemas/`, `config/`), and explicitly declared critical assets. Environment, runtime, vendored, generated, and other non-authoritative files are excluded by scope semantics rather than directory-specific blacklists.
- Evidence contract: every placeholder finding records relative path, line number, and matched token.
- Regression cases: `third_party_venv_tbd_does_not_block`, `bundled_runtime_todo_does_not_block`, `skill_md_tbd_blocks`, `reference_todo_blocks`, `authoritative_script_placeholder_is_detected`, `third_party_placeholders_do_not_enter_b02_evidence`.

## DOGFOOD-002

- Failure family: `git-history-not-wired-into-rule-bloat`
- Classification: V1.1 backlog item only.
- Current behavior: Rule Bloat receives `history=None`; missing Git history produces a warning and `SKIP`/limitation rather than a blocking result.
- Scope decision: not modified as part of DOGFOOD-001.
