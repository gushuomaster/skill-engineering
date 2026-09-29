from __future__ import annotations

import importlib.metadata

from engine.version import package_version


def test_package_version_falls_back_to_pyproject(monkeypatch) -> None:
    def missing_distribution(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing_distribution)

    assert package_version() == "1.1.0"
