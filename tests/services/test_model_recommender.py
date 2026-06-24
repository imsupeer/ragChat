from pathlib import Path

import pytest

from services.model_catalog import load_model_catalog, sanitize_catalog_for_api


def test_model_catalog_loads():
    catalog = load_model_catalog()
    assert len(catalog) >= 8


def test_model_catalog_required_fields_exist():
    catalog = load_model_catalog()
    required = {
        "id",
        "display_name",
        "provider_runtime",
        "ollama_name",
        "family",
        "parameter_size",
        "quantization",
        "approx_vram_gb",
        "min_ram_gb",
        "recommended_ram_gb",
        "context_tier",
        "strengths",
        "tradeoffs",
        "recommended_use_cases",
        "avoid_when",
        "notes",
    }

    for entry in catalog:
        assert required.issubset(entry.keys())


def test_model_catalog_has_no_duplicate_ids():
    catalog = load_model_catalog()
    ids = [entry["id"] for entry in catalog]
    assert len(ids) == len(set(ids))


def test_model_catalog_memory_values_are_positive():
    catalog = load_model_catalog()
    for entry in catalog:
        assert float(entry["approx_vram_gb"]) > 0
        assert float(entry["min_ram_gb"]) > 0
        assert float(entry["recommended_ram_gb"]) > 0


def test_model_catalog_rejects_invalid_file(tmp_path: Path):
    bad_path = tmp_path / "bad_catalog.json"
    bad_path.write_text('{"not": "a list"}', encoding="utf-8")

    with pytest.raises(ValueError, match="JSON array"):
        load_model_catalog(bad_path)


def test_sanitize_catalog_for_api_omits_internal_fields():
    catalog = load_model_catalog()
    sanitized = sanitize_catalog_for_api(catalog)
    assert "tradeoffs" not in sanitized[0]
    assert "avoid_when" not in sanitized[0]
    assert sanitized[0]["id"]
