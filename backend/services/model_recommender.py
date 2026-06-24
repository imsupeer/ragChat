from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from services.model_names import (
    build_install_command,
    build_run_command,
    catalog_name_set,
    model_matches_installed,
    resolve_installed_match,
)
from services.model_catalog import load_model_catalog, sanitize_catalog_for_api

logger = logging.getLogger(__name__)

Priority = Literal["speed", "quality", "balanced", "low_memory"]
UseCase = Literal[
    "general",
    "rag",
    "coding",
    "cybersecurity",
    "long_context",
    "agentic",
    "summarization",
]
Fit = Literal["comfortable", "tight", "offload", "not_recommended"]
Confidence = Literal["high", "medium", "low"]
Category = Literal[
    "best_overall",
    "fastest",
    "best_coding",
    "best_rag",
    "stretch",
    "avoid",
]

ALLOWED_PRIORITIES = {"speed", "quality", "balanced", "low_memory"}
ALLOWED_USE_CASES = {
    "general",
    "rag",
    "coding",
    "cybersecurity",
    "long_context",
    "agentic",
    "summarization",
}

CONTEXT_SUGGESTIONS = {
    "short": "2k-8k",
    "medium": "4k-16k",
    "long": "8k-32k",
}

DEFAULT_NOTES = [
    "Estimates are approximate and depend on quantization, context length, runtime, and background VRAM usage.",
    "Longer context windows increase memory use; start with shorter context if inference is tight.",
]


