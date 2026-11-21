"""Local-only FastAPI; no cloud calls or arbitrary user-controlled file paths."""
from __future__ import annotations
from pathlib import Path
import io, os, json, math
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from . import storage, charsets, templates, scanner, fonts

app=FastAPI(title='HandwriteFont',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5173','http://localhost:5173'],
                   allow_credentials=False,allow_methods=['*'],allow_headers=['*'])


class CreateProject(BaseModel):
    font_name:str='K.Saga writing'
    charset:str='all'
    custom_text:str=''
    page_size:str='A4'
    orientation:str='portrait'
    cols:int=Field(default=6,ge=2,le=12)
    rows:int=Field(default=8,ge=2,le=18)


class ReprocessParams(BaseModel):
    threshold:int=Field(default=22,ge=1,le=150)
    smooth:float=Field(default=0.0018,ge=0,le=.03)
    x_shift:int=Field(default=0,ge=-200,le=200)
    y_shift:int=Field(default=0,ge=-200,le=200)


def lookup(pid:str):
    try: return storage.get(pid)
    except (ValueError,FileNotFoundError) as e: raise HTTPException(status_code=404,detail=str(e)) from e


@app.get('/api/health')
def health():return {'ok':True,'app':'HandwriteFont','offline':True}


@app.get('/api/projects')
def projects():return storage.list_projects()


@app.post('/api/projects')
def project_create(body:CreateProject):
    try:
        if body.page_size not in {'A4','A3'} or body.orientation not in {'portrait','landscape'}:
            raise ValueError('Invalid paper format')
        cps=charsets.get_charset(body.charset,body.custom_text)
        p=storage.create(body.font_name,cps,body.page_size,body.orientation,body.cols,body.rows)
        templates.page_layout(p,0) # reject grids that cannot fit on the chosen sheet
        return project_details(p)
    except (ValueError,OSError) as e: raise HTTPException(status_code=422,detail=str(e)) from e


def project_details(p:dict)->dict:
    selected=set(int(k) for k in p['glyphs'])
    return {k:p[k] for k in ('id','font_name','page_size','orientation','cols','rows','created_at','modified_at')} | {
        'target_count':len(p['charset']),'pages':math.ceil(len(p['charset'])/(p['cols']*p['rows'])),
        'scanned_count':len(selected),'missing_count':len(set(p['charset'])-selected),
        'charset_preview':''.join(chr(cp) for cp in p['charset'][:140]),
        'glyphs':list(p['glyphs'].values())}


@app.get('/api/projects/{pid}')
def project_get(pid:str):return project_details(lookup(pid))


