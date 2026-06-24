import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def test_benchmark_retrieval_runs_with_fake_embeddings_from_eval():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT_DIR / "scripts" / "benchmark_retrieval.py"),
            "--fake-embeddings",
            "--from-eval",
            "--repeat",
            "2",
            "--queries",
            "Does PDF handling include OCR?",
        ],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Retrieval Benchmark" in result.stdout
    assert "Latency (ms)" in result.stdout
    assert "p95:" in result.stdout
    assert "Lexical cache" in result.stdout
