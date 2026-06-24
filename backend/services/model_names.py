from __future__ import annotations

from typing import Any, Literal

MatchType = Literal["exact", "alias", "custom", "none"]

KNOWN_ALIASES: dict[str, str] = {
    "llama3.1": "llama3.1:8b",
    "llama3.2": "llama3.2:3b",
}


def normalize_model_name(name: str) -> str:
    return name.strip().lower()


def model_base_name(name: str) -> str:
    return normalize_model_name(name).split(":")[0]


def resolve_canonical_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        return stripped
    normalized = normalize_model_name(stripped)
    return KNOWN_ALIASES.get(normalized, stripped)


def build_install_command(model: str) -> str:
    return f"ollama pull {model.strip()}"


def build_run_command(model: str) -> str:
    return f"ollama run {model.strip()}"


def catalog_name_set(catalog: list[dict[str, Any]]) -> set[str]:
    return {
        str(entry["ollama_name"]).strip()
        for entry in catalog
        if entry.get("ollama_name")
    }


def is_catalog_known(model: str, catalog_names: set[str]) -> bool:
    if not model.strip() or not catalog_names:
        return False

    normalized = normalize_model_name(model)
    catalog_normalized = {normalize_model_name(name) for name in catalog_names}
    if normalized in catalog_normalized:
        return True

    canonical = normalize_model_name(resolve_canonical_name(model))
    if canonical in catalog_normalized:
        return True

    base = model_base_name(model)
    return any(model_base_name(name) == base for name in catalog_names)


def _is_alias_match(requested_norm: str, installed_norm: str) -> bool:
    requested_canonical = normalize_model_name(resolve_canonical_name(requested_norm))
    installed_canonical = normalize_model_name(resolve_canonical_name(installed_norm))
    if requested_canonical == installed_canonical and requested_norm != installed_norm:
        return True

    if requested_norm in KNOWN_ALIASES:
        alias_target = normalize_model_name(KNOWN_ALIASES[requested_norm])
        if alias_target == installed_norm or installed_norm.startswith(f"{alias_target}:"):
            return True

    if installed_norm in KNOWN_ALIASES:
        alias_target = normalize_model_name(KNOWN_ALIASES[installed_norm])
        if alias_target == requested_norm or requested_norm.startswith(f"{alias_target}:"):
            return True

    return False


def model_matches_installed(requested: str, installed_name: str) -> bool:
    requested_norm = normalize_model_name(requested)
    installed_norm = normalize_model_name(installed_name)
    if requested_norm == installed_norm:
        return True
    if installed_norm.startswith(f"{requested_norm}:"):
        return True
    if requested_norm.startswith(f"{installed_norm}:"):
        return True
    return _is_alias_match(requested_norm, installed_norm)


def resolve_installed_match(
    requested: str,
    installed_names: list[str],
    catalog_names: set[str],
) -> dict[str, Any]:
    requested_stripped = requested.strip()
    if not requested_stripped:
        return {
            "installed": False,
            "installed_match": None,
            "match_type": "none",
            "catalog_known": False,
        }

    catalog_known = is_catalog_known(requested_stripped, catalog_names)

    for name in installed_names:
        if normalize_model_name(name) == normalize_model_name(requested_stripped):
            match_type: MatchType = "custom" if not catalog_known else "exact"
            return {
                "installed": True,
                "installed_match": name,
                "match_type": match_type,
                "catalog_known": catalog_known,
            }

    for name in installed_names:
        if _is_alias_match(
            normalize_model_name(requested_stripped),
            normalize_model_name(name),
        ):
            return {
                "installed": True,
                "installed_match": name,
                "match_type": "alias",
                "catalog_known": catalog_known,
            }

    for name in installed_names:
        requested_norm = normalize_model_name(requested_stripped)
        installed_norm = normalize_model_name(name)
        if installed_norm.startswith(f"{requested_norm}:") or requested_norm.startswith(
            f"{installed_norm}:"
        ):
            match_type = "alias" if catalog_known else "custom"
            return {
                "installed": True,
                "installed_match": name,
                "match_type": match_type,
                "catalog_known": catalog_known,
            }

    return {
        "installed": False,
        "installed_match": None,
        "match_type": "none",
        "catalog_known": catalog_known,
    }
