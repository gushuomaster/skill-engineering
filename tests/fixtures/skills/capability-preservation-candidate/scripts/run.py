from __future__ import annotations

import argparse
import json
from pathlib import Path


DOCUMENTS = ("SRS",)


def generate(output: Path, documents: tuple[str, ...] = DOCUMENTS) -> tuple[Path, ...]:
    output.mkdir(parents=True, exist_ok=True)
    generated = []
    for document in documents:
        path = output / f"{document}.docx"
        path.write_text(f"fixture:{document}\n", encoding="utf-8")
        generated.append(path)
    return tuple(generated)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.list:
        print(json.dumps(DOCUMENTS))
        return 0
    if args.output is None:
        parser.error("--output is required unless --list is used")
    generate(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
