import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.eval import answer_matches, resolve_eval_config


class FakeSettings:
    top_k = 5
    max_context_chunks = 5
    chunk_size = 800
    chunk_overlap = 200
    enable_hybrid = False
    enable_reranking = False
    rerank_top_m = 10
    rerank_top_k = 5


def test_answer_matches_live_refusal_phrase():
    expected = "The provided context does not contain enough information to answer this."
    actual = (
        "### Answer\n"
        "The provided context does not contain enough information to answer this.\n"
        "### Evidence\n- none"
    )
    assert answer_matches(expected, actual)


def test_resolve_eval_config_uses_settings_by_default():
    args = argparse.Namespace(
        top_k=None,
        max_context_chunks=None,
        chunk_size=None,
        chunk_overlap=None,
        enable_hybrid=None,
        enable_reranking=None,
        rerank_top_m=None,
        rerank_top_k=None,
    )

    config = resolve_eval_config(FakeSettings(), args)

    assert config["enable_hybrid"] is False
    assert config["enable_reranking"] is False
    assert config["retrieval_mode"] == "dense"
    assert config["rerank_top_m"] == 10
    assert config["rerank_top_k"] == 5


def test_resolve_eval_config_honors_cli_overrides():
    args = argparse.Namespace(
        top_k=None,
        max_context_chunks=None,
        chunk_size=None,
        chunk_overlap=None,
        enable_hybrid=True,
        enable_reranking=True,
        rerank_top_m=12,
        rerank_top_k=4,
    )

    config = resolve_eval_config(FakeSettings(), args)

    assert config["enable_hybrid"] is True
    assert config["enable_reranking"] is True
    assert config["retrieval_mode"] == "hybrid"
    assert config["rerank_top_m"] == 12
    assert config["rerank_top_k"] == 4


def test_eval_skip_generation_with_fake_embeddings():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT_DIR / "scripts" / "eval.py"),
            "--skip-generation",
            "--fake-embeddings",
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Retrieval recall@k: 1.0" in result.stdout
