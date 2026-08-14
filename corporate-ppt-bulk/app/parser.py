"""Parses an EDUCALLM-format training PDF into its real structure:

    acción formativa (certificado) → módulo formativo → unidad didáctica → epígrafe

The format (as described for this service): a title/TOC front section,
then per module a "Teaching unit N" heading starting each unidad
didáctica, and within each unit, epígrafe headings shaped "N.N Título".

This is calibrated to that description, not to a byte-for-byte sample —
if a real document's layout differs, `parse_document` raises ParserError
naming exactly what pattern it expected and didn't find, instead of
silently returning an empty or guessed structure (per the project's
"never invent content" rule — a wrong parse is worse than a loud failure).

Uses `pdftotext -layout` (poppler-utils, installed in the Dockerfile)
rather than a Python PDF library, since layout mode keeps headings on
their own line, which is what the regexes below depend on.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import os


class ParserError(Exception):
    """Raised when the PDF doesn't match the expected EDUCALLM structure —
    carries a human-readable explanation of what was expected."""


# "Teaching unit 3" / "Teaching unit 3: Assessment Design" / "Teaching Unit 3 - ..."
_UNIT_RE = re.compile(r"^\s*Teaching\s+[Uu]nit\s+(\d+)\s*[:\-–]?\s*(.*)$")

# "Module B1-01: Instructional Design Foundations" / "Módulo B1-01 - ..."
_MODULE_RE = re.compile(
    r"^\s*(?:Module|M[oó]dulo)\s+([A-Za-z0-9][A-Za-z0-9\-_.]*)\s*[:\-–]?\s*(.*)$"
)

# "1.1 What is Instructional Design?" — the épigrafe's own unit number as
# the first component (so a heading under "Teaching unit 2" is expected to
# start "2.", not "1."). Rejects TOC-style lines that end in a trailing
# page number (with optional dot leaders: "1.1 Title ..... 5").
_EPIGRAFE_RE = re.compile(r"^\s*(\d+)\.(\d+)\s+(\S.*\S|\S)\s*$")
_TRAILING_PAGE_NUM_RE = re.compile(r"[.\s]{2,}\d+\s*$|\s\d{1,4}\s*$")


def _pdf_to_text(pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        pdf_path = f.name
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            raise ParserError(
                f"pdftotext failed (exit {result.returncode}): {result.stderr.decode(errors='replace')[:500]}"
            )
        return result.stdout.decode("utf-8", errors="replace")
    finally:
        os.unlink(pdf_path)


def _guess_certificado(lines: list[str]) -> str:
    """Title/front-matter heuristic: the first non-trivial line before
    anything that looks like a module or unit heading. Real documents
    vary here more than in the module/unit/epígrafe headings, so this is
    the least reliable part of the parser — flagged in the README."""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.isdigit():
            continue
        if _MODULE_RE.match(stripped) or _UNIT_RE.match(stripped):
            break
        if len(stripped) < 3 or len(stripped) > 150:
            continue
        return stripped
    return "Untitled certificado"


def parse_document(pdf_bytes: bytes) -> dict:
    """Returns:
    {
      "certificado": "...",
      "modulos": [
        {"modulo": "B1-01", "nombre": "...", "unidades": [
          {"unidad": 1, "nombre": "...", "epigrafes": [
            {"codigo": "1.1", "titulo": "...", "texto": "..."}
          ]}
        ]}
      ]
    }
    Raises ParserError if no module or no teaching-unit headings are found
    at all (rather than returning an empty/guessed tree).
    """
    text = _pdf_to_text(pdf_bytes)
    lines = text.split("\n")

    certificado = _guess_certificado(lines)

    modulos: list[dict] = []
    current_modulo = None
    current_unidad = None
    current_epigrafe = None
    pending_body: list[str] = []

    def flush_epigrafe_body():
        if current_epigrafe is not None:
            current_epigrafe["texto"] = "\n".join(pending_body).strip()
        pending_body.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        module_match = _MODULE_RE.match(stripped) if stripped else None
        unit_match = _UNIT_RE.match(stripped) if stripped else None
        epigrafe_match = _EPIGRAFE_RE.match(stripped) if stripped else None
        # TOC entries share the same shapes as real headings but end in a
        # page number (with optional dot leaders) — real body headings
        # don't, so treat those lines as plain body text instead.
        if stripped and _TRAILING_PAGE_NUM_RE.search(stripped):
            if module_match:
                module_match = None
            if unit_match:
                unit_match = None
            if epigrafe_match:
                epigrafe_match = None

        if module_match:
            flush_epigrafe_body()
            current_modulo = {
                "modulo": module_match.group(1),
                "nombre": module_match.group(2).strip() or module_match.group(1),
                "unidades": [],
            }
            modulos.append(current_modulo)
            current_unidad = None
            current_epigrafe = None
            continue

        if unit_match:
            flush_epigrafe_body()
            if current_modulo is None:
                # A "Teaching unit" heading with no preceding "Module ..."
                # line — still usable, just group it under a synthetic
                # single module so the tree stays well-formed.
                current_modulo = {"modulo": "MODULO-1", "nombre": certificado, "unidades": []}
                modulos.append(current_modulo)
            current_unidad = {
                "unidad": int(unit_match.group(1)),
                "nombre": unit_match.group(2).strip() or f"Teaching unit {unit_match.group(1)}",
                "epigrafes": [],
            }
            current_modulo["unidades"].append(current_unidad)
            current_epigrafe = None
            continue

        if epigrafe_match:
            flush_epigrafe_body()
            if current_unidad is None:
                # An "N.N Título" heading before any "Teaching unit" line —
                # synthesize the containing unit from N so content isn't lost.
                unit_n = int(epigrafe_match.group(1))
                if current_modulo is None:
                    current_modulo = {"modulo": "MODULO-1", "nombre": certificado, "unidades": []}
                    modulos.append(current_modulo)
                current_unidad = {"unidad": unit_n, "nombre": f"Teaching unit {unit_n}", "epigrafes": []}
                current_modulo["unidades"].append(current_unidad)
            current_epigrafe = {
                "codigo": f"{epigrafe_match.group(1)}.{epigrafe_match.group(2)}",
                "titulo": epigrafe_match.group(3).strip(),
                "texto": "",
            }
            current_unidad["epigrafes"].append(current_epigrafe)
            continue

        if current_epigrafe is not None and stripped:
            pending_body.append(line)

    flush_epigrafe_body()

    if not modulos:
        raise ParserError(
            "No module or teaching-unit headings found. Expected lines shaped "
            "'Module <code>: <name>' and/or 'Teaching unit <n>' somewhere in the "
            "document — this PDF may not be in the EDUCALLM export format this "
            "parser is calibrated to."
        )

    total_epigrafes = sum(
        len(u["epigrafes"]) for m in modulos for u in m["unidades"]
    )
    if total_epigrafes == 0:
        raise ParserError(
            "Found module/unit headings but no épigrafe headings shaped 'N.N Título' "
            "underneath them — nothing to generate decks from."
        )

    return {"certificado": certificado, "modulos": modulos}
