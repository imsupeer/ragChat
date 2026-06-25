#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.config import Settings, get_settings
from core.dependencies import clear_dependency_caches, get_document_reindex_service


def post_reindex(
    *,
    base_url: str,
    dry_run: bool,
    document_ids: list[str] | None,
    force: bool,
    timeout_seconds: float,
) -> dict:
    payload = {
        "dry_run": dry_run,
        "document_ids": document_ids,
        "force": force,
    }
    url = f"{base_url.rstrip('/')}/documents/reindex"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def backend_reachable(base_url: str, timeout_seconds: float) -> bool:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/health", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def run_direct(
    *,
    dry_run: bool,
    document_ids: list[str] | None,
    force: bool,
) -> dict:
    clear_dependency_caches()
    service = get_document_reindex_service()
    if dry_run:
        return service.build_reindex_plan(
            document_ids=document_ids,
            force=force,
            dry_run=True,
        )
    return service.run_reindex_plan(
        document_ids=document_ids,
        force=force,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or run document reindexing.")
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Build a reindex plan without mutating data (default).",
    )
    parser.add_argument(
        "--run",
        dest="dry_run",
        action="store_false",
        help="Execute reindex into the active embeddings collection.",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace vectors in the active collection before reindexing.",
    )
    parser.add_argument(
        "--document-id",
        action="append",
        dest="document_ids",
        default=None,
        help="Limit reindex to one or more document IDs.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt for --run.",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Use the backend service directly instead of the HTTP API.",
    )
    args = parser.parse_args(argv)

    dry_run = args.dry_run
    settings: Settings = get_settings()
    backend_url = f"http://127.0.0.1:{settings.api_port}"

    if not dry_run and not args.yes:
        print(
            "This will reindex registered documents into the active embeddings collection.",
            file=sys.stderr,
        )
        print("Re-run with --yes to confirm.", file=sys.stderr)
        return 2

    try:
        if args.direct or not backend_reachable(
            backend_url,
            settings.llama_cpp_runtime_timeout_seconds,
        ):
            if not args.direct and not dry_run:
                print(
                    "Backend is unavailable; using direct service mode.",
                    file=sys.stderr,
                )
            result = run_direct(
                dry_run=dry_run,
                document_ids=args.document_ids,
                force=args.force,
            )
        else:
            result = post_reindex(
                base_url=backend_url,
                dry_run=dry_run,
                document_ids=args.document_ids,
                force=args.force,
                timeout_seconds=settings.llama_cpp_runtime_timeout_seconds,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Reindex request failed: HTTP {exc.code}", file=sys.stderr)
        if body:
            print(body, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Reindex failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    mode = "dry-run" if result.get("dry_run", dry_run) else "run"
    print(f"Reindex {mode}")
    print(f"Active provider: {result.get('active_provider')}")
    print(f"Active model: {result.get('active_model')}")
    print(f"Active collection: {result.get('active_collection')}")
    print(f"Summary: {result.get('summary')}")
    for item in result.get("documents", []):
        print(
            f"- {item.get('filename')} ({item.get('document_id')}): "
            f"{item.get('status')} - {item.get('reason')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
