"""Can run directly: PYTHONPATH=backend python tests/smoke_backend.py"""
from __future__ import annotations
import sys, io, os, tempfile, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from hwf import storage, templates, scanner, fonts
from hwf.charsets import get_charset
import fitz,cv2,numpy as np
from PIL import Image
from fontTools.ttLib import TTFont


def smoke():
    temp=tempfile.TemporaryDirectory()
    storage.ROOT=Path(temp.name)
    project=storage.create('K.Saga writing',get_charset('custom','あいうA'), 'A4','portrait',6,8)
    pdf=templates.generate_pdf(project)
    assert pdf[:4]==b'%PDF'
    doc=fitz.open(stream=pdf,filetype='pdf')
    pg=doc.load_page(0)
    pix=pg.get_pixmap(matrix=fitz.Matrix(200/72,200/72),alpha=False)
    image=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3).copy()
    print('image shape',image.shape)
    layout=templates.page_layout(project,0)
    for cell in layout['cells']:
        x0,y0,x1,y1=cell['rect']
        x=int((x0+x1)/2*200/72);y=int((layout['page_height']-(y0+y1)/2)*200/72)
        # A nonempty synthetic red handwritten stroke with a dot and a small enclosed loop.
        cv2.line(image,(x-35,y+22),(x+35,y-22),(215,24,31),5,cv2.LINE_AA)
        cv2.circle(image,(x+12,y+13),13,(205,28,18),3,cv2.LINE_AA)
        cv2.circle(image,(x-38,y-18),3,(215,18,18),-1)
    b=io.BytesIO();Image.fromarray(image).save(b,format='PNG')
    frames=scanner.decode_upload(b.getvalue(),'sample.png')
    got=scanner.read_page(frames[0],project)
    print('scanned',got['page'],got['accepted'],got['empty'][:10])
    assert len(got['accepted'])==4
    result=fonts.build(project)
    assert result['generated']==4, result
    for name in result['files'].values():
        font=TTFont(storage.project_dir(project['id'])/'exports'/name)
        assert 0x3042 in font.getBestCmap()
        print(name,'tables',font.keys())
    return temp,project,pdf,b.getvalue(),result

if __name__=='__main__':
    tmp,p,pdf,png,result=smoke()
    (root/'samples'/'sample-sheet.pdf').write_bytes(pdf)
    (root/'samples'/'sample-scan-synthetic.png').write_bytes(png)
    for file in (storage.project_dir(p['id'])/'exports').iterdir():
        import shutil
        shutil.copyfile(file,root/'samples'/file.name)
    tmp.cleanup()
    print('PASS',result['generated'])
