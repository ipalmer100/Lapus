from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import getpass
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - friendly runtime message in main()
    psycopg = None
    sql = None
    dict_row = None

from docx import Document
from docx.document import Document as _Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

# =============================================================================
# Configuration
# =============================================================================
PARSER_VERSION = "5.2-postgres-corpus"
DEFAULT_DATABASE_NAME = "Spec_Stage"
DEFAULT_SPECS_DIRNAME = "Specs"
DEFAULT_EXCLUDE_DIRS = {"_Corpus_Profile", "__pycache__"}

# The eleven specification tables, in Word/document order.
SECTION_NAMES = {
    "locations": "T02_Locations",
    "location": "T02_Locations",
    "bill of materials": "T03_Bill_of_Materials",
    "bill of material": "T03_Bill_of_Materials",
    "bom": "T03_Bill_of_Materials",
    "secondary approved materials": "T04_Secondary_Approved_Materials",
    "secondary approved material": "T04_Secondary_Approved_Materials",
    "approved secondary materials": "T04_Secondary_Approved_Materials",
    "alternate approved materials": "T04_Secondary_Approved_Materials",
    "alternative approved materials": "T04_Secondary_Approved_Materials",
    "process routing": "T05_Process_Routing",
    "routing": "T05_Process_Routing",
    "process route": "T05_Process_Routing",
    "physical attributes & testing": "T06_Physical_Attributes_Testing",
    "physical attributes and testing": "T06_Physical_Attributes_Testing",
    "physical attributes/testing": "T06_Physical_Attributes_Testing",
    "physical attributes": "T06_Physical_Attributes_Testing",
    "slitting information": "T07_Slitting_Information",
    "slit information": "T07_Slitting_Information",
    "slitting": "T07_Slitting_Information",
    "packing information": "T08_Packing_Information",
    "packaging information": "T08_Packing_Information",
    "packing": "T08_Packing_Information",
    "packaging": "T08_Packing_Information",
    "reporting requirements": "T09_Reporting_Requirements",
    "reporting requirement": "T09_Reporting_Requirements",
    "customer sampling requirements": "T10_Customer_Sampling_Requirements",
    "customer sample requirements": "T10_Customer_Sampling_Requirements",
    "sampling requirements": "T10_Customer_Sampling_Requirements",
    "revision history": "T11_Revision_History",
    "revision histories": "T11_Revision_History",
    "revision log": "T11_Revision_History",
}

# High-frequency supplemental/legacy headings observed in the corpus profile.
# They are intentionally NOT forced into T01-T11; their tables are preserved in T00.
KNOWN_SUPPLEMENTAL_HEADINGS = {
    "extruder distribution",
    "quality issues",
    "mcguires",
    "general information",
    "finish good information",
    "finish goods information",
    "finish good information information",
    "fg section",
    "materials",
}

# Labels are intentionally generic. They are used for schema detection only; values
# are extracted from the source Word document at ingestion time.
FIELD_ALIASES = {
    "product": {
        "customer": ["customer"],
        "spec_number": ["spec #", "spec number", "specification #", "specification number"],
        "item": ["item", "finished good", "finished good item"],
        "date_of_issue": ["date of issue", "issue date"],
        "structure_description": ["structure description", "structure"],
        "revision_number": ["revision #", "revision number", "revision"],
        "structure_code": ["structure code"],
    },
    "locations": {
        "customer_location": ["customer location", "location"],
        "facility": ["facility", "plant"],
        "spec_originator": ["spec originator", "specification originator", "originator"],
        "phone_number": ["phone number", "phone", "telephone"],
    },
    "material": {
        "basis_weight": ["basis wt", "basis weight"],
        "basis_weight_range": ["basis wt range", "basis weight range", "weight range"],
        "caliper_mils": ["caliper (mils)", "caliper", "caliper mils"],
        "raw_material": ["raw material", "material"],
        "supplier": ["raw material supplier", "supplier"],
        "raw_material_item_code": ["raw material item code", "material item code", "item code", "item"],
    },
    "routing": {
        "pass": ["pass"],
        "process": ["process"],
        "machine": ["machine"],
        "process_conditions": ["process conditions", "conditions"],
        "comments": ["comments", "comment"],
    },
    "testing": {
        "attribute": ["attribute"],
        "coa": ["coa"],
        "units": ["units", "unit"],
        "lsl": ["lsl"],
        "lcl": ["lcl"],
        "target": ["target"],
        "ucl": ["ucl"],
        "usl": ["usl"],
        "procedure": ["procedure", "test procedure"],
        "frequency": ["frequency", "test frequency"],
        "notes": ["comments", "comment", "notes", "note"],
    },
    "slitting": {
        "slit_width": ["slit width"],
        "core_id": ["core id"],
        "splice_tape": ["splice tape"],
        "width_tolerance": ["width tolerance"],
        "core_type": ["core type"],
        "splice_type": ["splice type"],
        "cutoff": ["cutoff", "cut off"],
        "lineal_ft_per_roll": ["lineal ft / roll", "lineal ft per roll", "lineal feet / roll", "lineal feet per roll"],
        "splice_location": ["splice location"],
        "eyemark_location": ["eyemark location", "eye mark location"],
        "maximum_od": ["maximum od", "max od"],
        "splice_stamp_flag": ["splice stamp/flag", "splice stamp flag"],
        "number_of_cuts": ["number of cuts", "# cuts"],
        "maximum_weight": ["maximum weight", "max weight"],
        "maximum_splices": ["maximum # splices", "maximum splices", "max # splices", "max splices"],
        "unwind": ["unwind"],
        "labels_across": ["# labels across", "labels across"],
        "core_tags": ["core tags"],
        "splice_code": ["splice code"],
        "splicing": ["splicing"],
        "end_of_roll_indicator": ["end of roll indicator"],
        "comments": ["comments", "comment"],
    },
    "packing": {
        "pallet_size": ["pallet size"],
        "poly_bags": ["poly bags", "poly bag"],
        "pallet_labels": ["pallet labels", "pallet label"],
        "pallet_type": ["pallet type"],
        "core_plugs": ["core plugs", "core plug"],
        "protective_corners": ["protective corners", "protective corner"],
        "rolls_per_layer": ["rolls / layer", "rolls per layer"],
        "roll_cradles": ["roll cradles", "roll cradle"],
        "stretch_wrap_pallet": ["stretch wrap pallet", "stretch wrapped pallet"],
        "layers_per_pallet": ["layers / pallet", "layers per pallet"],
        "tier_dividers": ["tier dividers", "tier divider"],
        "band_pallet": ["band pallet", "banded pallet"],
        "rolls_per_pallet": ["rolls / pallet", "rolls per pallet"],
        "top_layer": ["top layer"],
        "wooden_top": ["wooden top"],
        "feet_per_pallet": ["feet/pallet", "feet / pallet", "feet per pallet"],
        "end_boards": ["end boards", "end board"],
        "packing_instructions": ["packing instructions", "packaging instructions"],
        "additional_instructions": ["additional instructions", "special instructions"],
    },
    "reporting": {
        "coa_required": ["coa required?", "coa required"],
        "coa_recipients": ["coa recipient(s)", "coa recipients", "coa recipient"],
        "coa_format": ["coa format"],
        "coa_frequency": ["coa frequency"],
        "values_to_report_on_coa": ["values to report on coa", "coa values"],
    },
    "sampling": {
        "samples_required": ["samples required?", "samples required"],
        "send_to": ["send to"],
        "number_of_samples": ["number of samples", "# samples"],
        "sample_preparation_labeling": ["sample preparation/ labeling", "sample preparation / labeling", "sample preparation", "labeling"],
    },
    "revision": {
        "revision_number": ["revision #", "revision number", "rev #"],
        "who": ["who", "author", "revised by"],
        "revision_date": ["date", "revision date"],
        "revision": ["revision", "revision description", "description", "change"],
    },
}


