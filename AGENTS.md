# Skill Engineering Governance

- Prefer durable mechanisms over additional prompt instructions.
- Diagnose the cause before changing instructions or policy.
- Prefer implementation fixes, regression tests, schemas, validators, tooling, and workflow changes over Prompt Rules.
- Preserve historical failures with focused regression coverage when they represent a stable invariant.
- Consolidate overlapping guidance instead of adding duplicate rules.
- Require the engineering Quality Gate plus Codex confirmation of the current artifact before presenting a completed Skill.
- Keep semantic intent, RCA, classification, mechanism choice, rule governance, and completion decisions with Codex.
- Keep Provider configuration, Gate policy, and runtime input separate.
- Treat `scripts/skill_engineering.py` and the engine modules as the implementation authority.

Run focused checks while iterating:

```powershell
python -m pytest tests/unit -v
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer
```
