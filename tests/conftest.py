from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fake_directory import FakeDirectory


@pytest.fixture
def directory() -> FakeDirectory:
    return FakeDirectory()


@pytest.fixture
def client(directory: FakeDirectory) -> Iterator[TestClient]:
    settings = Settings(directory_api_url="http://directory.test", retry_backoff_seconds=0, max_retries=2)
    with TestClient(create_app(settings, transport=directory.transport)) as test_client:
        yield test_client


def make_csv(rows: int, header: str = "name,address,phone") -> bytes:
    lines = [header] + [f"Hospital {i},{i} Main St,555-000{i}" for i in range(1, rows + 1)]
    return "\n".join(lines).encode()


@pytest.fixture
def upload(client: TestClient) -> Callable[..., object]:
    def _upload(content: bytes, path: str = "/hospitals/bulk", filename: str = "hospitals.csv", **params: object):
        return client.post(path, files={"file": (filename, content, "text/csv")}, params=params)

    return _upload
