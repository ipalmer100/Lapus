"""Search and section reads against a real staging database."""

from __future__ import annotations

from lapus.repositories.admin import AdminRepository
from lapus.repositories.specs import SearchQuery, SpecRepository
from lapus.services.specs import SpecService


def test_search_without_a_term_returns_present_documents(database) -> None:
    rows, total = SpecRepository(database).search(SearchQuery())
    assert total > 0
    assert all(row["is_present"] == 1 for row in rows)


def test_missing_documents_are_hidden_unless_asked_for(database) -> None:
    repo = SpecRepository(database)
    _, without = repo.search(SearchQuery())
    _, with_missing = repo.search(SearchQuery(include_missing=True))
    assert with_missing > without, "the demo corpus includes a document whose source vanished"


def test_free_text_matches_customer_and_spec_number(database) -> None:
    repo = SpecRepository(database)
    rows, _ = repo.search(SearchQuery(text="Northwind"))
    assert rows and all("Northwind" in (r["customer"] or "") for r in rows)

    by_spec, _ = repo.search(SearchQuery(text="SP-4100"))
    assert any(r["spec_number"] == "SP-4100" for r in by_spec)


def test_free_text_reaches_material_rows(database) -> None:
    """A material search must find specs through their BOM, in the database."""
    rows, total = SpecRepository(database).search(SearchQuery(text="Vaultex"))
    assert total > 0, "expected the supplier to be found through the bill of materials"


def test_raw_material_filter_searches_both_material_tables(database) -> None:
    repo = SpecRepository(database)
    primary, _ = repo.search(SearchQuery(raw_material="Aluminium Foil"))
    alternates, _ = repo.search(SearchQuery(raw_material="Kestrel"))
    assert primary, "should match the primary bill of materials"
    assert alternates, "should match secondary approved materials"


def test_filters_combine(database) -> None:
    repo = SpecRepository(database)
    rows, _ = repo.search(SearchQuery(customer="Northwind", spec_number="SP-4100"))
    assert len(rows) == 1


def test_search_paginates_stably(database) -> None:
    repo = SpecRepository(database)
    first, total = repo.search(SearchQuery(limit=5, offset=0))
    second, _ = repo.search(SearchQuery(limit=5, offset=5))
    assert len(first) == 5
    ids = {r["document_id"] for r in first} & {r["document_id"] for r in second}
    assert not ids, "pages must not overlap"
    assert total > 5


def test_search_input_is_bound_not_interpolated(database) -> None:
    """A quote in a search term is data, never SQL."""
    rows, total = SpecRepository(database).search(SearchQuery(text="' OR '1'='1"))
    assert total == 0 and rows == []


def test_section_availability_counts_every_section(database, first_document_id) -> None:
    counts = SpecRepository(database).section_availability(first_document_id)
    assert set(counts) == set(range(1, 12))


def test_missing_section_renders_empty_not_error(database) -> None:
    """Legacy documents lack sections; that is a state, not a failure."""
    specs = SpecService(database)
    empties = []
    for document_id in [r["document_id"] for r, in [(row,) for row in
                        SpecRepository(database).search(SearchQuery(limit=20))[0]]]:
        for number in (9, 10):
            section = specs.get_section(document_id, number)
            if section["is_empty"]:
                empties.append(section)
    assert empties, "the demo corpus should include specs missing a section"
    for section in empties:
        assert section["rows"] == [] and section["label"]


def test_revision_history_is_in_document_order(database, first_document_id) -> None:
    rows = SpecService(database).get_section(first_document_id, 11)["rows"]
    source_rows = [r["identity"]["source_row"] for r in rows]
    assert source_rows == sorted(source_rows)


def test_admin_summary_reports_the_corpus(database) -> None:
    summary = AdminRepository(database).staging_summary()
    assert summary["total_documents"] > 0
    assert summary["missing_documents"] >= 1
    assert summary["ingestion_errors"] >= 1
    assert summary["parser_version_breakdown"]


