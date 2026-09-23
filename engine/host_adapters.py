"""Host adapters that turn discovered Codex Skills into executable Providers."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
import tomllib
from typing import Callable, Sequence
from uuid import uuid4

import yaml

from engine.models import ProviderDescriptor, ProviderResult, ProviderStatus
from engine.providers import normalize_provider_result


CommandExecutor = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class ProviderExecutionTiming:
    requested_at: float
    spawned_at: float | None = None
    request_sent_at: float | None = None
    first_output_at: float | None = None
    completed_at: float | None = None
    parsed_at: float | None = None
    schema_validated_at: float | None = None
    semantic_validated_at: float | None = None
    pid: int | None = None
    exit_code: int | None = None
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    timeout_reason: str | None = None
    input_bytes: int = 0
    target_file_count: int = 0
    target_bytes: int = 0
    snapshot_file_count: int = 0
    snapshot_bytes: int = 0
    snapshot_estimated_tokens: int = 0
    snapshot_required_bytes: int = 0
    snapshot_relevant_bytes: int = 0
    snapshot_optional_bytes: int = 0
    schema_bytes: int = 0
    stdout_tail: str = ""
    stderr_tail: str = ""
    structured_output_completed: bool = False

    def snapshot(self) -> dict[str, object]:
        payload = asdict(self)
        start = self.requested_at
        for key in (
            "spawned_at", "request_sent_at", "first_output_at", "completed_at",
            "parsed_at", "schema_validated_at", "semantic_validated_at",
        ):
            value = payload[key]
            payload[f"{key[:-3]}_ms"] = None if value is None else round((value - start) * 1000, 1)
            del payload[key]
        payload["total_ms"] = (
            None if self.completed_at is None
            else round((self.completed_at - start) * 1000, 1)
        )
        return payload

    def describe(self) -> str:
        return json.dumps(self.snapshot(), sort_keys=True)


class _ProviderProcessLifetime:
    def __init__(self, close_handle: Callable[[], None] | None = None) -> None:
        self._close_handle = close_handle

    def close(self) -> None:
        close_handle = self._close_handle
        self._close_handle = None
        if close_handle is not None:
            close_handle()


def _provider_process_lifetime(
    process: subprocess.Popen[bytes],
) -> _ProviderProcessLifetime:
    if os.name != "nt":
        return _ProviderProcessLifetime()

    import ctypes
    from ctypes import wintypes

    class JobObjectBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("per_process_user_time_limit", ctypes.c_longlong),
            ("per_job_user_time_limit", ctypes.c_longlong),
            ("limit_flags", wintypes.DWORD),
            ("minimum_working_set_size", ctypes.c_size_t),
            ("maximum_working_set_size", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority_class", wintypes.DWORD),
            ("scheduling_class", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("read_operation_count", ctypes.c_ulonglong),
            ("write_operation_count", ctypes.c_ulonglong),
            ("other_operation_count", ctypes.c_ulonglong),
            ("read_transfer_count", ctypes.c_ulonglong),
            ("write_transfer_count", ctypes.c_ulonglong),
            ("other_transfer_count", ctypes.c_ulonglong),
        ]

    class JobObjectExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("basic_limit_information", JobObjectBasicLimitInformation),
            ("io_info", IoCounters),
            ("process_memory_limit", ctypes.c_size_t),
            ("job_memory_limit", ctypes.c_size_t),
            ("peak_process_memory_used", ctypes.c_size_t),
            ("peak_job_memory_used", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    information = JobObjectExtendedLimitInformation()
    information.basic_limit_information.limit_flags = 0x00002000
    if not kernel32.SetInformationJobObject(
        job_handle,
        9,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job_handle)
        raise ctypes.WinError(error)
    if not kernel32.AssignProcessToJobObject(
        job_handle,
        wintypes.HANDLE(int(process._handle)),
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job_handle)
        raise ctypes.WinError(error)

    return _ProviderProcessLifetime(lambda: kernel32.CloseHandle(job_handle))


def _codex_provider_config() -> tuple[tuple[str, str], ...]:
    config_path = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        config = {}
    provider_name = os.environ.get("CODEX_PROVIDER_NAME") or config.get("model_provider")
    model = os.environ.get("CODEX_PROVIDER_MODEL") or config.get("model")
    providers = config.get("model_providers", {})
    provider = providers.get(provider_name, {}) if isinstance(providers, dict) else {}
    if not isinstance(provider, dict):
        provider = {}
    values: list[tuple[str, str]] = []
    if isinstance(provider_name, str) and provider_name:
        values.append(("model_provider", json.dumps(provider_name)))
    if isinstance(model, str) and model:
        values.append(("model", json.dumps(model)))
    reasoning = os.environ.get("CODEX_PROVIDER_REASONING_EFFORT", "low")
    values.append(("model_reasoning_effort", json.dumps(reasoning)))
    for key in ("name", "base_url", "wire_api", "requires_openai_auth"):
        value = provider.get(key)
        if value is not None and isinstance(provider_name, str) and provider_name:
            values.append((f"model_providers.{provider_name}.{key}", json.dumps(value)))
    return tuple(values)


def discover_skill_path(
    skill_name: str,
    *,
    roots: Sequence[Path] | None = None,
) -> Path:
    """Find an installed Skill by directory name without treating discovery as execution."""
    if not skill_name or Path(skill_name).name != skill_name:
        raise ValueError("skill name must be a single nonblank directory name")
    if roots is None:
        codex_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        roots = (codex_root / "skills", codex_root / "plugins" / "cache")
    candidates: list[Path] = []
    for root in roots:
        direct = (root / skill_name, root / ".system" / skill_name)
        candidates.extend(path for path in direct if (path / "SKILL.md").is_file())
        if root.is_dir():
            candidates.extend(
                item.parent for item in root.rglob("SKILL.md")
                if item.parent.name == skill_name
            )
    unique = sorted({item.resolve() for item in candidates}, key=lambda item: str(item).lower())
    if not unique:
        raise FileNotFoundError(f"installed Skill not found: {skill_name}")
    return unique[0]


def configured_provider(
    skill_name: str,
    *,
    config_path: Path,
) -> tuple[str, str]:
    """Resolve provider ID/capability from open configuration, not a code whitelist."""
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider configuration must be a mapping")
    for item in payload.get("providers", ()):
        if not isinstance(item, dict):
            continue
        provider_id = str(item.get("provider_id", ""))
        source_identity = str(item.get("source_identity", ""))
        if provider_id.rsplit(".", 1)[-1] == skill_name or source_identity.rsplit("/", 1)[-1] == skill_name:
            capability = item.get("capability")
            if not isinstance(capability, str) or not capability.strip():
                raise ValueError(f"configured Provider has no capability: {skill_name}")
            return provider_id, capability
    raise ValueError(f"Provider Skill is not mapped to a capability: {skill_name}")


class CodexSkillProviderAdapter:
    """Invoke an installed Skill in an isolated Codex session and validate its evidence."""

    def __init__(
        self,
        descriptor: ProviderDescriptor,
        *,
        skill_name: str,
        skill_path: Path,
        schema_path: Path,
        executable: str = "codex",
        timeout_seconds: int = 300,
        snapshot_max_bytes: int = 360_000,
        executor: CommandExecutor = subprocess.run,
    ) -> None:
        self.descriptor = descriptor
        self.skill_name = skill_name
        self.skill_path = skill_path.resolve(strict=True)
        self.schema_path = schema_path.resolve(strict=True)
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.snapshot_max_bytes = max(1, int(snapshot_max_bytes))
        self._executor = executor
        self.last_timing: ProviderExecutionTiming | None = None
        self.last_snapshot_profile: dict[str, int] = {}

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        if capability != self.descriptor.capability:
            raise ValueError("adapter capability does not match requested capability")
        target_raw = request.get("target_path")
        if not isinstance(target_raw, str) or not target_raw:
            raise ValueError("Codex Skill Provider requires an existing target_path")
        target = Path(target_raw).resolve(strict=True)
        if not target.is_dir():
            raise ValueError("Provider target_path must be a directory")

        nonce = uuid4().hex
        skill_digest = hashlib.sha256(
            (self.skill_path / "SKILL.md").read_bytes()
        ).hexdigest()
        prompt = self._prompt(capability, target, request, nonce, skill_digest)
        if not self.last_snapshot_profile.get("required_complete", 0):
            raise ValueError(
                "Provider input exceeds snapshot budget; required evidence coverage is incomplete"
            )
        timing = ProviderExecutionTiming(requested_at=time.perf_counter())
        timing.input_bytes = len(prompt.encode("utf-8"))
        profile = getattr(self, "last_snapshot_profile", {})
        timing.snapshot_file_count = int(profile.get("included_file_count", 0))
        timing.snapshot_bytes = int(profile.get("included_bytes", 0))
        timing.snapshot_estimated_tokens = round(timing.input_bytes / 4)
        timing.snapshot_required_bytes = int(profile.get("required_bytes", 0))
        timing.snapshot_relevant_bytes = int(profile.get("relevant_bytes", 0))
        timing.snapshot_optional_bytes = int(profile.get("optional_bytes", 0))
        timing.schema_bytes = self.schema_path.stat().st_size
        target_files = tuple(path for path in target.rglob("*") if path.is_file())
        timing.target_file_count = len(target_files)
        timing.target_bytes = sum(path.stat().st_size for path in target_files)
        self.last_timing = timing
        with tempfile.TemporaryDirectory(prefix="skill-provider-") as raw_temp:
            output = Path(raw_temp) / "provider-result.json"
            command = self._command(target, output)
            try:
                if self._executor is subprocess.run:
                    completed = self._run_subprocess(command, prompt, timing, output)
                else:
                    timing.spawned_at = time.perf_counter()
                    completed = self._executor(
                        command, input=prompt, cwd=target, text=True,
                        capture_output=True, encoding="utf-8", errors="replace",
                        timeout=self.timeout_seconds, check=False,
                    )
                    timing.request_sent_at = timing.spawned_at
                    timing.completed_at = time.perf_counter()
                    timing.exit_code = completed.returncode
                    timing.stdout_bytes = len((completed.stdout or "").encode("utf-8"))
                    timing.stderr_bytes = len((completed.stderr or "").encode("utf-8"))
            except subprocess.TimeoutExpired as exc:
                timing.timeout_reason = "wall_clock_timeout"
                timing.completed_at = time.perf_counter()
                raise TimeoutError(
                    f"{self.skill_name} Provider timed out after {self.timeout_seconds}s; "
                    f"timing={timing.describe()}"
                ) from exc
            if completed.returncode != 0 and not timing.structured_output_completed:
                detail = (completed.stderr or completed.stdout or "no process output").strip()
                raise RuntimeError(
                    f"{self.skill_name} Provider exited {completed.returncode}: {detail[-2000:]}"
                )
            if not output.is_file():
                raise ValueError("Provider produced no structured output")
            try:
                payload = json.loads(output.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Provider output is not valid UTF-8 JSON: {exc}") from exc
            timing.parsed_at = time.perf_counter()

        normalized = normalize_provider_result(
            payload, capability=capability, provider_id=self.descriptor.provider_id,
        )
        timing.schema_validated_at = time.perf_counter()
        markers = set(normalized.evidence)
        required_markers = {
            f"provider_skill={self.skill_name}",
            f"provider_skill_digest={skill_digest}",
            f"invocation_nonce={nonce}",
        }
        if not required_markers.issubset(markers):
            missing = sorted(required_markers - markers)
            raise ValueError("Provider evidence is missing execution markers: " + ", ".join(missing))
        if normalized.fallback_used:
            raise ValueError("primary Provider cannot self-report fallback execution")
        timing.semantic_validated_at = time.perf_counter()
        return normalized

    def _run_subprocess(
        self,
        command: list[str],
        prompt: str,
        timing: ProviderExecutionTiming,
        output_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=(command[command.index("-C") + 1] if "-C" in command else None),
        )
        try:
            lifetime = _provider_process_lifetime(process)
        except Exception:
            process.kill()
            process.wait()
            raise
        try:
            timing.spawned_at = time.perf_counter()
            timing.pid = process.pid
            assert process.stdin is not None
            process.stdin.write(prompt.encode("utf-8"))
            process.stdin.close()
            timing.request_sent_at = time.perf_counter()
            output_queue: queue.Queue[tuple[str, bytes, float]] = queue.Queue()

            def drain(name: str, stream: object) -> None:
                reader = stream
                while True:
                    chunk = reader.read1(8192)
                    if not chunk:
                        return
                    output_queue.put((name, chunk, time.perf_counter()))

            threads = [
                threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
                threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
            ]
            for thread in threads:
                thread.start()
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []
            deadline = time.perf_counter() + self.timeout_seconds
            exit_code: int | None = None
            stable_output_since: float | None = None
            stable_output_signature: tuple[int, int] | None = None
            while exit_code is None:
                while True:
                    try:
                        name, chunk, received_at = output_queue.get_nowait()
                    except queue.Empty:
                        break
                    if timing.first_output_at is None:
                        timing.first_output_at = received_at
                    if name == "stdout":
                        stdout_chunks.append(chunk)
                    else:
                        stderr_chunks.append(chunk)
                if process.poll() is not None:
                    exit_code = process.returncode
                    break
                try:
                    output_signature = (output_path.stat().st_size, output_path.stat().st_mtime_ns)
                    json.loads(output_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    output_signature = None
                if output_signature is not None:
                    if output_signature != stable_output_signature:
                        stable_output_signature = output_signature
                        stable_output_since = time.perf_counter()
                    elif stable_output_since is not None and time.perf_counter() - stable_output_since >= 0.25:
                        timing.structured_output_completed = True
                        process.terminate()
                        exit_code = process.wait()
                        break
                if time.perf_counter() >= deadline:
                    timing.timeout_reason = "wall_clock_timeout"
                    process.kill()
                    exit_code = process.wait()
                    break
                time.sleep(0.02)
            for thread in threads:
                thread.join(timeout=2)
            while True:
                try:
                    name, chunk, received_at = output_queue.get_nowait()
                except queue.Empty:
                    break
                if timing.first_output_at is None:
                    timing.first_output_at = received_at
                if name == "stdout":
                    stdout_chunks.append(chunk)
                else:
                    stderr_chunks.append(chunk)
            timing.completed_at = time.perf_counter()
            timing.exit_code = exit_code
            stdout = b"".join(stdout_chunks)
            stderr = b"".join(stderr_chunks)
            timing.stdout_bytes = len(stdout)
            timing.stderr_bytes = len(stderr)
            timing.stdout_tail = stdout[-2000:].decode("utf-8", "replace")
            timing.stderr_tail = stderr[-2000:].decode("utf-8", "replace")
            if timing.timeout_reason:
                raise subprocess.TimeoutExpired(
                    command,
                    self.timeout_seconds,
                    output=stdout,
                    stderr=stderr,
                )
            return subprocess.CompletedProcess(
                command,
                exit_code,
                stdout.decode("utf-8", "replace"),
                stderr.decode("utf-8", "replace"),
            )
        finally:
            lifetime.close()
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def _command(self, target: Path, output: Path) -> list[str]:
        command = [
            self.executable, "exec", "--ephemeral", "--ignore-user-config",
            "--ignore-rules", "--sandbox", "read-only", "--skip-git-repo-check", "-C", str(target),
        ]
        for key, value in _codex_provider_config():
            command.extend(("-c", f"{key}={value}"))
        command.extend((
            "--output-schema", str(self.schema_path),
            "--output-last-message", str(output), "-",
        ))
        return command

    def _prompt(
        self,
        capability: str,
        target: Path,
        request: dict[str, object],
        nonce: str,
        skill_digest: str,
    ) -> str:
        applicability = request.get(
            "deliverable_contract_applicability", "COMPATIBILITY"
        )
        if capability == "CAPABILITY_CONTRACT":
            scope = (
                "Extract an exhaustive capability_manifest from public claims, entrypoints, "
                "dispatch routes, implementation, profiles, deliverables, templates, schemas, "
                "and validation coverage. Use stable semantic IDs and UNVERIFIABLE when evidence "
                "is insufficient."
            )
        elif capability == "DELIVERABLE_CONTRACT":
            scope = (
                "Extract and evidence the target's declared deliverables, exposure routes, "
                "implementation dispatch, expected artifacts, behavioral proof, scope conflicts, "
                "and applicability. Return a deliverable_contract when applicability is REQUIRED "
                "or OPTIONAL."
            )
        else:
            scope = (
                "Evaluate only the Provider-owned structure, description/trigger, instruction-design, "
                "and responsibility-boundary concerns."
            )
        provider_instructions = (self.skill_path / "SKILL.md").read_text(encoding="utf-8")
        target_snapshot, profile = _build_text_snapshot(
            target,
            max_bytes=self.snapshot_max_bytes,
        )
        self.last_snapshot_profile = profile
        return f"""Use ${self.skill_name} as the Provider for capability {capability}.
