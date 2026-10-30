"""Reproducible synthetic CPU workload; not a claim of commercial parity."""
import argparse
import io
import json
import platform
import statistics
import time
from pathlib import Path
from PIL import Image, ImageDraw
from tracegarden.core import trace, Options


def image(kind, size):
    im=Image.new('RGB',(size,size),'#f4dfaa');d=ImageDraw.Draw(im)
    if kind=='logo':
        d.ellipse((size//8,size//8,size*7//8,size*7//8),fill='#315d45')
        d.rectangle((size//3,size//3,size*2//3,size*2//3),fill='#e89b54')
    elif kind=='illustration':
        for y in range(0,size,max(1,size//16)):
            for x in range(0,size,max(1,size//16)):
                d.ellipse((x,y,x+size//12,y+size//12),fill=(x*255//size,y*255//size,120))
    else:
        im.putdata([((x*255//size+y*31//size)%256,(y*255//size)%256,((x+y)*127//size)%256) for y in range(size) for x in range(size)])
    b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runs',type=int,default=3);args=parser.parse_args()
    trace(image('logo',64),Options())
    rows=[]
    for size in [512,1024,2048]:
        for kind in ['logo','illustration','gradient']:
            data=image(kind,size);results=[trace(data,Options(preset='photo' if kind=='gradient' else kind,max_size=4096)) for _ in range(args.runs)]
            times=[r['seconds'] for r in results];r=results[-1]
            rows.append(dict(case=kind,size=size,median_s=statistics.median(times),min_s=min(times),max_s=max(times),paths=r['paths'],svg_bytes=len(r['svg'].encode()),runs=args.runs))
            print(rows[-1],flush=True)
    out={'platform':platform.platform(),'processor':platform.processor(),'python':platform.python_version(),'engine':'vtracer 0.6.15','notes':'End-to-end decode, preprocessing, CPU tracing and serialization. Synthetic fixtures; no GPU or network. Quality and commercial-engine speed not compared.','results':rows}
    Path('benchmarks/results.json').write_text(json.dumps(out,indent=2))


if __name__=='__main__': main()