def test_admin_attention_list_includes_unmapped_and_missing(database) -> None:
    rows = AdminRepository(database).documents_needing_attention()
    assert rows
    assert any(r["unmapped_source_tables"] > 0 for r in rows)
    assert any(r["is_present"] == 0 for r in rows)


def test_ingestion_errors_survive_having_no_document(database) -> None:
    """A file that failed to parse has no document row; it must still be listed."""
    errors = AdminRepository(database).ingestion_errors()
    assert errors and errors[0]["filename"]


def test_specs_with_blank_identity_sort_last(database) -> None:
    """Specs the parser could not fully read must not open the application.

    An empty string sorts before every real value ('' < 'Alpha'), so ordering
    by customer alone put the least complete records on page one. Against a
    real corpus that meant the first screen showed nothing but blank customers
    and blank spec numbers, which reads as though no spec has either.
    """
    from lapus.repositories.changes import ChangeRepository  # noqa: F401

    rows, total = SpecRepository(database).search(SearchQuery(limit=200))
    assert total > 0

    customers = [(row["customer"] or "").strip() for row in rows]
    populated = [index for index, value in enumerate(customers) if value]
    blank = [index for index, value in enumerate(customers) if not value]

    if blank and populated:
        assert max(populated) < min(blank), (
            "specs with a blank customer must sort after those with one; "
            f"got {customers}"
        )


def test_blank_specs_are_still_returned(database) -> None:
    """Sorting them last must not drop them -- they are still real documents."""
    repo = SpecRepository(database)
    _, total = repo.search(SearchQuery(limit=200))
    assert total == database.scalar(
        "SELECT COUNT(*) FROM t00_documents WHERE is_present = 1"
    )


def test_section_grid_scope_matches_the_spec_list(database) -> None:
    """What the list shows filtered is exactly what a bulk edit can reach.

    A grid whose scope differed from the list the user was just looking at is
    how a mass edit quietly touches a spec meant to be out of scope.
    """
    from lapus.services.specs import SpecService

    service = SpecService(database)
    for query in (SearchQuery(), SearchQuery(text='Meridian'), SearchQuery(customer='Cascade')):
        listed = {r["document_id"] for r in service.search(query)["results"]}
        grid = {r["document_id"] for r in service.get_section_grid(7, query)["rows"]}
        # Every spec in the grid was in the list; the grid may hold fewer, as
        # it only covers specs that actually have the section.
        assert grid <= listed, f"grid reached beyond the list for {query}"


def test_section_grid_applies_overlays(database) -> None:
    from lapus.services.change_workflow import Actor, ChangeWorkflow
    from lapus.services.specs import SpecService

    service = SpecService(database)
    actor = Actor(email="tester@example.com", is_approver=True, may_self_approve=True)
    workflow = ChangeWorkflow(database)

    document_id = service.get_section_grid(7, SearchQuery(limit=1))["rows"][0]["document_id"]
    request = workflow.create_request(actor, document_id, "Overlay in grid", None)
    request_id = int(request["request_id"])
    workflow.add_item(actor, request_id, 7, None, "core_tags", "Grid overlay", False, None)
    workflow.submit(actor, request_id)
    workflow.approve(actor, request_id, None)

    row = next(
        r for r in service.get_section_grid(7, SearchQuery(limit=200))["rows"]
        if r["document_id"] == document_id
    )
    field = row["fields"]["core_tags"]
    assert field["value"] == "Grid overlay"
    assert field["is_overridden"] is True
    assert field["source_value"] != "Grid overlay", "the staged value must still be shown"


def test_repeating_section_grid_carries_record_ids(database) -> None:
    """BOM rows need their source primary key or a bulk edit cannot target them."""
    from lapus.services.specs import SpecService

    rows = SpecService(database).get_section_grid(3, SearchQuery(limit=10))["rows"]
    assert rows
    assert all(r["record_id"] is not None for r in rows)
