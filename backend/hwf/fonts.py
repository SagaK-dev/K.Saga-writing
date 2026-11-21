"""Generate genuine glyf TTF and CFF OTF from user handwriting."""
from __future__ import annotations
import re, json, math
from pathlib import Path
import numpy as np, cv2
from PIL import Image
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from . import storage, vector

UPM=1000


def _is_wide(cp:int) -> bool:
    import unicodedata
    return unicodedata.east_asian_width(chr(cp)) in {'F','W'} or cp>=0x2E80


def glyph_paths(mask:np.ndarray,cp:int,smooth:float=.0018,x_shift:int=0,y_shift:int=0):
    bbox=vector.ink_bbox(mask)
    if not bbox: return [], (1000 if _is_wide(cp) else 500,0)
    x0,y0,x1,y1=bbox
    wide=_is_wide(cp)
    advance=1000 if wide else 650
    ink_w=max(1,x1-x0);ink_h=max(1,y1-y0)
    region_w=830 if wide else 530
    region_h=790 if wide else 760
    scale=min(region_w/ink_w,region_h/ink_h)
    draw_w=ink_w*scale;draw_h=ink_h*scale
    left=(advance-draw_w)/2
    bottom=75 + (region_h-draw_h)/2
    contours=vector.contours_from_mask(mask,smooth)
    mapped=[]
    for item in contours:
        pts=[(round(left+(x-x0)*scale+x_shift),round(bottom+(y1-y)*scale+y_shift)) for x,y in item['points']]
        if len(set(pts)) < 3: continue
        # Contour direction normalized explicitly: outer clockwise and hole counter-clockwise.
        signed=sum((pts[(i+1)%len(pts)][0]-p[0])*(pts[(i+1)%len(pts)][1]+p[1]) for i,p in enumerate(pts))
        # signed > 0 indicates clockwise using this test in Cartesian y-up.
        if bool(signed>0) != (not item['hole']):
            pts.reverse()
        mapped.append(pts)
    return mapped, (advance,0)


def _draw_pen(pen,paths):
    for pts in paths:
        pen.moveTo(pts[0])
        # Closed cubic Bézier outlines. TTF uses Cu2QuPen to convert faithfully
        # to TrueType quadratic curves; CFF stores the cubic control points.
        for control1,control2,end in vector.cubic_segments(pts,.35):
            pen.curveTo(control1,control2,end)
        pen.closePath()


def _glyph_name(cp:int)->str:
    return f'uni{cp:04X}' if cp<=0xFFFF else f'u{cp:06X}'


def _font_names(project:dict):
    family=project['font_name']
    ps=re.sub(r'[^A-Za-z0-9-]','',family)[:48] or 'HandwriteFont'
    return {'familyName':family,'styleName':'Regular','uniqueFontIdentifier':ps+';1.000',
            'fullName':family+' Regular','psName':ps+'-Regular','version':'Version '+project.get('font_version','1.000'),
            'copyright':project.get('copyright','All rights reserved.'),
            'description':'Handwritten font generated with HandwriteFont. Personal use only.',
            'licenseDescription':project.get('license','Personal use only; redistribution prohibited.'),
            'designer':project.get('designer','K.Saga')}


def build(project:dict, out_dir:Path|None=None)->dict:
    root=storage.project_dir(project['id'])
    out_dir=out_dir or root/'exports'
    out_dir.mkdir(parents=True,exist_ok=True)
    # .notdef and space are valid, distinct glyphs; missing characters have no cmap entry.
    glyph_data={'.notdef':([],700),'space':([],500)}
    cmap={32:'space'}
    if 0x3000 in project['charset']:
        glyph_data['uni3000']=([],1000)
        cmap[0x3000]='uni3000'
    warnings=[]
    for cp in project['charset']:
        if cp in {32,0x3000}: continue
        entry=project['glyphs'].get(str(cp))
        if not entry: continue
        sel=entry['variants'][entry['selected']]
        f=root/sel['directory']/'mask.png'
        if not f.exists():
            warnings.append(f'U+{cp:04X}: selected version has no mask.png')
            continue
        mask=np.array(Image.open(f).convert('L'))
        if not np.any(mask): continue
        paths,metrics=glyph_paths(mask,cp,sel.get('smooth',.0018),sel.get('x_shift',0),sel.get('y_shift',0))
        if not paths: continue
        name=_glyph_name(cp)
        glyph_data[name]=(paths,metrics[0]);cmap[cp]=name
    if len(cmap)<=1:
        raise ValueError('No scanned handwriting glyphs; print, write and import a page before generating a font')
    order=['.notdef','space']+[n for n in glyph_data if n not in {'.notdef','space'}]
    metrics={name:(val[1],0) for name,val in glyph_data.items()}
    names=_font_names(project)
    outputs={}
    for ext in ('ttf','otf'):
        fb=FontBuilder(UPM,isTTF=(ext=='ttf'))
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap(cmap)
        if ext=='ttf':
            glyphs={}
            for name,(paths,_) in glyph_data.items():
                pen=TTGlyphPen(None)
                curves=Cu2QuPen(pen, max_err=1.5)
                _draw_pen(curves,paths)
                glyphs[name]=pen.glyph()
            fb.setupGlyf(glyphs)
        else:
            charstrings={}
            for name,(paths,advance) in glyph_data.items():
                pen=T2CharStringPen(advance,None)
                _draw_pen(pen,paths)
                charstrings[name]=pen.getCharString(private=None,globalSubrs=None)
            fb.setupCFF(names['psName'],{'FullName':names['fullName'],'FamilyName':names['familyName'],'Weight':'Regular'},charstrings,{})
        fb.setupHorizontalMetrics(metrics)
        fb.setupHorizontalHeader(ascent=850,descent=-150)
        fb.setupNameTable(names)
        fb.setupOS2(sTypoAscender=850,sTypoDescender=-150,sTypoLineGap=0,
                    usWinAscent=900,usWinDescent=200,sxHeight=500,sCapHeight=750,
                    sFamilyClass=0,usWeightClass=400,usWidthClass=5)
        fb.setupPost(keepGlyphNames=(ext=='ttf'))
        fb.setupMaxp()
        fb.setupHead()
        out=out_dir/(names['psName']+'.'+ext)
        fb.save(str(out))
        # Regression check: actual re-parse, complete cmap, drawable outlines and format.
        with TTFont(out) as check:
            if (ext=='ttf' and 'glyf' not in check) or (ext=='otf' and 'CFF ' not in check):
                raise RuntimeError(ext.upper()+' font outline table is missing')
            actual=check.getBestCmap()
            if any(actual.get(cp)!=name for cp,name in cmap.items()):
                raise RuntimeError('Missing or mismatched cmap entries')
        outputs[ext]=out.name
    requested=set(project['charset'])-{32,0x3000}
    generated=set(cmap)-{32,0x3000}
    report={'family':project['font_name'],'requested':len(requested),'generated':len(generated),
            'missing_count':len(requested-generated),
            'missing':[f'U+{cp:04X} {chr(cp)}' for cp in sorted(requested-generated)],
            'warnings':warnings,'files':outputs,
            'format_checks':{'ttf':'glyf TrueType outlines verified','otf':'CFF OpenType outlines verified'},
            'notes':['No physical handwriting scan verification unless explicitly recorded.',
                     'The source pen color is used for extraction; rendered font outlines are monochrome.',
                     'Output includes only scanned characters; missing characters require font fallback.']}
    storage.atomic_json(out_dir/'validation.json',report)
    return report
