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
        repo / "config" / "sources.yml",
        repo / "config" / "deduplication.yml",
        repo / "config" / "document_types.yml",
        repo / "config" / "diavgeia_entalmata.yml",
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
        municipalities = _require(data, "municipalities", list)
        _require(data, "regions", list)
        for item in municipalities:
            if isinstance(item, dict):
                _validate_ambiguous_aliases(item)
    elif name == "sources.yml":
        _require(data, "version", int)
        _require(data, "global_sources", list)
        _require(data, "scopes", list)
        _require(data, "collection_order", list)
        _require(data, "rules", list)
        authority_adapters = data.get("authority_adapters", [])
        if not isinstance(authority_adapters, list):
            raise ConfigValidationError("authority_adapters must be a list")
        for item in data["global_sources"]:
            if not isinstance(item, dict):
                raise ConfigValidationError("global_sources entries must be mappings")
            for key in ("id", "name", "type", "url"):
                if key not in item:
                    raise ConfigValidationError(f"global source missing required key: {key}")
        for item in data["scopes"]:
            if not isinstance(item, dict):
                raise ConfigValidationError("scopes entries must be mappings")
            for key in ("id", "name", "aliases", "sources"):
                if key not in item:
                    raise ConfigValidationError(f"scope missing required key: {key}")
            if not isinstance(item["aliases"], list) or not isinstance(item["sources"], list):
                raise ConfigValidationError("scope aliases and sources must be lists")
            _validate_ambiguous_aliases(item)
        for item in authority_adapters:
            if not isinstance(item, dict):
                raise ConfigValidationError("authority_adapters entries must be mappings")
            for key in ("id", "name", "scope_id", "scope_name", "adapter", "url"):
                if key not in item:
                    raise ConfigValidationError(f"authority adapter missing required key: {key}")
    elif name == "deduplication.yml":
        _require(data, "version", int)
        identity_keys = _require(data, "identity_keys", dict)
        _require(identity_keys, "exact", list)
        _require(data, "merge_levels", list)
        _require(data, "rules", list)
    elif name == "document_types.yml":
        document_types = _require(data, "document_types", dict)
        for key, value in document_types.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ConfigValidationError("document_types entries must be mappings")
            aliases = value.get("aliases")
            if not isinstance(aliases, list):
                raise ConfigValidationError(f"{key}.aliases must be a list")
    elif name == "diavgeia_entalmata.yml":
        _require(data, "api", dict)
        _require(data, "organizations", list)
        _require(data, "keywords", list)
        window_days = data.get("visible_window_days", 15)
        if not isinstance(window_days, int) or window_days < 1:
            raise ConfigValidationError("visible_window_days must be a positive integer")
        api = data.get("api") if isinstance(data.get("api"), dict) else {}
        max_pages = api.get("max_pages", 1)
        if not isinstance(max_pages, int) or max_pages < 1:
            raise ConfigValidationError("api.max_pages must be a positive integer")
        for item in data["organizations"]:
            if not isinstance(item, dict):
                raise ConfigValidationError("organizations entries must be mappings")
            for key in ("id", "name"):
                if key not in item:
                    raise ConfigValidationError(f"organization missing required key: {key}")
        if not all(isinstance(item, str) and item.strip() for item in data["keywords"]):
            raise ConfigValidationError("keywords must contain non-empty strings")
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


def _validate_ambiguous_aliases(item: dict[str, Any]) -> None:
    rules = item.get("ambiguous_aliases")
    if rules is None:
        return
    if not isinstance(rules, list):
        raise ConfigValidationError("ambiguous_aliases must be a list")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ConfigValidationError("ambiguous_aliases entries must be mappings")
        if not isinstance(rule.get("alias"), str) or not rule["alias"].strip():
            raise ConfigValidationError("ambiguous_aliases entries require a non-empty alias")
        for key in ("positive_context", "negative_context"):
            values = rule.get(key, [])
            if not isinstance(values, list):
                raise ConfigValidationError(f"ambiguous_aliases.{key} must be a list")
