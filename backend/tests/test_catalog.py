"""The allowlist that guards SQL identifiers.

A change item names a table and a column. Neither can travel as a bound
parameter, so this is the only thing standing between a request body and a
SQL identifier -- worth testing directly.
"""

from __future__ import annotations

import pytest

from lapus.catalog import (
    UnknownTarget, load_sections, readable_columns, section_by_number, validate_target,
)


def test_all_eleven_sections_load_in_order() -> None:
    sections = load_sections()
    assert [s.number for s in sections] == list(range(1, 12))
    assert sections[2].label == "Bill of Materials"


def test_repeating_sections_are_keyed_by_row() -> None:
    repeating = {s.table for s in load_sections() if s.is_repeating}
    assert repeating == {
        "t03_bill_of_materials", "t04_secondary_approved_materials",
        "t05_process_routing", "t06_physical_attributes_testing",
        "t11_revision_history",
    }


def test_known_target_validates() -> None:
    assert validate_target("t03_bill_of_materials", "supplier").number == 3


@pytest.mark.parametrize("table", [
    "sqlite_master",
    "t00_documents",
    "lapus.change_request",
    "t03_bill_of_materials; DROP TABLE t01_product_description",
    "T03_Bill_of_Materials",
    "",
])
def test_unknown_tables_are_refused(table: str) -> None:
    with pytest.raises(UnknownTarget):
        validate_target(table, "supplier")


@pytest.mark.parametrize("field", [
    "id",
    "document_id",
    "supplier; DROP TABLE t01_product_description",
    "supplier OR 1=1",
    "rowid",
    "",
])
def test_unknown_fields_are_refused(field: str) -> None:
    """Note that `id` and `document_id` are refused too: they identify a row,
    and proposing a change to one would break targeting rather than edit data."""
    with pytest.raises(UnknownTarget):
        validate_target("t03_bill_of_materials", field)


def test_revision_history_is_read_only() -> None:
    with pytest.raises(UnknownTarget, match="revision history"):
        validate_target("t11_revision_history", "revision")


def test_readable_columns_come_only_from_the_contract() -> None:
    """Nothing outside the section definition can reach a SELECT."""
    for section in load_sections():
        allowed = set(section.editable_fields) | {
            "id", "document_id", "source_table_index", "source_row", "row_type",
            "revision_number", "who", "revision_date", "revision",
        }
        assert set(readable_columns(section)) <= allowed


def test_section_lookup_rejects_out_of_range() -> None:
    for number in (0, 12, -1):
        with pytest.raises(UnknownTarget):
            section_by_number(number)
