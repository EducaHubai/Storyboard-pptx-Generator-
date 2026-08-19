"""FastAPI app wiring: upload a PDF, pick a scope, get a zip of .pptx decks.

    GET  /                     — single-page UI (static/index.html)
    POST /documents          — upload PDF, parse, return {doc_id, structure}
    POST /jobs                — start a background generation job for a scope
    GET  /jobs/{job_id}       — poll status (per-épigrafe progress/errors, ETA)
    POST /jobs/{job_id}/cancel — stop starting any more not-yet-started épigrafes
    POST /jobs/{job_id}/retry — re-run only this job's failed/skipped épigrafes
    GET  /jobs/{job_id}/download — download the finished zip
    GET  /health              — liveness + config check

Jobs over jobs.AUTOSAVE_THRESHOLD épigrafes are persisted to disk as they
run; load_persisted_jobs() (called at startup, below) recovers them after
a crash/redeploy so an already-open browser tab's polling picks the job
back up instead of hitting a 404.

No auth layer here on purpose — Coolify's own access protection is the
boundary (see README).
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import jobs

app = FastAPI(title="corporate-ppt-bulk")

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.on_event("startup")
def _recover_persisted_jobs():
    recovered = jobs.load_persisted_jobs()
    if recovered:
        print(f"Recovered {recovered} autosave job(s) from a previous run", file=sys.stderr)

_PDF_CONTENT_TYPES = ("application/pdf", "application/x-pdf")
_ZIP_CONTENT_TYPES = ("application/zip", "application/x-zip-compressed", "application/x-zip")
# Guard against zip bombs — total *decompressed* PDF bytes per uploaded zip.
_MAX_ZIP_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def _extract_pdfs_from_zip(zip_filename: str, raw: bytes) -> list[tuple[str, bytes]]:
    """Pulls every .pdf entry out of an uploaded zip, skipping directories
    and macOS junk (__MACOSX/, ._* resource forks). Labels each extracted
    PDF as "zipname:path/inside.pdf" so error messages and duplicate-module
    detection stay traceable to where it came from."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, f"'{zip_filename}' isn't a valid zip file")

    pdfs: list[tuple[str, bytes]] = []
    total_uncompressed = 0
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            base = os.path.basename(name)
            if not base.lower().endswith(".pdf"):
                continue
            if "__MACOSX" in name or base.startswith("."):
                continue
            total_uncompressed += info.file_size
            if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    400, f"'{zip_filename}' is too large once decompressed (PDFs exceed 200MB total)"
                )
            pdfs.append((f"{zip_filename}:{name}", zf.read(info)))

    if not pdfs:
        raise HTTPException(400, f"'{zip_filename}' doesn't contain any PDFs")
    return pdfs


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(_STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/health")
def health():
    return {
        "ok": True,
        "openaiConfigured": bool(os.environ.get("OPENAI_API_KEY")),
        "defaultModel": os.environ.get("OPENAI_MODEL", "gpt-4.1"),
    }


@app.post("/documents")
async def upload_document(files: list[UploadFile] = File(...)):
    """Accepts one or more PDFs — a single unit/course document, several
    PDFs that together make up one course/acción formativa (one per módulo,
    typically), or a zip bundling them (nested folders are fine — every
    .pdf entry inside is pulled out). All are parsed and merged into a
    single doc_id/structure so scope selection and bulk generation span
    all of them at once."""
    if not files:
        raise HTTPException(400, "No files uploaded")
    pdfs: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        name_lower = f.filename.lower()
        if name_lower.endswith(".zip") or f.content_type in _ZIP_CONTENT_TYPES:
            pdfs.extend(_extract_pdfs_from_zip(f.filename, raw))
        elif name_lower.endswith(".pdf") or f.content_type in _PDF_CONTENT_TYPES:
            pdfs.append((f.filename, raw))
        else:
            raise HTTPException(400, f"Expected a PDF or zip file, got '{f.filename}'")
    try:
        doc_id, structure = jobs.create_document(pdfs)
    except jobs.pdf_parser.ParserError as e:
        raise HTTPException(422, str(e))
    return {"doc_id": doc_id, "structure": structure}


class Selection(BaseModel):
    level: str
    items: list[Any] = []


class JobRequest(BaseModel):
    doc_id: str
    selection: Selection
    language: Optional[str] = "English"
    model: Optional[str] = None


@app.post("/jobs")
async def create_job(req: JobRequest):
    try:
        job = jobs.create_job(
            doc_id=req.doc_id,
            selection=req.selection.model_dump(),
            language=req.language or "English",
            model=req.model,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _job_view(job)


def _job_view(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "doc_id": job["doc_id"],
        "status": job["status"],
        "download_ready": job["download_ready"],
        "cancelled": job.get("cancelled", False),
        "estimated_seconds_remaining": jobs.compute_eta_seconds(job),
        "tasks": [
            {
                "modulo": t["modulo"],
                "unidad": t["unidad"],
                "codigo": t["codigo"],
                "titulo": t["titulo"],
                "status": t["status"],
                "error": t["error"],
                "filename": t["filename"],
                "contentWarning": t.get("content_warning"),
            }
            for t in job["tasks"]
        ],
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job_id")
    return _job_view(job)


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Stops a running job from starting any more not-yet-started
    épigrafes. Up to 2 already in flight (the concurrency cap) are left
    to finish rather than force-killed. Everything skipped is retryable
    afterward via POST /jobs/{job_id}/retry, same as a real failure."""
    try:
        job = jobs.cancel_job(job_id)
    except KeyError:
        raise HTTPException(404, "Unknown job_id")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _job_view(job)


@app.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    """Re-runs just this job's failed or skipped (stopped) tasks — whether
    that's the one épigrafe in a single-item job, or a handful out of a
    larger batch — without re-uploading the PDF(s) or reselecting scope.
    Succeeded tasks are left untouched and their decks stay in the zip."""
    try:
        job = jobs.retry_failed(job_id)
    except KeyError:
        raise HTTPException(404, "Unknown job_id")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _job_view(job)


@app.get("/jobs/{job_id}/download")
def download_job(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job_id")
    zip_path = jobs.get_job_zip_path(job_id)
    if zip_path is None:
        raise HTTPException(409, "Job not ready yet — poll GET /jobs/{job_id} until download_ready is true")
    return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}.zip")
