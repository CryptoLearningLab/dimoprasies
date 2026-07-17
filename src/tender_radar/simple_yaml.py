from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


class SimpleYamlError(ValueError):
    pass


def load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return _load_simple_yaml(path.read_text(encoding="utf-8"))
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_simple_yaml(text: str) -> Any:
    lines = text.splitlines()
    index = 0

    def parse_block(indent: int) -> Any:
        nonlocal index
        mapping: dict[str, Any] = {}
        sequence: list[Any] = []
        mode: str | None = None

        while index < len(lines):
            raw = lines[index]
            if not raw.strip() or raw.lstrip().startswith("#"):
                index += 1
                continue
            current_indent = len(raw) - len(raw.lstrip(" "))
            if current_indent < indent:
                break
            if current_indent > indent:
                raise SimpleYamlError(f"Unexpected indentation at line {index + 1}")

            stripped = raw.strip()
            if stripped.startswith("- "):
                if mode not in (None, "sequence"):
                    raise SimpleYamlError(f"Mixed mapping and sequence at line {index + 1}")
                mode = "sequence"
                value_text = stripped[2:].strip()
                value_text = _collect_multiline_value(value_text, indent)
                index += 1
                if value_text:
                    if _looks_like_key_value(value_text):
                        key, item_value = value_text.split(":", 1)
                        item: dict[str, Any] = {key.strip(): _parse_scalar(item_value.strip())}
                        if _next_indent() > indent:
                            nested = parse_block(indent + 2)
                            if not isinstance(nested, dict):
                                raise SimpleYamlError(
                                    f"Expected nested mapping at line {index + 1}"
                                )
                            item.update(nested)
                        sequence.append(item)
                    else:
                        sequence.append(_parse_scalar(value_text))
                else:
                    sequence.append(parse_block(indent + 2))
                continue

            if ":" not in stripped:
                raise SimpleYamlError(f"Expected key/value at line {index + 1}")
            if mode not in (None, "mapping"):
                raise SimpleYamlError(f"Mixed sequence and mapping at line {index + 1}")
            mode = "mapping"
            key, value_text = stripped.split(":", 1)
            key = key.strip()
            value_text = value_text.strip()
            value_text = _collect_multiline_value(value_text, indent)
            index += 1
            if value_text == ">":
                mapping[key] = _read_folded_scalar(indent + 2)
            elif value_text:
                mapping[key] = _parse_scalar(value_text)
            else:
                mapping[key] = parse_block(indent + 2)

        return sequence if mode == "sequence" else mapping

    def _collect_multiline_value(value_text: str, indent: int) -> str:
        nonlocal index
        if not value_text or value_text[0] not in "[{":
            return value_text
        opener = value_text[0]
        closer = "]" if opener == "[" else "}"
        collected = value_text
        while collected.count(opener) > collected.count(closer) and index + 1 < len(lines):
            next_raw = lines[index + 1]
            next_indent = len(next_raw) - len(next_raw.lstrip(" "))
            if next_indent <= indent:
                break
            collected += " " + next_raw.strip()
            index += 1
        return collected

    def _next_indent() -> int:
        probe = index
        while probe < len(lines):
            raw = lines[probe]
            if raw.strip() and not raw.lstrip().startswith("#"):
                return len(raw) - len(raw.lstrip(" "))
            probe += 1
        return -1

    def _read_folded_scalar(indent: int) -> str:
        nonlocal index
        parts: list[str] = []
        while index < len(lines):
            raw = lines[index]
            if not raw.strip():
                index += 1
                continue
            current_indent = len(raw) - len(raw.lstrip(" "))
            if current_indent < indent:
                break
            parts.append(raw[indent:].strip())
            index += 1
        return " ".join(parts)

    return parse_block(0)


def _parse_scalar(value: str) -> Any:
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "null":
        return None
    if value.startswith("[") or value.startswith("{"):
        return _parse_inline(value)
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_inline(value: str) -> Any:
    pythonish = _quote_inline_mapping_keys(value)
    pythonish = (
        pythonish.replace(": null", ": None")
        .replace(": true", ": True")
        .replace(": false", ": False")
    )
    try:
        return ast.literal_eval(pythonish)
    except (SyntaxError, ValueError):
        if value.startswith("{") and value.endswith("}"):
            inner = value[1:-1].strip()
            if not inner:
                return {}
            result: dict[str, Any] = {}
            for part in inner.split(","):
                key, raw_value = part.split(":", 1)
                result[key.strip()] = _parse_scalar(raw_value.strip())
            return result
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [_parse_scalar(part.strip()) for part in inner.split(",")]
        raise SimpleYamlError(f"Unsupported inline YAML: {value}")


def _looks_like_key_value(value: str) -> bool:
    if value.startswith(("[", "{", '"', "'")):
        return False
    return ":" in value


def _quote_inline_mapping_keys(value: str) -> str:
    if not (value.startswith("{") and value.endswith("}")):
        return value
    inner = value[1:-1].strip()
    if not inner:
        return "{}"
    parts = []
    for part in inner.split(","):
        key, raw_value = part.split(":", 1)
        parts.append(f"{key.strip()!r}: {raw_value.strip()}")
    return "{" + ", ".join(parts) + "}"
