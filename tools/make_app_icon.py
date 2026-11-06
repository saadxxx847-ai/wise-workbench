"""Render the project's geometric R/play mark into a Windows ICO (stdlib only)."""
from pathlib import Path
import struct
import zlib


def inside(x, y, points):
    value = False
    previous = points[-1]
    for current in points:
        ax, ay = previous
        bx, by = current
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            value = not value
        previous = current
    return value


def png(size):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows = []
    mark = [(17,48),(17,16),(36,16),(45,20),(47,27),(43,34),(37,36),
            (49,48),(35,48),(24,34),(34,34),(37,32),(37,27),(34,25),(27,25),(27,48)]
    for iy in range(size):
        row=bytearray([0])
        for ix in range(size):
            x,y=(ix+.5)*64/size,(iy+.5)*64/size
            dx,dy=max(10-x,0,x-54),max(10-y,0,y-54)
            alpha = 255 if dx*dx+dy*dy <= 100 else 0
            color=(23,27,18) if inside(x,y,mark) else (200,244,119)
            row.extend((*color,alpha))
        rows.append(row)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')


def main():
    sizes=[16,24,32,48,64,128,256]
    images=[png(size) for size in sizes]
    offset=6+16*len(sizes)
    entries=[]
    for size,data in zip(sizes,images):
        entries.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset))
        offset+=len(data)
    target=Path(__file__).resolve().parents[1]/'static'/'app.ico'
    target.write_bytes(struct.pack('<HHH',0,1,len(sizes))+b''.join(entries)+b''.join(images))


if __name__=='__main__':
    main()
