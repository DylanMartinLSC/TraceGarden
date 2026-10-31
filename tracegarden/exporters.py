"""Vector PDF/EPS/AI-compatible exports, PNG rasterization and CAD geometry."""

from __future__ import annotations
import io
import math
from typing import Literal
import numpy as np
from pydantic import BaseModel, Field
from svgpathtools import Line, CubicBezier, QuadraticBezier, Arc
from .svgdoc import NS, absolute_path, rings, serialize, validate_svg


class ExportOptions(BaseModel):
    dpi: int = Field(96, ge=24, le=1200)
    width_mm: float | None = Field(None, ge=1, le=5000)
    outline: bool = False
    color_space: Literal["rgb", "cmyk"] = "rgb"
    dxf_mode: Literal["spline", "polyline"] = "spline"
    grouping: Literal["none", "color"] = "none"
    draw_style: Literal["fill", "stroke", "fill-stroke"] = "fill"
    curve_mode: Literal["all", "cubic", "quadratic", "polyline"] = "all"
    compatibility: Literal["modern", "legacy"] = "modern"
    quality: int = Field(95, ge=1, le=100)
    memory_limit_mib: int = Field(1024, ge=128, le=32768)


def colors(hexcolor):
    if hexcolor in {"black", "white"}:
        return (0, 0, 0) if hexcolor == "black" else (1, 1, 1)
    return tuple(int(hexcolor[i : i + 2], 16) / 255 for i in (1, 3, 5))


def cubics(segment):
    if isinstance(segment, Arc):
        return list(
            segment.as_cubic_curves(curves=max(1, math.ceil(abs(segment.delta) / 45)))
        )
    if isinstance(segment, QuadraticBezier):
        return [
            CubicBezier(
                segment.start,
                segment.start + (segment.control - segment.start) * 2 / 3,
                segment.end + (segment.control - segment.end) * 2 / 3,
                segment.end,
            )
        ]
    return [segment]


def commands(path):
    for sub in path.continuous_subpaths():
        if not sub:
            continue
        yield "moveTo", (sub.start.real, sub.start.imag)
        for segment in sub:
            for seg in cubics(segment):
                if isinstance(seg, Line):
                    yield "lineTo", (seg.end.real, seg.end.imag)
                else:
                    yield (
                        "curveTo",
                        (
                            seg.control1.real,
                            seg.control1.imag,
                            seg.control2.real,
                            seg.control2.imag,
                            seg.end.real,
                            seg.end.imag,
                        ),
                    )
        if sub.isclosed():
            yield "close", ()


def gradient_map(root):
    return {g.get("id"): g for g in root.findall(f"{NS}defs/{NS}linearGradient")}


def render_png(root, options=None):
    """Render through independent CPU resvg, preserving SVG coverage and alpha."""
    import struct
    import zlib
    from resvg_py import svg_to_bytes

    options = options or ExportOptions()
    scale = (
        options.width_mm / 25.4 * options.dpi / float(root.get("width"))
        if options.width_mm
        else 1
    )
    w, h = (
        round(float(root.get("width")) * scale),
        round(float(root.get("height")) * scale),
    )
    maximum = options.memory_limit_mib * 1024**2 // 16
    if min(w, h) < 1 or w * h > maximum:
        raise ValueError(
            f"Requested PNG exceeds the {maximum / 1_000_000:.1f} megapixel limit for this memory budget."
        )
    data = svg_to_bytes(
        svg_string=serialize(root), width=w, height=h, skip_system_fonts=True
    )
    density = round(options.dpi / 0.0254)
    payload = struct.pack(">IIB", density, density, 1)
    physical = (
        struct.pack(">I", len(payload))
        + b"pHYs"
        + payload
        + struct.pack(">I", zlib.crc32(b"pHYs" + payload) & 0xFFFFFFFF)
    )
    # Add a single standard PNG physical-size chunk without decoding/reencoding.
    output = data[:8]
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        chunk = data[offset : offset + length + 12]
        if kind != b"pHYs":
            output += chunk
        if kind == b"IHDR":
            output += physical
        offset += length + 12
    return output