This is a read-only Provider invocation. Do not execute shell commands or read any other Skill,
plugin, or instruction file. Do not call any tool. Work only from the complete target text
evidence snapshot below; if it is insufficient for a claim, mark that claim UNVERIFIABLE.
The complete Provider Skill instructions are included below. Follow them directly and do not
invoke or read any other Skill, plugin, or instruction file:
--- Provider Skill ---
{provider_instructions}
--- End Provider Skill ---
--- Target Text Evidence Snapshot ---
{target_snapshot}
--- End Target Text Evidence Snapshot ---
{scope}
The inspection mode is {request.get('mode', 'UNKNOWN')} and deliverable-contract applicability is {applicability}.
If you return a deliverable_contract, bind it exactly to inspection_id={request.get('inspection_id', '')}, inspection_nonce={request.get('inspection_nonce', '')}, and target_digest={request.get('target_digest', '')}; evidence_origin must be provider.
If you return a capability_manifest, bind it exactly to inspection_id={request.get('inspection_id', '')}, inspection_nonce={request.get('inspection_nonce', '')}, artifact_role={request.get('artifact_role', '')}, artifact_digest={request.get('target_digest', '')}, and provider_identity={self.descriptor.provider_id}; evidence_origin must be provider.

Return exactly one JSON object matching the supplied provider-result schema.
- provider_id must be {self.descriptor.provider_id}
- capability must be {capability}
- provider_status must be AVAILABLE when execution completes
- findings contains concrete blocking findings; use an empty array when none exist
- candidate_changes must be an empty array because this invocation is read-only
- limitations contains only gaps in the Provider-owned dimensions listed above; Gate,
  safe-apply authorization, lifecycle, and behavior testing are outside this Provider contract and
  must not be listed as limitations. Use an empty array when all owned dimensions ran.
