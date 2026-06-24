import json
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "model_catalog.json"

REQUIRED_FIELDS = (
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
)


def load_model_catalog(catalog_path: Path | None = None) -> list[dict[str, Any]]:
    path = catalog_path or CATALOG_PATH
    with path.open(encoding="utf-8") as handle:
        catalog = json.load(handle)

    if not isinstance(catalog, list):
        raise ValueError("Model catalog must be a JSON array.")

    seen_ids: set[str] = set()
    for entry in catalog:
        if not isinstance(entry, dict):
            raise ValueError("Each catalog entry must be an object.")

        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        if missing:
            raise ValueError(f"Catalog entry missing fields: {', '.join(missing)}")

        model_id = str(entry["id"])
        if model_id in seen_ids:
            raise ValueError(f"Duplicate catalog model id: {model_id}")
        seen_ids.add(model_id)

        approx_vram = float(entry["approx_vram_gb"])
        min_ram = float(entry["min_ram_gb"])
        recommended_ram = float(entry["recommended_ram_gb"])
        if approx_vram <= 0 or min_ram <= 0 or recommended_ram <= 0:
            raise ValueError(f"Invalid memory estimate for model {model_id}")

    return catalog


def sanitize_catalog_for_api(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": entry["id"],
            "display_name": entry["display_name"],
            "provider_runtime": entry["provider_runtime"],
            "ollama_name": entry["ollama_name"],
            "family": entry["family"],
            "parameter_size": entry["parameter_size"],
            "quantization": entry["quantization"],
            "approx_vram_gb": entry["approx_vram_gb"],
            "min_ram_gb": entry["min_ram_gb"],
            "recommended_ram_gb": entry["recommended_ram_gb"],
            "context_tier": entry["context_tier"],
            "strengths": list(entry["strengths"]),
            "recommended_use_cases": list(entry["recommended_use_cases"]),
            "notes": entry["notes"],
        }
        for entry in catalog
    ]
