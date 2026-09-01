"""The eleven specification sections, and the allowlist that guards SQL identifiers.

Two jobs:

1. Describe each section once -- number, business label, source table, layout,
   key, and which fields may be proposed for change -- so the API, the change
   workflow and the frontend all agree without duplicating the mapping.

2. Act as the security boundary for identifiers. Every value Lapus binds into
   SQL travels as a parameter (AGENTS.md rule 10), but a change item names a
   *table* and a *column*, and neither can be bound. Those two are therefore
   checked against this allowlist before any SQL is built, and rejected if they
   are not a known section field. Nothing outside `config/spec_sections.json`
   can reach a query as an identifier.

The definitions load from `config/spec_sections.json` so the section contract
stays editable data rather than something buried in code -- the same file the
starter kit ships and the frontend renders from.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Belt-and-braces on top of the allowlist: even a name that appears in the
# config file has to look like a plain identifier before it is used.
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class UnknownTarget(ValueError):
    """A change item named a table or field Lapus will not touch."""


@dataclass(frozen=True)
class Section:
    number: int
    key: str
    label: str
    table: str
    layout: str
    primary_key: str
    editable_fields: tuple[str, ...]

    @property
    def is_repeating(self) -> bool:
        """True when the section holds many rows per document (BOM, routing...).

        Drives both rendering (table vs form) and change targeting: repeating
        rows are addressed by their source primary key, single-record sections
        by document_id.
        """
        return self.primary_key == "id"

    @property
    def is_editable(self) -> bool:
        return bool(self.editable_fields)


def _config_path() -> Path:
    """Locate spec_sections.json in both a source checkout and a frozen build."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        return Path(frozen_base) / "config" / "spec_sections.json"
    return Path(__file__).resolve().parent.parent.parent / "config" / "spec_sections.json"


@lru_cache(maxsize=1)
def load_sections() -> tuple[Section, ...]:
    raw = json.loads(_config_path().read_text(encoding="utf-8"))
    sections = []
    for entry in raw:
        table = entry["table"]
        if not _SAFE_IDENTIFIER.match(table):
            raise ValueError(f"Unsafe table name in spec_sections.json: {table!r}")
        fields = tuple(entry.get("editable_fields", ()))
        for field in fields:
            if not _SAFE_IDENTIFIER.match(field):
                raise ValueError(f"Unsafe field name in spec_sections.json: {field!r}")
        sections.append(
            Section(
                number=entry["number"],
                key=entry["key"],
                label=entry["label"],
                table=table,
                layout=entry["layout"],
                primary_key=entry["primary_key"],
                editable_fields=fields,
            )
        )
    sections.sort(key=lambda s: s.number)
    return tuple(sections)


@lru_cache(maxsize=1)
def _by_number() -> dict[int, Section]:
    return {s.number: s for s in load_sections()}


@lru_cache(maxsize=1)
def _by_table() -> dict[str, Section]:
    return {s.table: s for s in load_sections()}


def section_by_number(number: int) -> Section:
    try:
        return _by_number()[number]
    except KeyError:
        raise UnknownTarget(f"There is no section {number}. Sections run 1 to 11.") from None


def section_by_table(table: str) -> Section:
    try:
        return _by_table()[table]
    except KeyError:
        raise UnknownTarget(f"'{table}' is not a specification section table.") from None


def validate_target(table: str, field: str) -> Section:
    """Check a proposed change target, returning the section it belongs to.

    The single gate every change item passes through before its table and
    field names are allowed anywhere near a SQL string.
    """
    section = section_by_table(table)
    if not section.is_editable:
        raise UnknownTarget(
            f"{section.label} comes from the source document's own revision history "
            "and cannot be changed in Lapus."
        )
    if field not in section.editable_fields:
        raise UnknownTarget(f"'{field}' is not a changeable field of {section.label}.")
    return section


def readable_columns(section: Section) -> tuple[str, ...]:
    """Columns to select for a section, in a stable, display-friendly order.

    Built from the allowlist plus the section's own keys, so a SELECT can never
    name a column that did not come from the config file.
    """
    columns: list[str] = []
    if section.is_repeating:
        columns += ["id", "document_id", "source_table_index", "source_row"]
        if section.table in {"t03_bill_of_materials", "t04_secondary_approved_materials"}:
            columns.append("row_type")
    else:
        columns.append("document_id")
    columns += [f for f in section.editable_fields if f not in columns]
    if section.table == "t11_revision_history":
        # Revision history has no editable fields, so its content columns are
        # not covered by the allowlist above; they are named here explicitly.
        columns += ["revision_number", "who", "revision_date", "revision"]
    return tuple(dict.fromkeys(columns))
