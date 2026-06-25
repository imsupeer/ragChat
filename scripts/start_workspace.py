#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from workspace_startup import StartupOptions, execute_startup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the local RAG workspace (Ollama default or llama.cpp zero-Ollama mode).",
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--provider", choices=["ollama", "llama_cpp"], default="ollama")
    parser.add_argument("--download-model", action="store_true")
    parser.add_argument("--no-start-server", action="store_true")
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    parser.add_argument(
        "--embeddings",
        choices=["local_hash", "sentence_transformers"],
        default=None,
        help="Embeddings provider for llama_cpp mode (default: local_hash).",
    )
    args = parser.parse_args()

    options = StartupOptions(
        provider=args.provider,
        check_only=args.check_only,
        dry_run=args.dry_run,
        download_model=args.download_model,
        start_server=not args.no_start_server,
        backend_only=args.backend_only,
        frontend_only=args.frontend_only,
        embeddings=args.embeddings,
    )
    raise SystemExit(execute_startup(options))


if __name__ == "__main__":
    main()
