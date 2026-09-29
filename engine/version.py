"""Single package-version authority for Engine and governance receipts."""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path


def package_version() -> str:
    try:
        return importlib.metadata.version("skill-engineering")
    except importlib.metadata.PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(payload["project"]["version"])


__all__ = ["package_version"]
