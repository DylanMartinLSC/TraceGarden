import asyncio
from pathlib import Path
import xml.etree.ElementTree as ET
import io
import re
import zipfile
from importlib.metadata import version

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError, BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .core import Options, trace, export, MAX_BYTES
from .exporters import ExportOptions
from .svgdoc import EditRequest, edit_vector, validate_svg, serialize
from .jobs import JobManager
from contextlib import asynccontextmanager

jobs = JobManager()


@asynccontextmanager
async def lifespan(app):
    global jobs, gate
    # Tasks and semaphores belong to the event loop of this app session.
    # A later session must not inherit tasks from a loop that has shut down.
    jobs = JobManager()
    gate = asyncio.Semaphore(1)
    try:
        yield
    finally:
        await jobs.close()


app = FastAPI(title="TraceGarden", version=version("tracegarden"), lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
)
STATIC = Path(__file__).parent / "static"
gate = asyncio.Semaphore(1)


@app.middleware("http")
async def local_only(request: Request, call_next):
    length = request.headers.get("content-length")
    maximum = (
        MAX_BYTES + 1024 * 1024
        if request.url.path in {"/api/jobs", "/api/trace"}
        else 60 * 1024 * 1024
    )
    if length and (not length.isdigit() or int(length) > maximum):
        return Response("Request exceeds this endpoint's size limit.", status_code=413)
    origin = request.headers.get("origin")
    if origin and origin not in {
        f"http://{request.headers.get('host')}",
        f"https://{request.headers.get('host')}",
    }:
        return Response("Cross-origin requests are disabled.", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
    )
    return response


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.post("/api/trace")
async def convert(file: UploadFile = File(...), options: str = Form("{}")):
    try:
        config = Options.model_validate_json(options)
        data = await file.read(MAX_BYTES + 1)
        async with gate:
            return await asyncio.to_thread(trace, data, config)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()


class ExportRequest(BaseModel):
    svg: str
    format: str = "svg"
    options: ExportOptions = ExportOptions()


class BatchExport(BaseModel):
    items: list[ExportRequest]
    names: list[str]


@app.post("/api/export-batch")
async def download_batch(body: BatchExport):
    if not 1 <= len(body.items) <= 20 or len(body.names) != len(body.items):
        raise HTTPException(400, "Choose between 1 and 20 vectors.")

    def make_zip():
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            for i, (item, name) in enumerate(zip(body.items, body.names)):
                safe = re.sub(r"[^\w .-]", "_", name)[:100].strip(". ") or "image"
                archive.writestr(
                    f"{i + 1:02d}-{safe}.{item.format}",
                    export(item.svg, item.format, item.options),
                )
        return out.getvalue()

    try:
        async with gate:
            result = await asyncio.to_thread(make_zip)
        return Response(result, media_type="application/zip")
    except (ValueError, ET.ParseError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/export")
async def download(body: ExportRequest):
    try:
        async with gate:
            result = await asyncio.to_thread(
                export, body.svg, body.format, body.options
            )
        return Response(
            result,
            media_type={
                "svg": "image/svg+xml",
                "pdf": "application/pdf",
                "eps": "application/postscript",
                "dxf": "application/dxf",
                "png": "image/png",
            }.get(body.format, "application/octet-stream"),
        )
    except (ValueError, ET.ParseError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/edit")
async def edit(body: EditRequest):
    try:
        async with gate:
            return await asyncio.to_thread(edit_vector, body)
    except (ValueError, ET.ParseError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/validate-svg")
async def validate(body: ExportRequest):
    try:
        return {"svg": serialize(validate_svg(body.svg))}
    except (ValueError, ET.ParseError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/clipboard")
async def clipboard(body: ExportRequest):
    from .desktop import copy_vector

    try:
        async with gate:
            return await asyncio.to_thread(copy_vector, body.svg)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs", status_code=202)
async def submit_job(file: UploadFile = File(...), options: str = Form("{}")):
    try:
        config = Options.model_validate_json(options)
        data = await file.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise ValueError(
                f"Image must be between 1 byte and {MAX_BYTES // 1024 // 1024} MB."
            )
        return jobs.submit(data, config).public()
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()


@app.get("/api/jobs/{ident}")
async def job_status(ident: str):
    if ident not in jobs.jobs:
        raise HTTPException(404, "Job not found or expired.")
    return jobs.jobs[ident].public()


@app.delete("/api/jobs/{ident}")
async def cancel_job(ident: str):
    if ident not in jobs.jobs:
        raise HTTPException(404, "Job not found or expired.")
    job = jobs.cancel(ident)
    result = job.public()
    if job.task:
        await asyncio.gather(job.task, return_exceptions=True)
    jobs.jobs.pop(ident, None)
    return result


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.post("/api/shutdown")
async def shutdown(request: Request):
    server = getattr(request.app.state, "server", None)
    if server is None:
        raise HTTPException(409, "This session is managed by an external server.")
    server.should_exit = True
    return {"status": "stopping"}


@app.post("/api/updates")
async def updates():
    from .updates import check_updates

    try:
        return await asyncio.to_thread(check_updates)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
