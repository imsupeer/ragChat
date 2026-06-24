from __future__ import annotations

"""Live upload reliability harness.

Run directly (requires backend on http://127.0.0.1:8000):

    python scripts/test_upload_live.py

Or via pytest (opt-in):

    RUN_LIVE_TESTS=true python -m pytest tests/live/test_upload_live_harness.py
"""

import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
FIXTURE = Path(__file__).resolve().parents[1] / "scripts" / "eval_data" / "docs" / "architecture_ingestion.md"
SQLITE_PATH = Path(__file__).resolve().parents[1] / "backend" / "storage" / "test_app.db"
DOCS_DIR = Path(__file__).resolve().parents[1] / "backend" / "storage" / "test_docs"


def wait_for_health(client: httpx.Client, timeout_s: float = 30) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            response = client.get("/health", timeout=3)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Backend health check timed out")


def poll_job(client: httpx.Client, job_id: str, timeout_s: float = 120) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        response = client.get(f"/documents/jobs/{job_id}", timeout=10)
        response.raise_for_status()
        job = response.json()["job"]
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(1)
    raise RuntimeError(f"Job {job_id} did not finish within {timeout_s}s")


def test_upload_and_index(client: httpx.Client) -> str:
    print("1. Upload + index")
    with FIXTURE.open("rb") as handle:
        response = client.post(
            "/documents/upload",
            files={"file": (FIXTURE.name, handle, "text/markdown")},
            timeout=60,
        )
    response.raise_for_status()
    job = response.json()["job"]
    job_id = job["id"]
    print(f"   queued job {job_id}")

    finished = poll_job(client, job_id)
    assert finished["status"] == "completed", finished
    assert finished.get("document_id"), finished
    print(f"   completed document_id={finished['document_id']}")

    docs = client.get("/documents", timeout=10).json()["documents"]
    assert any(doc["id"] == finished["document_id"] for doc in docs)
    print("   document visible in registry")
    return job_id


def test_retry_guards(client: httpx.Client, completed_job_id: str) -> None:
    print("2. Retry endpoint guards")
    missing = client.post("/documents/jobs/does-not-exist/retry", timeout=10)
    assert missing.status_code == 404, missing.text
    print("   missing job -> 404")

    completed = client.post(f"/documents/jobs/{completed_job_id}/retry", timeout=10)
    assert completed.status_code == 400, completed.text
    print("   completed job -> 400")


def test_retry_failed_job(client: httpx.Client) -> None:
    print("3. Retry failed job")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}_{FIXTURE.name}"
    stored_path = DOCS_DIR / stored_name
    stored_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    job_id = str(uuid.uuid4())
    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.execute(
            """
            INSERT INTO upload_jobs (
                id, filename, file_size, stored_path, status, upload_progress, index_progress, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                FIXTURE.name,
                stored_path.stat().st_size,
                str(stored_path),
                "failed",
                100,
                80,
                "registry write failed",
            ),
        )
        conn.commit()

    response = client.post(f"/documents/jobs/{job_id}/retry", timeout=10)
    response.raise_for_status()
    retried = response.json()["job"]
    assert retried["status"] == "queued", retried
    print(f"   retry accepted for failed job {job_id}")

    finished = poll_job(client, job_id)
    assert finished["status"] == "completed", finished
    print("   retried job completed")


def main() -> int:
    results: list[str] = []
    with httpx.Client(base_url=BASE_URL) as client:
        wait_for_health(client)
        completed_job_id = test_upload_and_index(client)
        test_retry_guards(client, completed_job_id)
        test_retry_failed_job(client)
        results.append("upload+index")
        results.append("retry guards")
        results.append("retry failed job")

    print("\nLive upload reliability checks passed:")
    for item in results:
        print(f"  - {item}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"ASSERTION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