def vector_pdf(root, options):
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import Color, CMYKColor

    w, h = float(root.get("width")), float(root.get("height"))
    scale = options.width_mm * 72 / 25.4 / w if options.width_mm else 72 / options.dpi
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(w * scale, h * scale), pageCompression=1)
    c.setTitle("TraceGarden vector artwork")
    c.translate(0, h * scale)
    c.scale(scale, -scale)
    grads = gradient_map(root)

    def color(v):
        r, g, b = colors(v)
        if options.color_space == "cmyk":
            k = 1 - max(r, g, b)
            return CMYKColor(
                0 if k == 1 else (1 - r - k) / (1 - k),
                0 if k == 1 else (1 - g - k) / (1 - k),
                0 if k == 1 else (1 - b - k) / (1 - k),
                k,
            )
        return Color(r, g, b)

    for el in root.findall(NS + "path"):
        c.saveState()
        p = c.beginPath()
        for name, args in commands(absolute_path(el)):
            getattr(p, name)(*args)
        fill = el.get("fill", "#000000")
        stroke = el.get("stroke", "none")
        c.setFillAlpha(float(el.get("opacity", "1")))
        c.setStrokeAlpha(float(el.get("opacity", "1")))
        c.setLineWidth(float(el.get("stroke-width", "1")))
        if stroke != "none":
            c.setStrokeColor(color(stroke))
        if fill.startswith("url("):
            grad = grads[fill[5:-1]]
            stops = list(grad)
            c.saveState()
            c.clipPath(p, stroke=0, fill=0, fillMode=0)
            c.linearGradient(
                *[float(grad.get(a, "0")) for a in ["x1", "y1", "x2", "y2"]],
                colors=[color(s.get("stop-color")) for s in stops],
                positions=[float(s.get("offset")) for s in stops],
                extend=True,
            )
            c.restoreState()
            if stroke != "none":
                c.drawPath(p, stroke=1, fill=0)
        else:
            if fill != "none":
                c.setFillColor(color(fill))
            c.drawPath(
                p,
                stroke=stroke != "none",
                fill=fill != "none",
                fillMode=0 if el.get("fill-rule") == "evenodd" else 1,
            )
        c.restoreState()
    c.showPage()
    c.save()
    return out.getvalue()


def vector_eps(root, options):
    w, h = float(root.get("width")), float(root.get("height"))
    scale = options.width_mm * 72 / 25.4 / w if options.width_mm else 72 / options.dpi
    lines = [
        "%!PS-Adobe-3.0 EPSF-3.0",
        f"%%BoundingBox: 0 0 {math.ceil(w * scale)} {math.ceil(h * scale)}",
        "%%LanguageLevel: 3",
        "%%EndComments",
        f"0 {h * scale} translate {scale} {-scale} scale",
    ]
    grads = gradient_map(root)
    for el in root.findall(NS + "path"):
        fill = el.get("fill", "#000000")
        stroke = el.get("stroke", "none")
        lines += ["gsave", "newpath"]
        for name, args in commands(absolute_path(el)):
            lines.append(
                " ".join(f"{v:.5f}" for v in args)
                + " "
                + {
                    "moveTo": "moveto",
                    "lineTo": "lineto",
                    "curveTo": "curveto",
                    "close": "closepath",
                }[name]
            )
        # EPS has no alpha. Its limitation is surfaced by the UI/report.
        if fill.startswith("url("):
            grad = grads[fill[5:-1]]
            stops = list(grad)
            coords = " ".join(grad.get(a, "0") for a in ["x1", "y1", "x2", "y2"])
            c0 = " ".join(map(str, colors(stops[0].get("stop-color"))))
            c1 = " ".join(map(str, colors(stops[-1].get("stop-color"))))
            lines += [
                "gsave eoclip",
                f"<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [{coords}] /Function << /FunctionType 2 /Domain [0 1] /C0 [{c0}] /C1 [{c1}] /N 1 >> /Extend [true true] >> shfill",
                "grestore",
            ]
        elif fill != "none":
            lines += [
                "gsave",
                " ".join(map(str, colors(fill))) + " setrgbcolor",
                "eofill" if el.get("fill-rule") == "evenodd" else "fill",
                "grestore",
            ]
        if stroke != "none":
            lines += [
                " ".join(map(str, colors(stroke))) + " setrgbcolor",
                el.get("stroke-width", "1") + " setlinewidth",
                "stroke",
            ]
        lines += ["grestore"]
    lines += ["showpage", "%%EOF"]
    return "\n".join(lines).encode("ascii")


