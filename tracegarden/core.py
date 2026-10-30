from __future__ import annotations

import io
import math
import time
import xml.etree.ElementTree as ET
from typing import Literal

import vtracer
from PIL import Image, ImageOps, ImageFilter, UnidentifiedImageError
from pydantic import BaseModel, Field

MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', NS[1:-1])


class Options(BaseModel):
    preset: Literal['logo', 'illustration', 'photo', 'ink', 'pixel'] = 'logo'
    colors: int = Field(16, ge=2, le=256)
    speckle: int = Field(4, ge=0, le=64)
    corner: int = Field(60, ge=0, le=180)
    precision: int = Field(4, ge=1, le=8)
    threshold: int = Field(128, ge=0, le=255)
    max_size: int = Field(1600, ge=64, le=4096)
    smooth: bool = False
    remove_white: bool = False


def trace(data: bytes, options: Options) -> dict:
    started = time.perf_counter()
    if len(data) > MAX_BYTES:
        raise ValueError('Image exceeds the 25 MB limit.')
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ValueError('Image exceeds the 16 megapixel limit.')
            if source.format not in {'PNG', 'JPEG', 'WEBP', 'BMP', 'GIF', 'TIFF'}:
                raise ValueError('Choose PNG, JPEG, WebP, BMP, GIF or TIFF.')
            original = source.size
            image = ImageOps.exif_transpose(source).convert('RGBA')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('This image could not be opened. Try a PNG or JPEG.') from exc
    image.thumbnail((options.max_size, options.max_size), Image.Resampling.LANCZOS)
    alpha = image.getchannel('A')
    rgb = Image.new('RGB', image.size, 'white')
    rgb.paste(image, mask=alpha)
    if options.smooth:
        rgb = rgb.filter(ImageFilter.MedianFilter(3))
    if options.preset == 'ink':
        rgb = rgb.convert('L').point(lambda p: 255 if p >= options.threshold else 0).convert('RGB')
    elif options.preset != 'photo':
        rgb = rgb.quantize(colors=options.colors, method=Image.Quantize.MEDIANCUT).convert('RGB')
    image = rgb.convert('RGBA')
    image.putalpha(alpha)
    if options.remove_white:
        image.putdata([(r, g, b, 0 if min(r, g, b) > 245 else a) for r, g, b, a in image.getdata()])
    svg = vtracer.convert_pixels_to_svg(
        list(image.getdata()), image.size, colormode='color',
        hierarchical='stacked', mode='polygon' if options.preset == 'pixel' else 'spline',
        filter_speckle=options.speckle, color_precision=options.precision,
        corner_threshold=options.corner, length_threshold=4.0,
        max_iterations=10, splice_threshold=45, path_precision=3)
    root = ET.fromstring(svg)
    root.set('viewBox', f'0 0 {image.width} {image.height}')
    root.set('role', 'img')
    paths = root.findall(f'.//{NS}path')
    return {'svg': ET.tostring(root, encoding='unicode'), 'width': image.width,
            'height': image.height, 'original': original, 'paths': len(paths),
            'seconds': round(time.perf_counter() - started, 3),
            'palette': sorted({p.get('fill', '#000000') for p in paths}),
            'resized': original != image.size}


def export(svg: str, fmt: str) -> bytes:
    # Only accept the tiny SVG dialect produced by our tracer/editor.
    if len(svg) > 20_000_000 or '<!DOCTYPE' in svg.upper() or '<!ENTITY' in svg.upper():
        raise ValueError('Invalid or oversized vector document.')
    root = ET.fromstring(svg)
    for el in root.iter():
        if el.tag not in {NS+'svg', NS+'path'}:
            raise ValueError('Only traced SVG paths are supported.')
        if any(k not in {'width','height','viewBox','version','role','d','fill','transform','stroke','stroke-width','fill-rule'} for k in el.attrib):
            raise ValueError('Unsupported SVG attributes.')
        if any('url(' in v.lower() or 'javascript:' in v.lower() for v in el.attrib.values()):
            raise ValueError('External references are not supported.')
    clean = ET.tostring(root, encoding='utf-8')
    if fmt == 'svg':
        return clean
    if fmt in {'pdf', 'eps', 'png'}:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF, renderPS, renderPM
        drawing = svg2rlg(io.BytesIO(clean))
        if fmt == 'pdf':
            return renderPDF.drawToString(drawing)
        if fmt == 'png':
            return renderPM.drawToString(drawing, fmt='PNG', dpi=96, backend='_renderPM')
        return renderPS.drawToString(drawing)
    if fmt == 'dxf':
        import ezdxf
        from svgpathtools import parse_path
        import re
        doc = ezdxf.new('R2010')
        doc.units = 0  # unitless: one drawing unit equals one source pixel
        space = doc.modelspace()
        for el in root.findall(f'.//{NS}path'):
            values = re.findall(r'[-+]?(?:\d*\.)?\d+', el.get('transform', ''))
            tx, ty = (float(values[0]), float(values[1])) if len(values) == 2 else (0, 0)
            for path in parse_path(el.get('d', '')).continuous_subpaths():
                points = []
                for segment in path:
                    count = min(2048, max(2, math.ceil(segment.length(error=1e-3) / 2)))
                    points.extend((segment.point(i/count).real+tx, -segment.point(i/count).imag-ty) for i in range(count))
                if path:
                    points.append((path.end.real+tx, -path.end.imag-ty))
                if len(points) > 1:
                    space.add_lwpolyline(points, close=path.isclosed())
        out = io.StringIO()
        doc.write(out)
        return out.getvalue().encode('utf-8')
    raise ValueError('Unsupported export format.')
