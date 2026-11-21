"""Page alignment, red ink separation, glyph-version persistence."""
from __future__ import annotations
import io, json, math, uuid
from pathlib import Path
import numpy as np, cv2
from PIL import Image, ImageOps, UnidentifiedImageError
from . import storage, templates, vector

MAX_PIXELS=45_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
OUT_DPI=200


def decode_upload(content:bytes, filename:str) -> list[np.ndarray]:
    if len(content)>40_000_000:
        raise ValueError('Scan exceeds 40MB limit')
    if content[:4]==b'%PDF':
        import fitz
        doc=fitz.open(stream=content,filetype='pdf')
        if doc.page_count>80:
            raise ValueError('PDF must have at most 80 pages per upload')
        images=[]
        for page in doc:
            if page.rect.width*page.rect.height*(OUT_DPI/72)**2 > MAX_PIXELS:
                raise ValueError('Rendered PDF page exceeds pixel limit')
            pix=page.get_pixmap(matrix=fitz.Matrix(OUT_DPI/72,OUT_DPI/72),colorspace=fitz.csRGB,alpha=False)
            images.append(np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3).copy())
        doc.close()
        return images
    try:
        with Image.open(io.BytesIO(content)) as img:
            if img.format not in {'PNG','JPEG','TIFF'}:
                raise ValueError('Only PNG/JPEG/TIFF/PDF supported')
            frames=[]
            for i in range(getattr(img,'n_frames',1)):
                if i>=80: raise ValueError('Maximum 80 TIFF frames')
                img.seek(i)
                if img.width*img.height>MAX_PIXELS:
                    raise ValueError('Image exceeds pixel limit')
                frames.append(np.array(ImageOps.exif_transpose(img).convert('RGB')))
            return frames
    except (OSError, UnidentifiedImageError) as e:
        raise ValueError('Unrecognized or damaged scan file') from e


