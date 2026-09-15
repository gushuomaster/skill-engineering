from __future__ import annotations

import argparse


def checklist(topic: str) -> str:
    return f"Topic: {topic}\nScope\nValidation\nRollback"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    args = parser.parse_args()
    result = checklist(args.topic.strip())
    print(result)
    required = (f"Topic: {args.topic.strip()}", "Scope", "Validation", "Rollback")
    return 0 if all(section in result for section in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
