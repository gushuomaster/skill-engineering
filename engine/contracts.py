"""JSON Schema loading and validation for contract payloads."""
import json
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, object]:
    return json.loads((SCHEMA_ROOT / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
def validate_contract(schema_name: str, payload: dict[str, object]) -> None:
    Draft202012Validator(load_schema(schema_name)).validate(payload)
