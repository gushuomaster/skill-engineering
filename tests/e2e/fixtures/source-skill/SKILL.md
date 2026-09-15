---
name: source-skill
description: Normalize user-provided text to lowercase and verify the result with a local executable check.
critical_assets:
  - references/behavior.md
  - scripts/check.py
---

# Source Skill

Normalize input by following [the behavior contract](references/behavior.md).

Run `python scripts/check.py --value Example --expect example` to verify the behavior.
