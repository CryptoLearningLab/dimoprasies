from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tender_radar.simple_yaml import load_yaml


@dataclass(frozen=True)
class ValidationResult:
    path: Path
    ok: bool
    message: str


class ConfigValidationError(ValueError):
    pass


def repository_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").exists() and (candidate / "config").exists():
            return candidate
    raise ConfigValidationError("Could not locate repository root from current directory.")


def load_config(path: Path) -> Any:
    if not path.exists():
        raise ConfigValidationError(f"Missing config file: {path}")
    return load_yaml(path)


def validate_repository_configs(root: Path | None = None) -> list[ValidationResult]:
    repo = root or repository_root()
    paths = [
        repo / "config" / "locations.yml",
        repo / "config" / "document_types.yml",
        repo / "config" / "search_request.template.yml",
        *sorted((repo / "config" / "search_profiles").glob("*.yml")),
        *sorted((repo / "config" / "evaluation_profiles").glob("*.yml")),
    ]
    return [validate_config_file(path) for path in paths]


def validate_config_file(path: Path) -> ValidationResult:
    try:
        data = load_config(path)
        _validate_shape(path, data)
    except Exception as exc:
        return ValidationResult(path=path, ok=False, message=str(exc))
    return ValidationResult(path=path, ok=True, message="ok")


def _validate_shape(path: Path, data: Any) -> None:
    if not isinstance(data, dict):
        raise ConfigValidationError("top-level YAML value must be a mapping")
    name = path.name
    if name == "locations.yml":
        _require(data, "timezone", str)
        _require(data, "municipalities", list)
        _require(data, "regions", list)
    elif name == "document_types.yml":
        document_types = _require(data, "document_types", dict)
        for key, value in document_types.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ConfigValidationError("document_types entries must be mappings")
            aliases = value.get("aliases")
            if not isinstance(aliases, list):
                raise ConfigValidationError(f"{key}.aliases must be a list")
    elif name == "search_request.template.yml":
        request = _require(data, "search_request", dict)
        for key in ("scope", "document_types", "terms", "matching", "status", "output"):
            _require(request, key, dict)
    elif "evaluation_profiles" in path.parts:
        _require(data, "profile", dict)
        rules = _require(data, "rules", list)
        for item in rules:
            if not isinstance(item, dict):
                raise ConfigValidationError("evaluation rules must be mappings")
            for key in ("id", "label", "phrases"):
                if key not in item:
                    raise ConfigValidationError(f"evaluation rule missing required key: {key}")
            if not isinstance(item.get("phrases"), list):
                raise ConfigValidationError("evaluation rule phrases must be a list")
    else:
        _require(data, "profile", dict)
        _require(data, "scope", dict)
        _require(data, "document_types", dict)
        _require(data, "terms", dict)


def _require(data: dict[str, Any], key: str, expected_type: type) -> Any:
    if key not in data:
        raise ConfigValidationError(f"missing required key: {key}")
    value = data[key]
    if not isinstance(value, expected_type):
        raise ConfigValidationError(
            f"{key} must be {expected_type.__name__}, got {type(value).__name__}"
        )
    return value
