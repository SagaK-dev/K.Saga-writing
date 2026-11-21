"""Non-destructive contour extraction and SVG conversion."""
from __future__ import annotations
import cv2, numpy as np
from xml.sax.saxutils import escape


def make_mask(rgb: np.ndarray, mode: str='red', threshold: int=22) -> np.ndarray:
    """Separate a 0.7 mm red pen from light-cyan printed paper guides.

    The red-channel, HSV and LAB strategies are independent alternatives.
    The default `red` is conservative for the specified stationery. `auto` uses
    an intensity/coverage sanity check, favoring preservation of thin red ink.
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Expected RGB image')
    r=rgb[:,:,0].astype('int16');g=rgb[:,:,1].astype('int16');b=rgb[:,:,2].astype('int16')
    contrast=((r-np.maximum(g,b)>threshold)&(r>48)).astype('uint8')*255
    if mode=='red':
        return contrast
    if mode in {'hsv','auto'}:
        hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
        hue,sat,val=cv2.split(hsv)
        hsv_mask=((((hue<=12)|(hue>=168))&(sat>=max(35,threshold))&(val>=45))
                  &((r-g)>10)).astype('uint8')*255
        if mode=='hsv': return hsv_mask
        count_a=cv2.countNonZero(contrast);count_b=cv2.countNonZero(hsv_mask)
        # A serious color cast can weaken RGB contrast. Do not over-detect
        # cyan registration lines; choose only a plausible red candidate.
        if count_a<20 and count_b>count_a and count_b<rgb.shape[0]*rgb.shape[1]*.35:
            return hsv_mask
        return contrast
    if mode=='dark':
        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        return cv2.threshold(gray,min(225,max(45,255-threshold)),255,cv2.THRESH_BINARY_INV)[1]
    raise ValueError('Unknown extraction mode')


def contours_from_mask(mask: np.ndarray, smoothing: float=0.0018) -> list[dict]:
    """Contouring retains all components including diacritics; holes use tree parity."""
    contours,hierarchy = cv2.findContours(mask,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    result=[]
    for i,cont in enumerate(contours):
        area=cv2.contourArea(cont)
        if area < 2 or len(cont) < 3:
            continue
        epsilon=max(0.0,float(smoothing))*cv2.arcLength(cont,True)
        if epsilon>0:
            cont=cv2.approxPolyDP(cont,epsilon,True)
        pts=[[int(pt[0][0]),int(pt[0][1])] for pt in cont]
        if len(pts)<3:
            continue
        depth, parent = 0, int(hierarchy[0][i][3])
        while parent >= 0:
            depth+=1
            parent=int(hierarchy[0][parent][3])
        result.append({'points':pts,'hole':bool(depth%2)})
    return result


def cubic_segments(points: list, curvature: float=.35):
    """Closed cubic Bézier fit through vertices, with clamped control handles.

    Curvature 0 preserves corners. Curvature up to 0.35 modestly smooths digitized
    edges while retaining the original red ink's overall outline.
    """
    n=len(points)
    if n<3:
        return []
    segments=[]
    for i in range(n):
        previous=points[(i-1)%n]
        start=points[i]
        end=points[(i+1)%n]
        following=points[(i+2)%n]
        length=float(np.hypot(end[0]-start[0],end[1]-start[1]))
        def control(anchor,neighbor1,neighbor2,side):
            vx=(neighbor2[0]-neighbor1[0])*curvature/6.0*side
            vy=(neighbor2[1]-neighbor1[1])*curvature/6.0*side
            d=float(np.hypot(vx,vy))
            limit=length*.33
            if d>limit and d: vx*=limit/d;vy*=limit/d
            return (anchor[0]+vx,anchor[1]+vy)
        c1=control(start,previous,end,1)
        c2=control(end,start,following,-1)
        segments.append((c1,c2,tuple(end)))
    return segments


def svg_from_mask(mask: np.ndarray, smoothing: float=0.0018) -> str:
    h,w=mask.shape
    all_shapes=contours_from_mask(mask,smoothing)
    paths=[]
    strength=0.0 if smoothing==0 else 0.35
    for c in all_shapes:
        pts=c['points']
        seg=cubic_segments(pts,strength)
        d=f'M {pts[0][0]} {pts[0][1]} '
        for a,b,end in seg:
            d+=f'C {a[0]:.2f} {a[1]:.2f} {b[0]:.2f} {b[1]:.2f} {end[0]} {end[1]} '
        paths.append(d+'Z')
    d=' '.join(paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}"><path d="{d}" fill="#000" fill-rule="evenodd"/></svg>')


def ink_bbox(mask: np.ndarray):
    ys,xs=np.where(mask>0)
    if xs.size==0:
        return None
    return [int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1]
