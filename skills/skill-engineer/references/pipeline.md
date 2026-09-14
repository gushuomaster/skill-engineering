# Pipeline Contract

The orchestrator is the sole control plane. The shared sequence is: load context, detect intent and authorization, select workspace mode, analyze and classify, select a mechanism, apply authorized staged changes, audit, detect rule bloat, validate and regress, collect evidence, adjudicate the Quality Gate, then publish only after Gate PASS.

Create stages immediately and may use an internal fallback. Modify and Fix always isolate before edits. Audit Only remains read-only. Audit + Optimize audits first and isolates only when an authorized optimization is required.
