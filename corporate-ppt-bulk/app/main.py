"""FastAPI app wiring: upload a PDF, pick a scope, get a zip of .pptx decks.

    POST /documents          — upload PDF, parse, return {doc_id, structure}
    POST /jobs                — start a background generation job for a scope
    GET  /jobs/{job_id}       — poll status (per-épigrafe progress/errors)
    GET  /jobs/{job_id}/download — download the finished zip
    GET  /health              — liveness + config check

No auth layer here on purpose — Coolify's own access protection is the
boundary (see README).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import jobs

app = FastAPI(title="corporate-ppt-bulk")


@app.get("/health")
def health():
    return {
        "ok": True,
        "openaiConfigured": bool(os.environ.get("OPENAI_API_KEY")),
        "defaultModel": os.environ.get("OPENAI_MODEL", "gpt-4.1"),
    }


@app.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    if file.content_type not in ("application/pdf", "application/x-pdf") and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Expected a PDF file")
    pdf_bytes = await file.read()
    try:
        doc_id, structure = jobs.create_document(pdf_bytes)
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


@app.get("/jobs/{job_id}/download")
def download_job(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job_id")
    zip_path = jobs.get_job_zip_path(job_id)
    if zip_path is None:
        raise HTTPException(409, "Job not ready yet — poll GET /jobs/{job_id} until download_ready is true")
    return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}.zip")
