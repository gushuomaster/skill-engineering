# OpenSpace Cloud Discovery + Candidate Governance Verification

Date: 2026-09-29  
Package version: `1.1.0`  
Plugin version: `1.1.0+codex.20260929000000`

## A. Previous Production Path

The production Provider path required Codex to know an exact Skill name before governance began. `LocalSkillSource.find_exact(name)` searched local Skills and plugin cache entries, then the existing inspection, Evidence, Coverage, and Quality Gate pipeline governed that selected Provider. There was no production query-based OpenSpace Cloud discovery path.

## B. New Discovery Path

The new path is:

`query -> local/OpenSpace SkillSource search -> DiscoveryBundle -> Codex SelectionRecord -> quarantine resolution -> existing inspection/validation/confirmation -> candidate finalization`

The phase commands are `discover`, `record-selection`, `resolve-candidate`, the existing `inspect` / `validate` / `confirm` workflow, and `finalize-candidate`. `find_exact(name)` remains available for explicit names, existing Provider selection, and deterministic replay.

Candidate finalization emits only `APPROVED`, `BLOCKED`, or `INCOMPLETE`. `APPROVED` requires a proven immutable revision, unchanged quarantine digest, bound discovery and selection records, matching Inspection ID, `FULL` Coverage, a `PASS` Gate, and a matching `ManagedCompletionReceipt`.

## C. OpenSpace MCP Contract

The production adapter calls the official `cloud_browse_skills` MCP tool with:

- `action="search_skills"`
- `audience="requester_visible"`
- `artifact_filter="downloadable_only"`
- a positive result limit
- the user's natural-language query

The search call contains no import, download, target-directory, or local-placement argument. The official downloader command remains `openspace-download-skill --skill-id ... --output-dir ...` in the separate resolution phase. The currently observed public contract does not prove that `cloud_skill_id` is an immutable revision or that `manifest_hash` is the authoritative content digest of the resolved candidate. A downloaded candidate therefore remains `INCOMPLETE` unless the live service supplies that proof.

## D. Architecture Changes

- Extended the existing `SkillSource` abstraction with `OpenSpaceCloudSource`; no replacement discovery framework was introduced.
- Added source-neutral discovery, deduplication, source reports, digest-bound bundles, and Codex-authored selection records.
- Added an Engine-owned quarantine resolver with path, identity, size, file-count, and installation-root guards.
- Added candidate governance records and receipts bound to the existing Inspection, Gate, Coverage, and managed completion contracts.
- Added fail-closed CLI results for resolver failures and candidate integrity changes without fabricating Inspection or Gate fields.
- Added a single package-version authority with a `pyproject.toml` source-tree fallback.

## E. Security Boundary

Discovery metadata is untrusted ranking input and never becomes formal Evidence or installation authority. Discovery uses only the fixed Cloud browsing search action. Resolution writes only below the Engine artifact root and rejects registered Skill roots, plugin cache roots, path escape, missing `SKILL.md`, identity mismatch, oversized content, and malformed downloader output.

The governance phases do not install, execute, register, or promote discovered candidates. Installation remains a separate, explicitly authorized downstream responsibility.

## F. Test Results

- Current complete repository suite: `533 passed, 2 skipped` in 69.18 seconds.
- The two skips are Windows symlink tests skipped because the current process lacks symlink creation privilege (`WinError 1314`).
- Current OpenSpace adapter/config/Skill contract suite: `16 passed`.
- Current remote governance/E2E suite: `15 passed`.
- OpenSpace MCP dependency compatibility and related core suites: `108 passed`.
- Skill validator: `Skill is valid!` with exit code 0.
- Plugin validator: passed with exit code 0.
- `git diff --check`: no whitespace errors.

TDD regression evidence covered both production-contract failures: the old `search_skills(source="cloud", auto_import=false)` call and the old `skill_id/name/description` response mapping failed before implementation, then passed after switching to the live OpenSpace `cloud_browse_skills` search contract. OpenSpace now declares `mcp>=1.0.0,<2.0.0` in both packaging inputs because its client transports still use the MCP 1.x API; the active runtime is MCP `1.30.0`, and `pip check` reports no broken requirements.

## G. E2E Evidence

Fixture-backed production-path tests covered:

- `APPROVED`, `BLOCKED`, and `INCOMPLETE` candidate outcomes with no installation side effects.
- Missing downloader, nonzero downloader exit, malformed JSON, missing `SKILL.md`, and quarantine path escape as structured `INCOMPLETE` results.
- A complete OpenSpace candidate flow through discovery, Codex selection, quarantine resolution, real Engine inspection, and candidate finalization.

The real production `discover` command was rerun through `scripts/bootstrap_skill_engineering.py` using the configured `openspace-mcp --transport stdio` command and a harmless document-workflow query. The corrected call reached the live `cloud_browse_skills` implementation in approximately three seconds without starting the heavyweight local OpenSpace engine. It returned a valid Discovery Bundle with an `INCOMPLETE` OpenSpace source report and zero candidates. The non-secret blocker was:

`OpenSpace cloud is disabled. Set OPENSPACE_CLOUD_MODE=live to use cloud features.`

Safe configuration inspection confirmed `OPENSPACE_CLOUD_MODE=off` and no configured OpenSpace Cloud API key. No credential value was read or recorded, and no fixture result was substituted for this real probe.

Before and after the real probe:

- `%CODEX_HOME%\skills`: 504 files before and after; the relative-path, size, and last-write-time snapshot had zero differences.
- `%CODEX_HOME%\plugins\cache`: 1945 files before and after; the relative-path, size, and last-write-time snapshot had zero differences.

The plugin cache's standard `digest_tree()` was unavailable both before and after because a pre-existing `openai-bundled/chrome/latest` Windows reparse point is intentionally rejected by the inventory safety guard. A non-following, link-aware content snapshot was used for the equality proof; the reparse point was not traversed or modified.

## H. Remaining Blockers

1. A human must complete OpenSpace Cloud authentication and enable live mode before a real remote result can be retrieved. This external authorization is not inferred or fabricated by the discovery adapter.
2. After authentication, the live response must still provide authoritative immutable revision or content-digest evidence before a candidate can reach an `APPROVED` governance receipt. `manifest_hash` remains a quality signal until that contract is proven.

No credentials, authorization headers, tokens, or raw credential-bearing stderr were recorded in this report.

## I. Final Verdict

`NOT_READY`

The local+remote discovery architecture, current OpenSpace Cloud MCP contract, quarantine boundary, governance binding, CLI failure semantics, and no-installation guarantees are implemented and pass the repository checks. The MCP runtime incompatibility is resolved, and the real call now reaches the Cloud configuration boundary. Production readiness remains unproven because this machine is not authenticated or enabled for OpenSpace Cloud and no live result has yet supplied immutable revision/content proof required for approval.
