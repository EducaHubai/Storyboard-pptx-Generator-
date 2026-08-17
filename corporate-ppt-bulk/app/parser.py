"""Parses an EDUCALLM-format training PDF into its real structure:

    acción formativa (certificado) → módulo formativo → unidad didáctica → epígrafe

Calibrated against a real sample export (MC-A1 · Introduction to AI in
Education), which turned out to differ substantially from the format this
was originally guessed at:

  - Structural labels are Spanish literals even when the content itself is
    English: "Módulo formativo", "Unidad didáctica N", "Índice".
  - The module title isn't "Module <code>: <name>" — it's a "Módulo
    formativo" label line followed by a separate "<code> · <name>" line,
    which then also repeats as a running header on every single page.
  - There is no visible "N.N" épigrafe code anywhere in the body. Épigrafe
    headings are plain text (e.g. "Historical evolution of AI") with
    nothing distinguishing them from H3 subheadings (e.g. "A. Conceptual
    Origins...") except font size, which plain-text extraction loses.
  - The one reliable source for exact épigrafe titles is the Índice (TOC)
    page: each numbered unit line ("1. U1 <title>") is followed by plain,
    unnumbered lines — the épigrafe titles for that unit, in order. Those
    exact strings are then found again as heading lines in the body to
    slice out each épigrafe's real content.

Uses `pdftotext -layout` (poppler-utils, installed in the Dockerfile).
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import os


class ParserError(Exception):
    """Raised when the PDF doesn't match the expected EDUCALLM structure —
    carries a human-readable explanation of what was expected."""


_TOC_HEADER_RE = re.compile(r"^Índice$", re.IGNORECASE)
_MODULO_LABEL_RE = re.compile(r"^Módulo formativo$", re.IGNORECASE)
_UNIDAD_LABEL_RE = re.compile(r"^Unidad did[aá]ctica\s+(\d+)$", re.IGNORECASE)
# "MC-A1 · Introduction to AI in Education" — code, a middle dot, a name.
_MODULE_CODE_LINE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9\-]*)\s*·\s*(.+)$")
# "1. U1 What is AI? History, types, and key concepts"
_TOC_UNIT_RE = re.compile(r"^(\d+)\.\s*U(\d+)\s+(.+)$")
_PAGE_FOOTER_RE = re.compile(r"^\d+\s*/\s*\d+$")


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


def _is_noise_line(stripped: str) -> bool:
    """Running header ("<code> · <name>", repeated on every page) or page
    footer ("N / total") — neither belongs in a slide's source text."""
    if not stripped:
        return True
    if _PAGE_FOOTER_RE.match(stripped):
        return True
    if _MODULE_CODE_LINE_RE.match(stripped):
        return True
    return False


def _collect_wrapped_title(lines: list[str], start: int) -> tuple[str, int]:
    """From `start`, concatenates consecutive short, non-sentence-ending
    lines (a wrapped heading) and returns (joined_title, next_index).
    Stops at the first blank/noise line (page footer or running header) —
    without that check, a short, punctuation-free footer like "3 / 64"
    (or the header repeating on every page) looks just like another
    wrapped title line and gets swallowed, along with whatever heading
    comes right after it."""
    parts = []
    i = start
    while i < len(lines):
        nxt = lines[i].strip()
        if not nxt:
            break
        if _is_noise_line(nxt):
            break
        if len(nxt) < 80 and not nxt.endswith((".", "?", "!", ":")):
            parts.append(nxt)
            i += 1
            continue
        break
    return " ".join(parts).strip(), i


def _parse_modules_and_toc(lines: list[str]):
    """Pass 1: find every "Módulo formativo" title (code, name, and the
    line index it starts at — needed to associate later units with the
    right module in a multi-module document), and build the TOC's
    unit → ordered épigrafe titles map."""
    modules = []  # list of {"modulo", "nombre", "start_index"}
    toc_by_unit: dict[int, list[str]] = {}
    in_toc = False
    current_toc_unit = None

    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()

        if _TOC_HEADER_RE.match(stripped):
            in_toc = True
            i += 1
            continue

        if in_toc:
            if _UNIDAD_LABEL_RE.match(stripped) or _MODULO_LABEL_RE.match(stripped):
                in_toc = False
                continue  # re-process this line outside the TOC branch
            unit_match = _TOC_UNIT_RE.match(stripped)
            if unit_match:
                current_toc_unit = int(unit_match.group(2))
                toc_by_unit.setdefault(current_toc_unit, [])
                i += 1
                continue
            if stripped and current_toc_unit is not None and not _PAGE_FOOTER_RE.match(stripped):
                toc_by_unit[current_toc_unit].append(stripped)
            i += 1
            continue

        if _MODULO_LABEL_RE.match(stripped):
            title_start = i + 1
            code = None
            name_parts = []
            j = title_start
            while j < n:
                nxt = lines[j].strip()
                if not nxt:
                    if code is None:
                        j += 1
                        continue
                    break  # blank line ends the wrapped title block
                if code is None:
                    m = _MODULE_CODE_LINE_RE.match(nxt)
                    if m:
                        code = m.group(1)
                        name_parts.append(m.group(2))
                        j += 1
                        continue
                    break
                if _is_noise_line(nxt):
                    break
                if len(nxt) < 80 and not nxt.endswith((".", "?", "!", ":")):
                    name_parts.append(nxt)
                    j += 1
                    continue
                break
            if code:
                modules.append({"modulo": code, "nombre": " ".join(name_parts).strip(), "start_index": i})
                i = j
                continue

        i += 1

    return modules, toc_by_unit


