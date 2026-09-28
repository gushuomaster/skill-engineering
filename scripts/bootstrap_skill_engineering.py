#!/usr/bin/env python3
"""Provision and launch the Skill Engineering Engine in an isolated uv runtime."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "scripts" / "skill_engineering.py"
LOCK_FILE = ROOT / "uv.lock"
MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
MARKER_NAME = ".skill-engineering-runtime.json"
LOCK_NAME = ".skill-engineering-bootstrap.lock"
BOOTSTRAP_EXIT = 78


class BootstrapError(RuntimeError):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _emit_error(error: BootstrapError) -> None:
    print("BOOTSTRAP_ERROR", file=sys.stderr)
    print(f"reason={error.reason}", file=sys.stderr)
    print(f"detail={error.detail}", file=sys.stderr)


def _plugin_version(root: Path = ROOT) -> str:
    try:
        payload = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        version = str(payload["version"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BootstrapError("PLUGIN_MANIFEST_INVALID", str(exc)) from exc
    if not version:
        raise BootstrapError("PLUGIN_MANIFEST_INVALID", "plugin version is empty")
    return version


def _lock_digest(root: Path = ROOT) -> str:
    lock = root / "uv.lock"
    if not lock.is_file():
        raise BootstrapError("UV_LOCK_MISSING", f"required lock file not found: {lock}")
    try:
        return hashlib.sha256(lock.read_bytes()).hexdigest()
    except OSError as exc:
        raise BootstrapError("UV_LOCK_UNREADABLE", str(exc)) from exc


def _runtime_cache_root() -> Path:
    override = os.environ.get("SKILL_ENGINEERING_RUNTIME_CACHE")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "skill-engineering" / "runtimes"


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return normalized or "unknown"


def _identity(root: Path = ROOT) -> dict[str, str]:
    return {
        "plugin_version": _plugin_version(root),
        "uv_lock_sha256": _lock_digest(root),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": platform.system().lower(),
        "architecture": platform.machine().lower(),
    }


def _runtime_dir(identity: dict[str, str]) -> Path:
    runtime_platform = "-".join((
        f"py{identity['python'].replace('.', '')}",
        _safe_component(identity["platform"]),
        _safe_component(identity["architecture"]),
    ))
    return (
        _runtime_cache_root()
        / _safe_component(identity["plugin_version"])
        / identity["uv_lock_sha256"]
        / runtime_platform
    )


def _candidate_uv_paths() -> tuple[Path, ...]:
    candidates = [Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv")]
    if os.name == "nt":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        candidates.extend((
            local_app_data / "Programs" / "uv" / "uv.exe",
            Path.home() / ".cargo" / "bin" / "uv.exe",
        ))
        packages = local_app_data / "Packages"
        if packages.is_dir():
            candidates.extend(sorted(packages.glob(
                "OpenAI.Codex_*/LocalCache/Roaming/Python/Python*/Scripts/uv.exe"
            )))
    else:
        candidates.append(Path.home() / ".cargo" / "bin" / "uv")
    return tuple(candidates)


def find_uv() -> Path | None:
    override = os.environ.get("SKILL_ENGINEERING_UV")
    if override is not None:
        candidate = Path(override).expanduser()
        return candidate.resolve() if candidate.is_file() else None
    discovered = shutil.which("uv")
    if discovered:
        return Path(discovered).resolve()
    return next((candidate.resolve() for candidate in _candidate_uv_paths() if candidate.is_file()), None)


def _runtime_python(runtime: Path) -> Path:
    return runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _marker_matches(runtime: Path, identity: dict[str, str]) -> bool:
    marker = runtime / MARKER_NAME
    executable = _runtime_python(runtime)
    if not marker.is_file() or not executable.is_file():
        return False
    try:
        return json.loads(marker.read_text(encoding="utf-8")) == identity
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _write_marker(runtime: Path, identity: dict[str, str]) -> None:
    marker = runtime / MARKER_NAME
    temporary = runtime / f"{MARKER_NAME}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")
    os.replace(temporary, marker)


@contextmanager
def _provision_lock(runtime: Path, identity: dict[str, str]) -> Iterator[None]:
    runtime.parent.mkdir(parents=True, exist_ok=True)
    lock_path = runtime.parent / f".{runtime.name}{LOCK_NAME}"
    deadline = time.monotonic() + 120
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(descriptor)
            break
        except FileExistsError:
            if _marker_matches(runtime, identity):
                yield
                return
            try:
                stale = time.time() - lock_path.stat().st_mtime > 600
            except OSError:
                stale = False
            if stale:
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    pass
            if time.monotonic() >= deadline:
                raise BootstrapError(
                    "RUNTIME_LOCK_TIMEOUT", f"timed out waiting for runtime lock: {lock_path}"
                )
            time.sleep(0.1)
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _clean_environment(runtime: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("VIRTUAL_ENV", None)
    environment.pop("CONDA_PREFIX", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["UV_PROJECT_ENVIRONMENT"] = str(runtime)
    return environment


def _provision(root: Path, uv: Path, runtime: Path, identity: dict[str, str]) -> None:
    if _marker_matches(runtime, identity):
        return
    with _provision_lock(runtime, identity):
        if _marker_matches(runtime, identity):
            return
        if runtime.exists() and not _runtime_python(runtime).is_file():
            try:
                repaired = subprocess.run(
                    [str(uv), "venv", "--clear", "--python", sys.executable, str(runtime)],
                    cwd=root,
                    env=_clean_environment(runtime),
                    text=True,
                    capture_output=True,
                    encoding="utf-8",
                    check=False,
                )
            except OSError as exc:
                raise BootstrapError("RUNTIME_REPAIR_LAUNCH_FAILED", str(exc)) from exc
            if repaired.returncode != 0:
                detail = (repaired.stderr or repaired.stdout or "uv venv repair failed").strip()
                raise BootstrapError("RUNTIME_REPAIR_FAILED", detail[-4000:])
        command = [
            str(uv), "sync", "--frozen", "--no-dev", "--no-install-project",
            "--project", str(root), "--python", sys.executable,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                env=_clean_environment(runtime),
                text=True,
                capture_output=True,
                encoding="utf-8",
                check=False,
            )
        except OSError as exc:
            raise BootstrapError("UV_SYNC_LAUNCH_FAILED", str(exc)) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "uv sync failed").strip()
            raise BootstrapError("UV_SYNC_FAILED", detail[-4000:])
        if not _runtime_python(runtime).is_file():
            raise BootstrapError(
                "RUNTIME_PYTHON_MISSING", f"uv completed without creating {_runtime_python(runtime)}"
            )
        _verify_runtime(runtime)
        _write_marker(runtime, identity)


def _verify_runtime(runtime: Path) -> None:
    try:
        completed = subprocess.run(
            [str(_runtime_python(runtime)), "-I", "-c", "import jsonschema, yaml"],
            env=_clean_environment(runtime),
            text=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        raise BootstrapError("RUNTIME_VALIDATION_LAUNCH_FAILED", str(exc)) from exc
    if completed.returncode != 0:
        raise BootstrapError(
            "RUNTIME_DEPENDENCY_VALIDATION_FAILED",
            (completed.stderr or completed.stdout or "managed runtime import validation failed").strip(),
        )


def run(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not ENGINE.is_file():
        raise BootstrapError("ENGINE_NOT_FOUND", f"Engine entrypoint not found: {ENGINE}")
    uv = find_uv()
    if uv is None:
        raise BootstrapError(
            "UV_NOT_FOUND",
            "uv is required; set SKILL_ENGINEERING_UV to its executable or add uv to PATH",
        )
    identity = _identity(ROOT)
    runtime = _runtime_dir(identity)
    _provision(ROOT, uv, runtime, identity)
    _verify_runtime(runtime)
    try:
        completed = subprocess.run(
            [str(_runtime_python(runtime)), str(ENGINE), *arguments],
            cwd=Path.cwd(),
            env=_clean_environment(runtime),
            check=False,
        )
    except OSError as exc:
        raise BootstrapError("ENGINE_LAUNCH_FAILED", str(exc)) from exc
    return completed.returncode


def main() -> int:
    try:
        return run()
    except BootstrapError as exc:
        _emit_error(exc)
        return BOOTSTRAP_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
