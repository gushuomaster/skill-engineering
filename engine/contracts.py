"""JSON Schema loading and validation for contract payloads."""
import json
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, object]:
    path = SCHEMA_ROOT / f"{schema_name}.schema.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("$id", path.as_uri())
    return payload


@lru_cache(maxsize=1)
def _schema_registry() -> Registry:
    registry = Registry()
    for path in SCHEMA_ROOT.glob("*.schema.json"):
        schema_name = path.name.removesuffix(".schema.json")
        schema = load_schema(schema_name)
        registry = registry.with_resource(
            path.as_uri(), Resource.from_contents(schema)
        )
    return registry


def validate_contract(schema_name: str, payload: dict[str, object]) -> None:
    Draft202012Validator(
        load_schema(schema_name), registry=_schema_registry()
    ).validate(payload)
