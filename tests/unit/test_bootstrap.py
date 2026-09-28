from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "scripts" / "bootstrap_skill_engineering.py"


def test_bootstrap_reports_uv_missing_without_falling_back(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["SKILL_ENGINEERING_UV"] = str(tmp_path / "missing-uv")
    environment["SKILL_ENGINEERING_RUNTIME_CACHE"] = str(tmp_path / "runtime")
    environment.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, "-I", str(BOOTSTRAP), "--help"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 78
    assert "BOOTSTRAP_ERROR" in completed.stderr
    assert "reason=UV_NOT_FOUND" in completed.stderr
    assert not (tmp_path / "runtime").exists()


def test_bootstrap_is_standard_library_only() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert imports <= {
        "__future__", "contextlib", "hashlib", "json", "os", "pathlib",
        "platform", "re", "shutil", "subprocess", "sys", "time", "typing",
    }
    assert "pip install" not in source
    assert '"sync", "--frozen"' in source
