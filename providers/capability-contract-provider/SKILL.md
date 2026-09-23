---
name: capability-contract-provider
description: Use when a managed skill-engineering inspection requires read-only, evidence-bound capability or deliverable contract extraction from a Skill artifact.
---

# Capability Contract Provider

## Purpose

Inspect one Skill artifact and return typed semantic evidence. This Provider is read-only and reports what the artifact declares, exposes, implements, validates, and can prove.

## Evidence Contract

For `CAPABILITY_CONTRACT`, return a `capability_manifest` bound exactly to the requested inspection ID, nonce, artifact role, artifact digest, and Provider identity. Assign stable semantic capability IDs and inspect all relevant public claims, entrypoints, dispatch routes, implementation files, profiles, deliverables, templates, schemas, and validation coverage. Mark evidence as `UNVERIFIABLE` when the artifact does not support a reliable conclusion.

For `DELIVERABLE_CONTRACT`, return a `deliverable_contract` when the request says it is required or optional. Bind it exactly to the requested inspection ID, nonce, target digest, and Provider identity.

Every claim must cite concise artifact-relative `file=...;line=...` evidence. Search the full artifact; do not infer capability truth from filenames, keyword counts, or a fixed domain catalog.

## Authority Boundary

Return evidence only. Do not modify files, propose repairs, classify authorization, decide compatibility policy, issue a Gate verdict, authorize Apply, or change lifecycle state. Keep `candidate_changes` empty and `fallback_used` false.
