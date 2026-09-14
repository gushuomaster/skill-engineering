# V1 Verification Evidence

Date: 2026-09-14  
OS: Windows  
Python: `python` (runtime reported by test environment)  
Revision: recorded at commit `test: verify skill engineering v1`

## Commands and results

| Command | Exit | Result |
|---|---:|---|
| `python -m pytest tests/integration/test_end_to_end_flows.py tests/regression/test_governance_invariants.py -q` | 0 | 12 passed |
| `python -m pytest -q` | 0 | 281 passed, 2 skipped (Windows symlink privilege unavailable) |
| `python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py D:\project\skill-engineering\.worktrees\skill-engineering\skills\skill-engineer` | 0 | Skill is valid |
| `python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py D:\project\skill-engineering\.worktrees\skill-engineering` | 0 | Plugin validation passed |
| `$OutputEncoding = [System.Text.UTF8Encoding]::new($false); New-Item -ItemType Directory -Force $probe; python scripts/skill_engineering.py '只读审计此 Skill' --source tests/fixtures/skills/with-unicode --read-only --target-parent $probe --json` | 0 | Valid UTF-8 JSON emitted without replacement characters; fixture unchanged. Audit correctly returned blocking findings because fixture contains only a Unicode-named Markdown file. |

The integration matrix covers create, modify, fix, audit-only pass/fail, and audit-optimize flows. Governance regressions cover gate bypass, audit auto-upgrade, missing evidence, and cross-filesystem publication.