TABLE_DIRECTORY = [
    ("T00_Documents", 0, "control", "", "One row per source Word document; parent key for all extracted tables.", 0),
    ("T00_Table_Directory", 0, "control", "", "Directory of staging tables and their Word-document order.", 1),
    ("T00_Ingestion_Audit", 0, "control", "", "Audit trail for every body table encountered during ingestion.", 2),
    ("T00_Unmapped_Tables", 0, "control", "", "Lossless JSON capture of Word tables that could not be mapped.", 3),
    ("T00_Ingestion_Errors", 0, "control", "", "File-level errors encountered during staging.", 4),
    ("T01_Product_Description", 1, "specification", "Product Description", "Header-level customer, item, specification, revision, and structure data.", 10),
    ("T02_Locations", 2, "specification", "Locations", "Customer location, facility, spec originator, and phone number.", 20),
    ("T03_Bill_of_Materials", 3, "specification", "Bill of Materials", "Primary raw materials, basis weight, caliper, supplier, and item code.", 30),
    ("T04_Secondary_Approved_Materials", 4, "specification", "Secondary Approved Materials", "Alternate approved raw materials and suppliers.", 40),
    ("T05_Process_Routing", 5, "specification", "Process Routing", "Manufacturing passes, process instructions, machines, conditions, and comments.", 50),
    ("T06_Physical_Attributes_Testing", 6, "specification", "Physical Attributes & Testing", "Quality attributes, limits, targets, procedures, and frequencies.", 60),
    ("T07_Slitting_Information", 7, "specification", "Slitting Information", "Slit dimensions, roll/core/splice details, unwind, labels, and comments.", 70),
    ("T08_Packing_Information", 8, "specification", "Packing Information", "Pallet configuration, wrapping, dividers, roll counts, and packing instructions.", 80),
    ("T09_Reporting_Requirements", 9, "specification", "Reporting Requirements", "COA requirements, recipients, format, frequency, and reported values.", 90),
    ("T10_Customer_Sampling_Requirements", 10, "specification", "Customer Sampling Requirements", "Customer sample requirements and preparation/labeling instructions.", 100),
    ("T11_Revision_History", 11, "specification", "Revision History", "Specification revision number, author, date, and revision notes.", 110),
]

SPEC_TABLES = [f"T{i:02d}_{name}" for i, name in [
    (1, "Product_Description"),
    (2, "Locations"),
    (3, "Bill_of_Materials"),
    (4, "Secondary_Approved_Materials"),
    (5, "Process_Routing"),
    (6, "Physical_Attributes_Testing"),
    (7, "Slitting_Information"),
    (8, "Packing_Information"),
    (9, "Reporting_Requirements"),
    (10, "Customer_Sampling_Requirements"),
    (11, "Revision_History"),
]]

# =============================================================================
# Windows path discovery
# =============================================================================
def find_windows_desktop() -> Path:
    """Return the current user's Windows Desktop, including redirected desktops."""
    if os.name == "nt":
        try:
            import ctypes

            CSIDL_DESKTOPDIRECTORY = 0x0010
            SHGFP_TYPE_CURRENT = 0
            buffer = ctypes.create_unicode_buffer(32768)
            result = ctypes.windll.shell32.SHGetFolderPathW(
                None,
                CSIDL_DESKTOPDIRECTORY,
                None,
                SHGFP_TYPE_CURRENT,
                buffer,
            )
            if result == 0 and buffer.value:
                return Path(buffer.value)
        except Exception:
            pass

    candidates: list[Path] = []
    userprofile = os.environ.get("USERPROFILE")
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveCommercial")
    if userprofile:
        candidates.append(Path(userprofile) / "Desktop")
    if onedrive:
        candidates.append(Path(onedrive) / "Desktop")
    candidates.append(Path.home() / "Desktop")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else Path.home() / "Desktop"


def default_specs_root() -> Path:
    return find_windows_desktop() / DEFAULT_SPECS_DIRNAME


