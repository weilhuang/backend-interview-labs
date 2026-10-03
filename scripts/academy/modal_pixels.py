"""Exact complete-dialog pixels, independent of unrelated owned background pixels."""
import hashlib
import struct
import zlib
from display_diagnostic import clean_png

DOMAIN=b'ACADEMY_OWNED_PLUGIN_DIALOG_RGB_V1\0'
MODE='OWNED_PLUGIN_DIALOG_PIXELS_V1'

def require(ok):
    if not ok:raise ValueError('invalid complete plugin dialog pixels')

def rectangle(window):
    values=[window[k] for k in ('x','y','width','height')]
    require(all(type(n) is int for n in values));x,y,w,h=values
    require(0<=x<1280 and 0<=y<900 and 1<=w<=1280-x and 1<=h<=900-y and window['border']==0)
    return values

def pixel_hash(raw,window):
    """Strict 8-bit RGB/RGBA PNG; ancillary metadata never changes interpretation."""
    raw=clean_png(raw);x,y,w,h=rectangle(window)
    pos=8;compressed=bytearray();color=None
    while pos<len(raw):
        size=struct.unpack('>I',raw[pos:pos+4])[0];kind=raw[pos+4:pos+8];data=raw[pos+8:pos+8+size]
        if kind==b'IHDR':color=data[9]
        if kind==b'IDAT':compressed.extend(data)
        pos+=size+12
    bpp=3 if color==2 else 4;stride=1280*bpp
    decoded=zlib.decompress(compressed);previous=bytearray(stride)
    out=hashlib.sha256(DOMAIN+struct.pack('>4I',x,y,w,h))
    for row in range(900):
        at=row*(stride+1);kind=decoded[at];current=bytearray(decoded[at+1:at+stride+1])
        if kind:
            for i in range(stride):
                left=current[i-bpp] if i>=bpp else 0;up=previous[i];upper_left=previous[i-bpp] if i>=bpp else 0
                if kind==1:predict=left
                elif kind==2:predict=up
                elif kind==3:predict=(left+up)//2
                else:
                    p=left+up-upper_left;a=abs(p-left);b=abs(p-up);c=abs(p-upper_left)
                    predict=left if a<=b and a<=c else up if b<=c else upper_left
                current[i]=(current[i]+predict)&255
        if bpp==4:require(all(v==255 for v in current[3::4]))
        if y<=row<y+h:
            selected=current[x*bpp:(x+w)*bpp]
            if bpp==4:
                rgb=bytearray(w*3);rgb[0::3]=selected[0::4];rgb[1::3]=selected[1::4];rgb[2::3]=selected[2::4];out.update(rgb)
            else:out.update(selected)
        previous=current
    return out.hexdigest()
