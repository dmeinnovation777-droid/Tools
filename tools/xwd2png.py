import struct, sys
from PIL import Image
def conv(src,dst):
    d=open(src,'rb').read(); h=struct.unpack('>25I',d[:100])
    hsize,w,hgt,bpl,ncolors=h[0],h[4],h[5],h[12],h[19]
    raw=d[hsize+ncolors*12:][:bpl*hgt]
    img=Image.frombytes('RGBX',(bpl//4,hgt),raw).convert('RGB').crop((0,0,w,hgt))
    b,g,r=img.split(); Image.merge('RGB',(r,g,b)).save(dst)
    print(dst,w,hgt)
conv(sys.argv[1], sys.argv[2])
