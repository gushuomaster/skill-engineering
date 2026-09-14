# Quality Gate Contract

The internal Quality Gate is the only component that emits PASS or FAIL. It evaluates normalized deterministic evidence against the versioned policy and always records `publish_authorized`. Audit Only is never publish-authorized, Gate FAIL is never publish-authorized, and Gate PASS authorizes publication only for an authorized candidate with satisfied workspace preconditions.

