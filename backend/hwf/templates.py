"""A4/A3 registration sheets; all glyph identities are derived from layouts."""
from __future__ import annotations
import io, json, math, hashlib
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.pagesizes import A4, A3, landscape
from PIL import Image
import qrcode
from . import storage

VERSION = 1
FONT_CID = 'HeiseiKakuGo-W5'
try:
    pdfmetrics.registerFont(UnicodeCIDFont(FONT_CID))
except Exception:
    FONT_CID = 'Helvetica'


def get_dimensions(project: dict) -> tuple[float,float]:
    size = A3 if project['page_size'] == 'A3' else A4
    if project['orientation'] == 'landscape':
        size = landscape(size)
    return size


def signature(project: dict, page: int) -> str:
    values = ','.join(str(n) for n in project['charset'][page*project['cols']*project['rows']:(page+1)*project['cols']*project['rows']])
    return hashlib.sha256(f"{project['id']}:{page}:{values}:{VERSION}".encode()).hexdigest()[:12]


def page_layout(project: dict, index: int) -> dict:
    w,h = get_dimensions(project)
    cols,rows = project['cols'],project['rows']
    count = cols * rows
    page_cps = project['charset'][index*count:(index+1)*count]
    if not page_cps:
        raise ValueError('Page out of range')
    # A4 top margin for QR code and metadata; bottom margin for markers.
    margin_x, grid_bottom, grid_top = 15*mm, 15*mm, h-34*mm
    cell_w = (w-2*margin_x)/cols
    cell_h = (grid_top-grid_bottom)/rows
    if cell_w < 13*mm or cell_h < 17*mm:
        raise ValueError('Grid too dense. Reduce columns or rows.')
    cells = []
    for i,cp in enumerate(page_cps):
        r,c = divmod(i,cols)
        x = margin_x+c*cell_w
        y = grid_top-(r+1)*cell_h
        # image crop references are in PDF points, bottom-origin.
        rect = [x+2*mm, y+2*mm, x+cell_w-2*mm, y+cell_h-8*mm]
        cells.append({'index':i,'codepoint':cp,'char':chr(cp),'rect':rect,
                      'bounds':[x,y,x+cell_w,y+cell_h]})
    return {'version':VERSION, 'project_id':project['id'], 'index':index,
            'page_width':w,'page_height':h, 'cells':cells,
            'signature':signature(project,index)}


def qr_payload(project: dict, index: int) -> str:
    return f"HWF1:{project['id']}:{index}:{signature(project,index)}"


def generate_pdf(project: dict) -> bytes:
    stream = io.BytesIO()
    width,height = get_dimensions(project)
    c = canvas.Canvas(stream, pagesize=(width,height),pageCompression=1)
    count = project['cols']*project['rows']
    pages = math.ceil(len(project['charset'])/count)
    for page in range(pages):
        layout = page_layout(project,page)
        c.setTitle('HandwriteFont — ' + project['font_name'])
        c.setStrokeColor(black)
        c.setFillColor(black)
        c.setFont('Helvetica-Bold',11)
        c.drawString(15*mm,height-17*mm,'HandwriteFont / ' + project['font_name'][:45])
        c.setFont('Helvetica',8)
        c.drawString(15*mm,height-23*mm, f'Page {page+1}/{pages}  |  RED BALLPOINT PEN 0.7 mm  |  Print at 100%')
        c.drawString(15*mm,height-28*mm, f'ID: {project["id"][:8]}   Template v{VERSION}   |   Do not crop registration markers')
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=6,border=2)
        qr.add_data(qr_payload(project,page)); qr.make(fit=True)
        img=qr.make_image(fill_color='black',back_color='white').convert('RGB')
        from reportlab.lib.utils import ImageReader
        # QR sits in header at top-right, not on the writing grid.
        c.drawImage(ImageReader(img),width-37*mm,height-31*mm,25*mm,25*mm,mask='auto')
        # Four independent 7mm fiducials, with asymmetric dots for orientation.
        for mx,my in [(4*mm,4*mm),(width-11*mm,4*mm),(4*mm,height-11*mm),(width-11*mm,height-11*mm)]:
            c.setFillColor(black); c.rect(mx,my,7*mm,7*mm,stroke=0,fill=1)
        c.setStrokeColor(HexColor('#7DC5E4'))
        c.setLineWidth(0.65)
        for cell in layout['cells']:
            x0,y0,x1,y1=cell['bounds']
            c.rect(x0,y0,x1-x0,y1-y0,fill=0,stroke=1)
            # Header outside the pen area.
            c.setFillColor(black)
            c.setFont(FONT_CID,9.5)
            c.drawString(x0+2*mm,y1-4.3*mm,cell['char'])
            c.setFont('Helvetica',6.5)
            c.drawRightString(x1-2*mm,y1-4*mm,f"U+{cell['codepoint']:04X}")
            c.setStrokeColor(HexColor('#DDECF2'))
            rx0,ry0,rx1,ry1=cell['rect']
            # Thin guide in pale cyan. The mask uses red-channel dominance, so guides disappear.
            c.setDash(1.5,3)
            c.line((rx0+rx1)/2,ry0,(rx0+rx1)/2,ry1)
            c.line(rx0,(ry0+ry1)/2,rx1,(ry0+ry1)/2)
            c.setDash()
            c.setStrokeColor(HexColor('#7DC5E4'))
        c.showPage()
    c.save()
    return stream.getvalue()
