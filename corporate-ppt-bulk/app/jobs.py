"""Document/job store + background orchestration.

Small jobs (≤50 épigrafes) stay exactly as before: pure in-memory,
zip assembled once at the end from bytes held on each task. Nothing
about that path changed.

Bigger jobs (>50 épigrafes — AUTOSAVE_THRESHOLD) get durability that
actually matters at that scale: each rendered .pptx is written straight
to DATA_DIR/jobs/{job_id}/decks/ as soon as it's done (never held in
memory), and the job's state is persisted to DATA_DIR/jobs/{job_id}/job.json
after every task status change. If the process dies mid-job (crash,
OOM, redeploy), load_persisted_jobs() — called once at startup — reloads
every such job, marks whatever was still "pending"/"running" as a
retryable "error" (never left silently stuck), and rebuilds the zip from
whatever decks already made it to disk. An open browser tab just keeps
polling GET /jobs/{job_id} through the outage and picks the recovered
state back up automatically — no new frontend concept needed, it's the
same "Retry N failed" flow used for any other failure.

Jobs can also be stopped mid-run (cancel_job): tasks not yet started are
marked "skipped" and left retryable; tasks already in flight (at most 2,
per the concurrency limiter) are left to finish rather than force-killed
— there's no safe way to abort a blocking OpenAI/Playwright call
mid-thread.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
import zipfile

import anyio

import author
import parser as pdf_parser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "render"))
import render as render_engine  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", "/srv/data")
os.makedirs(DATA_DIR, exist_ok=True)

# Above this many épigrafes, a job gets disk-backed durability (immediate
# per-deck writes + persisted job.json) instead of pure in-memory state —
# the point where losing everything to a crash actually hurts.
AUTOSAVE_THRESHOLD = 50

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
    each carrying everything author.generate_plan/render need — including
    the real source text, so a persisted/recovered job never needs to
    re-read the original document to retry a task."""
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
            "content_warning": None,
            "started_at": None,
            "finished_at": None,
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


# ── Persistence (autosave-tier jobs only) ───────────────────
def _job_dir(job_id: str) -> str:
    return os.path.join(DATA_DIR, "jobs", job_id)


def _decks_dir(job_id: str) -> str:
    return os.path.join(_job_dir(job_id), "decks")


def _deck_path(job_id: str, task: dict) -> str:
    return os.path.join(_decks_dir(job_id), _zip_arcname(task))


