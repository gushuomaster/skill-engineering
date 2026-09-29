from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--fixture-mode", default="valid")
parser.add_argument("--skill-id", required=True)
parser.add_argument("--output-dir", required=True, type=Path)
args = parser.parse_args()

if args.fixture_mode == "nonzero":
    print("fixture download failed", file=sys.stderr)
    raise SystemExit(3)
if args.fixture_mode == "malformed-json":
    print("not-json")
    raise SystemExit(0)

fixture_root = Path(__file__).resolve().parents[1] / "skills"
source_name = "remote-invalid" if args.fixture_mode == "missing-skill-md" else "remote-valid"
source = fixture_root / source_name
target_parent = args.output_dir.resolve()
target = (
    target_parent.parent / "escaped-remote"
    if args.fixture_mode == "path-escape"
    else target_parent / "remote-valid"
)
shutil.copytree(source, target)
skill_id = "different-id" if args.fixture_mode == "skill-id-mismatch" else args.skill_id
(target / ".skill_id").write_text(skill_id + "\n", encoding="utf-8")

if args.fixture_mode == "too-many-files":
    generated = target / "generated"
    generated.mkdir()
    for index in range(1000):
        (generated / f"{index}.txt").write_text("x", encoding="utf-8")
if args.fixture_mode == "too-large":
    (target / "large.bin").write_bytes(b"x" * (10 * 1024 * 1024 + 1))

print(json.dumps({
    "status": "success",
    "skill_id": args.skill_id,
    "name": "remote-valid",
    "local_path": str(target),
    "files": ["SKILL.md", ".skill_id"],
}))
