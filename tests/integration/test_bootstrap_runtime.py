from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def _digest_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _bootstrap_module(path: Path | None = None):
    path = path or ROOT / "scripts" / "bootstrap_skill_engineering.py"
    spec = importlib.util.spec_from_file_location("skill_engineering_bootstrap", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _copy_plugin(destination: Path) -> Path:
    ignored = shutil.ignore_patterns(
        ".git", ".superpowers", ".pytest_cache", "__pycache__", "*.egg-info"
    )
    return Path(shutil.copytree(ROOT, destination, ignore=ignored))


def test_fresh_install_bootstrap_provisions_locked_runtime_and_runs_engine(
    tmp_path: Path,
) -> None:
    bootstrap_module = _bootstrap_module()
    uv = bootstrap_module.find_uv()
    assert uv is not None and uv.is_file(), "release validation requires an available uv executable"

    plugin = _copy_plugin(tmp_path / "installed-plugin")
    target = plugin / "tests" / "fixtures" / "skills" / "minimal-valid"
    runtime_cache = tmp_path / "managed-runtime-cache"
    inspection = tmp_path / "inspection.json"
    plugin_before = _digest_tree(plugin)
    target_before = _digest_tree(target)
    launcher = Path(getattr(sys, "_base_executable", sys.executable))
    environment = os.environ.copy()
    environment["SKILL_ENGINEERING_UV"] = str(uv)
    environment["SKILL_ENGINEERING_RUNTIME_CACHE"] = str(runtime_cache)
    environment.pop("PYTHONPATH", None)
    environment.pop("VIRTUAL_ENV", None)
    environment.pop("CONDA_PREFIX", None)
    copied_bootstrap = _bootstrap_module(
        plugin / "scripts" / "bootstrap_skill_engineering.py"
    )
    with patch.dict(os.environ, environment, clear=True):
        partial_runtime = copied_bootstrap._runtime_dir(
            copied_bootstrap._identity(plugin)
        )
    partial_runtime.mkdir(parents=True)
    command = [
        str(launcher), "-I", "-S",
        str(plugin / "scripts" / "bootstrap_skill_engineering.py"),
        "inspect", "--compatibility-no-default-providers",
        "--target", str(target), "--mode", "AUDIT",
        "--deliverable-contract-applicability", "NOT_REQUIRED",
        "--deliverable-not-required-rationale", "Fixture declares no implemented deliverable.",
        "--output", str(inspection),
    ]

    first = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=180,
    )

    assert first.returncode == 0, first.stderr
    assert inspection.is_file()
    assert '"inspection_id"' in inspection.read_text(encoding="utf-8")
    markers = tuple(runtime_cache.rglob(".skill-engineering-runtime.json"))
    assert len(markers) == 1
    marker_mtime = markers[0].stat().st_mtime_ns
    managed_python = markers[0].parent / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    imports = subprocess.run(
        [str(managed_python), "-I", "-c", "import jsonschema, yaml"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert imports.returncode == 0, imports.stderr
    assert managed_python.parent.parent == partial_runtime
    assert not (plugin / ".venv").exists()
    assert not tuple(plugin.glob("*.egg-info"))
    assert _digest_tree(plugin) == plugin_before
    assert _digest_tree(target) == target_before

    second = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=180,
    )

    assert second.returncode == 0, second.stderr
    assert markers[0].stat().st_mtime_ns == marker_mtime
