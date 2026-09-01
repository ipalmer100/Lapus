"""HTTP behaviour: routes, status codes, and what does not leak to the browser."""

from __future__ import annotations

import pytest


def test_health_reports_the_protected_boundary(client) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"]["dialect"] == "sqlite"
    assert body["database"]["staging_is_readonly"] is True
    assert body["database"]["document_count"] > 0


def test_search_returns_a_page_and_a_total(client) -> None:
    body = client.get("/api/specs", params={"limit": 5}).json()
    assert len(body["results"]) <= 5
    assert body["total"] >= len(body["results"])
    assert set(body) == {"results", "total", "limit", "offset", "has_more"}


def test_search_rejects_an_absurd_limit(client) -> None:
    assert client.get("/api/specs", params={"limit": 100_000}).status_code == 422


def test_section_contract_is_served(client) -> None:
    sections = client.get("/api/specs/sections").json()
    assert len(sections) == 11
    assert sections[0]["label"] == "Product Description"


def test_unknown_spec_is_404(client) -> None:
    assert client.get("/api/specs/999999").status_code == 404


def test_unknown_section_number_is_422(client, first_document_id) -> None:
    assert client.get(f"/api/specs/{first_document_id}/sections/99").status_code == 422


def test_every_section_of_every_spec_renders(client) -> None:
    """No spec in the corpus, however incomplete, may fail to render."""
    for spec in client.get("/api/specs", params={"limit": 50, "include_missing": True}).json()["results"]:
        response = client.get(f"/api/specs/{spec['document_id']}/sections")
        assert response.status_code == 200
        assert len(response.json()) == 11


def test_fields_always_carry_provenance(client, first_document_id) -> None:
    """No endpoint returns a bare value for spec content."""
    for section in client.get(f"/api/specs/{first_document_id}/sections").json():
        for row in section["rows"]:
            for field in row["fields"].values():
                assert set(field) == {"value", "source_value", "is_overridden", "provenance"}


def test_full_workflow_over_http(client, first_document_id) -> None:
    bom = client.get(f"/api/specs/{first_document_id}/sections/3").json()
    record_id = bom["rows"][0]["record_id"]

    created = client.post("/api/change-requests", json={
        "document_id": first_document_id, "title": "Requalify supplier", "reason": "Trial",
    })
    assert created.status_code == 201
    request_id = created.json()["request_id"]

    item = client.post(f"/api/change-requests/{request_id}/items", json={
        "section_number": 3, "target_record_id": record_id, "target_field": "supplier",
        "proposed_value": "Kestrel Substrates", "clears_value": False,
        "change_comment": "Qualified",
    })
    assert item.status_code == 201

    assert client.post(f"/api/change-requests/{request_id}/submit").json()["status"] == "SUBMITTED"
    approved = client.post(f"/api/change-requests/{request_id}/approve", json={"comment": "OK"})
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"

    after = client.get(f"/api/specs/{first_document_id}/sections/3").json()
    field = after["rows"][0]["fields"]["supplier"]
    assert field["value"] == "Kestrel Substrates"
    assert field["source_value"] != "Kestrel Substrates"
    assert field["provenance"]["approved_by"]


def test_invalid_transition_is_409(client, first_document_id) -> None:
    created = client.post("/api/change-requests", json={
        "document_id": first_document_id, "title": "Empty", "reason": None,
    }).json()
    response = client.post(f"/api/change-requests/{created['request_id']}/submit")
    assert response.status_code == 409
    assert "at least one change" in response.json()["detail"]


def test_invalid_target_is_422_and_names_the_problem(client, first_document_id) -> None:
    created = client.post("/api/change-requests", json={
        "document_id": first_document_id, "title": "Bad target", "reason": None,
    }).json()
    response = client.post(f"/api/change-requests/{created['request_id']}/items", json={
        "section_number": 3, "target_record_id": 1, "target_field": "supplier; DROP TABLE t01_product_description",
        "proposed_value": "x", "clears_value": False, "change_comment": None,
    })
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "not a changeable field" in detail


@pytest.mark.parametrize("path", [
    "/api/specs/999999", "/api/change-requests/999999",
])
def test_errors_never_leak_internals(client, path: str) -> None:
    """No SQL, file paths or stack traces in an error the browser can see."""
    detail = client.get(path).json()["detail"]
    lowered = detail.lower()
    for leak in ("select ", "sqlite", "traceback", "/home/", "attach", ".db"):
        assert leak not in lowered, f"error text leaked {leak!r}: {detail}"


def test_change_history_is_separate_from_document_revisions(client, first_document_id) -> None:
    history = client.get(f"/api/specs/{first_document_id}/changes").json()
    assert set(history) == {"document_id", "items", "requests"}
    revisions = client.get(f"/api/specs/{first_document_id}/sections/11").json()
    assert revisions["label"] == "Revision History"
    # The two are unrelated records and must not be conflated.
    assert revisions["is_editable"] is False


def test_admin_endpoints_serve_parser_health(client) -> None:
    status = client.get("/api/admin/staging-status").json()
    assert status["summary"]["total_documents"] > 0
    assert "change_request_counts" in status
    exceptions = client.get("/api/admin/exceptions").json()
    assert set(exceptions) == {"worklist", "unmapped_tables", "ingestion_errors"}
