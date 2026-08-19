"""In-memory document/job store + background orchestration.

Per the README's known v1 limits: documents and jobs live in this
process's RAM (a redeploy/restart loses them — only already-finished
zips under DATA_DIR survive if it's mounted as a volume), this isn't
built to scale horizontally, and each job renders 2 épigrafes at a time
(author.generate_plan + render) to avoid saturating OpenAI rate limits or
CPU (Chromium screenshots aren't free). A task that fails (OpenAI error,
still-invalid plan after retry, render error) is marked "error" with the
message — the rest of the job keeps going; re-run just that épigrafe with
a fresh job if needed.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import uuid
import zipfile

import anyio

import author
import parser as pdf_parser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "render"))
import render as render_engine  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", "/srv/data")
os.makedirs(DATA_DIR, exist_ok=True)

DOCUMENTS: dict[str, dict] = {}
JOBS: dict[str, dict] = {}

# Caps real concurrency at 2 (per README) using anyio's own worker-thread
# pool — the same mechanism Starlette/FastAPI use internally for sync
# endpoints, so it's guaranteed compatible with the ASGI server's
# thread/event-loop bridging (a raw concurrent.futures.ThreadPoolExecutor
# + loop.run_in_executor was tried first and deadlocked: the sync work
# completed but its future never resolved back onto the running loop).
_CONCURRENCY_LIMITER = anyio.CapacityLimiter(2)


def _clean_filename(s: str) -> str:
    s = re.sub(r"[^\w\s.-]", "", s or "", flags=re.UNICODE).strip()
    return re.sub(r"\s+", " ", s) or "untitled"


# ── Documents ────────────────────────────────────────────────
def _merge_structures(structures: list[dict]) -> dict:
    """Concatenates several PDFs' módulos into one combined structure, for
    the case where a course/acción formativa is split across one PDF per
    módulo. Raises ParserError if two uploaded PDFs claim the same módulo
    code — that's either a duplicate upload or two modules that collide,
    and either way resolve_selection() can't tell them apart by code."""
    modulos: list[dict] = []
    seen_codes: set[str] = set()
    certificado = ""
    for s in structures:
        if not certificado:
            certificado = s.get("certificado", "")
        for m in s["modulos"]:
            if m["modulo"] in seen_codes:
                raise pdf_parser.ParserError(
                    f"Module code '{m['modulo']}' appears in more than one uploaded PDF — "
                    "check you didn't upload the same module twice, or that two different "
                    "modules don't share a code."
                )
            seen_codes.add(m["modulo"])
            modulos.append(m)
    return {"certificado": certificado, "modulos": modulos}


def create_document(pdfs: list[tuple[str, bytes]]) -> tuple[str, dict]:
    """`pdfs` is a list of (filename, pdf_bytes) — one or more PDFs that
    together make up a single course/acción formativa (e.g. one PDF per
    módulo). Each is parsed independently, then merged into one structure
    sharing a single doc_id so scope selection/generation spans all of
    them at once."""
    structures = []
    for filename, pdf_bytes in pdfs:
        try:
            structures.append(pdf_parser.parse_document(pdf_bytes))
        except pdf_parser.ParserError as e:
            raise pdf_parser.ParserError(f"{filename}: {e}") from e
    structure = _merge_structures(structures)
    doc_id = uuid.uuid4().hex
    DOCUMENTS[doc_id] = structure
    return doc_id, structure


def get_document(doc_id: str) -> dict | None:
    return DOCUMENTS.get(doc_id)


# ── Selection → flat task list ──────────────────────────────
def _all_epigrafes_for_modulo(structure: dict, modulo_code: str):
    for m in structure["modulos"]:
        if m["modulo"] == modulo_code:
            for u in m["unidades"]:
                for e in u["epigrafes"]:
                    yield m, u, e


def resolve_selection(structure: dict, selection: dict) -> list[dict]:
    """Returns a flat list of task dicts (one per épigrafe to generate),
    each carrying everything author.generate_plan/render need."""
    level = selection.get("level")
    items = selection.get("items") or []
    certificado = structure.get("certificado", "")
    tasks: list[dict] = []

    def add_task(m, u, e):
        tasks.append({
            "modulo": m["modulo"],
            "modulo_nombre": m.get("nombre", m["modulo"]),
            "unidad": u["unidad"],
            "unidad_nombre": u.get("nombre", f"Teaching unit {u['unidad']}"),
            "codigo": e["codigo"],
            "titulo": e["titulo"],
            "texto": e["texto"],
            "certificado": certificado,
            "status": "pending",
            "error": None,
            "filename": None,
        })

    if level == "epigrafe":
        for item in items:
            modulo_code, unidad_n, codigo = item.get("modulo"), item.get("unidad"), item.get("codigo")
            found = False
            for m, u, e in _all_epigrafes_for_modulo(structure, modulo_code):
                if u["unidad"] == unidad_n and e["codigo"] == codigo:
                    add_task(m, u, e)
                    found = True
                    break
            if not found:
                raise ValueError(f"No épigrafe found for modulo={modulo_code} unidad={unidad_n} codigo={codigo}")

    elif level == "unidad":
        for item in items:
            modulo_code, unidad_n = item.get("modulo"), item.get("unidad")
            found_any = False
            for m, u, e in _all_epigrafes_for_modulo(structure, modulo_code):
                if u["unidad"] == unidad_n:
                    add_task(m, u, e)
                    found_any = True
            if not found_any:
                raise ValueError(f"No unidad {unidad_n} found in modulo={modulo_code}")

    elif level == "modulo":
        for item in items:
            # README example 2c passes bare module-code strings; also
            # accept {"modulo": code} for consistency with the other levels.
            modulo_code = item if isinstance(item, str) else item.get("modulo")
            found_any = False
            for m, u, e in _all_epigrafes_for_modulo(structure, modulo_code):
                add_task(m, u, e)
                found_any = True
            if not found_any:
                raise ValueError(f"No modulo '{modulo_code}' found in this document")

    elif level == "formacion":
        for m in structure["modulos"]:
            for u in m["unidades"]:
                for e in u["epigrafes"]:
                    add_task(m, u, e)

    else:
        raise ValueError(f"Unknown selection.level '{level}' — expected epigrafe/unidad/modulo/formacion")

    if not tasks:
        raise ValueError("Selection resolved to 0 épigrafes")
    return tasks


