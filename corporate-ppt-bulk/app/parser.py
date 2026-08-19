"""Parses a training PDF into its real structure:

    acción formativa (certificado) → módulo formativo → unidad didáctica → epígrafe

Two strategies, tried in order:

1. `_parse_educallm_format` — a fast, free, deterministic regex parser
   calibrated against one real EDUCALLM export (MC-A1 · Introduction to AI
   in Education): Spanish structural labels ("Módulo formativo", "Unidad
   didáctica N", "Índice") even when the content itself is English, no
   visible "N.N" épigrafe codes, and the Índice (TOC) as the only reliable
   source of exact épigrafe titles (matched verbatim as heading lines in
   the body to slice out real content). See the functions below for the
   full detail — this only matches documents shaped exactly like that one.

2. `_parse_generic_via_llm` — used only when #1 raises ParserError (the
   document doesn't match that exact shape — e.g. a different EDUCALLM
   course template with English labels and no Índice at all, seen in
   practice). Hand-coding a new regex strategy per template doesn't scale
   as more show up, so this asks the OpenAI model already used elsewhere
   in this app to identify the módulo/unidad/épigrafe hierarchy from the
   raw text instead. It still never invents content: the model is asked
   for heading text VERBATIM, and the code only accepts a heading if that
   exact string (tolerant of line-wrap whitespace) is actually found in
   the source — any heading it can't verify is dropped, not fabricated.
   This costs one OpenAI call per upload, but only for documents the free
   regex path can't already handle.

Uses `pdftotext -layout` (poppler-utils, installed in the Dockerfile).
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import os

from openai import OpenAI


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


def _parse_educallm_format(text: str) -> dict:
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


# ── Generic fallback: LLM-identified structure, verbatim-matched slicing ──

_STRUCTURE_MODEL = os.environ.get("OPENAI_STRUCTURE_MODEL", "gpt-4.1-mini")
# Character budget for the structure-identification call. Generous enough
# for a several-hundred-page export (gpt-4.1-mini's context comfortably
# fits this many tokens) — only truncated as a last resort so an
# unusually large document degrades gracefully instead of erroring outright.
_MAX_STRUCTURE_CHARS = 700_000
_structure_client: OpenAI | None = None


def _get_structure_client() -> OpenAI:
    global _structure_client
    if _structure_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ParserError(
                "This PDF doesn't match the known EDUCALLM format, and OPENAI_API_KEY isn't "
                "configured for the generic structure-detection fallback to run."
            )
        _structure_client = OpenAI(api_key=api_key)
    return _structure_client


_STRUCTURE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "certificado": {"type": ["string", "null"]},
        "running_header": {
            "type": ["string", "null"],
            "description": (
                "The exact text of a header/footer line repeated on most pages (e.g. a "
                "running module title), copied verbatim, so it can be stripped from "
                "extracted content. Null if there isn't one."
            ),
        },
        "modulos": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "modulo": {"type": "string", "description": "Module code, e.g. 'C04-01'."},
                    "nombre": {
                        "type": "string",
                        "description": (
                            "The module's title heading, EXACTLY as it appears in the source "
                            "text — same characters, case, and punctuation. Used to locate it "
                            "again by exact match."
                        ),
                    },
                    "unidades": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "unidad": {"type": "integer"},
                                "nombre": {
                                    "type": "string",
                                    "description": "The unit's heading, verbatim as in the source text.",
                                },
                                "epigrafes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "titulo": {
                                                "type": "string",
                                                "description": "The épigrafe/section heading, verbatim as in the source text.",
                                            },
                                        },
                                        "required": ["titulo"],
                                    },
                                },
                            },
                            "required": ["unidad", "nombre", "epigrafes"],
                        },
                    },
                },
                "required": ["modulo", "nombre", "unidades"],
            },
        },
    },
    "required": ["certificado", "running_header", "modulos"],
}

_STRUCTURE_SYSTEM_PROMPT = """You read the raw text of a training PDF, extracted via pdftotext, and
identify its real structure: módulo formativo (module) → unidad didáctica
(unit) → epígrafe (section). Formats vary — labels may be in Spanish or
English, and there may or may not be a table of contents.

Rules:
- Every heading you return (module title, unit title, épigrafe title)
  must be copied EXACTLY as it appears in the source text — same
  characters, case, and punctuation, character-for-character. Do not
  paraphrase, translate, or clean it up. It will be located again by an
  exact text match, so an inexact copy means that section is silently
  dropped.
- If you're not confident a heading is real (vs. body text that merely
  looks like one), leave it out rather than guessing.
- If you can't identify any reliable módulo/unidad/épigrafe structure at
  all, return an empty modulos list — don't force a structure onto text
  that doesn't have one.
- If a header or footer line repeats near-identically across most pages
  (e.g. a running module title, or a page number), copy ONE exact
  instance of it into running_header so it can be stripped from content
  — or null if you don't see one.
