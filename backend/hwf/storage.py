"""Project persistence. IDs and paths are bounded and never user-supplied filenames."""
from __future__ import annotations
from pathlib import Path
import json, os, uuid, zipfile, io, shutil, re
from datetime import datetime, timezone

ROOT = Path(os.environ.get('HWF_DATA_DIR', str(Path.home() / '.handwritefont'))).resolve()


def project_dir(pid: str) -> Path:
    try:
        normalized = str(uuid.UUID(pid))
    except (ValueError, AttributeError) as e:
        raise ValueError('Invalid project ID') from e
    return ROOT / normalized


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def get(pid: str) -> dict:
    file = project_dir(pid) / 'project.json'
    if not file.is_file():
        raise FileNotFoundError('Project not found')
    return read_json(file)


def audit(pid: str, action: str, details: dict) -> None:
    """Append a local, redacted audit event. Never store user scan bytes in logs."""
    record={'at':datetime.now(timezone.utc).isoformat(),'action':action,'details':details}
    dest=project_dir(pid)/'audit.jsonl'
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('a',encoding='utf-8') as fp:
        fp.write(json.dumps(record,ensure_ascii=False)+'\n')


def save(project: dict) -> None:
    project['modified_at'] = datetime.now(timezone.utc).isoformat()
    atomic_json(project_dir(project['id']) / 'project.json', project)


def create(name: str, codepoints: list[int], page_size: str, orientation: str, cols: int, rows: int) -> dict:
    if not (1 <= len(codepoints) <= 25000):
        raise ValueError('Character count must be 1–25000')
    if not (1 <= len(name) <= 80) or any(ord(c) < 32 for c in name):
        raise ValueError('Font name must contain 1–80 printable characters')
    pid = str(uuid.uuid4())
    p = {'id': pid, 'font_name': name, 'charset': codepoints, 'page_size': page_size,
         'orientation': orientation, 'cols': cols, 'rows': rows, 'glyphs': {},
         'created_at': datetime.now(timezone.utc).isoformat(), 'font_version': '1.000',
         'designer': 'K.Saga', 'license': 'Personal use only. Redistribution prohibited.',
         'copyright': 'Copyright (c) K.Saga. All rights reserved.', 'processing': {'threshold': 22, 'smooth': 0.0018}}
    save(p)
    audit(pid,'create',{'font_name':name,'target_count':len(codepoints)})
    for folder in ['scans', 'glyphs', 'exports']:
        (project_dir(pid) / folder).mkdir(exist_ok=True)
    return p


def list_projects() -> list[dict]:
    ROOT.mkdir(parents=True, exist_ok=True)
    projects = []
    for folder in ROOT.iterdir():
        if folder.is_dir() and (folder / 'project.json').is_file():
            try:
                p = read_json(folder / 'project.json')
                projects.append({key: p[key] for key in ('id','font_name','created_at','modified_at')})
            except (ValueError, KeyError):
                pass
    return sorted(projects, key=lambda x: x.get('modified_at', ''), reverse=True)


def export_zip(pid: str) -> bytes:
    base = project_dir(pid)
    get(pid)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for f in base.rglob('*'):
            if f.is_file() and f.stat().st_size < 100_000_000:
                z.write(f, f.relative_to(base).as_posix())
    return buffer.getvalue()


def import_zip(content: bytes) -> dict:
    if len(content) > 100_000_000:
        raise ValueError('ZIP is too large')
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        info = z.infolist()
        if len(info) > 30000 or sum(i.file_size for i in info) > 500_000_000:
            raise ValueError('ZIP expansion limit exceeded')
        if any(i.is_dir() is False and (i.filename.startswith('/') or '..' in Path(i.filename).parts or '\\' in i.filename) for i in info):
            raise ValueError('Unsafe archive path')
        if any((i.external_attr >> 16) & 0o170000 == 0o120000 for i in info):
            raise ValueError('Symbolic links are not allowed')
        if 'project.json' not in z.namelist():
            raise ValueError('Missing project.json')
        obj = json.loads(z.read('project.json'))
        if not isinstance(obj,dict) or not isinstance(obj.get('glyphs'),dict):
            raise ValueError('Invalid project data')
        if not isinstance(obj.get('charset'),list) or not 1<=len(obj['charset'])<=25000 or any(not isinstance(cp,int) or not 0<=cp<=0x10FFFF for cp in obj['charset']):
            raise ValueError('Invalid character list')
        for key,record in obj['glyphs'].items():
            if not key.isdecimal() or int(key) not in obj['charset'] or not isinstance(record,dict):
                raise ValueError('Invalid glyph index')
            variants=record.get('variants',[])
            if not isinstance(variants,list) or not variants or not isinstance(record.get('selected'),int) or not 0<=record['selected']<len(variants):
                raise ValueError('Invalid glyph variants')
            for v in variants:
                directory=v.get('directory','') if isinstance(v,dict) else ''
                if not re.fullmatch(r'glyphs/[0-9A-F]{6}/v[0-9]{3,6}',directory) or directory.split('/')[1]!=f'{int(key):06X}':
                    raise ValueError('Invalid glyph file directory')
                if not re.fullmatch(r'scans/[a-zA-Z0-9_.-]+\.png',v.get('source','')):
                    raise ValueError('Invalid source path')
        old = obj.get('id')
        if not old:
            raise ValueError('Missing project ID')
        project_dir(old)  # validate input UUID
        new = str(uuid.uuid4())
        dest = project_dir(new)
        dest.mkdir(parents=True)
        try:
            for entry in info:
                if entry.is_dir():
                    continue
                target = dest / entry.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(entry) as inp, target.open('wb') as out:
                    shutil.copyfileobj(inp, out)
            obj['id'] = new
            save(obj)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise
    return obj
