import asyncio
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import io
import re
import zipfile

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError, BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .core import Options, trace, export, MAX_BYTES

app = FastAPI(title='TraceGarden', version='0.1.0')
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
STATIC = Path(__file__).parent / 'static'
gate = asyncio.Semaphore(1)


@app.middleware('http')
async def local_only(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and origin not in {f'http://{request.headers.get("host")}', f'https://{request.headers.get("host")}'}:
        return Response('Cross-origin requests are disabled.', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
    return response


@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html')


@app.post('/api/trace')
async def convert(file: UploadFile = File(...), options: str = Form('{}')):
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
    format: str = 'svg'


class BatchExport(BaseModel):
    items: list[ExportRequest]
    names: list[str]


@app.post('/api/export-batch')
async def download_batch(body: BatchExport):
    if not 1 <= len(body.items) <= 20 or len(body.names) != len(body.items):
        raise HTTPException(400, 'Choose between 1 and 20 vectors.')
    def make_zip():
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
            for i, (item, name) in enumerate(zip(body.items, body.names)):
                safe = re.sub(r'[^\w .-]', '_', name)[:100].strip('. ') or 'image'
                archive.writestr(f'{i+1:02d}-{safe}.{item.format}', export(item.svg, item.format))
        return out.getvalue()
    try:
        async with gate:
            result = await asyncio.to_thread(make_zip)
        return Response(result, media_type='application/zip')
    except (ValueError, ET.ParseError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post('/api/export')
async def download(body: ExportRequest):
    try:
        async with gate:
            result = await asyncio.to_thread(export, body.svg, body.format)
        return Response(result, media_type={'svg':'image/svg+xml','pdf':'application/pdf','eps':'application/postscript','dxf':'application/dxf','png':'image/png'}.get(body.format, 'application/octet-stream'))
    except (ValueError, ET.ParseError) as exc:
        raise HTTPException(400, str(exc)) from exc


app.mount('/static', StaticFiles(directory=STATIC), name='static')
