from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient


@contextmanager
def test_client_for_router(
    router,
    *,
    overrides: dict | None = None,
) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    if overrides:
        app.dependency_overrides.update(overrides)

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
