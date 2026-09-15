from __future__ import annotations

import argparse


def normalize(value: str) -> str:
    return value.strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--value", required=True)
    parser.add_argument("--expect", required=True)
    args = parser.parse_args()
    actual = normalize(args.value)
    print(f"actual={actual}")
    return 0 if actual == args.expect else 1


if __name__ == "__main__":
    raise SystemExit(main())
