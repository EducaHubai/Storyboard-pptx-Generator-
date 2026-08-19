"""FastAPI app wiring: upload a PDF, pick a scope, get a zip of .pptx decks.

    GET  /                     — single-page UI (static/index.html)
    POST /documents          — upload PDF, parse, return {doc_id, structure}
    POST /jobs                — start a background generation job for a scope
    GET  /jobs/{job_id}       — poll status (per-épigrafe progress/errors)
    POST /jobs/{job_id}/retry — re-run only this job's failed épigrafes
    GET  /jobs/{job_id}/download — download the finished zip
    GET  /health              — liveness + config check

No auth layer here on purpose — Coolify's own access protection is the
boundary (see README).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import jobs

app = FastAPI(title="corporate-ppt-bulk")

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


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
    """Accepts one or more PDFs — a single unit/course document, or several
    PDFs that together make up one course/acción formativa (one per módulo,
    typically). All are parsed and merged into a single doc_id/structure so
    scope selection and bulk generation span all of them at once."""
    if not files:
        raise HTTPException(400, "No files uploaded")
    pdfs = []
    for f in files:
        if f.content_type not in ("application/pdf", "application/x-pdf") and not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Expected a PDF file, got '{f.filename}'")
        pdfs.append((f.filename, await f.read()))
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


@app.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    """Re-runs just this job's failed tasks — whether that's the one
    épigrafe in a single-item job, or a handful out of a larger batch —
    without re-uploading the PDF(s) or reselecting scope. Succeeded tasks
    are left untouched and their decks stay in the zip."""
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