- fallback_used must be false
- evidence must include these exact three strings:
  - provider_skill={self.skill_name}
  - provider_skill_digest={skill_digest}
  - invocation_nonce={nonce}
Also include concise file/line evidence supporting the result.
Do not emit a Gate verdict, safe-apply decision, or lifecycle transition.
"""


def _text_snapshot(target: Path, *, max_bytes: int = 360_000) -> str:
    snapshot, _ = _build_text_snapshot(target, max_bytes=max_bytes)
    return snapshot


def _build_text_snapshot(
    target: Path,
    *,
    max_bytes: int = 300_000,
) -> tuple[str, dict[str, int]]:
    extensions = {
        ".md", ".py", ".yaml", ".yml", ".json", ".toml", ".txt", ".ini", ".cfg", ".sh",
    }
    excluded_dirs = {
        ".git", ".venv", "venv", "node_modules", "build", "dist", "coverage",
        ".pytest_cache", "__pycache__", "cache", "archives", "archive",
    }
    required_dirs = {
        "scripts", "references", "schemas", "src", "lib", "app", "engine", "validators",
        "config", "agents",
    }
    text_paths = {
        path.relative_to(target).as_posix(): path
        for path in target.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in extensions
    }
    dependency_paths = _dependency_text_paths(target, text_paths)
    behavioral_test_ranks = _behavioral_test_ranks(text_paths)
    candidates: list[tuple[tuple[int, int], Path, str, str, int]] = []
    total_by_category = {"required": 0, "relevant": 0, "optional": 0}
    for relative, path in text_paths.items():
        if any(part in excluded_dirs for part in Path(relative).parts[:-1]):
            continue
        relative_path = path.relative_to(target)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        category = "required" if relative in dependency_paths else (
            "relevant" if relative_path.parts[0] == "tests" else "optional"
        )
        priority = (
            (0, 0)
            if category == "required"
            else (1, behavioral_test_ranks.get(relative, 1_000_000))
            if category == "relevant"
            else (2, 0)
        )
        relative = relative_path.as_posix()
        lines = "\n".join(f"{index}: {line}" for index, line in enumerate(text.splitlines(), 1))
        chunk = f"FILE: {relative}\n{lines}\n"
        encoded_size = len(chunk.encode("utf-8"))
        candidates.append((priority, relative_path, category, chunk, encoded_size))
        total_by_category[category] += encoded_size
    candidates.sort(key=lambda item: (item[0], str(item[1]).lower()))
    chunks: list[str] = []
    used = 0
    included_by_category = {"required": 0, "relevant": 0, "optional": 0}
    included_count = 0
    for _, relative_path, category, chunk, encoded_size in candidates:
        if used + encoded_size > max_bytes:
            continue
        chunks.append(chunk)
        used += encoded_size
        included_count += 1
        included_by_category[category] += encoded_size
    omitted = len(candidates) - included_count
    if omitted:
        chunks.append(f"[omitted_files={omitted}; excluded_dirs={','.join(sorted(excluded_dirs))}]\n")
    profile = {
        "candidate_file_count": len(candidates),
        "included_file_count": included_count,
        "included_bytes": used,
        "required_bytes": included_by_category["required"],
        "relevant_bytes": included_by_category["relevant"],
        "optional_bytes": included_by_category["optional"],
        "candidate_required_bytes": total_by_category["required"],
        "candidate_relevant_bytes": total_by_category["relevant"],
        "candidate_optional_bytes": total_by_category["optional"],
        "required_complete": int(
            included_by_category["required"] == total_by_category["required"]
        ),
    }
    return ("\n".join(chunks) or "[no supported text files found]"), profile


def _dependency_text_paths(target: Path, text_paths: dict[str, Path]) -> set[str]:
    selected = {relative for relative in text_paths if len(Path(relative).parts) == 1}
    skill_text = text_paths.get("SKILL.md")
    if skill_text is not None:
        content = skill_text.read_text(encoding="utf-8", errors="replace")
        selected.update(
            relative for relative in re.findall(r"`([^`]+)`", content)
            if relative in text_paths
        )
    package_entrypoints: list[str] = []
    pyproject = text_paths.get("pyproject.toml")
    if pyproject is not None:
        content = pyproject.read_text(encoding="utf-8", errors="replace")
        package_entrypoints.extend(re.findall(r"=\s*\"([A-Za-z0-9_.]+):", content))
    package_roots = {module.split(".", 1)[0] for module in package_entrypoints}
    selected.update(
        relative for relative in text_paths
        if any(relative.startswith(f"scripts/{root}/data/") for root in package_roots)
    )
    package_files = {
        relative: path for relative, path in text_paths.items()
        if relative.startswith("scripts/") and relative.endswith(".py")
    }
    module_by_path = {
        relative: relative.removeprefix("scripts/").removesuffix(".py").replace("/", ".").removesuffix(".__init__")
        for relative in package_files
    }
    path_by_module = {module: relative for relative, module in module_by_path.items()}
    for entrypoint in package_entrypoints:
        relative = path_by_module.get(entrypoint)
        if relative:
            selected.add(relative)
    queue_paths = [(relative, 0) for relative in selected if relative.endswith(".py")]
    visited: set[str] = set()
    while queue_paths:
        relative, depth = queue_paths.pop()
        if relative in visited:
            continue
        visited.add(relative)
        if depth >= 1:
            continue
        path = text_paths.get(relative)
        if path is None:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except SyntaxError:
            continue
        current_module = module_by_path.get(relative, "")
        current_package = current_module.rsplit(".", 1)[0] if "." in current_module else current_module
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.level:
                    base = current_package.split(".")
                    if node.level > 1:
                        base = base[:-(node.level - 1)]
                    modules.append(".".join((*base, *node.module.split("."))))
                else:
                    modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
        for module in modules:
            if module.split(".", 1)[0] not in package_roots:
                continue
            candidate = path_by_module.get(module)
            if candidate in package_files and candidate not in selected:
                selected.add(candidate)
                queue_paths.append((candidate, depth + 1))
    return selected


def _behavioral_test_ranks(text_paths: dict[str, Path]) -> dict[str, int]:
    pyproject = text_paths.get("pyproject.toml")
    if pyproject is None:
        return {}
    content = pyproject.read_text(encoding="utf-8", errors="replace")
    entrypoints = re.findall(r"=\s*\"([A-Za-z0-9_.]+):", content)
    if not entrypoints:
        return {}
    package_roots = {module.split(".", 1)[0] for module in entrypoints}
    package_files = {
        relative: path for relative, path in text_paths.items()
        if relative.startswith("scripts/") and relative.endswith(".py")
    }
    module_by_path = {
        relative: relative.removeprefix("scripts/").removesuffix(".py").replace("/", ".").removesuffix(".__init__")
        for relative in package_files
    }
    path_by_module = {module: relative for relative, module in module_by_path.items()}
    module_depths = {module: 0 for module in entrypoints if module in path_by_module}
    queue_modules = list(module_depths)
    while queue_modules:
        module = queue_modules.pop(0)
        relative = path_by_module[module]
        path = package_files[relative]
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except SyntaxError:
            continue
        current_package = module.rsplit(".", 1)[0] if "." in module else module
        for imported in _imported_modules(tree, current_package):
            if imported.split(".", 1)[0] not in package_roots:
                continue
            if imported not in path_by_module or imported in module_depths:
                continue
            module_depths[imported] = module_depths[module] + 1
            queue_modules.append(imported)
    ranks: dict[str, int] = {}
    for relative, path in text_paths.items():
        if not relative.startswith("tests/") or not relative.endswith(".py"):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except SyntaxError:
            continue
        imported_depths = [
            module_depths[module]
            for module in _imported_modules(tree, "")
            if module in module_depths
        ]
        if imported_depths:
            ranks[relative] = min(imported_depths)
            if "selected_document_types" in content:
                ranks[relative] = -1
    return ranks


def _imported_modules(tree: ast.AST, current_package: str) -> tuple[str, ...]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.level:
                base = current_package.split(".") if current_package else []
                if node.level > 1:
                    base = base[:-(node.level - 1)]
                modules.append(".".join((*base, *node.module.split("."))))
            else:
                modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return tuple(modules)


class UnavailableSkillProviderAdapter:
    """Represent a configured but undiscovered Skill without fabricating execution."""

    def __init__(self, descriptor: ProviderDescriptor) -> None:
        if descriptor.availability is not ProviderStatus.UNAVAILABLE:
            raise ValueError("unavailable adapter requires UNAVAILABLE descriptor")
        self.descriptor = descriptor

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        raise RuntimeError("unavailable Skill Provider cannot be invoked")


def build_codex_skill_adapter(
    skill_name: str,
    *,
    capability: str | None = None,
    config_path: Path,
    schema_path: Path,
    roots: Sequence[Path] | None = None,
    executor: CommandExecutor = subprocess.run,
    timeout_seconds: int = 300,
) -> CodexSkillProviderAdapter | UnavailableSkillProviderAdapter:
    """Discover a configured Skill and construct its production Codex host adapter."""
    if capability is None:
        provider_id, capability = configured_provider(skill_name, config_path=config_path)
    else:
        provider_id = skill_name
        if not capability.strip():
            raise ValueError("explicit Provider capability must be nonblank")
    try:
        skill_path = discover_skill_path(skill_name, roots=roots)
    except FileNotFoundError:
        return UnavailableSkillProviderAdapter(ProviderDescriptor(
            provider_id, f"installed-skill:{skill_name}", None, capability,
            ProviderStatus.UNAVAILABLE, "codex-exec",
            (f"installed Skill not found: {skill_name}",), None,
        ))
    revision = hashlib.sha256((skill_path / "SKILL.md").read_bytes()).hexdigest()
    descriptor = ProviderDescriptor(
        provider_id, str(skill_path), revision, capability,
        ProviderStatus.AVAILABLE, "codex-exec", (), None,
    )
    return CodexSkillProviderAdapter(
        descriptor, skill_name=skill_name, skill_path=skill_path,
        schema_path=schema_path, executor=executor,
        timeout_seconds=timeout_seconds,
    )


def build_default_provider_adapters(
    plugin_root: Path,
    *,
    executor: CommandExecutor = subprocess.run,
    timeout_seconds: int = 300,
) -> tuple[CodexSkillProviderAdapter, ...]:
    """Construct the packaged semantic Providers declared by this plugin."""
    root = plugin_root.resolve(strict=True)
    config_path = root / "config" / "providers.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("providers"), list):
        raise ValueError("provider configuration must contain a providers list")
    adapters: list[CodexSkillProviderAdapter] = []
    for item in payload["providers"]:
        if not isinstance(item, dict) or item.get("availability") != "packaged":
            continue
        resource_path = item.get("resource_path")
        if not isinstance(resource_path, str) or not resource_path:
            raise ValueError("packaged Provider must declare resource_path")
        skill_path = (root / resource_path).resolve(strict=True)
        if root not in skill_path.parents:
            raise ValueError("packaged Provider resource_path escapes plugin root")
        skill_file = skill_path / "SKILL.md"
        if not skill_file.is_file():
            raise FileNotFoundError(f"packaged Provider Skill not found: {skill_file}")
        provider_id = str(item.get("provider_id", ""))
        capability = str(item.get("capability", ""))
        if not provider_id or not capability:
            raise ValueError("packaged Provider requires provider_id and capability")
        revision = hashlib.sha256(skill_file.read_bytes()).hexdigest()
        descriptor = ProviderDescriptor(
            provider_id,
            str(item.get("source_identity", f"bundled-provider:{skill_path.name}")),
            revision,
            capability,
            ProviderStatus.AVAILABLE,
            str(item.get("invocation_adapter", "codex-exec")),
            (),
            item.get("fallback_provider"),
        )
        adapters.append(CodexSkillProviderAdapter(
            descriptor,
            skill_name=skill_path.name,
            skill_path=skill_path,
            schema_path=root / "schemas" / "provider-result.schema.json",
            executor=executor,
            timeout_seconds=timeout_seconds,
        ))
    return tuple(adapters)
