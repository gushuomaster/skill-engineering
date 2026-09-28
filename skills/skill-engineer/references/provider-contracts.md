# Provider Contract

Codex selects professional Skills from their real installed instructions and the current audit findings. The Engine invokes only explicitly selected Skills; there is no fixed standard-name mapping or closed domain catalog.

A Provider result must identify the actual Skill, capability, invocation phase, availability, execution state, evidence validity, findings, evidence, limitations, and whether resilience fallback ran. Discovery is not execution. Missing installation is handled by standard-dependency preflight, not normalized into Provider runtime failure.

The bundled `CAPABILITY_CONTRACT` Provider is mandatory for managed work. It runs read-only against the immutable baseline and the Engine-staged candidate, returning evidence-bound Capability Manifests with stable semantic IDs. It marks insufficient evidence `UNVERIFIABLE`; it never proposes repairs.

Provider results are advisory until independently validated and tied to the requested coverage. Providers may supply semantic evidence, but they cannot own intent, RCA, issue classification, governance, mechanism selection, capability-change authorization, Gate policy, semantic confirmation, or safe-apply authorization.

Only the selected `DELIVERABLE_CONTRACT` Provider may return a `deliverable_contract`; all other Provider capabilities must return that field as null. The contract is bound to the current `inspection_id`, `inspection_nonce`, target digest, and Provider identity. The Engine independently verifies exposure, dispatch, generated artifacts, behavioral proof, evidence paths, and scope conflicts. Missing, stale, self-reported, or unexecuted contract evidence is never a complete audit pass.

Only the selected `CAPABILITY_CONTRACT` Provider may return a `capability_manifest`; all other Provider capabilities must return that field as null. Schema validation, Provider normalization, and Engine routing enforce these ownership boundaries before typed evidence reaches the `EvidenceCollector`.