@app.get('/api/projects/{pid}/template')
def template(pid:str):
    p=lookup(pid)
    try: content=templates.generate_pdf(p)
    except (ValueError,RuntimeError) as e: raise HTTPException(status_code=422,detail=str(e)) from e
    return Response(content,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="HandwriteFont-template.pdf"'})


@app.post('/api/projects/{pid}/scans')
async def scan_upload(pid:str,files:list[UploadFile]=File(...),
                      manual_page:int|None=Form(default=None),manual_corners:str|None=Form(default=None)):
    p=lookup(pid)
    if len(files)>8: raise HTTPException(status_code=413,detail='At most 8 upload files at once')
    try:
        corners=json.loads(manual_corners) if manual_corners else None
        if corners is not None and (not isinstance(corners,list) or len(corners)!=4):
            raise ValueError('manual_corners must contain four pixel coordinate pairs')
        results=[]
        page_offset=0
        for file in files:
            content=await file.read(40_000_001)
            if len(content)>40_000_000: raise ValueError('File exceeds 40 MB')
            frames=scanner.decode_upload(content,file.filename or '')
            for idx,image in enumerate(frames):
                # Additional pages require the QR code or an explicitly incremented page assignment.
                page=None if manual_page is None else manual_page+page_offset+idx
                try:
                    r=scanner.read_page(image,p,manual_page=page,manual_corners=corners)
                    results.append({'file':file.filename,'index':idx,'status':'ok',**r})
                except ValueError as e:
                    results.append({'file':file.filename,'index':idx,'status':'error','error':str(e)})
            page_offset+=len(frames)
        return {'pages':results,'project':project_details(p)}
    except (ValueError,OSError,KeyError) as e: raise HTTPException(status_code=422,detail=str(e)) from e


@app.get('/api/projects/{pid}/glyphs')
def glyph_list(pid:str):
    p=lookup(pid)
    return {'glyphs':list(p['glyphs'].values()),'missing':[cp for cp in p['charset'] if str(cp) not in p['glyphs']]}


@app.get('/api/projects/{pid}/glyphs/{cp}/asset/{kind}')
def glyph_asset(pid:str,cp:int,kind:str):
    p=lookup(pid)
    if kind not in {'raw','mask','svg'}: raise HTTPException(status_code=400,detail='Unknown image kind')
    record=p['glyphs'].get(str(cp))
    if not record: raise HTTPException(status_code=404,detail='Glyph not found')
    directory=record['variants'][record['selected']]['directory']
    f=storage.project_dir(pid)/directory/({'raw':'raw.png','mask':'mask.png','svg':'ink.svg'}[kind])
    return FileResponse(f,media_type='image/svg+xml' if kind=='svg' else 'image/png')


@app.put('/api/projects/{pid}/glyphs/{cp}')
def glyph_reprocess(pid:str,cp:int,body:ReprocessParams):
    p=lookup(pid)
    try:return scanner.reprocess(p,cp,body.threshold,body.smooth,body.x_shift,body.y_shift)
    except ValueError as e:raise HTTPException(status_code=422,detail=str(e)) from e


@app.post('/api/projects/{pid}/glyphs/{cp}/select/{version}')
def glyph_select(pid:str,cp:int,version:int):
    p=lookup(pid);record=p['glyphs'].get(str(cp))
    if record is None or not 0<=version<len(record['variants']):
        raise HTTPException(status_code=404,detail='Glyph version not found')
    record['selected']=version;storage.save(p);storage.audit(pid,'select_variant',{'codepoint':cp,'version':version});return record


@app.post('/api/projects/{pid}/build')
def build(pid:str):
    p=lookup(pid)
    try:
        result=fonts.build(p)
        storage.audit(pid,'build',{'generated':result['generated'],'missing':result['missing_count']})
        return result
    except (ValueError,RuntimeError) as e:raise HTTPException(status_code=422,detail=str(e)) from e


@app.get('/api/projects/{pid}/exports/{filename}')
def export_artifact(pid:str,filename:str):
    lookup(pid)
    if filename!='validation.json' and not (filename.endswith('.ttf') or filename.endswith('.otf')):
        raise HTTPException(status_code=400,detail='Unsupported export')
    if filename!=Path(filename).name:raise HTTPException(status_code=400,detail='Invalid filename')
    f=storage.project_dir(pid)/'exports'/filename
    if not f.is_file(): raise HTTPException(status_code=404,detail='Not generated')
    return FileResponse(f,filename=filename)


@app.get('/api/projects/{pid}/archive')
def archive(pid:str):
    lookup(pid)
    return Response(storage.export_zip(pid),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="HandwriteFont-project.zip"'})


@app.post('/api/projects/import')
async def import_archive(file:UploadFile=File(...)):
    try:
        content=await file.read(100_000_001)
        return project_details(storage.import_zip(content))
    except (ValueError,OSError,KeyError,RuntimeError) as e:raise HTTPException(status_code=422,detail=str(e)) from e

# The static frontend is registered LAST, so every /api route takes precedence.
from fastapi.staticfiles import StaticFiles
FRONTEND_DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
FALLBACK_DIR = Path(__file__).resolve().parents[2] / 'frontend' / 'fallback'
app.mount('/', StaticFiles(directory=FRONTEND_DIST if FRONTEND_DIST.is_dir() else FALLBACK_DIR, html=True),name='frontend')