"""


def _extract_structure_via_llm(text: str) -> dict:
    client = _get_structure_client()
    trimmed = text[:_MAX_STRUCTURE_CHARS]
    try:
        response = client.chat.completions.create(
            model=_STRUCTURE_MODEL,
            messages=[
                {"role": "system", "content": _STRUCTURE_SYSTEM_PROMPT},
                {"role": "user", "content": trimmed},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "document_structure", "strict": True, "schema": _STRUCTURE_SCHEMA},
            },
        )
        return json.loads(response.choices[0].message.content)
    except ParserError:
        raise
    except Exception as e:
        raise ParserError(f"Generic structure detection failed (OpenAI call error): {e}") from e


def _find_verbatim(text: str, needle: str, start: int) -> tuple[int, int] | None:
    """Finds `needle` in `text` at or after `start`. Tries an exact
    substring match first; if the heading wraps across a line break that
    the model's verbatim copy doesn't reflect, retries with runs of
    whitespace (including newlines) collapsed to a single space in both
    the needle and a mapped copy of the haystack, so the original offsets
    can still be recovered."""
    if not needle:
        return None
    idx = text.find(needle, start)
    if idx != -1:
        return idx, idx + len(needle)

    collapsed_needle = re.sub(r"\s+", " ", needle).strip()
    if not collapsed_needle:
        return None

    window = text[start:]
    mapped_chars: list[str] = []
    index_map: list[int] = []
    prev_space = False
    for i, ch in enumerate(window):
        if ch.isspace():
            if not prev_space:
                mapped_chars.append(" ")
                index_map.append(i)
            prev_space = True
        else:
            mapped_chars.append(ch)
            index_map.append(i)
            prev_space = False
    collapsed_window = "".join(mapped_chars)
    cidx = collapsed_window.find(collapsed_needle)
    if cidx == -1:
        return None
    orig_start = start + index_map[cidx]
    orig_end = start + index_map[cidx + len(collapsed_needle) - 1] + 1
    return orig_start, orig_end


def _strip_generic_noise(chunk: str, running_header: str | None) -> str:
    header_stripped = (running_header or "").strip()
    out = []
    for line in chunk.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _PAGE_FOOTER_RE.match(stripped):
            continue
        if header_stripped and stripped == header_stripped:
            continue
        out.append(stripped)
    return "\n".join(out).strip()


def _parse_generic_via_llm(text: str) -> dict:
    structure = _extract_structure_via_llm(text)
    modulos_in = structure.get("modulos") or []
    if not modulos_in:
        raise ParserError(
            "Generic structure detection (via OpenAI) couldn't confidently identify any "
            "módulo/unidad/épigrafe hierarchy in this document — it may not be a "
            "training-unit document, or its structure is too irregular to detect."
        )

    running_header = structure.get("running_header")
    # Flat list of every accepted heading's start position (any level) —
    # used so each épigrafe's content stops at the very next heading of
    # ANY kind, not just the next épigrafe, so it never bleeds into the
    # next unit's or module's material.
    all_starts: list[int] = []
    cursor = 0
    modulos_out = []

    for m in modulos_in:
        m_name = (m.get("nombre") or "").strip()
        m_pos = _find_verbatim(text, m_name, cursor) if m_name else None
        if m_pos:
            all_starts.append(m_pos[0])
            cursor = m_pos[1]
        unidades_out = []
        for u in m.get("unidades") or []:
            u_name = (u.get("nombre") or "").strip()
            u_pos = _find_verbatim(text, u_name, cursor) if u_name else None
            if u_pos:
                all_starts.append(u_pos[0])
                cursor = u_pos[1]
            epi_raw = []
            for e in u.get("epigrafes") or []:
                title = (e.get("titulo") or "").strip()
                if not title:
                    continue
                pos = _find_verbatim(text, title, cursor)
                if pos is None:
                    # The model proposed a heading that isn't actually in the
                    # text (or copied it inexactly) — drop it, don't invent
                    # content for it.
                    continue
                all_starts.append(pos[0])
                cursor = pos[1]
                epi_raw.append({"titulo": title, "start": pos[0], "end": pos[1]})
            if epi_raw:
                unidades_out.append({"unidad": u.get("unidad"), "nombre": u_name or f"Unit {u.get('unidad')}", "_raw": epi_raw})
        if unidades_out:
            modulos_out.append({"modulo": m.get("modulo") or "", "nombre": m_name, "unidades": unidades_out})

    all_starts.sort()

    def _next_boundary_after(pos: int) -> int:
        for p in all_starts:
            if p > pos:
                return p
        return len(text)

    final_modulos = []
    for m in modulos_out:
        unidades_final = []
        for u in m["unidades"]:
            epigrafes_final = []
            for i, e in enumerate(u["_raw"]):
                content_end = _next_boundary_after(e["start"])
                texto = _strip_generic_noise(text[e["end"]:content_end], running_header)
                epigrafes_final.append({"codigo": f"{u['unidad']}.{i + 1}", "titulo": e["titulo"], "texto": texto})
            unidades_final.append({"unidad": u["unidad"], "nombre": u["nombre"], "epigrafes": epigrafes_final})
        final_modulos.append({"modulo": m["modulo"], "nombre": m["nombre"], "unidades": unidades_final})

    total_epigrafes = sum(len(u["epigrafes"]) for m in final_modulos for u in m["unidades"])
    if total_epigrafes == 0:
        raise ParserError(
            "Generic structure detection proposed a hierarchy, but none of its épigrafe "
            "headings could be found verbatim in the actual text — nothing to generate "
            "decks from."
        )

    certificado = structure.get("certificado") or (
        f"{final_modulos[0]['modulo']} — {final_modulos[0]['nombre']}".strip(" —")
        if final_modulos else ""
    )
    return {"certificado": certificado, "modulos": final_modulos}


def parse_document(pdf_bytes: bytes) -> dict:
    """Tries the free/deterministic EDUCALLM-shaped regex parser first;
    if the document doesn't match that exact structure, falls back to
    LLM-identified generic structure detection (see module docstring)."""
    text = _pdf_to_text(pdf_bytes)
    try:
        return _parse_educallm_format(text)
    except ParserError as educallm_err:
        try:
            return _parse_generic_via_llm(text)
        except ParserError as generic_err:
            raise ParserError(
                f"Doesn't match the known EDUCALLM format ({educallm_err}), and generic "
                f"structure detection also failed: {generic_err}"
            ) from generic_err
