import pytest

pytestmark = pytest.mark.live


def test_live_upload_reliability_harness():
    from scripts.test_upload_live import main

    assert main() == 0
