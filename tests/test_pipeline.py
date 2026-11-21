"""Image-to-font regression tests using synthetic red pen strokes."""
from __future__ import annotations
import io, os, sys, json, zipfile
from pathlib import Path
import fitz, cv2, numpy as np, pytest
from PIL import Image
from fontTools.ttLib import TTFont
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from hwf import storage, charsets, templates, scanner, vector, fonts
from hwf.api import app

@pytest.fixture(autouse=True)
def store(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'ROOT',tmp_path/'projects')


def project(txt='あいう',rows=8):
    return storage.create('K.Saga writing',charsets.get_charset('custom',txt),'A4','portrait',6,rows)


def rendered_pdf(p,index=0):
    data=templates.generate_pdf(p)
    with fitz.open(stream=data,filetype='pdf') as doc:
        pix=doc[index].get_pixmap(matrix=fitz.Matrix(200/72,200/72),alpha=False)
    return np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3).copy()


def ink_image(p,index=0,characters=None):
    img=rendered_pdf(p,index)
    layout=templates.page_layout(p,index)
    for cell in layout['cells'] if characters is None else layout['cells'][:characters]:
        x0,y0,x1,y1=cell['rect']
        x=int((x0+x1)/2*200/72);y=int((layout['page_height']-(y0+y1)/2)*200/72)
        cv2.line(img,(x-24,y+25),(x+24,y-25),(193,22,30),5,cv2.LINE_AA)
        cv2.circle(img,(x+5,y),12,(203,23,19),3,cv2.LINE_AA)
        cv2.circle(img,(x-25,y-15),3,(210,30,25),-1)
    return img


def test_charsets():
    assert len(charsets.get_charset('joyo'))==2136
    assert len(charsets.get_charset('jis'))==6355
    assert len(charsets.get_charset('all'))==2442
    assert len(charsets.get_charset('kana'))==177
    assert len(charsets.get_charset('custom','ああい'))==2
    with pytest.raises(ValueError): charsets.get_charset('custom','\u0301')


def test_templates_qr_and_fiducials():
    p=project()
    assert templates.qr_payload(p,0).startswith('HWF1:')
    img=rendered_pdf(p)
    assert scanner._decode_qr(img)==templates.qr_payload(p,0)
    assert scanner._markers(img).shape==(4,2)
    assert len(templates.generate_pdf(p))>1000


def test_scan_red_and_no_guide_lines():
    p=project('あい')
    blank=rendered_pdf(p)
    result=scanner.read_page(blank,p)
    assert result['accepted']==[]
    ink=ink_image(p)
    result=scanner.read_page(ink,p)
    assert result['accepted']==[ord('あ'),ord('い')]
    f=storage.project_dir(p['id'])/'glyphs'/f'{ord("あ"):06X}'/'v001'
    raw=np.array(Image.open(f/'raw.png'))
    mask=np.array(Image.open(f/'mask.png'))
    assert np.count_nonzero(mask)>0
    assert '<path' in (f/'ink.svg').read_text()
    assert raw.shape[:2]==mask.shape


def test_scanner_rotated_180():
    p=project('あ')
    img=ink_image(p)
    rotated=cv2.rotate(img,cv2.ROTATE_180)
    assert scanner.read_page(rotated,p)['accepted']==[ord('あ')]


def test_scanner_perspective():
    p=project('あ')
    img=ink_image(p)
    h,w=img.shape[:2]
    src=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
    dst=np.float32([[35,10],[w-70,50],[w-35,h-40],[50,h-30]])
    warped=cv2.warpPerspective(img,cv2.getPerspectiveTransform(src,dst),(w,h),borderValue=(255,255,255))
    assert scanner.read_page(warped,p)['accepted']==[ord('あ')]


def test_qr_rejects_unmatched_project():
    p=project('あ')
    im=ink_image(p)
    other=project('あ')
    with pytest.raises(ValueError,match='different project'):
        scanner.read_page(im,other)


def test_read_multiple_pages():
    p=project('あ'*1 + ''.join(chr(0x3041+i) for i in range(60)))
    assert len(p['charset'])>48
    img1=ink_image(p,0,characters=2)
    img2=ink_image(p,1,characters=2)
    r1=scanner.read_page(img1,p)
    r2=scanner.read_page(img2,p)
    assert r1['page']==0 and r2['page']==1
    assert len(r1['accepted'])==2 and len(r2['accepted'])==2


def test_vector_holes_and_dots():
    mask=np.zeros((150,150),np.uint8)
    cv2.circle(mask,(70,70),35,255,-1)
    cv2.circle(mask,(70,70),16,0,-1)
    cv2.circle(mask,(126,24),3,255,-1)
    contours=vector.contours_from_mask(mask)
    assert len(contours)==3
    assert sum(c['hole'] for c in contours)==1
    assert len(vector.svg_from_mask(mask))>200


def test_font_ttf_cff_reopen_and_missing():
    p=project('あいう')
    scanner.read_page(ink_image(p,characters=2),p)
    result=fonts.build(p)
    assert result['generated']==2 and result['missing_count']==1
    for ext,filename in result['files'].items():
        with TTFont(storage.project_dir(p['id'])/'exports'/filename) as font:
            assert ord('あ') in font.getBestCmap()
            assert ord('い') in font.getBestCmap()
            assert ord('う') not in font.getBestCmap()
            assert ('CFF ' in font) == (ext=='otf')
            assert ('glyf' in font) == (ext=='ttf')


def test_variants_and_reprocess():
    p=project('あ')
    img=ink_image(p)
    scanner.read_page(img,p)
    scanner.read_page(img,p)
    record=p['glyphs'][str(ord('あ'))]
    assert len(record['variants'])==2 and record['selected']==1
    v=scanner.reprocess(p,ord('あ'),threshold=30,smooth=.002,x_shift=7)
    assert v['x_shift']==7


def test_archive_round_trip_and_zip_slip():
    p=project('あ')
    content=storage.export_zip(p['id'])
    imported=storage.import_zip(content)
    assert imported['id']!=p['id'] and imported['font_name']==p['font_name']
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('../outside.txt','bad')
        z.writestr('project.json',json.dumps(p))
    with pytest.raises(ValueError,match='Unsafe archive'):
        storage.import_zip(buf.getvalue())


def test_api_create_template_and_build():
    client=TestClient(app)
    response=client.post('/api/projects',json={'font_name':'K.Saga writing','charset':'custom','custom_text':'あいう'})
    assert response.status_code==200,response.text
    p=response.json();pid=p['id']
    pdf=client.get(f'/api/projects/{pid}/template')
    assert pdf.status_code==200 and pdf.content[:4]==b'%PDF'
    error=client.post(f'/api/projects/{pid}/build')
    assert error.status_code==422
    scan=ink_image(storage.get(pid))
    b=io.BytesIO();Image.fromarray(scan).save(b,format='PNG')
    upload=client.post(f'/api/projects/{pid}/scans',files=[('files',('scan.png',b.getvalue(),'image/png'))])
    assert upload.status_code==200,upload.text
    assert upload.json()['pages'][0]['status']=='ok'
    font=client.post(f'/api/projects/{pid}/build')
    assert font.status_code==200,font.text
    out=font.json()
    assert client.get(f'/api/projects/{pid}/exports/{out["files"]["ttf"]}').status_code==200


def test_invalid_file():
    with pytest.raises(ValueError):
        scanner.decode_upload(b'not a real image','foo.png')
