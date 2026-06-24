import os
import subprocess
import sys
from pathlib import Path


def test_live_tests_skipped_by_default():
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("RUN_LIVE_TESTS", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/live/test_upload_live_harness.py",
            "-q",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "skipped" in result.stdout.lower()