class HardwareProfileRequest(BaseModel):
    gpu_vendor: str | None = None
    gpu_model: str | None = None
    vram_gb: float | None = None
    ram_gb: float | None = None
    cpu: str | None = None
    os: str | None = None
    runtime: str = "ollama"
    priority: Priority = "balanced"
    use_cases: list[UseCase] = Field(default_factory=lambda: ["general"])
    needs_long_context: bool = False
    prefer_installed_models: bool = True
    installed_models: list[str] = Field(default_factory=list)

    @field_validator("vram_gb", "ram_gb")
    @classmethod
    def validate_positive_memory(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("Memory values must be positive when provided.")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        normalized = (value or "balanced").strip().lower()
        if normalized not in ALLOWED_PRIORITIES:
            allowed = ", ".join(sorted(ALLOWED_PRIORITIES))
            raise ValueError(f"priority must be one of: {allowed}")
        return normalized

    @field_validator("use_cases")
    @classmethod
    def validate_use_cases(cls, value: list[str]) -> list[str]:
        if not value:
            return ["general"]
        normalized: list[str] = []
        for item in value:
            candidate = (item or "").strip().lower()
            if candidate not in ALLOWED_USE_CASES:
                allowed = ", ".join(sorted(ALLOWED_USE_CASES))
                raise ValueError(f"use_cases entries must be one of: {allowed}")
            if candidate not in normalized:
                normalized.append(candidate)
        return normalized


class AvoidEntry(BaseModel):
    model: str
    reason: str


class RecommendationEntry(BaseModel):
    model_config = {"protected_namespaces": ()}

    rank: int
    model_id: str
    display_name: str
    ollama_name: str
    category: Category
    fit: Fit
    estimated_vram_gb: float
    why: list[str]
    tradeoffs: list[str]
    suggested_context: str
    run_command: str
    install_command: str
    catalog_known: bool = True
    installed: bool | None = None
    installed_match: str | None = None
    match_type: str | None = None


class HardwareSummary(BaseModel):
    vram_gb: float | None
    ram_gb: float | None
    detected_tier: str


class RecommendationResponse(BaseModel):
    status: Literal["ok"] = "ok"
    confidence: Confidence
    hardware_summary: HardwareSummary
    recommendations: list[RecommendationEntry]
    avoid: list[AvoidEntry]
    notes: list[str]


class ModelRecommenderService:
    def __init__(
        self,
        catalog: list[dict[str, Any]] | None = None,
        installed_models_provider: Any | None = None,
    ) -> None:
        self._catalog = catalog if catalog is not None else load_model_catalog()
        self._installed_models_provider = installed_models_provider

    def get_catalog(self) -> list[dict[str, Any]]:
        return sanitize_catalog_for_api(self._catalog)

    def recommend(self, profile: HardwareProfileRequest) -> RecommendationResponse:
        effective_use_cases = list(profile.use_cases)
        if profile.needs_long_context and "long_context" not in effective_use_cases:
            effective_use_cases.append("long_context")

        installed_models = self._resolve_installed_models(profile)
        vram_gb = profile.vram_gb
        ram_gb = profile.ram_gb
        confidence = self._compute_confidence(profile, vram_gb, ram_gb)
        detected_tier = self._detect_hardware_tier(vram_gb, ram_gb)

        scored: list[dict[str, Any]] = []
        for entry in self._catalog:
            fit = self._compute_fit(entry, vram_gb, ram_gb)
            score, why = self._score_model(
                entry,
                fit=fit,
                priority=profile.priority,
                use_cases=effective_use_cases,
                installed_models=installed_models,
                prefer_installed=profile.prefer_installed_models,
            )
            scored.append(
                {
                    "entry": entry,
                    "fit": fit,
                    "score": score,
                    "why": why,
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)

        recommendations = self._build_category_recommendations(
            scored, profile.priority, installed_models
        )
        avoid = self._build_avoid_list(scored)
        notes = list(DEFAULT_NOTES)
        if "cybersecurity" in effective_use_cases:
            notes.append(
                "Cybersecurity guidance is educational; verify commands, exploits, and configs in isolated lab environments."
            )
        if not installed_models and profile.prefer_installed_models:
            notes.append(
                "Installed-model boost was skipped because no local Ollama model list was available."
            )

        return RecommendationResponse(
            confidence=confidence,
            hardware_summary=HardwareSummary(
                vram_gb=vram_gb,
                ram_gb=ram_gb,
                detected_tier=detected_tier,
            ),
            recommendations=recommendations,
            avoid=avoid,
            notes=notes,
        )

    def _resolve_installed_models(self, profile: HardwareProfileRequest) -> list[str]:
        if profile.installed_models:
            return [name.strip() for name in profile.installed_models if name.strip()]

        if not profile.prefer_installed_models or self._installed_models_provider is None:
            return []

        try:
            models = self._installed_models_provider()
            if not models:
                return []
            return [name.strip() for name in models if name.strip()]
        except Exception as exc:
            logger.info("Installed model lookup unavailable: %s", exc)
            return []

    def _compute_confidence(
        self,
        profile: HardwareProfileRequest,
        vram_gb: float | None,
        ram_gb: float | None,
    ) -> Confidence:
        signals = 0
        if vram_gb is not None:
            signals += 1
        if ram_gb is not None:
            signals += 1
        if profile.gpu_model:
            signals += 1
        if profile.cpu:
            signals += 1

        if signals >= 3:
            return "high"
        if signals >= 1:
            return "medium"
        return "low"

    def _detect_hardware_tier(self, vram_gb: float | None, ram_gb: float | None) -> str:
        if vram_gb is None and ram_gb is None:
            return "unknown"

        if vram_gb is None or vram_gb <= 0:
            if ram_gb and ram_gb >= 32:
                return "cpu_only_capable"
            return "cpu_only_or_unknown_gpu"

        if vram_gb <= 4:
            return "low_memory_gpu"
        if vram_gb <= 8:
            return "entry_gpu"
        if vram_gb <= 12:
            return "mid_range_local_ai"
        if vram_gb <= 16:
            return "upper_mid_gpu"
        return "high_end_consumer"

    def _compute_fit(
        self,
        entry: dict[str, Any],
        vram_gb: float | None,
        ram_gb: float | None,
    ) -> Fit:
        model_vram = float(entry["approx_vram_gb"])
        min_ram = float(entry["min_ram_gb"])

        if vram_gb is None and ram_gb is None:
            return "comfortable"

        effective_vram = vram_gb if vram_gb is not None and vram_gb > 0 else 0.0
        effective_ram = ram_gb if ram_gb is not None else min_ram

        if effective_vram > 0:
            if model_vram <= effective_vram * 0.7:
                return "comfortable"
            if model_vram <= effective_vram * 0.95:
                return "tight"
            if effective_ram >= model_vram * 1.5 and effective_ram >= min_ram:
                return "offload"
            return "not_recommended"

        if effective_ram >= float(entry["recommended_ram_gb"]):
            return "offload"
        if effective_ram >= min_ram:
            return "tight"
        return "not_recommended"

    def _score_model(
        self,
        entry: dict[str, Any],
        *,
        fit: Fit,
        priority: Priority,
        use_cases: list[str],
        installed_models: list[str],
        prefer_installed: bool,
    ) -> tuple[float, list[str]]:
        score = 0.0
        why: list[str] = []

        fit_scores = {
            "comfortable": 40.0,
            "tight": 22.0,
            "offload": 8.0,
            "not_recommended": -50.0,
        }
        score += fit_scores[fit]
        if fit == "comfortable":
            why.append("Likely fits in available VRAM with comfortable headroom")
        elif fit == "tight":
            why.append("May fit but with limited VRAM headroom")
        elif fit == "offload":
            why.append("May require CPU/RAM offload depending on runtime settings")

        param_size = str(entry["parameter_size"]).upper()
        model_vram = float(entry["approx_vram_gb"])
        strengths = {str(item).lower() for item in entry["strengths"]}
        use_case_tags = {str(item).lower() for item in entry["recommended_use_cases"]}

        if priority == "speed":
            score += max(0.0, 12.0 - model_vram)
            if "speed" in strengths:
                score += 8.0
                why.append("Prioritized for speed on this hardware profile")
        elif priority == "quality":
            if param_size in {"14B", "12B", "30B", "8B"}:
                score += 10.0
            if fit in {"comfortable", "tight"}:
                score += 6.0
                why.append("Quality priority allows larger models when hardware likely supports them")
        elif priority == "low_memory":
            if param_size in {"1B", "3B", "4B"}:
                score += 14.0
                why.append("Low-memory priority favors compact models")
            score -= model_vram * 2.0
        else:
            if param_size in {"7B", "8B"} and fit in {"comfortable", "tight"}:
                score += 10.0
                why.append("Balanced 7B/8B class fit for typical local AI GPUs")

        for use_case in use_cases:
            if use_case == "coding" and ("coding" in strengths or "coding" in use_case_tags):
                score += 12.0
                why.append("Coding use case boosts coder-capable models")
            if use_case == "cybersecurity" and (
                "coding" in strengths or "reasoning" in strengths
            ):
                score += 8.0
                why.append("Cybersecurity learning benefits from coding/reasoning models")
            if use_case == "rag" and ("rag" in strengths or "general" in strengths):
                score += 10.0
                why.append("RAG use case favors instruction-following general models")
            if use_case == "long_context" and entry["context_tier"] == "long":
                score += 10.0
                why.append("Long-context use case favors models with longer context tiers")
            elif use_case == "long_context" and entry["context_tier"] != "long":
                score -= 6.0
            if use_case == "general" and "general" in strengths:
                score += 4.0
            if use_case == "summarization" and (
                "general" in strengths or "summarization" in use_case_tags
            ):
                score += 4.0

        ollama_name = str(entry["ollama_name"])
        installed_match_info = None
        if installed_models:
            match = resolve_installed_match(
                ollama_name,
                list(installed_models),
                catalog_name_set(self._catalog),
            )
            installed_match_info = match

        is_installed = (
            installed_match_info["installed"]
            if installed_match_info is not None
            else None
        )
        if prefer_installed and is_installed and fit != "not_recommended":
            score += 12.0
            why.append("Already installed locally")

        if fit == "not_recommended":
            score -= model_vram

        deduped_why = list(dict.fromkeys(why))
        return score, deduped_why[:4]

    def _build_category_recommendations(
        self,
        scored: list[dict[str, Any]],
        priority: Priority,
        installed_models: list[str],
    ) -> list[RecommendationEntry]:
        usable = [item for item in scored if item["fit"] != "not_recommended"]
        if not usable:
            usable = sorted(scored, key=lambda item: item["score"], reverse=True)[:1]

        used_ids: set[str] = set()
        categories: list[tuple[Category, dict[str, Any] | None]] = [
            ("best_overall", self._pick_best_overall(usable, used_ids)),
            ("fastest", self._pick_fastest(usable, used_ids)),
            ("best_coding", self._pick_by_strength(usable, "coding", used_ids)),
            ("best_rag", self._pick_by_use_case(usable, "rag", used_ids)),
            ("stretch", self._pick_stretch(scored, priority, used_ids)),
        ]

        recommendations: list[RecommendationEntry] = []
        rank = 1

        for category, item in categories:
            if item is None:
                continue
            entry = item["entry"]
            model_id = str(entry["id"])
            used_ids.add(model_id)
            recommendations.append(
                self._to_recommendation(rank, category, item, installed_models)
            )
            rank += 1

        if not recommendations and scored:
            recommendations.append(
                self._to_recommendation(1, "best_overall", scored[0], installed_models)
            )

        return recommendations

    def _exclude_used(
        self,
        items: list[dict[str, Any]],
        used_ids: set[str],
    ) -> list[dict[str, Any]]:
        if not used_ids:
            return items
        remaining = [
            item for item in items if str(item["entry"]["id"]) not in used_ids
        ]
        return remaining or items

    def _pick_best_overall(
        self,
        usable: list[dict[str, Any]],
        used_ids: set[str],
    ) -> dict[str, Any] | None:
        preferred = [
            item
            for item in usable
            if item["fit"] in {"comfortable", "tight"}
        ]
        pool = self._exclude_used(preferred or usable, used_ids)
        return pool[0] if pool else None

    def _pick_fastest(
        self,
        usable: list[dict[str, Any]],
        used_ids: set[str],
    ) -> dict[str, Any] | None:
        candidates = [
            item
            for item in usable
            if "speed" in {str(s).lower() for s in item["entry"]["strengths"]}
            or str(item["entry"]["parameter_size"]).upper() in {"1B", "3B", "4B"}
        ]
        if not candidates:
            candidates = sorted(usable, key=lambda item: float(item["entry"]["approx_vram_gb"]))
        else:
            candidates = sorted(
                candidates,
                key=lambda item: float(item["entry"]["approx_vram_gb"]),
            )
        pool = self._exclude_used(candidates, used_ids)
        return pool[0] if pool else None

    def _pick_by_strength(
        self,
        usable: list[dict[str, Any]],
        strength: str,
        used_ids: set[str],
    ) -> dict[str, Any] | None:
        matches = [
            item
            for item in usable
            if strength in {str(s).lower() for s in item["entry"]["strengths"]}
        ]
        if strength == "coding":
            dedicated = [
                item
                for item in matches
                if "coder" in str(item["entry"]["ollama_name"]).lower()
                or "deepseek" in str(item["entry"]["family"]).lower()
            ]
            if dedicated:
                dedicated.sort(key=lambda item: item["score"], reverse=True)
                pool = self._exclude_used(dedicated, used_ids)
                if pool:
                    return pool[0]
        pool = self._exclude_used(matches, used_ids)
        return pool[0] if pool else None

    def _pick_by_use_case(
        self,
        usable: list[dict[str, Any]],
        use_case: str,
        used_ids: set[str],
    ) -> dict[str, Any] | None:
        matches = [
            item
            for item in usable
            if use_case
            in {str(tag).lower() for tag in item["entry"]["recommended_use_cases"]}
            or (
                use_case == "rag"
                and "general" in {str(s).lower() for s in item["entry"]["strengths"]}
            )
        ]
        pool = self._exclude_used(matches, used_ids)
        return pool[0] if pool else None

    def _pick_stretch(
        self,
        scored: list[dict[str, Any]],
        priority: Priority,
        used_ids: set[str],
    ) -> dict[str, Any] | None:
        if priority not in {"quality", "balanced"}:
            return None

        stretch_candidates = [
            item
            for item in scored
            if item["fit"] in {"tight", "offload"}
            and str(item["entry"]["parameter_size"]).upper() in {"12B", "14B", "30B", "8B"}
        ]
        if not stretch_candidates:
            stretch_candidates = [
                item for item in scored if item["fit"] == "offload"
            ]
        stretch_candidates.sort(key=lambda item: item["score"], reverse=True)
        pool = self._exclude_used(stretch_candidates, used_ids)
        return pool[0] if pool else None

    def _build_avoid_list(self, scored: list[dict[str, Any]]) -> list[AvoidEntry]:
        avoid: list[AvoidEntry] = []
        for item in scored:
            if item["fit"] != "not_recommended":
                continue
            entry = item["entry"]
            avoid.append(
                AvoidEntry(
                    model=str(entry["ollama_name"]),
                    reason=(
                        f"Likely too heavy for the provided VRAM/RAM unless heavily quantized or offloaded "
                        f"(~{entry['approx_vram_gb']}GB estimated)."
                    ),
                )
            )
        return avoid[:5]

    def _to_recommendation(
        self,
        rank: int,
        category: Category,
        item: dict[str, Any],
        installed_models: list[str],
    ) -> RecommendationEntry:
        entry = item["entry"]
        tradeoffs = [str(value) for value in entry["tradeoffs"]][:3]
        context_tier = str(entry["context_tier"])
        ollama_name = str(entry["ollama_name"])
        match = resolve_installed_match(
            ollama_name,
            installed_models,
            catalog_name_set(self._catalog),
        )
        return RecommendationEntry(
            rank=rank,
            model_id=str(entry["id"]),
            display_name=str(entry["display_name"]),
            ollama_name=ollama_name,
            category=category,
            fit=item["fit"],
            estimated_vram_gb=float(entry["approx_vram_gb"]),
            why=item["why"] or [str(entry["notes"])],
            tradeoffs=tradeoffs,
            suggested_context=CONTEXT_SUGGESTIONS.get(context_tier, "4k-16k"),
            run_command=build_run_command(ollama_name),
            install_command=build_install_command(ollama_name),
            catalog_known=True,
            installed=match["installed"] if installed_models else None,
            installed_match=match["installed_match"],
            match_type=match["match_type"],
        )
