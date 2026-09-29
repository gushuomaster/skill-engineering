# Skill Discovery and Candidate Governance

Use this reference when the user describes a capability they need and no exact local Provider Skill has already been selected.

## Boundary

Discovery finds candidates.
Codex selects candidates.
skill-engineering governs candidates.
Installer installs only explicitly authorized candidates.

Discovery metadata is untrusted ranking input, not Evidence and not installation authority. A remote workflow must stop before installation. It must not execute, register, import, or write a candidate into `%CODEX_HOME%\skills`, `%CODEX_HOME%\plugins\cache`, or this plugin's packaged `skills/` directory.

OpenSpace Cloud discovery calls `cloud_browse_skills` with `action="search_skills"`, the user's query, a positive limit, `audience="requester_visible"`, and `artifact_filter="downloadable_only"`. This search-only call does not contain an import, download, target-directory, or local-placement argument. Source failure remains visible as an `INCOMPLETE` source report while other configured sources may still return candidates.

## Production phases

Run every phase through `scripts/bootstrap_skill_engineering.py` from the installed plugin root.

1. `discover` accepts a natural-language query and emits a digest-bound `DiscoveryBundle` containing source reports and deduplicated candidates.
2. Codex ranks the returned candidates, then `record-selection` records one candidate ID, the current bundle digest, and Codex's rationale. This decision is not delegated to a Provider.
3. `resolve-candidate` downloads an OpenSpace candidate with `openspace-download-skill` into the Engine artifact root's quarantine directory. Resolver failure uses `--failure-output` to emit `INCOMPLETE` without fabricating a resolved candidate, Inspection, or Gate.
4. Run the existing `inspect`, `validate`, and `confirm` governance path against the quarantined candidate. Remote origin metadata never substitutes for required Evidence, Coverage, semantic confirmation, or the Quality Gate.
5. `finalize-candidate` binds the resolved candidate, Selection Record, Inspection Bundle, Gate result, and optional `ManagedCompletionReceipt`. It emits exactly one terminal candidate status: `APPROVED`, `BLOCKED`, or `INCOMPLETE`.

`APPROVED` requires all of the following: a proven immutable revision, an unchanged quarantine digest, matching discovery and selection digests, a matching Inspection ID, `FULL` coverage, a `PASS` Gate, and a valid managed completion receipt bound to the same candidate. Only APPROVED creates a `CandidateGovernanceReceipt`; none of these phases installs the candidate.

OpenSpace's current public contract does not guarantee an immutable revision or authoritative content digest. Unless the live service supplies that proof, a successfully downloaded candidate remains `INCOMPLETE`.

## Exact-name path

Keep `find_exact(name)` for a user-specified Skill, an already selected Provider, and deterministic replay. Use query-based discovery when Codex needs to find or compare candidates from local and remote sources.
