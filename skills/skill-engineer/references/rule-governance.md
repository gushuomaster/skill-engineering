# Rule Governance Contract

Detectors emit signals such as duplication, density, conflicts, history gaps, and cross-layer overlap. They do not emit actions or target layers. Codex reviews each applicable signal in context and supplies `KEEP`, `MERGE`, `MOVE`, or `DELETE` decisions with rationale and evidence. The Engine validates decision coverage and shape; it never derives an action from a score, keyword, or regular expression.
