"""Values chosen to break things, round-tripped through the whole workflow.

Specification text is not sanitised prose. It comes out of Word cells written
over twenty years and contains quotes, newlines, tabs, em-dashes, bilingual
text and the occasional control character. A change proposed against one of
those must come back byte-identical, and a search for one must not fail.

These are regression tests for a class of bug rather than a specific one: SQL
built by string concatenation, a value mangled by over-eager trimming, a
LIKE pattern taken as a placeholder.
"""

from __future__ import annotations

import pytest

from lapus.repositories.specs import SearchQuery, SpecRepository
from lapus.services.change_workflow import ChangeWorkflow
from lapus.services.specs import SpecService

HOSTILE = [
    pytest.param("'; DROP TABLE t01_product_description; --", id="sql-drop"),
    pytest.param("' OR '1'='1", id="sql-tautology"),
    pytest.param("%", id="bare-percent"),
    pytest.param("_", id="like-wildcard"),
    pytest.param("100%% recycled", id="double-percent"),
    pytest.param("back\\slash", id="backslash"),
    pytest.param('double "quoted"', id="double-quote"),
    pytest.param("line one\nline two", id="newline"),
    pytest.param("\ttabbed", id="tab"),
    pytest.param("Ünïcödé — 中文 — 🧪", id="unicode"),
    pytest.param("A" * 5000, id="very-long"),
    pytest.param("<script>alert(1)</script>", id="html"),
    pytest.param("${jndi:ldap://x}", id="template-injection"),
]


@pytest.mark.parametrize("value", HOSTILE)
def test_hostile_search_terms_do_not_break_search(database, value: str) -> None:
    """A '%' in a search term is data. On PostgreSQL it is also a placeholder
    marker to psycopg, which is how this class of bug bites."""
    repo = SpecRepository(database)
    for query in (
        SearchQuery(text=value),
        SearchQuery(customer=value),
        SearchQuery(raw_material=value),
        SearchQuery(spec_number=value),
    ):
        rows, total = repo.search(query)
        assert isinstance(total, int) and total >= 0
        assert isinstance(rows, list)


@pytest.mark.parametrize("value", HOSTILE)
def test_hostile_values_round_trip_byte_identical(
    database, actor, first_document_id, value: str
) -> None:
    """What was proposed is what the overlay shows -- exactly."""
    specs, workflow = SpecService(database), ChangeWorkflow(database)
    record_id = specs.get_section(first_document_id, 3)["rows"][0]["record_id"]

    request = workflow.create_request(actor, first_document_id, "Hostile", None)
    request_id = int(request["request_id"])
    item = workflow.add_item(actor, request_id, 3, record_id, "supplier", value, False, None)
    assert item["proposed_value"] == value, "the stored value was altered"

    workflow.submit(actor, request_id)
    workflow.approve(actor, request_id, None)

    field = specs.get_section(first_document_id, 3)["rows"][0]["fields"]["supplier"]
    assert field["value"] == value, "the overlay altered the value"


def test_null_byte_is_preserved_or_cleanly_refused(database, actor, first_document_id) -> None:
    """A NUL in a value must not silently truncate the rest of it."""
    specs, workflow = SpecService(database), ChangeWorkflow(database)
    record_id = specs.get_section(first_document_id, 3)["rows"][0]["record_id"]
    value = "before\x00after"

    request = workflow.create_request(actor, first_document_id, "Null byte", None)
    request_id = int(request["request_id"])
    try:
        item = workflow.add_item(actor, request_id, 3, record_id, "supplier", value, False, None)
    except Exception:
        return  # refusing outright is an acceptable answer
    assert item["proposed_value"] == value, "the value was truncated at the NUL"


def test_whitespace_only_value_is_not_silently_the_same_as_empty(
    database, actor, first_document_id
) -> None:
    """Proposing '   ' is a real proposal; it must not be confused with a clear."""
    specs, workflow = SpecService(database), ChangeWorkflow(database)
    record_id = specs.get_section(first_document_id, 3)["rows"][0]["record_id"]

    request = workflow.create_request(actor, first_document_id, "Spaces", None)
    request_id = int(request["request_id"])
    item = workflow.add_item(actor, request_id, 3, record_id, "supplier", "   ", False, None)
    assert item["proposed_value"] == "   "
    assert item["clears_value"] == 0, "a whitespace value must not be recorded as a clear"
