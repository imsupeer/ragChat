#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.config import Settings
from services.sentence_transformers_runtime import inspect_sentence_transformers_setup


def build_report(settings: Settings) -> dict[str, object]:
    return inspect_sentence_transformers_setup(
        model_name=settings.sentence_transformers_model,
        dimension=settings.sentence_transformers_dimension,
        device=settings.sentence_transformers_device,
        cache_dir=settings.sentence_transformers_cache_dir,
        local_files_only=settings.sentence_transformers_local_files_only,
    )


def print_report(report: dict[str, object]) -> None:
    print("sentence-transformers embeddings check")
    print("======================================")
    print(f"Status: {report.get('status')}")
    print(f"Model: {report.get('model_name')}")
    print(f"Dimension: {report.get('dimension')}")
    print(f"Device: {report.get('device')}")
    print(f"Local files only: {report.get('local_files_only')}")
    print(f"Dependency installed: {report.get('dependency_installed')}")
    print(f"Model available: {report.get('model_available')}")
    if report.get("message"):
        print(f"Message: {report['message']}")
    if report.get("setup_command"):
        print(f"Setup: {report['setup_command']}")
    if report.get("check_command"):
        print(f"Check: {report['check_command']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check local sentence-transformers embeddings setup.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    report = build_report(settings)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    if args.strict and report.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
