import time

from fastapi.testclient import TestClient

from tests.conftest import make_csv
from tests.fake_directory import FakeDirectory


def test_creates_and_activates_all_hospitals(upload, directory: FakeDirectory) -> None:
    response = upload(make_csv(5))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["total_hospitals"] == 5
    assert body["processed_hospitals"] == 5
    assert body["failed_hospitals"] == 0
    assert body["batch_activated"] is True
    assert {h["status"] for h in body["hospitals"]} == {"created_and_activated"}
    assert [h["row"] for h in body["hospitals"]] == [1, 2, 3, 4, 5]
    assert directory.activated_batches == [body["batch_id"]]
    assert all(h["creation_batch_id"] == body["batch_id"] and h["active"] for h in directory.hospitals.values())


def test_does_not_activate_when_a_row_fails(upload, directory: FakeDirectory) -> None:
    directory.failing_names = {"Hospital 2"}

    body = upload(make_csv(3)).json()

    assert body["status"] == "failed"
    assert body["batch_activated"] is False
    assert body["processed_hospitals"] == 2
    assert body["failed_hospitals"] == 1
    assert body["hospitals"][1]["status"] == "failed"
    assert "422" in body["hospitals"][1]["error"]
    assert directory.activated_batches == []
    assert directory.create_attempts["Hospital 2"] == 1


def test_retries_transient_upstream_errors(upload, directory: FakeDirectory) -> None:
    directory.transient_failures = {"Hospital 1": 2}

    body = upload(make_csv(2)).json()

    assert body["batch_activated"] is True
    assert directory.create_attempts["Hospital 1"] == 3


def test_gives_up_after_max_retries(upload, directory: FakeDirectory) -> None:
    directory.transient_failures = {"Hospital 1": 10}

    body = upload(make_csv(1)).json()

    assert body["failed_hospitals"] == 1
    assert directory.create_attempts["Hospital 1"] == 3


def test_resume_retries_only_failed_rows_then_activates(upload, client: TestClient, directory: FakeDirectory) -> None:
    directory.failing_names = {"Hospital 2"}
    batch_id = upload(make_csv(3)).json()["batch_id"]

    directory.failing_names = set()
    body = client.post(f"/hospitals/bulk/{batch_id}/resume").json()

    assert body["status"] == "completed"
    assert body["batch_activated"] is True
    assert body["processed_hospitals"] == 3
    assert directory.create_attempts == {"Hospital 1": 1, "Hospital 2": 2, "Hospital 3": 1}
    assert len(directory.hospitals) == 3


def test_resume_after_activation_failure_does_not_recreate(
    upload, client: TestClient, directory: FakeDirectory
) -> None:
    directory.activation_failures = 10
    first = upload(make_csv(2)).json()

    assert first["batch_activated"] is False
    assert "activation failed" in first["error"]
    assert {h["status"] for h in first["hospitals"]} == {"created"}

    directory.activation_failures = 0
    body = client.post(f"/hospitals/bulk/{first['batch_id']}/resume").json()

    assert body["batch_activated"] is True
    assert len(directory.hospitals) == 2


def test_resume_unknown_batch_returns_404(client: TestClient) -> None:
    assert client.post("/hospitals/bulk/missing/resume").status_code == 404


def test_invalid_csv_is_rejected_before_any_upstream_call(upload, directory: FakeDirectory) -> None:
    response = upload(b"name,address\n,1 Main St\n")

    assert response.status_code == 400
    assert response.json()["errors"] == [{"row": 1, "message": "'name' is required"}]
    assert not directory.create_attempts


def test_rejects_more_than_20_rows(upload, directory: FakeDirectory) -> None:
    response = upload(make_csv(21))

    assert response.status_code == 400
    assert not directory.create_attempts


def test_rejects_non_csv_file(upload) -> None:
    assert upload(make_csv(1), filename="hospitals.txt").status_code == 400


def test_get_batch_status(upload, client: TestClient) -> None:
    batch_id = upload(make_csv(2)).json()["batch_id"]

    body = client.get(f"/hospitals/bulk/{batch_id}").json()

    assert body["batch_id"] == batch_id
    assert body["status"] == "completed"
    assert client.get("/hospitals/bulk/unknown").status_code == 404


def test_background_mode_can_be_polled(upload, client: TestClient) -> None:
    response = upload(make_csv(4), background=True)

    assert response.status_code == 202
    batch_id = response.json()["batch_id"]

    deadline = time.monotonic() + 5
    body = client.get(f"/hospitals/bulk/{batch_id}").json()
    while body["status"] == "processing" and time.monotonic() < deadline:
        time.sleep(0.02)
        body = client.get(f"/hospitals/bulk/{batch_id}").json()

    assert body["status"] == "completed"
    assert body["batch_activated"] is True


def test_validate_endpoint(upload, directory: FakeDirectory) -> None:
    valid = upload(make_csv(2), path="/hospitals/bulk/validate").json()
    invalid = upload(b"name,address\nGeneral,\n", path="/hospitals/bulk/validate").json()

    assert valid == {"valid": True, "total_rows": 2, "errors": []}
    assert invalid["valid"] is False
    assert invalid["errors"] == [{"row": 1, "message": "'address' is required"}]
    assert not directory.create_attempts


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
