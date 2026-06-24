import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
FIXTURE = Path(__file__).resolve().parent / "eval_data" / "docs" / "limitations.md"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def ok(message: str) -> None:
    print(f"OK: {message}")


def parse_sse(text: str) -> list[dict]:
    events = []
    for chunk in text.split("\n\n"):
        if not chunk.startswith("data: "):
            continue
        events.append(json.loads(chunk.removeprefix("data: ")))
    return events


def wait_for_job(client: httpx.Client, job_id: str, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        response = client.get(f"{BASE}/documents/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()["job"]
        status = job["status"]
        if status == "completed":
            return
        if status == "failed":
            fail(f"upload job failed: {job.get('error')}")
        time.sleep(1)
    fail(f"upload job {job_id} did not complete in {timeout_s}s")


def main() -> None:
    checks_passed = 0

    with httpx.Client(timeout=120.0) as client:
        health = client.get(f"{BASE}/health")
        health.raise_for_status()
        ok(f"backend health {health.status_code}")
        checks_passed += 1

        with FIXTURE.open("rb") as handle:
            upload = client.post(
                f"{BASE}/documents/upload",
                files={"file": (FIXTURE.name, handle, "text/markdown")},
            )
        upload.raise_for_status()
        job_id = upload.json()["job"]["id"]
        wait_for_job(client, job_id)
        ok(f"document indexed from {FIXTURE.name}")
        checks_passed += 1

        create = client.post(f"{BASE}/chats", json={"title": "Batch 4 manual check"})
        create.raise_for_status()
        chat_id = create.json()["chat"]["id"]
        ok(f"created chat {chat_id}")
        checks_passed += 1

        stream = client.post(
            f"{BASE}/chat/stream",
            json={
                "question": "What are the current limitations?",
                "chat_id": chat_id,
            },
        )
        stream.raise_for_status()
        events = parse_sse(stream.text)
        if not any(event.get("type") == "sources" for event in events):
            fail("stream missing sources event")
        if not any(event.get("type") == "done" for event in events):
            fail("stream missing done event")
        done = next(event for event in events if event.get("type") == "done")
        live_debug = done.get("debug") or {}
        if not live_debug.get("trace_id"):
            fail("live stream debug missing trace_id")
        if not live_debug.get("retrieval"):
            fail("live stream debug missing retrieval section")
        if not live_debug.get("prompt"):
            fail("live stream debug missing prompt section")
        if "used_chunks" not in (live_debug.get("prompt") or {}):
            fail("live stream debug missing prompt.used_chunks")
        ok(f"stream returned debug trace {live_debug['trace_id'][:8]} with retrieval/prompt/used_chunks")
        checks_passed += 1

        reload = client.get(f"{BASE}/chats/{chat_id}/messages")
        reload.raise_for_status()
        messages = reload.json()["messages"]
        assistant = next(message for message in reversed(messages) if message["role"] == "assistant")
        persisted = assistant.get("debug") or {}
        if persisted.get("trace_id") != live_debug.get("trace_id"):
            fail("persisted debug trace_id does not match live stream")
        if not persisted.get("generation"):
            fail("persisted debug missing generation metadata after reload")
        if not (persisted.get("prompt") or {}).get("used_chunks") is not None:
            fail("persisted debug missing prompt.used_chunks after reload")
        ok("reload via GET /messages returned persisted debug metadata")
        checks_passed += 1

        first_trace = persisted["trace_id"]

        regen = client.post(
            f"{BASE}/chat/stream",
            json={
                "question": "What are the current limitations?",
                "chat_id": chat_id,
                "regenerate": True,
            },
        )
        regen.raise_for_status()
        regen_events = parse_sse(regen.text)
        regen_done = next(event for event in regen_events if event.get("type") == "done")
        regen_trace = (regen_done.get("debug") or {}).get("trace_id")
        if not regen_trace:
            fail("regenerate stream missing debug trace_id")
        if regen_trace == first_trace:
            fail("regenerate did not produce a new trace_id")

        after_regen = client.get(f"{BASE}/chats/{chat_id}/messages")
        after_regen.raise_for_status()
        assistant_after = next(
            message for message in reversed(after_regen.json()["messages"]) if message["role"] == "assistant"
        )
        if assistant_after.get("debug", {}).get("trace_id") != regen_trace:
            fail("regenerate did not persist replacement debug metadata")
        user_messages = [message for message in after_regen.json()["messages"] if message["role"] == "user"]
        if len(user_messages) != 1:
            fail(f"regenerate duplicated user messages (count={len(user_messages)})")
        ok(f"regenerate persisted new debug trace {regen_trace[:8]} without duplicate user message")
        checks_passed += 1

    print(f"\nAll {checks_passed} manual persistence checks passed.")


if __name__ == "__main__":
    main()
