"""Optional FastAPI wrapper:  uvicorn api:app --reload
POST /screen   {"input_dir": "./resumes"}  -> runs the pipeline, stores + returns the batch summary
GET  /results  -> the full latest result
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from resume_screener.config import Settings  # noqa: E402
from resume_screener.pipeline import run_pipeline_async  # noqa: E402

app = FastAPI(title="AI Resume Screener")
_latest: dict | None = None


class ScreenRequest(BaseModel):
    input_dir: str = "./resumes"
    use_llm: bool = True


@app.post("/screen")
async def screen(req: ScreenRequest):
    global _latest
    try:
        _latest = await run_pipeline_async(Path(req.input_dir), Settings(), analyzer="auto" if req.use_llm else None)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _latest["batch_summary"]


@app.get("/results")
async def results():
    if _latest is None:
        raise HTTPException(status_code=404, detail="No run yet - POST /screen first")
    return _latest