def _markers(img:np.ndarray) -> np.ndarray:
    h,w=img.shape[:2]
    g=cv2.cvtColor(img,cv2.COLOR_RGB2GRAY)
    _,bw=cv2.threshold(g,65,255,cv2.THRESH_BINARY_INV)
    contours,_=cv2.findContours(bw,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for cont in contours:
        x,y,cw,ch=cv2.boundingRect(cont)
        if ch==0 or cw==0: continue
        ratio=cw/ch
        if not 0.66<=ratio<=1.5: continue
        fraction=cw/w
        if not 0.014<=fraction<=0.065: continue
        # Solid black square. Printed QR components are mostly too small/non-solid.
        area=cv2.contourArea(cont)
        if area/(cw*ch)<0.72: continue
        cx,cy=x+cw/2,y+ch/2
        candidates.append((cx,cy,cw,ch))
    expected=[(0.035,0.025),(0.965,0.025),(0.965,0.975),(0.035,0.975)]
    corners=[]
    for ex,ey in expected:
        close=[z for z in candidates if abs(z[0]/w-ex)<0.115 and abs(z[1]/h-ey)<0.11]
        if not close:
            raise ValueError('Registration marker missing; scan all four sheet corners')
        # favor proximity to expected marker locations.
        z=min(close,key=lambda a:(a[0]/w-ex)**2+(a[1]/h-ey)**2)
        corners.append([z[0],z[1]])
    if len({tuple(pt) for pt in corners}) != 4:
        raise ValueError('Four distinct registration markers were not found')
    return np.array(corners,dtype=np.float32)


def _decode_qr(image:np.ndarray, header_only:bool=False) -> str:
    h,w=image.shape[:2]
    det=cv2.QRCodeDetector()
    # The QR lives in the top-right header: crop is faster and avoids grid noise.
    crop=image[0:int(h*.17),int(w*.76):w]
    info,_,_=det.detectAndDecode(cv2.cvtColor(crop,cv2.COLOR_RGB2BGR))
    if info or header_only: return info or ''
    info,_,_=det.detectAndDecode(cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
    return info or ''


def align_page(image:np.ndarray,project:dict,manual_corners:list|None=None)->np.ndarray:
    width,height=templates.get_dimensions(project)
    iw,ih=round(width/72*OUT_DPI),round(height/72*OUT_DPI)
    # Fiducial centers in PDF top-left pixel space; actual squares go from 4 to 11mm.
    px=7.5/25.4*OUT_DPI
    src=np.array(manual_corners,dtype=np.float32) if manual_corners is not None else _markers(image)
    if src.shape!=(4,2): raise ValueError('manual_corners requires [TL,TR,BR,BL] in input pixel coordinates')
    dest=np.array([[px,px],[iw-px,px],[iw-px,ih-px],[px,ih-px]],dtype=np.float32)
    transform=cv2.getPerspectiveTransform(src,dest)
    return cv2.warpPerspective(image,transform,(iw,ih),flags=cv2.INTER_LINEAR,borderValue=(255,255,255))


def read_page(image:np.ndarray,project:dict,manual_page:int|None=None,
              manual_corners:list|None=None,threshold:int=22,smooth:float=.0018)->dict:
    # The four solid registration squares are symmetrical, so infer orientation
    # from the QR's known top-right location before assigning ANY glyph cells.
    qr=''
    aligned=None
    rotations=[image] if manual_corners is not None else [image,cv2.rotate(image,cv2.ROTATE_180),
        cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE),cv2.rotate(image,cv2.ROTATE_90_COUNTERCLOCKWISE)]
    for rotated in rotations:
        candidate=align_page(rotated,project,manual_corners)
        qr=_decode_qr(candidate,header_only=True)
        if qr:
            aligned=candidate
            break
    if aligned is None:
        aligned=align_page(image,project,manual_corners)
        # A QR elsewhere on the sheet indicates ambiguous orientation; do not
        # import blank/wrong cells silently unless the page is manually selected.
        if manual_page is None and _decode_qr(aligned):
            raise ValueError('QR code is outside its expected location; check page orientation')
    reported=None
    if qr:
        parts=qr.split(':')
        if len(parts)!=4 or parts[0]!='HWF1' or parts[1]!=project['id']:
            raise ValueError('QR code belongs to a different project or is invalid')
        try: page=int(parts[2])
        except ValueError as e: raise ValueError('Invalid QR page number') from e
        if parts[3]!=templates.signature(project,page):
            raise ValueError('QR code checksum differs from the project template')
        if manual_page is not None and manual_page!=page:
            raise ValueError('Specified page number conflicts with QR')
    elif manual_page is not None:
        page=manual_page
        reported='QR unreadable: manually confirmed page assignment'
    else:
        raise ValueError('QR code unreadable; specify the correct page number manually')
    layout=templates.page_layout(project,page)
    scale=OUT_DPI/72
    summary={'page':page,'qr':qr,'warning':reported,'accepted':[],'empty':[],'preview':None}
    root=storage.project_dir(project['id'])
    scanfile=f'scans/page-{page:04d}-{uuid.uuid4().hex[:12]}.png'
    Image.fromarray(aligned).save(root/scanfile)
    for cell in layout['cells']:
        x0,y0,x1,y1=cell['rect']
        crop=aligned[max(0,round((layout['page_height']-y1)*scale)):round((layout['page_height']-y0)*scale),
                     max(0,round(x0*scale)):round(x1*scale)]
        if crop.size==0: continue
        mask=vector.make_mask(crop,mode='auto',threshold=threshold)
        cp=cell['codepoint']
        if cv2.countNonZero(mask)<max(12,int(mask.size*0.00025)):
            summary['empty'].append(cp)
            continue
        folder=root/'glyphs'/f'{cp:06X}'
        record=project['glyphs'].get(str(cp),{'codepoint':cp,'char':chr(cp),'variants':[],'selected':0})
        n=len(record['variants'])+1
        vfolder=folder/f'v{n:03d}'
        vfolder.mkdir(parents=True,exist_ok=True)
        Image.fromarray(crop).save(vfolder/'raw.png')
        Image.fromarray(mask).save(vfolder/'mask.png')
        (vfolder/'ink.svg').write_text(vector.svg_from_mask(mask,smooth),encoding='utf-8')
        variant={'directory':f'glyphs/{cp:06X}/v{n:03d}', 'source':scanfile,
                 'page':page,'cell':cell['index'],'threshold':threshold,'smooth':smooth,
                 'bbox':vector.ink_bbox(mask),'x_shift':0,'y_shift':0}
        record['variants'].append(variant)
        record['selected']=len(record['variants'])-1
        project['glyphs'][str(cp)]=record
        summary['accepted'].append(cp)
    storage.save(project)
    storage.audit(project['id'],'scan',{'page':page,'accepted':len(summary['accepted']),'empty':len(summary['empty']),'manual':bool(reported)})
    return summary


def reprocess(project:dict, cp:int,threshold:int=22,smooth:float=.0018,
              x_shift:int=0,y_shift:int=0):
    """Create a NEW immutable version; the previous version remains selectable."""
    record=project['glyphs'].get(str(cp))
    if not record: raise ValueError('Glyph has not been scanned')
    old=record['variants'][record['selected']]
    root=storage.project_dir(project['id'])
    old_folder=root/old['directory']
    rgb=np.array(Image.open(old_folder/'raw.png').convert('RGB'))
    mask=vector.make_mask(rgb,'red',threshold)
    if not np.any(mask): raise ValueError('No red ink detected at this threshold')
    version=len(record['variants'])+1
    directory=f'glyphs/{cp:06X}/v{version:03d}'
    folder=root/directory
    folder.mkdir(parents=True,exist_ok=True)
    Image.fromarray(rgb).save(folder/'raw.png')
    Image.fromarray(mask).save(folder/'mask.png')
    (folder/'ink.svg').write_text(vector.svg_from_mask(mask,smooth),encoding='utf-8')
    v={'directory':directory,'source':old['source'],'page':old['page'],'cell':old['cell'],
       'threshold':threshold,'smooth':smooth,'x_shift':x_shift,'y_shift':y_shift,
       'bbox':vector.ink_bbox(mask),'derived_from':old['directory']}
    record['variants'].append(v)
    record['selected']=len(record['variants'])-1
    storage.save(project)
    storage.audit(project['id'],'reprocess',{'codepoint':cp,'threshold':threshold,'smooth':smooth,'new_version':version})
    return v
