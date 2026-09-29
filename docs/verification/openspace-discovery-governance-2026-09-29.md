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

The production adapter calls the official `search_skills` MCP tool with:

- `source="cloud"`
- `auto_import=false`
- a positive result limit
- the user's natural-language query

The official downloader command is `openspace-download-skill --skill-id ... --output-dir ...`. The currently observed public contract does not provide an authoritative immutable revision or content digest. A downloaded candidate therefore remains `INCOMPLETE` unless the live service supplies new immutable proof.

## D. Architecture Changes

- Extended the existing `SkillSource` abstraction with `OpenSpaceCloudSource`; no replacement discovery framework was introduced.
- Added source-neutral discovery, deduplication, source reports, digest-bound bundles, and Codex-authored selection records.
- Added an Engine-owned quarantine resolver with path, identity, size, file-count, and installation-root guards.
- Added candidate governance records and receipts bound to the existing Inspection, Gate, Coverage, and managed completion contracts.
- Added fail-closed CLI results for resolver failures and candidate integrity changes without fabricating Inspection or Gate fields.
- Added a single package-version authority with a `pyproject.toml` source-tree fallback.

## E. Security Boundary

Discovery metadata is untrusted ranking input and never becomes formal Evidence or installation authority. Search uses `auto_import=false`. Resolution writes only below the Engine artifact root and rejects registered Skill roots, plugin cache roots, path escape, missing `SKILL.md`, identity mismatch, oversized content, and malformed downloader output.

The governance phases do not install, execute, register, or promote discovered candidates. Installation remains a separate, explicitly authorized downstream responsibility.

## F. Test Results

- Unit suite: `356 passed, 2 skipped` in 2.45 seconds.
- Complete repository suite after dependency correction: `533 passed, 2 skipped` in 60.13 seconds.
- Final quiet regression: `533 passed, 2 skipped` in 60.83 seconds.
- The two skips are Windows symlink tests skipped because the current process lacks symlink creation privilege (`WinError 1314`).
- Focused remote governance/E2E suite: `10 passed`.
- Skill validator: `Skill is valid!` with exit code 0.
- Plugin validator: passed with exit code 0.
- `git diff --check`: no whitespace errors.

The complete suite initially exposed that the wheel-packaging test invoked `python -m pip` without declaring `pip` in the `test` extra. `pip>=24,<27` was added to the test dependency contract and lockfile; the original failing test then passed, followed by the fresh complete-suite result above.

## G. E2E Evidence

Fixture-backed production-path tests covered:

- `APPROVED`, `BLOCKED`, and `INCOMPLETE` candidate outcomes with no installation side effects.
- Missing downloader, nonzero downloader exit, malformed JSON, missing `SKILL.md`, and quarantine path escape as structured `INCOMPLETE` results.
- A complete OpenSpace candidate flow through discovery, Codex selection, quarantine resolution, real Engine inspection, and candidate finalization.

The real production `discover` command was run through `scripts/bootstrap_skill_engineering.py` using the configured `openspace-mcp --transport stdio` command and a harmless document-workflow query. The process returned a valid Discovery Bundle with an `INCOMPLETE` OpenSpace source report and zero candidates. The non-secret blocker was:

`OpenSpace MCP error: cannot import name 'McpError' from 'mcp.shared.exceptions'`

No fixture result was substituted for this real probe.

Before and after the real probe:

- `%CODEX_HOME%\skills`: 504 files before and after; file lists equal; standard `digest_tree()` remained `a3f0551a74652dabde7b65d67ada6739a7ba429152b43892f6c57bebc4069d01`; link-safe snapshot digest also remained equal.
- `%CODEX_HOME%\plugins\cache`: 1945 files before and after; file lists equal; link-safe snapshot digest remained `0a683df0ce8e82f7dc01ec7a46885e5fea28b2350fbf1259d52e40db95bbfa13`.

The plugin cache's standard `digest_tree()` was unavailable both before and after because a pre-existing `openai-bundled/chrome/latest` Windows reparse point is intentionally rejected by the inventory safety guard. A non-following, link-aware content snapshot was used for the equality proof; the reparse point was not traversed or modified.

## H. Remaining Blockers

1. The installed real `openspace-mcp` runtime is incompatible with its installed Python `mcp` dependency and cannot currently execute `search_skills`.
2. Even after that external runtime is repaired, the current OpenSpace response contract must provide authoritative immutable revision or content-digest evidence before a live candidate can reach an `APPROVED` governance receipt.

No credentials, authorization headers, tokens, or raw credential-bearing stderr were recorded in this report.

## I. Final Verdict

`NOT_READY`

The local+remote discovery architecture, quarantine boundary, governance binding, CLI failure semantics, and no-installation guarantees are implemented and pass the repository Quality Gate. Real OpenSpace production readiness is not established because the live MCP runtime failed before returning candidates, and the confirmed public contract still lacks immutable revision/content proof required for approval.