# ── Jobs ─────────────────────────────────────────────────────
def create_job(doc_id: str, selection: dict, language: str = "English", model: str | None = None) -> dict:
    structure = get_document(doc_id)
    if structure is None:
        raise ValueError(f"Unknown doc_id '{doc_id}' — has it been re-uploaded since the last redeploy?")

    tasks = resolve_selection(structure, selection)
    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "doc_id": doc_id,
        "language": language,
        "model": model,
        "status": "pending",
        "tasks": tasks,
        "zip_path": None,
        "download_ready": False,
        "error": None,
    }
    JOBS[job_id] = job
    asyncio.create_task(_run_job(job_id))
    return job


def get_job(job_id: str) -> dict | None:
    return JOBS.get(job_id)


def get_job_zip_path(job_id: str) -> str | None:
    job = JOBS.get(job_id)
    if job and job["download_ready"]:
        return job["zip_path"]
    return None


def retry_failed(job_id: str) -> dict:
    """Re-runs only this job's failed tasks — reuses the doc_id/structure
    and the job's original language/model already in memory, so the
    caller never has to re-upload the PDF(s) or reselect scope just
    because one épigrafe (out of one, or one out of many) hit a
    transient failure. Newly-succeeded decks are appended to the
    existing zip rather than rebuilding it from scratch."""
    job = JOBS.get(job_id)
    if job is None:
        raise KeyError(job_id)
    if job["status"] == "running":
        raise ValueError("Job is still running — wait for it to finish before retrying")
    failed = [t for t in job["tasks"] if t["status"] == "error"]
    if not failed:
        raise ValueError("No failed tasks to retry")

    for t in failed:
        t["status"] = "pending"
        t["error"] = None
    job["status"] = "running"
    job["download_ready"] = False
    asyncio.create_task(_run_retry(job_id, failed))
    return job


def _render_one_task(task: dict, language: str, model: str | None) -> None:
    """Runs in a worker thread: generate the plan (OpenAI, with its own
    internal retry), then render it to .pptx bytes. Mutates task in place."""
    unit_meta = {
        "unidad_nombre": task["unidad_nombre"],
        "modulo": task["modulo"],
        "modulo_nombre": task["modulo_nombre"],
        "certificado": task["certificado"],
    }
    plan = author.generate_plan(task, unit_meta, language=language, model=model)

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = os.path.join(tmp_dir, "deck.pptx")
        render_engine.assemble_pptx(plan, tmp_dir, out_path)
        try:
            render_engine.embed_fonts(out_path)
        except Exception as font_err:  # non-fatal: ship without embedded fonts
            print(f"WARNING: font embedding failed for {task['codigo']}: {font_err}", file=sys.stderr)
        with open(out_path, "rb") as f:
            task["_pptx_bytes"] = f.read()

    task["filename"] = f"{_clean_filename(task['codigo'])} - {_clean_filename(task['titulo'])}.pptx"
    task["content_warning"] = plan.get("contentWarning")


def _zip_arcname(task: dict) -> str:
    folder = _clean_filename(f"{task['modulo']} - {task['modulo_nombre']}")
    return f"{folder}/{task['filename']}"


async def _run_retry(job_id: str, tasks: list[dict]) -> None:
    job = JOBS[job_id]
    await _run_tasks(job, tasks)

    # Append-only: previously successful tasks already have their bytes
    # written into the zip and popped from memory (see _run_job below) —
    # only newly-done tasks from this retry round need adding.
    newly_done = [t for t in tasks if t["status"] == "done"]
    if newly_done:
        with zipfile.ZipFile(job["zip_path"], "a", zipfile.ZIP_DEFLATED) as zf:
            for task in newly_done:
                zf.writestr(_zip_arcname(task), task.pop("_pptx_bytes"))

    job["download_ready"] = True
    job["status"] = "done"


async def _run_tasks(job: dict, tasks: list[dict]) -> None:
    """Runs `tasks` (a subset or all of job["tasks"]) against the shared
    concurrency limiter. Used both for a job's first pass and for
    retry_failed()'s re-run of just the failed subset."""
    async def run_task(task):
        task["status"] = "running"
        try:
            await anyio.to_thread.run_sync(
                _render_one_task, task, job["language"], job["model"],
                limiter=_CONCURRENCY_LIMITER,
            )
            task["status"] = "done"
        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)

    # _CONCURRENCY_LIMITER caps real concurrency at 2; gather here just lets
    # all tasks queue against it without a separate semaphore layer.
    async with anyio.create_task_group() as tg:
        for t in tasks:
            tg.start_soon(run_task, t)


async def _run_job(job_id: str) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    await _run_tasks(job, job["tasks"])

    zip_path = os.path.join(DATA_DIR, f"{job_id}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for task in job["tasks"]:
            if task["status"] != "done":
                continue
            zf.writestr(_zip_arcname(task), task.pop("_pptx_bytes"))

    job["zip_path"] = zip_path
    job["download_ready"] = True
    job["status"] = "done"
