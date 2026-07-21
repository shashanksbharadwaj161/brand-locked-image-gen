#!/usr/bin/env python3
"""
Brand-Locked Image Generator — FastAPI service
==============================================
One process serves both the JSON/SSE API and the single-page frontend, so the
whole app runs with a single command and has no cross-origin configuration:

    uvicorn main:app --host 0.0.0.0 --port 8000
    # then open http://localhost:8000

API keys are never stored: they arrive per request from the browser, are used
in memory, and are discarded when the request ends. Uploaded logos are written
to a unique temp file only for the duration of a generation run, then deleted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import gbn_prompts as gp
from generators import (
    FatalGenerationError,
    make_generator,
    provider_catalog,
)
from orchestrator import preview_prompts, run_jobs

FRONTEND_DIR = (Path(__file__).resolve().parent.parent / "frontend")

app = FastAPI(title="Brand-Locked Image Generator", version="1.0.0")

# Keys are per-request from the client, so permissive CORS is safe and lets the
# frontend be hosted separately (e.g. Vercel) if ever split from the backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",   # disable proxy buffering so events flush live
}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ProductItem(BaseModel):
    product_name: str
    size: str = ""
    category: str = ""


class PreviewRequest(BaseModel):
    product_name: str
    size: str = ""
    category: str = ""
    brand_name: str = gp.DEFAULT_BRAND_NAME


class TestConnectionRequest(BaseModel):
    provider: str
    api_key: str = ""


class GenerateRequest(BaseModel):
    provider: str
    api_key: str = ""
    logo_base64: str = ""
    brand_name: str = gp.DEFAULT_BRAND_NAME
    product_name: str
    size: str = ""
    category: str = ""
    custom_prompts: Optional[Dict[str, str]] = None
    custom_negatives: Optional[Dict[str, str]] = None
    raw_prompts: Optional[Dict[str, str]] = None
    only_slots: Optional[List[str]] = None
    dry_run: bool = False


class BatchRequest(BaseModel):
    provider: str
    api_key: str = ""
    logo_base64: str = ""
    brand_name: str = gp.DEFAULT_BRAND_NAME
    products: List[ProductItem] = Field(default_factory=list)
    dry_run: bool = False


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------
def _sse(events) -> StreamingResponse:
    def stream():
        try:
            for ev in events:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:  # noqa: BLE001 - always close the stream cleanly
            payload = {"type": "fatal", "message": f"server error: {e}"}
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers=_SSE_HEADERS)


# ---------------------------------------------------------------------------
# JSON endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "profiles": len(gp.PROFILES)}


@app.get("/api/providers")
def providers():
    return {"providers": provider_catalog()}


@app.post("/api/audit")
def audit():
    issues = gp.audit_uniqueness()
    return {"passed": not issues, "issues": issues}


@app.post("/api/preview-prompts")
def preview(req: PreviewRequest):
    """Works for ANY product name: a curated profile if one matches, else the
    universal generic engine. Only fails on a blank product name."""
    try:
        prompts, source = preview_prompts(req.product_name, req.size,
                                          req.category, req.brand_name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "prompts": prompts, "source": source}


@app.post("/api/test-connection")
def test_connection(req: TestConnectionRequest):
    try:
        gen = make_generator(req.provider, req.api_key, dry_run=False)
    except FatalGenerationError as e:
        return {"ok": False, "message": str(e)}
    try:
        ok, message = gen.test_connection()
    except Exception as e:  # noqa: BLE001 - report, never 500 on a probe
        return {"ok": False, "message": f"connection check failed: {e}"}
    return {"ok": ok, "message": message}


# ---------------------------------------------------------------------------
# SSE generation endpoints
# ---------------------------------------------------------------------------
@app.post("/api/generate")
def generate(req: GenerateRequest):
    custom = req.custom_prompts if (req.custom_prompts and
                                    any(v.strip() for v in
                                        req.custom_prompts.values())) else None
    jobs = [(req.product_name, req.size, req.category)]
    return _sse(run_jobs(
        provider=req.provider, api_key=req.api_key, dry_run=req.dry_run,
        logo_base64=req.logo_base64, brand_name=req.brand_name, jobs=jobs,
        custom_prompts=custom, custom_negatives=req.custom_negatives,
        raw_prompts=req.raw_prompts, only_slots=req.only_slots))


@app.post("/api/generate-batch")
def generate_batch(req: BatchRequest):
    jobs = [(p.product_name, p.size, p.category) for p in req.products
            if p.product_name.strip()]
    return _sse(run_jobs(
        provider=req.provider, api_key=req.api_key, dry_run=req.dry_run,
        logo_base64=req.logo_base64, brand_name=req.brand_name, jobs=jobs))


# ---------------------------------------------------------------------------
# Frontend (mounted last so /api/* and /health match first)
# ---------------------------------------------------------------------------
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True),
              name="frontend")
else:  # pragma: no cover - only if the build layout is broken
    @app.get("/")
    def _missing_frontend():
        return JSONResponse(
            {"error": f"frontend directory not found at {FRONTEND_DIR}"},
            status_code=500)
