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
def create_document(pdf_bytes: bytes) -> tuple[str, dict]:
    structure = pdf_parser.parse_document(pdf_bytes)
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


async def _run_job(job_id: str) -> None:
    job = JOBS[job_id]
    job["status"] = "running"

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
        for t in job["tasks"]:
            tg.start_soon(run_task, t)

    zip_path = os.path.join(DATA_DIR, f"{job_id}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for task in job["tasks"]:
            if task["status"] != "done":
                continue
            folder = _clean_filename(f"{task['modulo']} - {task['modulo_nombre']}")
            arcname = f"{folder}/{task['filename']}"
            zf.writestr(arcname, task.pop("_pptx_bytes"))

    job["zip_path"] = zip_path
    job["download_ready"] = True
    job["status"] = "done"
