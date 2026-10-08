from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]


def test_built_wheel_contains_runtime_contract_schemas(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
    for package in ("engine", "validators", "schemas"):
        shutil.copytree(ROOT / package, source / package)

    wheel_dir = tmp_path / "wheel"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    wheel = next(wheel_dir.glob("skill_engineering-*.whl"))
    with ZipFile(wheel) as archive:
        assert "schemas/provider-result.schema.json" in archive.namelist()


def test_installed_wheel_loads_default_gate_policy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
    for package in ("engine", "validators", "schemas", "config"):
        shutil.copytree(ROOT / package, source / package)

    wheel_dir = tmp_path / "wheel"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    wheel = next(wheel_dir.glob("skill_engineering-*.whl"))
    install_root = tmp_path / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_root),
            str(wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(install_root)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from engine.quality_gate import load_gate_policy; "
                "print(load_gate_policy()['policy_version'])"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
