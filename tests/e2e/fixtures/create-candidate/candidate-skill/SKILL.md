---
name: candidate-skill
description: Create a concise release checklist for a named topic and verify that all required sections are present.
critical_assets:
  - references/behavior.md
  - scripts/check.py
---

# Candidate Skill

Use this workflow when a user asks for a release checklist:

1. Read [the behavior contract](references/behavior.md).
2. Identify the release topic supplied by the user.
3. Produce scope, validation, and rollback sections for that topic.
4. Run `python scripts/check.py --topic release` to verify the executable behavior.
5. Return the verified checklist and state any evidence limitations.
