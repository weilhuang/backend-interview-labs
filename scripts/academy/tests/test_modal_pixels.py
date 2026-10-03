"""Exact PNG sample decoding; no display or legal action."""
import hashlib,struct,sys,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import modal_pixels as pixels

WINDOW={'x':380,'y':335,'width':520,'height':235,'border':0}
def sample_png(changes=None,alpha=False,filter_kind=0,metadata=b''):
    changes=changes or {};bpp=4 if alpha else 3;rows=[];previous=bytes(1280*bpp)
    for y in range(900):
        row=bytearray(([0,0,0,255] if alpha else [0,0,0])*1280)
        for (x,yy),rgb in changes.items():
            if yy==y:row[x*bpp:(x+1)*bpp]=bytes(rgb)
        encoded=bytearray(row)
        if filter_kind:
            for at in range(len(row)):
                a=row[at-bpp] if at>=bpp else 0;b=previous[at];c=previous[at-bpp] if at>=bpp else 0
                if filter_kind==1:p=a
                elif filter_kind==2:p=b
                elif filter_kind==3:p=(a+b)//2
                else:
                    n=a+b-c;aa=abs(n-a);bb=abs(n-b);cc=abs(n-c);p=a if aa<=bb and aa<=cc else b if bb<=cc else c
                encoded[at]=(row[at]-p)&255
        rows.append(bytes([filter_kind])+encoded);previous=row
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1280,900,8,6 if alpha else 2,0,0,0))+(chunk(b'tEXt',metadata) if metadata else b'')+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')

class PixelTests(unittest.TestCase):
    def test_exact_domain_rectangle_and_complete_rgb_bytes(self):
        expected=hashlib.sha256(pixels.DOMAIN+struct.pack('>4I',380,335,520,235)+b'\0'*(520*235*3)).hexdigest()
        self.assertEqual(pixels.pixel_hash(sample_png(),WINDOW),expected)
    def test_outside_changes_only_leave_hash_equal(self):
        original=pixels.pixel_hash(sample_png(),WINDOW)
        self.assertEqual(pixels.pixel_hash(sample_png({(379,335):(1,2,3),(900,335):(4,5,6),(380,570):(7,8,9)}),WINDOW),original)
        for point in [(380,335),(899,569),(448,403),(448,443),(765,539),(685,539)]:
            with self.subTest(point=point):self.assertNotEqual(pixels.pixel_hash(sample_png({point:(1,2,3)}),WINDOW),original)
    def test_all_png_filters_match_same_samples(self):
        changes={(380,335):(12,42,242),(899,569):(97,85,13)}
        expected=pixels.pixel_hash(sample_png(changes),WINDOW)
        for kind in (1,2,3,4):self.assertEqual(pixels.pixel_hash(sample_png(changes,filter_kind=kind),WINDOW),expected)
    def test_opaque_rgba_and_stripped_metadata_same_hash(self):
        plain=pixels.pixel_hash(sample_png(),WINDOW)
        self.assertEqual(pixels.pixel_hash(sample_png(alpha=True),WINDOW),plain)
        self.assertEqual(pixels.pixel_hash(sample_png(metadata=b'irrelevant fixture metadata'),WINDOW),plain)
        with self.assertRaises(ValueError):pixels.pixel_hash(sample_png({(0,0):(0,0,0,254)},alpha=True),WINDOW)
    def test_geometry_bool_partial_and_bad_png_rejected(self):
        image=sample_png()
        for changed in ({'x':True},{'border':1},{'x':-1},{'width':0},{'height':1000}):
            with self.assertRaises(ValueError):pixels.pixel_hash(image,{**WINDOW,**changed})
        for bad in (image[:-1],image+b'x',b'x'*100):
            with self.assertRaises(ValueError):pixels.pixel_hash(bad,WINDOW)
        self.assertNotEqual(pixels.pixel_hash(image,{**WINDOW,'width':519}),pixels.pixel_hash(image,WINDOW))
if __name__=='__main__':unittest.main()
