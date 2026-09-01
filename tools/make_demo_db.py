"""Build a demo Spec_Stage.db so Lapus can be run, tested and shown without
the real corpus.

The production database is the output of the V5.2 parser reading ~14,000 Word
specifications off a network share. That corpus cannot be checked in, and a
developer cloning this repo needs *something* to point the app at. This script
writes a small database with the exact staging schema (db/sqlite/000_staging_schema.sql)
and plausible flexible-packaging data.

It is deliberately not uniform. Real staged documents vary, and the UI has to
survive that, so the generated set includes:

  * specs missing whole sections (older documents that never had them),
  * a document flagged is_present = 0 (its source file has disappeared),
  * supplemental and unmapped source tables, and an ingestion error,
  * mapping confidence below 1.0 on a document with a damaged heading,

which between them exercise every empty state and the whole admin panel.

Usage:
    python tools/make_demo_db.py [--output PATH] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = REPO_ROOT / "db" / "sqlite" / "000_staging_schema.sql"
PARSER_VERSION = "5.2.0-corpus-aware"

CUSTOMERS = [
    ("Northwind Foods", "Cincinnati, OH", "Ohio Converting"),
    ("Sunbelt Produce Packing", "Lakeland, FL", "Florida Converting"),
    ("Harbour Pet Nutrition", "Green Bay, WI", "Wisconsin Converting"),
    ("Cascade Snack Co.", "Portland, OR", "Ohio Converting"),
    ("Meridian Coffee Roasters", "Seattle, WA", "Wisconsin Converting"),
    ("Alpine Dairy Group", "Boise, ID", "Ohio Converting"),
]

STRUCTURES = [
    ("48ga PET / 2.5mil LLDPE", "PET-LLD-48-250", "Laminated pouch film"),
    ("Foil laminate 48ga PET / .000285 Foil / 3.0mil LLDPE", "PET-FOIL-LLD", "High barrier laminate"),
    ("2.0mil Met PET / 2.0mil LLDPE", "MPET-LLD-200", "Metallised barrier film"),
    ("60ga BOPP / 80ga Met BOPP", "BOPP-MBOPP-60", "Coffee lamination"),
    ("75ga PET / 1.5mil Sealant", "PET-SEAL-75", "Lidding film"),
    ("Paper 40# / 1.0mil LDPE", "PAP-LDPE-40", "Paper poly laminate"),
]

RAW_MATERIALS = [
    ("48 ga Polyester Film", "Vaultex Films", "RM-PET-0048", "0.48", "0.46 - 0.50", "0.480"),
    ("2.5 mil LLDPE Sealant Web", "Cordell Resins", "RM-LLD-0250", "2.50", "2.40 - 2.60", "2.500"),
    ("0.000285 Aluminium Foil", "Northline Foil", "RM-FOIL-285", "0.29", "0.27 - 0.31", "0.285"),
    ("80 ga Metallised BOPP", "Vaultex Films", "RM-MBOPP-080", "0.80", "0.78 - 0.82", "0.800"),
    ("Solventless Adhesive 2K", "Bonnet Adhesives", "RM-ADH-2K01", "1.75", "1.60 - 1.90", None),
    ("40# Natural Kraft", "Ridgeway Paper", "RM-PAP-0040", "40.0", "38.0 - 42.0", "2.600"),
    ("White Ink Base", "Spectra Inks", "RM-INK-WHT1", None, None, None),
]

PROCESSES = [
    ("1", "Flexographic Printing", "Flexo Press 3", "8 colour, 600 fpm, corona treat inline", "Match approved colour standard"),
    ("2", "Solventless Lamination", "Laminator 2", "Adhesive 1.75 lb/ream, nip 65 psi, 180 degF", None),
    ("3", "Curing", "Cure Room A", "72 hours at ambient, minimum 68 degF", "Do not slit before cure release"),
    ("4", "Slitting", "Slitter 5", "Tension 1.2 lb/in, 900 fpm", None),
]

ATTRIBUTES = [
    ("Laminate", "Bond Strength", "Yes", "g/in", "250", "300", "450", "600", "650", "ASTM F904", "1 per roll", None),
    ("Laminate", "Total Thickness", "Yes", "mils", "3.60", "3.70", "3.90", "4.10", "4.20", "ASTM D6988", "1 per roll", None),
    ("Sealant", "Seal Strength", "Yes", "lb/in", "5.0", "5.5", "7.0", "8.5", "9.0", "ASTM F88", "1 per lot", "Seal at 350 degF, 40 psi, 0.5 s"),
    ("Sealant", "COF Sealant Side", "No", "kinetic", "0.15", None, "0.25", None, "0.40", "ASTM D1894", "1 per lot", None),
    ("Barrier", "OTR", "Yes", "cc/100in2/day", None, None, "0.06", None, "0.10", "ASTM D3985", "1 per production run", "23 degC, 0% RH"),
    ("Barrier", "WVTR", "Yes", "g/100in2/day", None, None, "0.02", None, "0.05", "ASTM F1249", "1 per production run", "38 degC, 90% RH"),
    ("Print", "Colour Delta E", "No", "dE", None, None, "1.0", None, "2.0", "Internal QA-114", "Each set-up", "Against approved draw-down"),
]

REVISION_NOTES = [
    "Initial release.",
    "Updated sealant supplier following qualification trial.",
    "Bond strength lower spec limit raised from 200 to 250 g/in.",
    "Added secondary approved material for foil web.",
    "Corrected pallet pattern to 4 rolls per layer.",
    "Annual review - no technical change.",
    "Customer requested COA frequency change to every lot.",
]

ORIGINATORS = [
    ("D. Whitfield", "513-555-0142"),
    ("M. Okafor", "920-555-0198"),
    ("S. Berglund", "503-555-0177"),
    ("A. Ramirez", "208-555-0164"),
]


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def build(output: Path, force: bool = False) -> Path:
    if output.exists():
        if not force:
            raise SystemExit(f"{output} already exists. Pass --force to replace it.")
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)

    # Fixed seed: the demo database is regenerated often (see packaging notes on
    # resetting a demo), and a stable dataset means screenshots, tests and
    # rehearsed walkthroughs keep referring to the same specs.
    rng = random.Random(20260901)

    conn = sqlite3.connect(output)
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))

    imported = datetime(2026, 8, 24, 9, 15, tzinfo=timezone.utc)
    audit_rows: list[tuple] = []

    conn.executemany(
        """INSERT INTO T00_Table_Directory
           (sqlite_table_name, table_number, table_role, word_section, description, display_order)
           VALUES (?,?,?,?,?,?)""",
        [
            (f"T{n:02d}_{key}", n, "specification", label, f"Section {n} of the source specification", n)
            for n, key, label in [
                (1, "Product_Description", "Product Description"),
                (2, "Locations", "Locations"),
                (3, "Bill_of_Materials", "Bill of Materials"),
                (4, "Secondary_Approved_Materials", "Secondary Approved Materials"),
                (5, "Process_Routing", "Process Routing"),
                (6, "Physical_Attributes_Testing", "Physical Attributes & Testing"),
                (7, "Slitting_Information", "Slitting Information"),
                (8, "Packing_Information", "Packing Information"),
                (9, "Reporting_Requirements", "Reporting Requirements"),
                (10, "Customer_Sampling_Requirements", "Customer Sampling Requirements"),
                (11, "Revision_History", "Revision History"),
            ]
        ],
    )

    doc_count = 18
    for index in range(doc_count):
        customer, location, facility = CUSTOMERS[index % len(CUSTOMERS)]
        structure, structure_code, structure_kind = STRUCTURES[index % len(STRUCTURES)]
        originator, phone = ORIGINATORS[index % len(ORIGINATORS)]
        spec_number = f"SP-{4100 + index * 7}"
        item = f"{700000 + index * 137}"
        revision = index % 6
        issued = imported - timedelta(days=30 * (index % 24) + 5)

        folder = customer.split()[0].replace(".", "")
        relative_path = f"{folder}/{spec_number}_{item}_Rev{revision}.docx"
        filename = relative_path.rsplit("/", 1)[-1]

        # One document stands in for a spec whose source file has been moved or
        # deleted since the last parser run: staged data is retained, is_present
        # goes to 0. The UI has to keep showing it, flagged.
        is_present = 0 if index == doc_count - 1 else 1

        document_id = conn.execute(
            """INSERT INTO T00_Documents
               (relative_path, filename, source_directory, source_file_size,
                source_modified_ns, sha256, imported_at, last_seen_at,
                is_present, parser_version, paragraph_content)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                relative_path,
                filename,
                f"C:\\Users\\parser\\Desktop\\Specs\\{folder}",
                rng.randint(48_000, 260_000),
                int(issued.timestamp() * 1_000_000_000),
                hashlib.sha256(relative_path.encode()).hexdigest(),
                _iso(imported),
                _iso(imported),
                is_present,
                PARSER_VERSION,
                f"{structure_kind} specification for {customer}.",
            ),
        ).lastrowid

        def audit(table_index: int, section: str, rows: int, cols: int,
                  status: str = "mapped", method: str = "heading_exact",
                  confidence: float = 1.0, details: str | None = None) -> None:
            audit_rows.append(
                (document_id, relative_path, filename, table_index, section, rows,
                 cols, status, method, confidence, details, _iso(imported))
            )

        # --- T01 Product Description -------------------------------------
        conn.execute(
            """INSERT INTO T01_Product_Description
               (document_id, customer, spec_number, item, date_of_issue,
                structure_description, revision_number, structure_code)
               VALUES (?,?,?,?,?,?,?,?)""",
            (document_id, customer, spec_number, item, issued.strftime("%m/%d/%Y"),
             structure, str(revision), structure_code),
        )
        audit(0, "T01_Product_Description", 4, 4)

        # --- T02 Locations ------------------------------------------------
        conn.execute(
            """INSERT INTO T02_Locations
               (document_id, customer_location, facility, spec_originator, phone_number)
               VALUES (?,?,?,?,?)""",
            (document_id, location, facility, originator, phone),
        )
        audit(1, "T02_Locations", 2, 4)

        # --- T03 Bill of Materials ----------------------------------------
        layer_count = 2 + (index % 3)
        for row, material in enumerate(RAW_MATERIALS[:layer_count], start=1):
            name, supplier, code, weight, weight_range, caliper = material
            conn.execute(
                """INSERT INTO T03_Bill_of_Materials
                   (document_id, source_table_index, source_row, row_type,
                    basis_weight, basis_weight_range, caliper_mils,
                    raw_material, supplier, raw_material_item_code)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (document_id, 2, row, "material", weight, weight_range, caliper,
                 name, supplier, code),
            )
        audit(2, "T03_Bill_of_Materials", layer_count, 6)

        # --- T04 Secondary Approved Materials -----------------------------
        # Not every spec has alternates; roughly a third do not.
        if index % 3 != 2:
            for row, material in enumerate(RAW_MATERIALS[1:3], start=1):
                name, supplier, code, weight, weight_range, caliper = material
                conn.execute(
                    """INSERT INTO T04_Secondary_Approved_Materials
                       (document_id, source_table_index, source_row, row_type,
                        basis_weight, basis_weight_range, caliper_mils,
                        raw_material, supplier, raw_material_item_code)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (document_id, 3, row, "material", weight, weight_range, caliper,
                     f"{name} (alternate)", "Kestrel Substrates", code.replace("RM-", "ALT-"),
                     ),
                )
            audit(3, "T04_Secondary_Approved_Materials", 2, 6)

        # --- T05 Process Routing -------------------------------------------
        for row, step in enumerate(PROCESSES, start=1):
            pass_no, process, machine, conditions, comments = step
            conn.execute(
                """INSERT INTO T05_Process_Routing
                   (document_id, source_table_index, source_row, pass, process,
                    machine, process_conditions, comments)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (document_id, 4, row, pass_no, process, machine, conditions, comments),
            )
        audit(4, "T05_Process_Routing", len(PROCESSES), 5)

        # --- T06 Physical Attributes & Testing ------------------------------
        for row, attr in enumerate(ATTRIBUTES, start=1):
            conn.execute(
                """INSERT INTO T06_Physical_Attributes_Testing
                   (document_id, source_table_index, source_row, pass_name, attribute,
                    coa, units, lsl, lcl, target, ucl, usl, procedure, frequency, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (document_id, 5, row, *attr),
            )
        # Every fourth document had its testing table split across two Word
        # tables -- exactly the case the corpus work found and the V5.2 parser
        # recombines. Recorded in the audit as a lower-confidence content match.
        if index % 4 == 0:
            audit(5, "T06_Physical_Attributes_Testing", 4, 13)
            audit(6, "T06_Physical_Attributes_Testing", 3, 13,
                  method="content_signature", confidence=0.82,
                  details="Continuation table recombined into section 6; heading absent.")
        else:
            audit(5, "T06_Physical_Attributes_Testing", len(ATTRIBUTES), 13)

        # --- T07 Slitting Information ---------------------------------------
        conn.execute(
            """INSERT INTO T07_Slitting_Information
               (document_id, slit_width, core_id, splice_tape, width_tolerance,
                core_type, splice_type, cutoff, lineal_ft_per_roll, splice_location,
                eyemark_location, maximum_od, splice_stamp_flag, number_of_cuts,
                maximum_weight, maximum_splices, unwind, labels_across, core_tags,
                splice_code, splicing, end_of_roll_indicator, comments)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (document_id, f"{10 + index % 6}.250\"", "3\"", "Yellow 2 mil", "+/- 0.031\"",
             "Fibre", "Butt splice", f"{7 + index % 4}.500\"", "12,000", "Outside 3 wraps",
             "Left edge", "24\"", "Yes", str(2 + index % 3), "450 lb", "2", "Over",
             "1", "Required", f"SC-{index:03d}", "Flag both ends", "Red tail flag",
             "Do not use tape on idlers." if index % 5 == 0 else None),
        )
        audit(7, "T07_Slitting_Information", 8, 6)

        # --- T08 Packing Information ------------------------------------------
        conn.execute(
            """INSERT INTO T08_Packing_Information
               (document_id, pallet_size, poly_bags, pallet_labels, pallet_type,
                core_plugs, protective_corners, rolls_per_layer, roll_cradles,
                stretch_wrap_pallet, layers_per_pallet, tier_dividers, band_pallet,
                rolls_per_pallet, top_layer, wooden_top, feet_per_pallet, end_boards,
                packing_instructions, additional_instructions)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (document_id, "48\" x 40\"", "Yes - 2 mil", "2 per pallet", "4-way GMA",
             "Yes", "Yes - 4 corners", str(3 + index % 3), "No", "Yes - 5 revolutions",
             str(2 + index % 2), "Corrugated", "Yes - 2 straps",
             str((3 + index % 3) * (2 + index % 2)), "Corrugated cap", "No",
             f"{(3 + index % 3) * (2 + index % 2) * 12000:,}", "Yes",
             "Rolls packed eye-to-sky. Do not double stack.",
             "Notify customer 24 hours before shipment." if index % 4 == 1 else None),
        )
        audit(8, "T08_Packing_Information", 10, 6)

        # --- T09 Reporting Requirements ----------------------------------------
        # Older specs (the highest revision ages) predate formal COA reporting.
        if index % 5 != 3:
            conn.execute(
                """INSERT INTO T09_Reporting_Requirements
                   (document_id, coa_required, coa_recipients, coa_format,
                    coa_frequency, values_to_report_on_coa)
                   VALUES (?,?,?,?,?,?)""",
                (document_id, "Yes", f"quality@{folder.lower()}.example.com", "PDF via email",
                 "Every lot", "Bond strength, seal strength, total thickness, OTR"),
            )
            audit(9, "T09_Reporting_Requirements", 5, 2)

        # --- T10 Customer Sampling Requirements ---------------------------------
        if index % 4 != 3:
            conn.execute(
                """INSERT INTO T10_Customer_Sampling_Requirements
                   (document_id, samples_required, send_to, number_of_samples,
                    sample_preparation_labeling)
                   VALUES (?,?,?,?,?)""",
                (document_id, "Yes", f"{customer} - Incoming QA, {location}",
                 str(2 + index % 3),
                 "Label with spec number, lot number, production date and roll number."),
            )
            audit(10, "T10_Customer_Sampling_Requirements", 4, 2)

        # --- T11 Revision History -------------------------------------------------
        for rev in range(revision + 1):
            rev_date = issued - timedelta(days=180 * (revision - rev))
            conn.execute(
                """INSERT INTO T11_Revision_History
                   (document_id, source_table_index, source_row, revision_number,
                    who, revision_date, revision)
                   VALUES (?,?,?,?,?,?,?)""",
                (document_id, 11, rev + 1, str(rev), originator,
                 rev_date.strftime("%m/%d/%Y"), REVISION_NOTES[rev % len(REVISION_NOTES)]),
            )
        audit(11, "T11_Revision_History", revision + 1, 4)

        # --- Parser diagnostics ------------------------------------------------
        # A genuinely supplemental table: manufacturing content that belongs to
        # no numbered section, preserved in T00 rather than forced into T01-T11.
        if index % 5 == 0:
            conn.execute(
                """INSERT INTO T00_Unmapped_Tables
                   (document_id, source_table_index, preceding_heading, signature,
                    classification, suggested_section, mapping_method, raw_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (document_id, 12, "*** No Tape Allowed on Idlers ***",
                 "2x2|note|handling", "supplemental", "T07_Slitting_Information",
                 "content_signature",
                 '{"rows": [["Handling", "No tape on idlers"], '
                 '["Applies to", "All passes"]]}'),
            )
            audit(12, "supplemental", 2, 2, status="supplemental",
                  method="content_signature", confidence=0.61,
                  details="Handling note table retained as supplemental content.")

        # A table the parser could not place at all.
        if index % 7 == 3:
            conn.execute(
                """INSERT INTO T00_Unmapped_Tables
                   (document_id, source_table_index, preceding_heading, signature,
                    classification, suggested_section, mapping_method, raw_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (document_id, 13, "Customer Drawing Reference", "3x1|reference",
                 "unmapped", None, "none",
                 '{"rows": [["Drawing", "DWG-4471-C"], ["Sheet", "2 of 3"]]}'),
            )
            audit(13, "unmapped", 3, 1, status="unmapped", method="none",
                  confidence=0.0, details="No heading match and no content signature.")

    # One document failed to parse outright and therefore has no T00_Documents
    # row at all -- errors are keyed by path, which is why the admin panel reads
    # them separately rather than joining through the document table.
    conn.execute(
        """INSERT INTO T00_Ingestion_Errors
           (relative_path, filename, error_type, error_message, created_at)
           VALUES (?,?,?,?,?)""",
        ("Meridian/SP-4188_LEGACY.doc", "SP-4188_LEGACY.doc", "UnsupportedFormat",
         "Legacy .doc binary format; convert to .docx and re-run the parser.",
         _iso(imported)),
    )

    conn.executemany(
        """INSERT INTO T00_Ingestion_Audit
           (document_id, relative_path, filename, source_table_index, detected_section,
            row_count, column_count, status, mapping_method, mapping_confidence,
            details, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        audit_rows,
    )

    conn.commit()
    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "T00_Documents", "T01_Product_Description", "T03_Bill_of_Materials",
            "T05_Process_Routing", "T06_Physical_Attributes_Testing",
            "T11_Revision_History", "T00_Unmapped_Tables", "T00_Ingestion_Errors",
        )
    }
    conn.close()

    print(f"Demo staging database written to {output}")
    for table, count in counts.items():
        print(f"  {table:34} {count:>5} rows")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "Spec_Stage.db")
    parser.add_argument("--force", action="store_true", help="Replace an existing file.")
    args = parser.parse_args()
    build(args.output, force=args.force)


if __name__ == "__main__":
    main()
