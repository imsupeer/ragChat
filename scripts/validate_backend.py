#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def run_command(command: list[str], title: str) -> None:
    print(f"\n== {title} ==")
    print(" ".join(command))
    result = subprocess.run(command, cwd=ROOT_DIR)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run local backend validation checks (no frontend, no Ollama by default).",
    )
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--include-live", action="store_true")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use quiet pytest and skip eval markdown report generation.",
    )
    args = parser.parse_args()

    python = sys.executable
    pytest_cmd = [python, "-m", "pytest"]
    if args.fast:
        pytest_cmd.append("-q")
    else:
        pytest_cmd.append("-v")

    if args.include_live:
        pytest_cmd.extend(["-m", "live", "tests/live/"])
    else:
        pytest_cmd.extend(["-m", "not live"])

    run_command(pytest_cmd, "Backend pytest")

    if not args.skip_eval:
        run_command(
            [python, "scripts/eval.py", "--skip-generation", "--fake-embeddings"],
            "Eval (fake embeddings)",
        )
        if not args.fast:
            run_command(
                [
                    python,
                    "scripts/eval.py",
                    "--skip-generation",
                    "--fake-embeddings",
                    "--report-md",
                    "(folder_example)/eval_report.md",
                ],
                "Eval markdown report",
            )

    if not args.skip_benchmark:
        run_command(
            [
                python,
                "scripts/benchmark_retrieval.py",
                "--fake-embeddings",
                "--from-eval",
                "--repeat",
                "5",
            ],
            "Retrieval benchmark",
        )

    if args.include_live:
        env = os.environ.copy()
        env["RUN_LIVE_TESTS"] = "true"
        print("\n== Live upload harness ==")
        result = subprocess.run(
            [python, "-m", "pytest", "tests/live/", "-m", "live", "-v"],
            cwd=ROOT_DIR,
            env=env,
        )
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    print("\nAll backend validation checks passed.")


if __name__ == "__main__":
    main()