def cad_export(root, options):
    import ezdxf

    doc = ezdxf.new("R12" if options.compatibility == "legacy" else "R2010")
    doc.units = 4 if options.width_mm else 0
    width = float(root.get("width"))
    scale = options.width_mm / width if options.width_mm else 1
    space = doc.modelspace()

    def pt(z):
        return (z.real * scale, -z.imag * scale, 0)

    for el in root.findall(NS + "path"):
        if options.dxf_mode == "polyline" or options.compatibility == "legacy":
            for ring in rings(el, step=0.5):
                if len(ring) > 1:
                    method = (
                        space.add_polyline2d
                        if options.compatibility == "legacy"
                        else space.add_lwpolyline
                    )
                    method(
                        [(x * scale, -y * scale) for x, y in ring],
                        close=ring[0] == ring[-1],
                    )
            continue
        for seg in absolute_path(el):
            if isinstance(seg, Arc) and abs(seg.radius.real - seg.radius.imag) < 1e-4:
                center = seg.center
                r = seg.radius.real * scale
                a = math.degrees(
                    math.atan2(
                        -(seg.start - seg.center).imag, (seg.start - seg.center).real
                    )
                )
                b = math.degrees(
                    math.atan2(
                        -(seg.end - seg.center).imag, (seg.end - seg.center).real
                    )
                )
                if seg.delta > 0:
                    a, b = b, a
                space.add_arc(pt(center), r, a, b)
            elif isinstance(seg, Arc):
                rx, ry = seg.radius.real, seg.radius.imag
                angle = math.radians(seg.rotation)
                if rx >= ry:
                    major = (
                        rx * math.cos(angle) * scale,
                        -rx * math.sin(angle) * scale,
                        0,
                    )
                    start = -math.radians(seg.theta)
                    end = -math.radians(seg.theta + seg.delta)
                else:
                    major = (
                        -ry * math.sin(angle) * scale,
                        -ry * math.cos(angle) * scale,
                        0,
                    )
                    start = math.pi / 2 - math.radians(seg.theta)
                    end = math.pi / 2 - math.radians(seg.theta + seg.delta)
                if seg.delta > 0:
                    start, end = end, start
                space.add_ellipse(
                    pt(seg.center),
                    major_axis=major,
                    ratio=min(rx, ry) / max(rx, ry),
                    start_param=start,
                    end_param=end,
                )
            else:
                for part in cubics(seg):
                    if isinstance(part, Line):
                        space.add_line(pt(part.start), pt(part.end))
                    else:
                        spline = space.add_spline(degree=3)
                        spline.control_points = [
                            pt(z)
                            for z in [
                                part.start,
                                part.control1,
                                part.control2,
                                part.end,
                            ]
                        ]
                        spline.knots = [0, 0, 0, 0, 1, 1, 1, 1]
    out = io.StringIO()
    doc.write(out)
    return out.getvalue().encode()


def export_document(svg, fmt, options=None):
    options = options or ExportOptions()
    root = validate_svg(svg)
    if fmt not in {
        "svg",
        "pdf",
        "eps",
        "ai",
        "dxf",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "bmp",
        "tiff",
    }:
        raise ValueError("Unsupported export format.")
    if options.outline:
        for el in root.findall(NS + "path"):
            el.set("stroke", "#000000")
            el.set("stroke-width", "0.5")
            el.set("fill", "none")
    elif options.draw_style != "fill":
        for el in root.findall(NS + "path"):
            el.set(
                "stroke",
                el.get("fill")
                if not el.get("fill", "").startswith("url(")
                and el.get("fill") != "none"
                else "#000000",
            )
            el.set("stroke-width", "1")
            if options.draw_style == "stroke":
                el.set("fill", "none")
    if options.curve_mode != "all":
        from .curves import convert_curves

        convert_curves(root, options.curve_mode)
    if fmt == "svg":
        if options.width_mm:
            ratio = float(root.get("height")) / float(root.get("width"))
            root.set("width", f"{options.width_mm:g}mm")
            root.set("height", f"{options.width_mm * ratio:g}mm")
        if options.grouping == "color":
            import xml.etree.ElementTree as ET

            groups = {}
            for el in list(root.findall(NS + "path")):
                color = el.get("fill", "none")
                if color not in groups:
                    groups[color] = ET.SubElement(root, NS + "g")
                root.remove(el)
                groups[color].append(el)
        return serialize(root).encode()
    if fmt == "png":
        return render_png(root, options)
    if fmt in {"jpg", "jpeg", "gif", "bmp", "tiff"}:
        from PIL import Image

        image = Image.open(io.BytesIO(render_png(root, options))).convert("RGBA")
        matte = Image.new("RGB", image.size, "white")
        matte.paste(image, mask=image.getchannel("A"))
        out = io.BytesIO()
        if fmt == "gif":
            pal = matte.quantize(colors=255)
            alpha = np.asarray(image.getchannel("A"))
            indices = np.asarray(pal).copy()
            indices[alpha < 128] = 255
            final = Image.fromarray(indices, "P")
            final.putpalette(pal.getpalette())
            final.save(out, format="GIF", transparency=255)
        else:
            matte.save(
                out,
                format={"jpg": "JPEG", "jpeg": "JPEG", "bmp": "BMP", "tiff": "TIFF"}[
                    fmt
                ],
                quality=options.quality,
                dpi=(options.dpi, options.dpi),
            )
        return out.getvalue()
    if fmt in {"pdf", "ai"}:
        return vector_pdf(root, options)
    if fmt == "eps":
        return vector_eps(root, options)
    return cad_export(root, options)
