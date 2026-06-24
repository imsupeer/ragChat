from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_models import router as models_router
from core.dependencies import get_local_metrics_service, get_model_recommender_service
from services.metrics import LocalMetrics
from services.model_recommender import HardwareProfileRequest, ModelRecommenderService


def build_client(recommender: ModelRecommenderService | None = None):
    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_model_recommender_service] = lambda: (
        recommender or ModelRecommenderService(installed_models_provider=lambda: [])
    )
    app.dependency_overrides[get_local_metrics_service] = lambda: LocalMetrics()
    return TestClient(app)


def test_post_model_recommendations_returns_structured_response():
    with build_client() as client:
        response = client.post(
            "/models/recommendations",
            json={
                "vram_gb": 12,
                "ram_gb": 32,
                "priority": "balanced",
                "use_cases": ["rag", "coding"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["confidence"] in {"high", "medium", "low"}
    assert payload["recommendations"]
    first = payload["recommendations"][0]
    assert first["install_command"].startswith("ollama pull ")
    assert first["run_command"].startswith("ollama run ")
    assert first["catalog_known"] is True
    assert payload["notes"]
    assert "hardware_summary" in payload


def test_post_model_recommendations_invalid_negative_vram_returns_validation_error():
    with build_client() as client:
        response = client.post(
            "/models/recommendations",
            json={"vram_gb": -1, "ram_gb": 16},
        )

    assert response.status_code == 422


def test_post_model_recommendations_partial_input_works():
    with build_client() as client:
        response = client.post(
            "/models/recommendations",
            json={"priority": "speed"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] in {"low", "medium"}
    assert payload["recommendations"]


def test_post_model_recommendations_includes_avoid_section_for_heavy_hardware_mismatch():
    with build_client() as client:
        response = client.post(
            "/models/recommendations",
            json={
                "vram_gb": 4,
                "ram_gb": 16,
                "priority": "balanced",
                "use_cases": ["general"],
            },
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["avoid"]
    assert any("30b" in item["model"].lower() for item in payload["avoid"])


def test_post_model_recommendations_response_has_no_path_leaks():
    with build_client() as client:
        response = client.post(
            "/models/recommendations",
            json={"vram_gb": 8, "ram_gb": 32},
        )

    text = response.text
    assert "C:\\" not in text
    assert "/Users/" not in text


def test_get_model_catalog_returns_sanitized_entries():
    with build_client() as client:
        response = client.get("/models/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["models"]
    assert "tradeoffs" not in payload["models"][0]


def test_post_model_recommendations_increments_metrics():
    metrics = LocalMetrics()
    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_model_recommender_service] = lambda: ModelRecommenderService(
        installed_models_provider=lambda: []
    )
    app.dependency_overrides[get_local_metrics_service] = lambda: metrics

    with TestClient(app) as client:
        response = client.post("/models/recommendations", json={"vram_gb": 12, "ram_gb": 32})

    assert response.status_code == 200
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["models.recommendation.request"] == 1
    assert snapshot["counters"]["models.recommendation.success"] == 1
    assert snapshot["last_values"]["models.recommendation.last_confidence"] in {
        "high",
        "medium",
        "low",
    }


def test_recommender_low_vram_recommends_small_models():
    service = ModelRecommenderService(installed_models_provider=lambda: [])
    response = service.recommend(
        HardwareProfileRequest(
            vram_gb=4,
            ram_gb=16,
            priority="low_memory",
            use_cases=["general"],
        )
    )

    fastest = next(
        (item for item in response.recommendations if item.category == "fastest"),
        None,
    )
    assert fastest is not None
    assert fastest.estimated_vram_gb <= 4.0


def test_recommender_mid_vram_recommends_balanced_8b_class():
    service = ModelRecommenderService(installed_models_provider=lambda: [])
    response = service.recommend(
        HardwareProfileRequest(
            vram_gb=12,
            ram_gb=32,
            priority="balanced",
            use_cases=["rag"],
        )
    )

    overall = next(
        (item for item in response.recommendations if item.category == "best_overall"),
        None,
    )
    assert overall is not None
    assert overall.fit in {"comfortable", "tight", "offload"}
    assert overall.estimated_vram_gb <= 12.0


def test_recommender_coding_use_case_boosts_coder_models():
    service = ModelRecommenderService(installed_models_provider=lambda: [])
    response = service.recommend(
        HardwareProfileRequest(
            vram_gb=12,
            ram_gb=32,
            priority="balanced",
            use_cases=["coding"],
        )
    )

    coding = next(
        (item for item in response.recommendations if item.category == "best_coding"),
        None,
    )
    assert coding is not None
    assert "coder" in coding.ollama_name.lower() or "deepseek" in coding.ollama_name.lower()


def test_recommender_quality_priority_includes_stretch_option():
    service = ModelRecommenderService(installed_models_provider=lambda: [])
    response = service.recommend(
        HardwareProfileRequest(
            vram_gb=12,
            ram_gb=32,
            priority="quality",
            use_cases=["coding"],
        )
    )

    categories = {item.category for item in response.recommendations}
    assert "stretch" in categories


def test_recommender_installed_model_boost():
    service = ModelRecommenderService(
        installed_models_provider=lambda: ["llama3.2:3b"]
    )
    response = service.recommend(
        HardwareProfileRequest(
            vram_gb=8,
            ram_gb=16,
            priority="balanced",
            use_cases=["general"],
            prefer_installed_models=True,
            installed_models=["llama3.2:3b"],
        )
    )

    names = {item.ollama_name for item in response.recommendations}
    assert "llama3.2:3b" in names


def test_recommender_missing_hardware_returns_lower_confidence():
    service = ModelRecommenderService(installed_models_provider=lambda: [])
    response = service.recommend(HardwareProfileRequest())

    assert response.confidence == "low"
    assert response.recommendations


def test_installed_models_provider_failure_does_not_break_recommendations():
    failing_provider = MagicMock(side_effect=RuntimeError("ollama down"))
    service = ModelRecommenderService(installed_models_provider=failing_provider)

    response = service.recommend(
        HardwareProfileRequest(
            vram_gb=8,
            ram_gb=16,
            prefer_installed_models=True,
        )
    )

    assert response.recommendations
    assert response.status == "ok"