def _module_for_line(modules: list[dict], line_index: int) -> dict:
    """Last module whose title page starts at or before this line."""
    candidate = modules[0]
    for m in modules:
        if m["start_index"] <= line_index:
            candidate = m
        else:
            break
    return candidate


def _slice_unit_epigrafes(lines: list[str], unit_start: int, unit_end: int, titles: list[str]) -> list[dict]:
    """Finds each title as an exact heading line within lines[unit_start:unit_end]
    (in order) and returns [{"titulo", "texto"}] slicing the content between
    consecutive titles."""
    positions = []
    search_from = unit_start
    for title in titles:
        found_at = None
        for idx in range(search_from, unit_end):
            if lines[idx].strip() == title:
                found_at = idx
                break
        if found_at is None:
            # Título del Índice no encontrado tal cual en el cuerpo — se
            # omite en vez de inventar contenido para él.
            continue
        positions.append((title, found_at))
        search_from = found_at + 1

    epigrafes = []
    for idx, (title, pos) in enumerate(positions):
        content_start = pos + 1
        content_end = positions[idx + 1][1] if idx + 1 < len(positions) else unit_end
        body_lines = [
            lines[k].strip() for k in range(content_start, content_end)
            if not _is_noise_line(lines[k].strip())
        ]
        epigrafes.append({"titulo": title, "texto": "\n".join(body_lines).strip()})
    return epigrafes


def parse_document(pdf_bytes: bytes) -> dict:
    """Returns:
    {
      "certificado": "...",
      "modulos": [
        {"modulo": "MC-A1", "nombre": "...", "unidades": [
          {"unidad": 1, "nombre": "...", "epigrafes": [
            {"codigo": "1.1", "titulo": "...", "texto": "..."}
          ]}
        ]}
      ]
    }
    Raises ParserError if no module title or no Índice/TOC is found, or if
    the TOC lists épigrafes that can't be found as real body headings.
    """
    text = _pdf_to_text(pdf_bytes)
    lines = text.split("\n")

    modules, toc_by_unit = _parse_modules_and_toc(lines)

    if not modules:
        raise ParserError(
            "No 'Módulo formativo' title page found. This parser is calibrated to the "
            "EDUCALLM export format, which marks each module's title page with that "
            "exact label line — this PDF may use a different layout."
        )
    if not toc_by_unit:
        raise ParserError(
            "No 'Índice' (table of contents) found. It's the only reliable source for "
            "exact épigrafe titles in this format — without it, épigrafe boundaries "
            "in the body can't be trusted."
        )

    # Locate every "Unidad didáctica N" marker and its title-heading span,
    # associate it with the right module, then slice its épigrafes.
    unit_markers = []  # (unit_number, line_index_of_label)
    for i, line in enumerate(lines):
        m = _UNIDAD_LABEL_RE.match(line.strip())
        if m:
            unit_markers.append((int(m.group(1)), i))

    if not unit_markers:
        raise ParserError(
            "No 'Unidad didáctica N' heading found in the body, even though an Índice "
            "listing units was found — the document may be truncated or malformed."
        )

    for idx, (unit_n, label_idx) in enumerate(unit_markers):
        unit_end = unit_markers[idx + 1][1] if idx + 1 < len(unit_markers) else len(lines)
        module = _module_for_line(modules, label_idx)
        module.setdefault("unidades", [])

        # Skip past the repeated "U<n> <title>" heading directly under the label.
        unit_title, after_title_idx = _collect_wrapped_title(lines, label_idx + 1)

        titles = toc_by_unit.get(unit_n, [])
        epigrafes_raw = _slice_unit_epigrafes(lines, after_title_idx, unit_end, titles)
        epigrafes = [
            {"codigo": f"{unit_n}.{i + 1}", "titulo": e["titulo"], "texto": e["texto"]}
            for i, e in enumerate(epigrafes_raw)
        ]
        module["unidades"].append({"unidad": unit_n, "nombre": unit_title or f"Unidad {unit_n}", "epigrafes": epigrafes})

    total_epigrafes = sum(len(u["epigrafes"]) for m in modules for u in m.get("unidades", []))
    if total_epigrafes == 0:
        raise ParserError(
            "Índice listed épigrafe titles, but none of them could be found as exact "
            "heading lines in the body — nothing to generate decks from. This can happen "
            "if the PDF's line-wrapping differs from what this parser expects."
        )

    certificado = modules[0]["modulo"] + (" · " + modules[0]["nombre"] if modules[0]["nombre"] else "")
    for m in modules:
        m.pop("start_index", None)

    return {"certificado": certificado, "modulos": modules}