def _persist_job(job: dict) -> None:
    """Writes job.json for autosave-tier jobs only — a no-op for smaller
    jobs, which stay pure in-memory exactly as before. Every field on a
    job/task dict is already JSON-safe (autosave jobs never hold raw
    pptx bytes in the task dict — those go straight to disk instead), so
    this can serialize the dict directly."""
    if not job.get("autosave"):
        return
    d = _job_dir(job["job_id"])
    os.makedirs(d, exist_ok=True)
    tmp_path = os.path.join(d, "job.json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(job, f)
    os.replace(tmp_path, os.path.join(d, "job.json"))  # atomic on POSIX


def _build_zip_from_decks_dir(job_id: str) -> str:
    decks_dir = _decks_dir(job_id)
    zip_path = os.path.join(DATA_DIR, f"{job_id}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.isdir(decks_dir):
            for root, _dirs, files in os.walk(decks_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    zf.write(full, os.path.relpath(full, decks_dir))
    return zip_path


def load_persisted_jobs() -> int:
    """Call once at process startup. Reloads any autosave-tier jobs left
    on disk by a previous process (crash, OOM, redeploy) so a still-open
    browser tab's polling picks the job back up instead of hitting a 404.
    Any task that was "pending" or "running" when the process died is
    reset to "error" — nothing is left stuck silently; it's retryable via
    the normal retry_failed() flow, same as any other failure. Returns
    how many jobs were recovered."""
    jobs_root = os.path.join(DATA_DIR, "jobs")
    if not os.path.isdir(jobs_root):
        return 0
    recovered = 0
    for job_id in os.listdir(jobs_root):
        job_json = os.path.join(jobs_root, job_id, "job.json")
        if not os.path.isfile(job_json):
            continue
        try:
            with open(job_json, encoding="utf-8") as f:
                job = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        for t in job.get("tasks", []):
            if t.get("status") in ("pending", "running"):
                t["status"] = "error"
                t["error"] = "Interrupted — the server restarted before this finished. Retry to complete it."

        job["status"] = "done"
        job["cancel_requested"] = False
        zip_path = os.path.join(DATA_DIR, f"{job_id}.zip")
        if not os.path.isfile(zip_path):
            zip_path = _build_zip_from_decks_dir(job_id)
        job["zip_path"] = zip_path
        job["download_ready"] = True

        JOBS[job_id] = job
        _persist_job(job)
        recovered += 1
    return recovered


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
        "autosave": len(tasks) > AUTOSAVE_THRESHOLD,
        "cancel_requested": False,
        "cancelled": False,
        "created_at": time.time(),
    }
    JOBS[job_id] = job
    _persist_job(job)
    asyncio.create_task(_run_job(job_id))
    return job


def get_job(job_id: str) -> dict | None:
    return JOBS.get(job_id)


def get_job_zip_path(job_id: str) -> str | None:
    job = JOBS.get(job_id)
    if job and job["download_ready"]:
        return job["zip_path"]
    return None


def compute_eta_seconds(job: dict) -> float | None:
    """Rough remaining-time estimate from the average duration of tasks
    that have actually finished so far — None until at least one has, so
    the UI can show "estimating…" rather than a fake number from nothing."""
    durations = [
        t["finished_at"] - t["started_at"]
        for t in job["tasks"]
        if t.get("status") == "done" and t.get("started_at") and t.get("finished_at")
    ]
    if not durations:
        return None
    avg = sum(durations) / len(durations)
    remaining = sum(1 for t in job["tasks"] if t["status"] in ("pending", "running"))
    if remaining == 0:
        return 0.0
    effective_parallelism = min(2, remaining)
    return avg * remaining / effective_parallelism


def cancel_job(job_id: str) -> dict:
    """Stops a running job from starting any more not-yet-started tasks.
    Tasks already in flight (at most 2) are left to finish — there's no
    safe way to abort a blocking OpenAI/render call mid-thread. Everything
    skipped is retryable afterward exactly like a failed task."""
    job = JOBS.get(job_id)
    if job is None:
        raise KeyError(job_id)
    if job["status"] != "running":
        raise ValueError("Job isn't running")
    job["cancel_requested"] = True
    job["cancelled"] = True
    _persist_job(job)
    return job


def retry_failed(job_id: str) -> dict:
    """Re-runs only this job's failed/skipped tasks — reuses the job's
    original language/model already in memory (or reloaded from disk
    after a crash), so the caller never has to re-upload the PDF(s) or
    reselect scope just because one épigrafe (out of one, or one out of
    many) hit a transient failure, got skipped by a stop, or was
    interrupted by a restart. Newly-succeeded decks are appended to the
    existing zip rather than rebuilding it from scratch (small jobs) or
    written straight to disk and re-zipped (autosave-tier jobs)."""
    job = JOBS.get(job_id)
    if job is None:
        raise KeyError(job_id)
    if job["status"] == "running":
        raise ValueError("Job is still running — wait for it to finish before retrying")
    failed = [t for t in job["tasks"] if t["status"] in ("error", "skipped")]
    if not failed:
        raise ValueError("No failed tasks to retry")

    for t in failed:
        t["status"] = "pending"
        t["error"] = None
    job["status"] = "running"
    job["download_ready"] = False
    job["cancel_requested"] = False
    job["cancelled"] = False
    _persist_job(job)
    asyncio.create_task(_run_retry(job_id, failed))
    return job


def _render_one_task(task: dict, language: str, model: str | None, deck_path: str | None) -> None:
    """Runs in a worker thread: generate the plan (OpenAI, with its own
    internal retry), then render it to .pptx. Mutates task in place.
    When `deck_path` is given (autosave-tier jobs), the file is written
    straight to disk and never held in memory; otherwise its bytes are
    kept on the task dict until the job's final in-memory zip step."""
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

        task["filename"] = f"{_clean_filename(task['codigo'])} - {_clean_filename(task['titulo'])}.pptx"

        if deck_path:
            os.makedirs(os.path.dirname(deck_path), exist_ok=True)
            shutil.copyfile(out_path, deck_path)
        else:
            with open(out_path, "rb") as f:
                task["_pptx_bytes"] = f.read()

    task["content_warning"] = plan.get("contentWarning")


def _zip_arcname(task: dict) -> str:
    folder = _clean_filename(f"{task['modulo']} - {task['modulo_nombre']}")
    filename = task["filename"] or f"{_clean_filename(task['codigo'])} - {_clean_filename(task['titulo'])}.pptx"
    return f"{folder}/{filename}"


async def _run_tasks(job: dict, tasks: list[dict]) -> None:
    """Runs `tasks` (a subset or all of job["tasks"]) against the shared
    concurrency limiter. Used for a job's first pass and for
    retry_failed()'s re-run of just the failed/skipped subset. Honors
    cancel_job(): any task not yet started when the flag is set is marked
    "skipped" instead of run.

    The cancel check happens *inside* the acquired limiter slot, not
    before — checking before acquiring doesn't actually gate on anything,
    since asyncio schedules every task's coroutine up to its first real
    suspension point almost immediately. With the check before the
    limiter, a batch of 60 tasks could all race past it (all still
    "pending", flag still False) before cancel_job() is even called,
    leaving nothing to skip. Only 2 tasks can be past the `async with`
    at once, so the other N-2 are genuinely waiting — by the time a slot
    frees up, a since-set flag is reliably seen."""
    autosave = job.get("autosave", False)

    async def run_task(task):
        async with _CONCURRENCY_LIMITER:
            if job.get("cancel_requested") and task["status"] == "pending":
                task["status"] = "skipped"
                _persist_job(job)
                return

            task["status"] = "running"
            task["started_at"] = time.time()
            _persist_job(job)
            deck_path = _deck_path(job["job_id"], task) if autosave else None
            try:
                await anyio.to_thread.run_sync(_render_one_task, task, job["language"], job["model"], deck_path)
                task["status"] = "done"
            except Exception as e:
                task["status"] = "error"
                task["error"] = str(e)
            finally:
                task["finished_at"] = time.time()
                _persist_job(job)

    async with anyio.create_task_group() as tg:
        for t in tasks:
            tg.start_soon(run_task, t)


async def _run_job(job_id: str) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    _persist_job(job)
    await _run_tasks(job, job["tasks"])

    if job.get("autosave"):
        zip_path = _build_zip_from_decks_dir(job_id)
    else:
        zip_path = os.path.join(DATA_DIR, f"{job_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for task in job["tasks"]:
                if task["status"] != "done":
                    continue
                zf.writestr(_zip_arcname(task), task.pop("_pptx_bytes"))

    job["zip_path"] = zip_path
    job["download_ready"] = True
    job["status"] = "done"
    _persist_job(job)


async def _run_retry(job_id: str, tasks: list[dict]) -> None:
    job = JOBS[job_id]
    await _run_tasks(job, tasks)

    if job.get("autosave"):
        job["zip_path"] = _build_zip_from_decks_dir(job_id)
    else:
        # Append-only: previously successful tasks already have their bytes
        # written into the zip and popped from memory — only newly-done
        # tasks from this retry round need adding.
        newly_done = [t for t in tasks if t["status"] == "done"]
        if newly_done:
            with zipfile.ZipFile(job["zip_path"], "a", zipfile.ZIP_DEFLATED) as zf:
                for task in newly_done:
                    zf.writestr(_zip_arcname(task), task.pop("_pptx_bytes"))

    job["download_ready"] = True
    job["status"] = "done"
    _persist_job(job)