# =============================================================================
# General helpers
# =============================================================================
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: str | None) -> str:
    """Preserve Word line breaks, but remove trailing spaces and blank edges."""
    if value is None:
        return ""
    lines = [line.rstrip() for line in value.replace("\r", "").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def norm(value: str | None) -> str:
    """Normalization used only for matching headings/labels."""
    return re.sub(r"\s+", " ", clean(value)).strip().lower()


def norm_match(value: str | None) -> str:
    """More aggressive normalization for corpus-aware heading/label matching."""
    text = norm(value)
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    text = text.replace(" and ", " & ")
    text = re.sub(r"[^a-z0-9#&]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_heading_paragraph(p: Paragraph) -> bool:
    style_name = (p.style.name or "") if p.style is not None else ""
    return bool(re.match(r"^heading\s*\d*", style_name.strip(), flags=re.I))


def section_from_heading(value: str | None) -> str | None:
    """Map observed heading variants to T02-T11 without over-mapping supplemental headings."""
    raw = norm(value)
    if not raw:
        return None

    if raw in SECTION_NAMES:
        return SECTION_NAMES[raw]

    n = norm_match(raw)
    # Exact normalized aliases first.
    for alias, table_name in SECTION_NAMES.items():
        if n == norm_match(alias):
            return table_name

    # Corpus-observed punctuation, bilingual, and prefixed/suffixed heading variants.
    canonical = [
        ("secondary approved materials", "T04_Secondary_Approved_Materials"),
        ("physical attributes & testing", "T06_Physical_Attributes_Testing"),
        ("customer sampling requirements", "T10_Customer_Sampling_Requirements"),
        ("reporting requirements", "T09_Reporting_Requirements"),
        ("revision history", "T11_Revision_History"),
        ("bill of materials", "T03_Bill_of_Materials"),
        ("process routing", "T05_Process_Routing"),
        ("slitting information", "T07_Slitting_Information"),
        ("packing information", "T08_Packing_Information"),
        ("locations", "T02_Locations"),
    ]
    for phrase, table_name in canonical:
        p = norm_match(phrase)
        if n.startswith(p + " ") or n.endswith(" " + p) or n == p:
            return table_name

    # Short corrupted prefixes observed in the corpus (eLocations, kLocations, 9Revision History).
    if len(n) <= 28 and n.endswith("locations"):
        return "T02_Locations"
    if len(n) <= 36 and n.endswith("revision history"):
        return "T11_Revision_History"
    if len(n) <= 36 and n.endswith("process routing"):
        return "T05_Process_Routing"

    # Explicit legacy/bilingual structures observed by the profiler.
    if "slitting" in n and "information" in n:
        return "T07_Slitting_Information"
    if "packing information" in n:
        return "T08_Packing_Information"
    if n.startswith("secondary approved materials"):
        return "T04_Secondary_Approved_Materials"
    if n.startswith("process routing"):
        return "T05_Process_Routing"

    # Conservative typo recovery (e.g. "Physical Attribues & Testing").
    candidates = {
        norm_match(alias): table_name
        for alias, table_name in SECTION_NAMES.items()
        if len(norm_match(alias)) >= 8
    }
    best = difflib.get_close_matches(n, candidates.keys(), n=1, cutoff=0.88)
    if best:
        return candidates[best[0]]
    return None


def is_known_supplemental_heading(value: str | None) -> bool:
    n = norm_match(value)
    return any(n == norm_match(x) for x in KNOWN_SUPPLEMENTAL_HEADINGS)


def _label_words(alias: str) -> list[str]:
    return re.findall(r"[a-z0-9#]+", alias.lower())


def label_match_score(value: str, alias: str) -> int:
    """0=no match, 2=label-only/exact, 1=label followed by an inline value."""
    n = norm_match(value)
    a = norm_match(alias)
    if not n or not a:
        return 0
    if n == a:
        return 2
    if n.startswith(a + " "):
        return 1
    return 0


def inline_value_after_label(value: str, alias: str) -> str:
    """Return text after an inline label such as 'Customer: ABC'."""
    raw = clean(value)
    words = _label_words(alias)
    if not raw or not words:
        return ""
    sep = r"[\s\W_]*"
    pattern = r"^\s*" + sep.join(re.escape(w) for w in words) + r"[\s\W_]*[:?]?\s*(.*)$"
    m = re.match(pattern, raw, flags=re.I)
    if not m:
        return ""
    remainder = clean(m.group(1))
    if norm_match(remainder) == norm_match(alias):
        return ""
    return remainder


def next_distinct_cell(cells: list[str], index: int, label_value: str) -> str:
    label_n = norm_match(label_value)
    for candidate in cells[index + 1 :]:
        if clean(candidate) and norm_match(candidate) != label_n:
            return clean(candidate)
    return ""


def extract_labeled_fields(table: Table, alias_map: dict[str, list[str]]) -> dict[str, str]:
    """Extract values from either label/value cells or inline 'Label: value' cells."""
    out = {field: "" for field in alias_map}
    alias_items = sorted(
        ((field, alias) for field, aliases in alias_map.items() for alias in aliases),
        key=lambda x: len(norm_match(x[1])),
        reverse=True,
    )
    for row in table.rows:
        cells = row_values(row)
        for i, cell in enumerate(cells):
            if not clean(cell):
                continue
            for field, alias in alias_items:
                if out[field]:
                    continue
                score = label_match_score(cell, alias)
                if not score:
                    continue
                inline = inline_value_after_label(cell, alias) if score == 1 else ""
                value = inline or next_distinct_cell(cells, i, cell)
                if value:
                    out[field] = value
                    break
    return out


def recognized_fields(table: Table, alias_map: dict[str, list[str]]) -> set[str]:
    found: set[str] = set()
    alias_items = sorted(
        ((field, alias) for field, aliases in alias_map.items() for alias in aliases),
        key=lambda x: len(norm_match(x[1])),
        reverse=True,
    )
    for row in table.rows:
        for cell in row_values(row):
            for field, alias in alias_items:
                if label_match_score(cell, alias):
                    found.add(field)
                    break
    return found


def collapse_adjacent_duplicates(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if out and norm_match(out[-1]) == norm_match(value) and clean(value):
            continue
        out.append(value)
    return out


def column_map_from_header(
    table: Table,
    alias_map: dict[str, list[str]],
    search_rows: int = 3,
) -> tuple[int, dict[str, int]]:
    """Find the most label-rich header row and map logical fields to source columns."""
    best_row = 0
    best_map: dict[str, int] = {}
    alias_items = sorted(
        ((field, alias) for field, aliases in alias_map.items() for alias in aliases),
        key=lambda x: len(norm_match(x[1])),
        reverse=True,
    )
    for row_idx, row in enumerate(table.rows[:search_rows]):
        mapping: dict[str, int] = {}
        rank_by_field: dict[str, tuple[int, int]] = {}
        for col_idx, cell in enumerate(row_values(row)):
            for field, alias in alias_items:
                score = label_match_score(cell, alias)
                if score <= 0:
                    continue
                rank = (score, len(norm_match(alias)))
                if field not in rank_by_field or rank > rank_by_field[field]:
                    mapping[field] = col_idx
                    rank_by_field[field] = rank
        if len(mapping) > len(best_map):
            best_row, best_map = row_idx, mapping
    return best_row, best_map


def value_at(cells: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(cells):
        return ""
    return clean(cells[index])


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def row_values(row) -> list[str]:
    return [clean(cell.text) for cell in row.cells]


def table_json(table: Table) -> str:
    return json.dumps([row_values(r) for r in table.rows], ensure_ascii=False)


def iter_block_items(parent: _Document):
    """Yield paragraphs and tables in the same order they appear in Word."""
    parent_elm = parent.element.body
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def first_unique_after_label(cells: list[str], label: str) -> str:
    target = norm(label)
    for i, cell in enumerate(cells):
        if norm(cell) == target:
            for candidate in cells[i + 1 :]:
                if clean(candidate) and norm(candidate) != target:
                    return clean(candidate)
    return ""


def header_signature(table: Table) -> str:
    if not table.rows:
        return ""
    return " | ".join(norm(v) for v in row_values(table.rows[0]))


def rel_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def list_docx_files(root: Path, exclude_dirs: set[str]) -> list[Path]:
    """Recursively find Word specs while excluding control/output folders."""
    files: list[Path] = []
    root = root.resolve()
    for current, dirs, names in os.walk(root):
        # Prune excluded directories before os.walk descends into them.
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]
        current_path = Path(current)
        for name in names:
            if name.startswith("~$"):
                continue
            if not name.lower().endswith(".docx"):
                continue
            files.append(current_path / name)
    files.sort(key=lambda p: rel_path(p, root).lower())
    return files


# =============================================================================
# PostgreSQL schema / connection helpers
# =============================================================================
# PostgreSQL folds unquoted identifiers to lowercase. The logical names remain
# T00_... through T11_..., while tools such as Retool/pgAdmin will normally show
# them as t00_... through t11_.... This avoids quoted, case-sensitive identifiers.
POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS T00_Documents (
    id BIGSERIAL PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    source_directory TEXT,
    source_file_size BIGINT,
    source_modified_ns BIGINT,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_present INTEGER NOT NULL DEFAULT 1,
    parser_version TEXT NOT NULL,
    paragraph_content TEXT
);

CREATE TABLE IF NOT EXISTS T00_Table_Directory (
    sqlite_table_name TEXT PRIMARY KEY,
    table_number INTEGER NOT NULL,
    table_role TEXT NOT NULL,
    word_section TEXT,
    description TEXT,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS T01_Product_Description (
    document_id BIGINT PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    customer TEXT,
    spec_number TEXT,
    item TEXT,
    date_of_issue TEXT,
    structure_description TEXT,
    revision_number TEXT,
    structure_code TEXT
);

CREATE TABLE IF NOT EXISTS T02_Locations (
    document_id BIGINT PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    customer_location TEXT,
    facility TEXT,
    spec_originator TEXT,
    phone_number TEXT
);

CREATE TABLE IF NOT EXISTS T03_Bill_of_Materials (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    row_type TEXT NOT NULL,
    basis_weight TEXT,
    basis_weight_range TEXT,
    caliper_mils TEXT,
    raw_material TEXT,
    supplier TEXT,
    raw_material_item_code TEXT
);

CREATE TABLE IF NOT EXISTS T04_Secondary_Approved_Materials (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    row_type TEXT NOT NULL,
    basis_weight TEXT,
    basis_weight_range TEXT,
    caliper_mils TEXT,
    raw_material TEXT,
    supplier TEXT,
    raw_material_item_code TEXT
);

CREATE TABLE IF NOT EXISTS T05_Process_Routing (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    pass TEXT,
    process TEXT,
    machine TEXT,
    process_conditions TEXT,
    comments TEXT
);

CREATE TABLE IF NOT EXISTS T06_Physical_Attributes_Testing (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    pass_name TEXT,
    attribute TEXT,
    coa TEXT,
    units TEXT,
    lsl TEXT,
    lcl TEXT,
    target TEXT,
    ucl TEXT,
    usl TEXT,
    procedure TEXT,
    frequency TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS T07_Slitting_Information (
    document_id BIGINT PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    slit_width TEXT,
    core_id TEXT,
    splice_tape TEXT,
    width_tolerance TEXT,
    core_type TEXT,
    splice_type TEXT,
    cutoff TEXT,
    lineal_ft_per_roll TEXT,
    splice_location TEXT,
    eyemark_location TEXT,
    maximum_od TEXT,
    splice_stamp_flag TEXT,
    number_of_cuts TEXT,
    maximum_weight TEXT,
    maximum_splices TEXT,
    unwind TEXT,
    labels_across TEXT,
    core_tags TEXT,
    splice_code TEXT,
    splicing TEXT,
    end_of_roll_indicator TEXT,
    comments TEXT
);

CREATE TABLE IF NOT EXISTS T08_Packing_Information (
    document_id BIGINT PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    pallet_size TEXT,
    poly_bags TEXT,
    pallet_labels TEXT,
    pallet_type TEXT,
    core_plugs TEXT,
    protective_corners TEXT,
    rolls_per_layer TEXT,
    roll_cradles TEXT,
    stretch_wrap_pallet TEXT,
    layers_per_pallet TEXT,
    tier_dividers TEXT,
    band_pallet TEXT,
    rolls_per_pallet TEXT,
    top_layer TEXT,
    wooden_top TEXT,
    feet_per_pallet TEXT,
    end_boards TEXT,
    packing_instructions TEXT,
    additional_instructions TEXT
);

CREATE TABLE IF NOT EXISTS T09_Reporting_Requirements (
    document_id BIGINT PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    coa_required TEXT,
    coa_recipients TEXT,
    coa_format TEXT,
    coa_frequency TEXT,
    values_to_report_on_coa TEXT
);

CREATE TABLE IF NOT EXISTS T10_Customer_Sampling_Requirements (
    document_id BIGINT PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    samples_required TEXT,
    send_to TEXT,
    number_of_samples TEXT,
    sample_preparation_labeling TEXT
);

CREATE TABLE IF NOT EXISTS T11_Revision_History (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    revision_number TEXT,
    who TEXT,
    revision_date TEXT,
    revision TEXT
);

CREATE TABLE IF NOT EXISTS T00_Ingestion_Audit (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES T00_Documents(id) ON DELETE CASCADE,
    relative_path TEXT,
    filename TEXT NOT NULL,
    source_table_index INTEGER,
    detected_section TEXT,
    row_count INTEGER,
    column_count INTEGER,
    status TEXT NOT NULL,
    mapping_method TEXT,
    mapping_confidence DOUBLE PRECISION,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS T00_Unmapped_Tables (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    preceding_heading TEXT,
    signature TEXT,
    classification TEXT,
    suggested_section TEXT,
    mapping_method TEXT,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS T00_Ingestion_Errors (
    id BIGSERIAL PRIMARY KEY,
    relative_path TEXT,
    filename TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_documents_filename ON T00_Documents(filename);
CREATE INDEX IF NOT EXISTS ix_documents_present ON T00_Documents(is_present);
CREATE INDEX IF NOT EXISTS ix_bom_document ON T03_Bill_of_Materials(document_id);
CREATE INDEX IF NOT EXISTS ix_secondary_document ON T04_Secondary_Approved_Materials(document_id);
CREATE INDEX IF NOT EXISTS ix_routing_document ON T05_Process_Routing(document_id);
CREATE INDEX IF NOT EXISTS ix_testing_document ON T06_Physical_Attributes_Testing(document_id);
CREATE INDEX IF NOT EXISTS ix_revision_document ON T11_Revision_History(document_id);
"""

POSTGRES_VIEW_SQL = """
CREATE OR REPLACE VIEW V00_Document_Staging_Status AS
SELECT
    d.id AS document_id,
    d.relative_path,
    d.filename,
    d.parser_version,
    d.is_present,
    SUM(CASE WHEN a.status = 'mapped' THEN 1 ELSE 0 END) AS mapped_source_tables,
    SUM(CASE WHEN a.status = 'supplemental' THEN 1 ELSE 0 END) AS supplemental_source_tables,
    SUM(CASE WHEN a.status = 'unmapped' THEN 1 ELSE 0 END) AS unmapped_source_tables,
    SUM(CASE WHEN a.status = 'error' THEN 1 ELSE 0 END) AS table_errors,
    MIN(CASE WHEN a.mapping_confidence IS NULL THEN 1.0 ELSE a.mapping_confidence END) AS minimum_mapping_confidence
FROM T00_Documents d
LEFT JOIN T00_Ingestion_Audit a ON a.document_id = d.id
GROUP BY d.id, d.relative_path, d.filename, d.parser_version, d.is_present;

CREATE OR REPLACE VIEW V00_Exception_Worklist AS
SELECT
    d.relative_path,
    a.source_table_index,
    a.detected_section,
    a.status,
    a.mapping_method,
    a.mapping_confidence,
    a.details
FROM T00_Ingestion_Audit a
JOIN T00_Documents d ON d.id = a.document_id
WHERE a.status <> 'mapped'
ORDER BY d.relative_path, a.source_table_index;
"""


def qmark_to_postgres(query: str) -> str:
    """Translate sqlite-style qmark placeholders used by the parser to psycopg %s."""
    return query.replace("?", "%s")


class PgCompatConnection:
    """Tiny compatibility layer so the proven V5 parser logic stays unchanged."""
    def __init__(self, raw):
        self.raw = raw

    def execute(self, query: str, params=None):
        cur = self.raw.cursor()
        cur.execute(qmark_to_postgres(query), params or ())
        return cur

    def executemany(self, query: str, params_seq):
        cur = self.raw.cursor()
        cur.executemany(qmark_to_postgres(query), params_seq)
        return cur

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def transaction(self):
        return self.raw.transaction()


def split_sql_script(script: str) -> list[str]:
    """Split the controlled DDL script into statements (no procedural SQL is used)."""
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def execute_script(conn: PgCompatConnection, script: str) -> None:
    for statement in split_sql_script(script):
        conn.execute(statement)


def table_columns(conn: PgCompatConnection, table_name: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = lower(?)
        """,
        (table_name,),
    ).fetchall()
    return {row["column_name"] for row in rows}


def existing_tables(conn: PgCompatConnection) -> set[str]:
    rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
        """
    ).fetchall()
    return {row["table_name"] for row in rows}


def ensure_audit_relative_path(conn: PgCompatConnection) -> None:
    if "t00_ingestion_audit" not in existing_tables(conn):
        return
    cols = table_columns(conn, "T00_Ingestion_Audit")
    if "relative_path" not in cols:
        conn.execute("ALTER TABLE T00_Ingestion_Audit ADD COLUMN relative_path TEXT")
        conn.execute("UPDATE T00_Ingestion_Audit SET relative_path = filename WHERE relative_path IS NULL")


def ensure_v5_schema(conn: PgCompatConnection) -> bool:
    """Idempotently add corpus-aware columns if a prior PostgreSQL staging schema exists."""
    changed = False
    additions = {
        "T03_Bill_of_Materials": [("source_table_index", "INTEGER")],
        "T04_Secondary_Approved_Materials": [("source_table_index", "INTEGER")],
        "T05_Process_Routing": [("source_table_index", "INTEGER")],
        "T06_Physical_Attributes_Testing": [("source_table_index", "INTEGER"), ("notes", "TEXT")],
        "T11_Revision_History": [("source_table_index", "INTEGER")],
        "T00_Ingestion_Audit": [("mapping_method", "TEXT"), ("mapping_confidence", "DOUBLE PRECISION")],
        "T00_Unmapped_Tables": [
            ("classification", "TEXT"),
            ("suggested_section", "TEXT"),
            ("mapping_method", "TEXT"),
        ],
    }
    tables = existing_tables(conn)
    for table_name, columns in additions.items():
        if table_name.lower() not in tables:
            continue
        existing = table_columns(conn, table_name)
        for column_name, sql_type in columns:
            if column_name not in existing:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}")
                changed = True
    return changed


def populate_table_directory(conn: PgCompatConnection) -> None:
    conn.executemany(
        """
        INSERT INTO T00_Table_Directory
        (sqlite_table_name, table_number, table_role, word_section, description, display_order)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (sqlite_table_name) DO UPDATE SET
            table_number = EXCLUDED.table_number,
            table_role = EXCLUDED.table_role,
            word_section = EXCLUDED.word_section,
            description = EXCLUDED.description,
            display_order = EXCLUDED.display_order
        """,
        TABLE_DIRECTORY,
    )


def database_exists(raw_conn, database_name: str) -> bool:
    with raw_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
        return cur.fetchone() is not None


def ensure_database(host: str, port: int, user: str, password: str | None, database_name: str, sslmode: str) -> None:
    """Create the target database when possible; otherwise provide a clear DBA-friendly error."""
    maintenance_kwargs = {
        "host": host,
        "port": port,
        "user": user,
        "dbname": "postgres",
        "sslmode": sslmode,
        "row_factory": dict_row,
        "autocommit": True,
    }
    if password:
        maintenance_kwargs["password"] = password
    try:
        with psycopg.connect(**maintenance_kwargs) as raw:
            if database_exists(raw, database_name):
                return
            try:
                raw.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
                print(f"Created PostgreSQL database: {database_name}")
            except Exception as exc:
                raise RuntimeError(
                    f"Database '{database_name}' does not exist and this PostgreSQL role could not create it. "
                    "Create the database once in pgAdmin/psql or grant CREATEDB, then rerun. "
                    f"PostgreSQL error: {exc}"
                ) from exc
    except Exception as exc:
        raise RuntimeError(
            "Could not connect to PostgreSQL maintenance database 'postgres'. "
            "Verify PostgreSQL is running and check --host/--port/--user credentials. "
            f"Details: {exc}"
        ) from exc


def connect_target(host: str, port: int, user: str, password: str | None, database_name: str, sslmode: str):
    kwargs = {
        "host": host,
        "port": port,
        "user": user,
        "dbname": database_name,
        "sslmode": sslmode,
        "row_factory": dict_row,
    }
    if password:
        kwargs["password"] = password
    raw = psycopg.connect(**kwargs)
    return raw, PgCompatConnection(raw)


def reset_staging_schema(conn: PgCompatConnection) -> None:
    """Drop only this staging application's views/tables; never drop the database itself."""
    conn.execute("DROP VIEW IF EXISTS V00_Exception_Worklist")
    conn.execute("DROP VIEW IF EXISTS V00_Document_Staging_Status")
    for table_name in reversed([row[0] for row in TABLE_DIRECTORY]):
        conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    conn.commit()


def prepare_database(conn: PgCompatConnection, rebuild: bool = False) -> None:
    if rebuild:
        reset_staging_schema(conn)
        print("Rebuild requested: existing Spec staging tables/views were dropped; the PostgreSQL database was retained.")
    execute_script(conn, POSTGRES_SCHEMA_SQL)
    ensure_audit_relative_path(conn)
    ensure_v5_schema(conn)
    execute_script(conn, POSTGRES_VIEW_SQL)
    populate_table_directory(conn)
    conn.commit()


# =============================================================================
# Section parsers
# =============================================================================
def parse_product_description(doc: Document) -> dict[str, str]:
    """Parse the best Product Description header across legacy/current header layouts."""
    best = {field: "" for field in FIELD_ALIASES["product"]}
    best_score = -1
    for section in doc.sections:
        for table in section.header.tables:
            candidate = extract_labeled_fields(table, FIELD_ALIASES["product"])
            score = sum(bool(v) for v in candidate.values())
            # A candidate should contain at least two key product labels. This permits
            # legacy 3x7 headers that omit Customer or Structure Code.
            key_score = sum(bool(candidate.get(k)) for k in ["item", "date_of_issue", "revision_number", "spec_number", "customer"])
            if key_score >= 2 and score > best_score:
                best = candidate
                best_score = score
    return best


def parse_locations(table: Table) -> dict[str, str]:
    return extract_labeled_fields(table, FIELD_ALIASES["locations"])


def material_fallback(cells: list[str]) -> tuple[str, str, str, str, str, str]:
    """Fallback for the common 6-column and merged 7-column BOM variants."""
    if len(cells) >= 7:
        return cells[0], cells[1], cells[3], cells[4], cells[5], cells[6]
    padded = cells + [""] * (6 - len(cells))
    return tuple(padded[:6])


def insert_material_table(
    conn: PgCompatConnection,
    table_name: str,
    document_id: int,
    source_table_index: int,
    table: Table,
) -> None:
    header_row, cmap = column_map_from_header(table, FIELD_ALIASES["material"], search_rows=3)
    useful_map = "raw_material" in cmap and ("supplier" in cmap or "raw_material_item_code" in cmap)
    start_row = header_row + 1 if useful_map else 1

    for source_row, row in enumerate(table.rows[start_row:], start=start_row):
        cells = row_values(row)
        if useful_map:
            vals = (
                value_at(cells, cmap.get("basis_weight")),
                value_at(cells, cmap.get("basis_weight_range")),
                value_at(cells, cmap.get("caliper_mils")),
                value_at(cells, cmap.get("raw_material")),
                value_at(cells, cmap.get("supplier")),
                value_at(cells, cmap.get("raw_material_item_code")),
            )
        else:
            vals = material_fallback(cells)

        basis_weight, basis_range, caliper, raw_material, supplier, item_code = vals
        if not any(vals):
            continue
        all_norm = " ".join(norm_match(x) for x in cells if clean(x))
        row_type = "total" if norm_match(raw_material) == "total" or all_norm == "total" else "material"
        conn.execute(
            f"""
            INSERT INTO {table_name}
            (document_id, source_table_index, source_row, row_type, basis_weight, basis_weight_range,
             caliper_mils, raw_material, supplier, raw_material_item_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                source_table_index,
                source_row,
                row_type,
                basis_weight,
                basis_range,
                caliper,
                raw_material,
                supplier,
                item_code,
            ),
        )


def insert_process_routing(
    conn: PgCompatConnection,
    document_id: int,
    source_table_index: int,
    table: Table,
) -> None:
    header_row, cmap = column_map_from_header(table, FIELD_ALIASES["routing"], search_rows=3)
    useful_map = len(set(cmap) & {"pass", "process", "machine"}) >= 2
    start_row = header_row + 1 if useful_map else 1

    for source_row, row in enumerate(table.rows[start_row:], start=start_row):
        cells = row_values(row)
        if not any(cells):
            continue
        if useful_map:
            vals = [
                value_at(cells, cmap.get("pass")),
                value_at(cells, cmap.get("process")),
                value_at(cells, cmap.get("machine")),
                value_at(cells, cmap.get("process_conditions")),
                value_at(cells, cmap.get("comments")),
            ]
        else:
            vals = (cells + [""] * 5)[:5]
        conn.execute(
            """
            INSERT INTO T05_Process_Routing
            (document_id, source_table_index, source_row, pass, process, machine, process_conditions, comments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, source_table_index, source_row, *vals),
        )


def insert_physical_testing(
    conn: PgCompatConnection,
    document_id: int,
    source_table_index: int,
    table: Table,
) -> None:
    tokens = recognized_fields(table, FIELD_ALIASES["testing"])
    # Corpus-observed legacy continuation table: a 1x2 Comments table after the
    # main Physical Attributes table. Preserve it as a notes row in T06.
    if tokens <= {"notes"} and "notes" in tokens:
        parsed = extract_labeled_fields(table, {"notes": FIELD_ALIASES["testing"]["notes"]})
        note = parsed.get("notes", "")
        if note:
            conn.execute(
                """
                INSERT INTO T06_Physical_Attributes_Testing
                (document_id, source_table_index, source_row, pass_name, attribute, notes)
                VALUES (?, ?, 0, '', 'Comments', ?)
                """,
                (document_id, source_table_index, note),
            )
        return

    header_aliases = {k: v for k, v in FIELD_ALIASES["testing"].items() if k != "notes"}
    header_row, cmap = column_map_from_header(table, header_aliases, search_rows=4)
    useful_map = "attribute" in cmap and len(cmap) >= 4
    start_row = header_row + 1 if useful_map else 1
    current_pass = ""

    for source_row, row in enumerate(table.rows[start_row:], start=start_row):
        cells = row_values(row)
        if not any(cells):
            continue
        unique_nonempty = [x for x in collapse_adjacent_duplicates(cells) if clean(x)]
        if len(unique_nonempty) == 1 and norm_match(unique_nonempty[0]).startswith("pass "):
            current_pass = unique_nonempty[0]
            continue

        if useful_map:
            vals = [value_at(cells, cmap.get(field)) for field in [
                "attribute", "coa", "units", "lsl", "lcl", "target", "ucl", "usl", "procedure", "frequency"
            ]]
        else:
            vals = (cells + [""] * 10)[:10]
        if not any(vals):
            continue
        conn.execute(
            """
            INSERT INTO T06_Physical_Attributes_Testing
            (document_id, source_table_index, source_row, pass_name, attribute, coa, units, lsl, lcl,
             target, ucl, usl, procedure, frequency, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
            """,
            (document_id, source_table_index, source_row, current_pass, *vals),
        )


def parse_slitting(table: Table) -> dict[str, str]:
    d = extract_labeled_fields(table, FIELD_ALIASES["slitting"])

    # Word's Slitting table has a corpus-stable merged row where Unwind / # Labels
    # Across and Core Tags / Splice Code are stacked in neighboring cells. Parse it
    # explicitly so merged-cell geometry does not turn a label into the value.
    for row in table.rows:
        cells = row_values(row)
        if not cells:
            continue
        first = norm_match(cells[0])
        if first == "unwind":
            # Current format: ['Unwind:', '', 'Duplex/MLP\n# Labels Across', '2',
            #                  'Core Tags:\nSplice Code:', 'Yes\nSP-001']
            if len(cells) > 2 and clean(cells[2]):
                parts = [clean(x) for x in cells[2].split("\n") if clean(x)]
                if parts:
                    d["unwind"] = parts[0]
                if len(parts) > 1 and norm_match(parts[1]).endswith("labels across") and len(cells) > 3:
                    d["labels_across"] = clean(cells[3])
            elif len(cells) > 1 and clean(cells[1]):
                d["unwind"] = clean(cells[1])

            if len(cells) > 5:
                labels = [clean(x) for x in cells[4].split("\n") if clean(x)]
                values = [clean(x) for x in cells[5].split("\n") if clean(x)]
                for label, value in zip(labels, values):
                    ln = norm_match(label)
                    if ln == "core tags":
                        d["core_tags"] = value
                    elif ln == "splice code":
                        d["splice_code"] = value
    return d


def parse_packing(table: Table) -> dict[str, str]:
    return extract_labeled_fields(table, FIELD_ALIASES["packing"])


def parse_reporting(table: Table) -> dict[str, str]:
    return extract_labeled_fields(table, FIELD_ALIASES["reporting"])


def parse_sampling(table: Table) -> dict[str, str]:
    return extract_labeled_fields(table, FIELD_ALIASES["sampling"])


def insert_revision_history(
    conn: PgCompatConnection,
    document_id: int,
    source_table_index: int,
    table: Table,
) -> None:
    header_row, cmap = column_map_from_header(table, FIELD_ALIASES["revision"], search_rows=3)
    useful_map = len(set(cmap) & {"revision_number", "who", "revision_date", "revision"}) >= 3
    start_row = header_row + 1 if useful_map else 1
    for source_row, row in enumerate(table.rows[start_row:], start=start_row):
        cells = row_values(row)
        if not any(cells):
            continue
        if useful_map:
            vals = [
                value_at(cells, cmap.get("revision_number")),
                value_at(cells, cmap.get("who")),
                value_at(cells, cmap.get("revision_date")),
                value_at(cells, cmap.get("revision")),
            ]
        else:
            vals = collapse_adjacent_duplicates(cells)
            vals = (vals + [""] * 4)[:4]
        if not any(vals):
            continue
        conn.execute(
            """
            INSERT INTO T11_Revision_History
            (document_id, source_table_index, source_row, revision_number, who, revision_date, revision)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, source_table_index, source_row, *vals),
        )


def merge_single_row(
    conn: PgCompatConnection,
    table_name: str,
    document_id: int,
    data: dict[str, str],
) -> list[str]:
    """Insert once; on companion tables fill blanks without overwriting primary values."""
    existing = conn.execute(f"SELECT * FROM {table_name} WHERE document_id = ?", (document_id,)).fetchone()
    if existing is None:
        columns = ["document_id"] + list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
            [document_id] + list(data.values()),
        )
        return []

    updates: dict[str, str] = {}
    conflicts: list[str] = []
    for field, value in data.items():
        if not clean(value):
            continue
        old = clean(existing[field]) if field in existing.keys() else ""
        if not old:
            updates[field] = value
        elif norm_match(old) != norm_match(value):
            conflicts.append(field)
    if updates:
        assignment = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(
            f"UPDATE {table_name} SET {assignment} WHERE document_id = ?",
            list(updates.values()) + [document_id],
        )
    return conflicts


def insert_single_row(conn: PgCompatConnection, table_name: str, document_id: int, data: dict[str, str]) -> None:
    """Compatibility wrapper used for the Product Description parent row."""
    merge_single_row(conn, table_name, document_id, data)


# =============================================================================
# Table detection
# =============================================================================
def _section_token_strength(table: Table, table_name: str) -> tuple[int, set[str]]:
    group = {
        "T02_Locations": "locations",
        "T03_Bill_of_Materials": "material",
        "T04_Secondary_Approved_Materials": "material",
        "T05_Process_Routing": "routing",
        "T06_Physical_Attributes_Testing": "testing",
        "T07_Slitting_Information": "slitting",
        "T08_Packing_Information": "packing",
        "T09_Reporting_Requirements": "reporting",
        "T10_Customer_Sampling_Requirements": "sampling",
        "T11_Revision_History": "revision",
    }.get(table_name)
    if not group:
        return 0, set()
    tokens = recognized_fields(table, FIELD_ALIASES[group])

    if table_name == "T02_Locations":
        score = int("spec_originator" in tokens) + int("phone_number" in tokens) + int("customer_location" in tokens) + int("facility" in tokens)
    elif table_name in {"T03_Bill_of_Materials", "T04_Secondary_Approved_Materials"}:
        score = 3 * int("raw_material" in tokens) + 2 * int("supplier" in tokens) + int("raw_material_item_code" in tokens) + int("basis_weight" in tokens) + int("caliper_mils" in tokens)
    elif table_name == "T05_Process_Routing":
        score = 2 * int("process" in tokens) + 2 * int("machine" in tokens) + int("pass" in tokens) + int("process_conditions" in tokens) + int("comments" in tokens)
    elif table_name == "T06_Physical_Attributes_Testing":
        score = 4 * int("attribute" in tokens) + sum(int(k in tokens) for k in ["units", "lsl", "lcl", "target", "ucl", "usl", "procedure", "frequency"])
        if tokens == {"notes"}:
            score = 2
    elif table_name == "T07_Slitting_Information":
        score = 4 * int("slit_width" in tokens) + 2 * int("core_id" in tokens) + sum(int(k in tokens) for k in ["cutoff", "width_tolerance", "splice_location", "unwind", "maximum_splices", "comments"])
    elif table_name == "T08_Packing_Information":
        score = 4 * int("pallet_size" in tokens) + 2 * int("rolls_per_pallet" in tokens) + sum(int(k in tokens) for k in ["pallet_type", "poly_bags", "layers_per_pallet", "rolls_per_layer", "packing_instructions", "additional_instructions"])
    elif table_name == "T09_Reporting_Requirements":
        score = sum(2 * int(k in tokens) for k in ["coa_required", "coa_format", "coa_frequency", "values_to_report_on_coa"]) + int("coa_recipients" in tokens)
    elif table_name == "T10_Customer_Sampling_Requirements":
        score = sum(2 * int(k in tokens) for k in ["samples_required", "send_to", "number_of_samples", "sample_preparation_labeling"])
    else:  # T11
        score = sum(2 * int(k in tokens) for k in ["revision_number", "who", "revision_date", "revision"])
    return score, tokens


def detect_table(
    table: Table,
    heading: str | None,
    heading_fresh: bool,
    material_seen: int,
) -> tuple[str | None, str, float, bool]:
    """Return (section, method, confidence, supplemental_only).

    Content evidence is allowed to override a stale heading. This specifically fixes
    corpus-observed cases where Slitting tables remained under a preceding Physical
    Attributes heading and where legacy Locations/BOM/Routing headings were malformed.

    V5.2 also recognizes the corpus-confirmed Blown Film extrusion-input companion
    table by its structural signature. This specialized process table is preserved
    losslessly in T00_Unmapped_Tables as supplemental rather than being forced into
    one of the standardized T01-T11 specification sections.
    """
    # Corpus-confirmed Blown Film extrusion-input companion table. The four remaining
    # V5.1 unmapped tables shared this signature and appeared in Blown Film specs.
    # Match on stable structural labels rather than filename or folder so future specs
    # with the same table format are classified correctly.
    sig_tokens = {
        norm_match(part).replace(" ", "")
        for part in header_signature(table).split("|")
        if clean(part)
    }
    blown_film_required = {"extinputid", "throughputlbs", "loadpercent", "thickness"}
    if blown_film_required.issubset(sig_tokens):
        return None, "corpus_signature_rule", 0.99, True

    heading_section = section_from_heading(heading)

    # Strong content-first rules. Thresholds were selected from the corpus profile's
    # generic label signatures and intentionally avoid the unlabeled supplemental tables.
    candidates = [
        "T07_Slitting_Information",
        "T08_Packing_Information",
        "T09_Reporting_Requirements",
        "T10_Customer_Sampling_Requirements",
        "T11_Revision_History",
        "T06_Physical_Attributes_Testing",
        "T05_Process_Routing",
        "T02_Locations",
    ]
    scored: list[tuple[int, str, set[str]]] = []
    for name in candidates:
        score, tokens = _section_token_strength(table, name)
        scored.append((score, name, tokens))
    scored.sort(reverse=True)
    best_score, best_name, best_tokens = scored[0]

    thresholds = {
        "T02_Locations": 2,
        "T05_Process_Routing": 4,
        "T06_Physical_Attributes_Testing": 6,
        "T07_Slitting_Information": 6,
        "T08_Packing_Information": 6,
        "T09_Reporting_Requirements": 4,
        "T10_Customer_Sampling_Requirements": 4,
        "T11_Revision_History": 6,
    }
    if best_score >= thresholds.get(best_name, 999):
        # A fresh explicit heading wins only if its table has plausible content for that heading.
        if heading_fresh and heading_section and heading_section != best_name:
            h_score, _ = _section_token_strength(table, heading_section)
            if h_score > 0:
                return heading_section, "fresh_heading+content", 0.96, False
        return best_name, "content_signature", 0.95, False

    # Materials need a separate primary-vs-secondary decision.
    material_score, material_tokens = _section_token_strength(table, "T03_Bill_of_Materials")
    if material_score >= 5:
        if heading_section in {"T03_Bill_of_Materials", "T04_Secondary_Approved_Materials"}:
            return heading_section, "heading+material_signature", 0.98, False
        inferred = "T03_Bill_of_Materials" if material_seen == 0 else "T04_Secondary_Approved_Materials"
        return inferred, "material_signature+sequence", 0.88, False

    # A directly preceding known heading is strong evidence for the first table under
    # that section even when the legacy table has weak/no recognizable labels.
    if heading_fresh and heading_section:
        return heading_section, "fresh_heading", 0.90, False

    # Persisted section context is useful for split tables only when some relevant label
    # evidence exists. Unlabeled image/diagram/helper tables become supplemental instead
    # of being forced into a clean staging table.
    if heading_section:
        h_score, h_tokens = _section_token_strength(table, heading_section)
        if h_score > 0:
            return heading_section, "section_context+content", 0.78, False
        return heading_section, "section_context_supplemental", 0.55, True

    if heading and is_known_supplemental_heading(heading):
        return None, "known_supplemental_heading", 0.90, True

    return None, "unmapped", 0.0, False


# =============================================================================
# Ingestion
# =============================================================================
def clear_document_children(conn: PgCompatConnection, document_id: int) -> None:
    """Clear extracted rows for one document while preserving its stable document_id."""
    for table in [
        "T00_Ingestion_Audit",
        "T00_Unmapped_Tables",
        "T01_Product_Description",
        "T02_Locations",
        "T03_Bill_of_Materials",
        "T04_Secondary_Approved_Materials",
        "T05_Process_Routing",
        "T06_Physical_Attributes_Testing",
        "T07_Slitting_Information",
        "T08_Packing_Information",
        "T09_Reporting_Requirements",
        "T10_Customer_Sampling_Requirements",
        "T11_Revision_History",
    ]:
        conn.execute(f"DELETE FROM {table} WHERE document_id = ?", (document_id,))


def find_existing_document(conn: PgCompatConnection, relative_path: str, filename: str, sha: str | None = None):
    row = conn.execute(
        "SELECT * FROM T00_Documents WHERE relative_path = ?",
        (relative_path,),
    ).fetchone()
    if row:
        return row

    # V3 migration compatibility: an old root-level record may only know filename.
    if sha:
        candidates = conn.execute(
            """
            SELECT * FROM T00_Documents
            WHERE filename = ? AND sha256 = ? AND (source_directory = '' OR source_directory IS NULL)
            """,
            (filename, sha),
        ).fetchall()
        if len(candidates) == 1:
            return candidates[0]
    return None


def ingest_document(conn: PgCompatConnection, path: Path, root: Path, full_rescan: bool = False) -> str:
    relative = rel_path(path, root)
    stat = path.stat()
    seen_at = utc_now()

    existing = conn.execute(
        "SELECT * FROM T00_Documents WHERE relative_path = ?",
        (relative,),
    ).fetchone()

    # Fast unchanged check. Parser-version changes deliberately force a re-parse so
    # corpus-aware upgrades can be applied without --full-rescan.
    if existing and not full_rescan:
        if (
            existing["source_file_size"] == stat.st_size
            and existing["source_modified_ns"] == stat.st_mtime_ns
            and existing["parser_version"] == PARSER_VERSION
        ):
            conn.execute(
                "UPDATE T00_Documents SET last_seen_at = ?, is_present = 1 WHERE id = ?",
                (seen_at, existing["id"]),
            )
            return f"SKIP unchanged: {relative}"

    sha = file_sha256(path)
    existing = find_existing_document(conn, relative, path.name, sha)

    if existing and existing["sha256"] == sha and not full_rescan and existing["parser_version"] == PARSER_VERSION:
        conn.execute(
            """
            UPDATE T00_Documents
            SET relative_path = ?, filename = ?, source_directory = ?, source_file_size = ?,
                source_modified_ns = ?, last_seen_at = ?, is_present = 1
            WHERE id = ?
            """,
            (
                relative,
                path.name,
                str(Path(relative).parent.as_posix()) if Path(relative).parent.as_posix() != "." else "",
                stat.st_size,
                stat.st_mtime_ns,
                seen_at,
                existing["id"],
            ),
        )
        return f"SKIP unchanged: {relative}"

    doc = Document(str(path))
    paragraph_content = "\n".join(clean(p.text) for p in doc.paragraphs if clean(p.text))

    if existing:
        document_id = existing["id"]
        clear_document_children(conn, document_id)
        conn.execute(
            """
            UPDATE T00_Documents
            SET relative_path = ?, filename = ?, source_directory = ?, source_file_size = ?,
                source_modified_ns = ?, sha256 = ?, imported_at = ?, last_seen_at = ?,
                is_present = 1, parser_version = ?, paragraph_content = ?
            WHERE id = ?
            """,
            (
                relative,
                path.name,
                str(Path(relative).parent.as_posix()) if Path(relative).parent.as_posix() != "." else "",
                stat.st_size,
                stat.st_mtime_ns,
                sha,
                seen_at,
                seen_at,
                PARSER_VERSION,
                paragraph_content,
                document_id,
            ),
        )
        action = "UPDATED"
    else:
        cur = conn.execute(
            """
            INSERT INTO T00_Documents
            (relative_path, filename, source_directory, source_file_size, source_modified_ns,
             sha256, imported_at, last_seen_at, is_present, parser_version, paragraph_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            RETURNING id
            """,
            (
                relative,
                path.name,
                str(Path(relative).parent.as_posix()) if Path(relative).parent.as_posix() != "." else "",
                stat.st_size,
                stat.st_mtime_ns,
                sha,
                seen_at,
                seen_at,
                PARSER_VERSION,
                paragraph_content,
            ),
        )
        document_id = cur.fetchone()["id"]
        action = "LOADED"

    merge_single_row(conn, "T01_Product_Description", document_id, parse_product_description(doc))

    current_heading: str | None = None
    heading_fresh = False
    table_index = 0
    material_seen = 0
    section_occurrences: dict[str, int] = {}

    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = clean(block.text)
            if not text:
                continue
            # Track both recognized and unknown Heading-styled paragraphs. Unknown headings
            # must reset context so a Quality Issues/Extruder Distribution table is not
            # accidentally attributed to the preceding standard section.
            if is_heading_paragraph(block) or section_from_heading(text):
                current_heading = text
                heading_fresh = True
            continue

        table_index += 1
        detected, mapping_method, confidence, supplemental_only = detect_table(
            block, current_heading, heading_fresh, material_seen
        )
        row_count = len(block.rows)
        col_count = max((len(row.cells) for row in block.rows), default=0)
        status = "mapped" if detected and not supplemental_only else ("supplemental" if supplemental_only else "unmapped")
        details = ""

        try:
            if supplemental_only:
                conn.execute(
                    """
                    INSERT INTO T00_Unmapped_Tables
                    (document_id, source_table_index, preceding_heading, signature,
                     classification, suggested_section, mapping_method, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        table_index,
                        current_heading or "",
                        header_signature(block),
                        "supplemental",
                        ("Blown Film Extrusion Inputs" if mapping_method == "corpus_signature_rule" else (detected or "")),
                        mapping_method,
                        table_json(block),
                    ),
                )
                details = "Preserved as supplemental/companion table; not forced into clean staging columns."
            elif detected == "T02_Locations":
                conflicts = merge_single_row(conn, "T02_Locations", document_id, parse_locations(block))
                if conflicts:
                    details = "Conflicting companion values retained from first table: " + ", ".join(conflicts)
            elif detected == "T03_Bill_of_Materials":
                insert_material_table(conn, "T03_Bill_of_Materials", document_id, table_index, block)
                material_seen += 1
            elif detected == "T04_Secondary_Approved_Materials":
                insert_material_table(conn, "T04_Secondary_Approved_Materials", document_id, table_index, block)
                material_seen += 1
            elif detected == "T05_Process_Routing":
                insert_process_routing(conn, document_id, table_index, block)
            elif detected == "T06_Physical_Attributes_Testing":
                insert_physical_testing(conn, document_id, table_index, block)
            elif detected == "T07_Slitting_Information":
                conflicts = merge_single_row(conn, "T07_Slitting_Information", document_id, parse_slitting(block))
                if conflicts:
                    details = "Conflicting companion values retained from first table: " + ", ".join(conflicts)
            elif detected == "T08_Packing_Information":
                conflicts = merge_single_row(conn, "T08_Packing_Information", document_id, parse_packing(block))
                if conflicts:
                    details = "Conflicting companion values retained from first table: " + ", ".join(conflicts)
            elif detected == "T09_Reporting_Requirements":
                conflicts = merge_single_row(conn, "T09_Reporting_Requirements", document_id, parse_reporting(block))
                if conflicts:
                    details = "Conflicting companion values retained from first table: " + ", ".join(conflicts)
            elif detected == "T10_Customer_Sampling_Requirements":
                conflicts = merge_single_row(conn, "T10_Customer_Sampling_Requirements", document_id, parse_sampling(block))
                if conflicts:
                    details = "Conflicting companion values retained from first table: " + ", ".join(conflicts)
            elif detected == "T11_Revision_History":
                insert_revision_history(conn, document_id, table_index, block)
            else:
                classification = "known_supplemental" if (current_heading and is_known_supplemental_heading(current_heading)) else "unmapped"
                conn.execute(
                    """
                    INSERT INTO T00_Unmapped_Tables
                    (document_id, source_table_index, preceding_heading, signature,
                     classification, suggested_section, mapping_method, raw_json)
                    VALUES (?, ?, ?, ?, ?, '', ?, ?)
                    """,
                    (
                        document_id,
                        table_index,
                        current_heading or "",
                        header_signature(block),
                        classification,
                        mapping_method,
                        table_json(block),
                    ),
                )

            if detected and not supplemental_only:
                section_occurrences[detected] = section_occurrences.get(detected, 0) + 1
                # Preserve subsequent single-row companion source tables losslessly even
                # when some blank fields were merged into the primary clean row.
                if section_occurrences[detected] > 1 and detected in {
                    "T02_Locations", "T07_Slitting_Information", "T08_Packing_Information",
                    "T09_Reporting_Requirements", "T10_Customer_Sampling_Requirements",
                }:
                    conn.execute(
                        """
                        INSERT INTO T00_Unmapped_Tables
                        (document_id, source_table_index, preceding_heading, signature,
                         classification, suggested_section, mapping_method, raw_json)
                        VALUES (?, ?, ?, ?, 'section_companion', ?, ?, ?)
                        """,
                        (
                            document_id,
                            table_index,
                            current_heading or "",
                            header_signature(block),
                            detected,
                            mapping_method,
                            table_json(block),
                        ),
                    )
        except Exception as exc:
            status = "error"
            details = repr(exc)
            raise
        finally:
            conn.execute(
                """
                INSERT INTO T00_Ingestion_Audit
                (document_id, relative_path, filename, source_table_index, detected_section,
                 row_count, column_count, status, mapping_method, mapping_confidence, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    relative,
                    path.name,
                    table_index,
                    detected or "",
                    row_count,
                    col_count,
                    status,
                    mapping_method,
                    confidence,
                    details,
                    utc_now(),
                ),
            )

        # The exact heading remains as section context for split/companion tables. The
        # "fresh" flag is cleared after one table so unlabeled follow-ons are supplemental.
        heading_fresh = False

    return f"{action}: {relative} (document_id={document_id})"


# =============================================================================
# Reporting / command line
# =============================================================================
def scalar_count(conn: PgCompatConnection, query: str, params=()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row["n"] if row else 0)


def print_counts(conn: PgCompatConnection) -> None:
    tables = [row[0] for row in TABLE_DIRECTORY]
    print("\nRow counts:")
    for table in tables:
        count = scalar_count(conn, f"SELECT COUNT(*) AS n FROM {table}")
        print(f"  {table:<38} {count:>8}")

    current_docs = scalar_count(conn, "SELECT COUNT(*) AS n FROM T00_Documents WHERE is_present = 1")
    missing_docs = scalar_count(conn, "SELECT COUNT(*) AS n FROM T00_Documents WHERE is_present = 0")
    print(f"\n  Current source documents: {current_docs}")
    print(f"  Previously staged but now missing: {missing_docs}")


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Recursively extract Word manufacturing specs under the current Windows user's "
            "Desktop\\Specs folder into PostgreSQL for Retool / application prototyping."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Override source root. Default: current Windows user's Desktop\\Specs.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("SPEC_PG_HOST", "localhost"),
        help="PostgreSQL host. Default: SPEC_PG_HOST or localhost.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SPEC_PG_PORT", "5432")),
        help="PostgreSQL port. Default: SPEC_PG_PORT or 5432.",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("SPEC_PG_USER", "postgres"),
        help="PostgreSQL user. Default: SPEC_PG_USER or postgres.",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SPEC_PG_PASSWORD") or os.environ.get("PGPASSWORD"),
        help="PostgreSQL password. Prefer SPEC_PG_PASSWORD/PGPASSWORD or .pgpass instead of command-line use.",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("SPEC_PG_DATABASE", DEFAULT_DATABASE_NAME),
        help=f"Target PostgreSQL database. Default: SPEC_PG_DATABASE or {DEFAULT_DATABASE_NAME}.",
    )
    parser.add_argument(
        "--sslmode",
        default=os.environ.get("SPEC_PG_SSLMODE", "prefer"),
        choices=["disable", "allow", "prefer", "require", "verify-ca", "verify-full"],
        help="PostgreSQL SSL mode. Default: prefer.",
    )
    parser.add_argument(
        "--full-rescan",
        action="store_true",
        help="Re-parse every discovered Word file, even if it appears unchanged.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop/recreate only the staging tables and views in the target PostgreSQL database.",
    )
    parser.add_argument(
        "--prune-missing",
        action="store_true",
        help="Delete staged documents that no longer exist under the source root. Default is retain + is_present=0.",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name to exclude from recursive scanning. May be supplied more than once.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print a progress line every N files (default: 100).",
    )
    parser.add_argument("--verbose", action="store_true", help="Print every loaded/updated/skipped file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if psycopg is None:
        print("ERROR: PostgreSQL driver is not installed.")
        print(r"Install with: C:\Python314\python.exe -m pip install 'psycopg[binary]' python-docx")
        return 1

    root = (args.root.expanduser().resolve() if args.root else default_specs_root().resolve())
    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS) | set(args.exclude_dir)

    print(f"Python:        {sys.version.split()[0]}")
    print(f"Specs root:    {root}")
    print(f"PostgreSQL:    {args.host}:{args.port}")
    print(f"Database:      {args.database}")
    print(f"User:          {args.user}")
    print(f"Parser version:{PARSER_VERSION}")

    if not root.exists():
        print(f"\nERROR: Specs folder does not exist: {root}")
        print("Create a folder named 'Specs' on the current Windows user's Desktop, or pass --root to override it.")
        return 1

    try:
        ensure_database(args.host, args.port, args.user, args.password, args.database, args.sslmode)
        raw_conn, conn = connect_target(args.host, args.port, args.user, args.password, args.database, args.sslmode)
    except Exception as exc:
        auth_text = str(exc).lower()
        can_prompt = (not args.password) and sys.stdin.isatty() and (
            "password" in auth_text or "authentication" in auth_text
        )
        if can_prompt:
            try:
                args.password = getpass.getpass(f"PostgreSQL password for {args.user}: ")
                ensure_database(args.host, args.port, args.user, args.password, args.database, args.sslmode)
                raw_conn, conn = connect_target(args.host, args.port, args.user, args.password, args.database, args.sslmode)
            except Exception as retry_exc:
                print(f"\nERROR connecting to PostgreSQL: {retry_exc}")
                return 1
        else:
            print(f"\nERROR connecting to PostgreSQL: {exc}")
            return 1

    files = list_docx_files(root, exclude_dirs)
    print(f"Word files:    {len(files)}")
    if not files:
        raw_conn.close()
        print("\nERROR: No .docx files were found under the Specs folder or its subfolders.")
        return 1

    loaded = 0
    updated = 0
    skipped = 0
    errors = 0

    try:
        prepare_database(conn, rebuild=args.rebuild)

        # Mark all rows absent first; each discovered file flips itself back to 1.
        conn.execute("UPDATE T00_Documents SET is_present = 0")
        conn.commit()

        total = len(files)
        for index, path in enumerate(files, start=1):
            relative = rel_path(path, root)
            try:
                with conn.transaction():
                    result = ingest_document(conn, path, root, full_rescan=args.full_rescan)
                if result.startswith("LOADED"):
                    loaded += 1
                elif result.startswith("UPDATED"):
                    updated += 1
                else:
                    skipped += 1
                if args.verbose:
                    print(result)
            except Exception as exc:
                errors += 1
                try:
                    with conn.transaction():
                        conn.execute(
                            """
                            INSERT INTO T00_Ingestion_Errors
                            (relative_path, filename, error_type, error_message, created_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (relative, path.name, type(exc).__name__, str(exc), utc_now()),
                        )
                except Exception as log_exc:
                    print(f"WARNING: could not log ingestion error to PostgreSQL: {log_exc}")
                print(f"ERROR: {relative}: {type(exc).__name__}: {exc}")

            if args.progress_every > 0 and (index % args.progress_every == 0 or index == total):
                print(
                    f"Progress: {index:,}/{total:,} | loaded {loaded:,} | updated {updated:,} | "
                    f"skipped {skipped:,} | errors {errors:,}"
                )

        if args.prune_missing:
            missing = conn.execute("SELECT id FROM T00_Documents WHERE is_present = 0").fetchall()
            with conn.transaction():
                for row in missing:
                    conn.execute("DELETE FROM T00_Documents WHERE id = ?", (row["id"],))
            print(f"Pruned missing documents: {len(missing)}")

        print_counts(conn)
        unmapped = scalar_count(
            conn,
            "SELECT COUNT(*) AS n FROM T00_Unmapped_Tables WHERE classification = 'unmapped' OR classification IS NULL",
        )
        supplemental = scalar_count(
            conn,
            "SELECT COUNT(*) AS n FROM T00_Unmapped_Tables WHERE classification IN ('supplemental','known_supplemental','section_companion')",
        )
        audit_errors = scalar_count(conn, "SELECT COUNT(*) AS n FROM T00_Ingestion_Audit WHERE status = 'error'")
    except Exception as exc:
        conn.rollback()
        print(f"\nERROR preparing or loading PostgreSQL staging database: {type(exc).__name__}: {exc}")
        return 1
    finally:
        raw_conn.close()

    print("\nImport summary:")
    print(f"  Loaded new: {loaded}")
    print(f"  Updated:    {updated}")
    print(f"  Unchanged:  {skipped}")
    print(f"  File errors:{errors}")
    print(f"  Unmapped tables currently staged: {unmapped}")
    print(f"  Supplemental/companion tables:    {supplemental}")
    print(f"  Table-level audit errors:         {audit_errors}")
    print(f"\nPostgreSQL database ready: {args.database} @ {args.host}:{args.port}")
    print("Retool should connect to the PostgreSQL server/database as a PostgreSQL resource; it does not connect to a .sql file.")

    if errors:
        print("\nSome files failed. Review T00_Ingestion_Errors in PostgreSQL and copy representative errors back into ChatGPT.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
