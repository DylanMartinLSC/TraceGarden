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
    import cv2
    from PIL import Image

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
    if min(w, h) < 1 or w * h > 20_000_000:
        raise ValueError("Requested PNG exceeds the 20 megapixel limit.")
    # Premultiplied alpha compositing, no background matte.
    canvas = np.zeros((h, w, 4), np.float32)
    grads = gradient_map(root)
    for el in root.findall(NS + "path"):
        coordinates = [np.array(r) * scale for r in rings(el, step=0.75)]
        if not coordinates:
            continue
        points = np.concatenate(coordinates)
        padding = max(2, math.ceil(float(el.get("stroke-width", "1")) * scale))
        left = max(0, int(np.floor(points[:, 0].min())) - padding)
        top = max(0, int(np.floor(points[:, 1].min())) - padding)
        right = min(w, int(np.ceil(points[:, 0].max())) + padding + 1)
        bottom = min(h, int(np.ceil(points[:, 1].max())) + padding + 1)
        if left >= right or top >= bottom:
            continue
        target = canvas[top:bottom, left:right]
        mask = np.zeros((bottom - top, right - left), np.uint8)
        contours = [
            np.rint((r - [left, top]) * 256).astype(np.int32) for r in coordinates
        ]
        fill = el.get("fill", "#000000")
        opacity = float(el.get("opacity", "1"))
        if fill != "none" and contours:
            cv2.fillPoly(
                mask,
                [c for c in contours if len(c) >= 3],
                255,
                lineType=cv2.LINE_AA,
                shift=8,
            )
            alpha = mask.astype(np.float32) / 255 * opacity
            if fill.startswith("url("):
                grad = grads[fill[5:-1]]
                stops = list(grad)
                start = (
                    np.array([float(grad.get("x1", "0")), float(grad.get("y1", "0"))])
                    * scale
                )
                end = (
                    np.array([float(grad.get("x2", "1")), float(grad.get("y2", "0"))])
                    * scale
                )
                vec = end - start
                den = max(float(vec @ vec), 1e-8)
                yy, xx = np.ogrid[top:bottom, left:right]
                t = np.clip(
                    ((xx - start[0]) * vec[0] + (yy - start[1]) * vec[1]) / den, 0, 1
                )
                c0, c1 = (
                    np.array(colors(stops[0].get("stop-color"))),
                    np.array(colors(stops[-1].get("stop-color"))),
                )
                rgb = (
                    c0[None, None, :] * (1 - t[:, :, None])
                    + c1[None, None, :] * t[:, :, None]
                )
            else:
                rgb = np.array(colors(fill))
            target[:, :, :3] = rgb * alpha[:, :, None] + target[:, :, :3] * (
                1 - alpha[:, :, None]
            )
            target[:, :, 3] = alpha + target[:, :, 3] * (1 - alpha)
        stroke = el.get("stroke", "none")
        if stroke != "none" and contours:
            mask[:] = 0
            cv2.polylines(
                mask,
                contours,
                False,
                255,
                max(1, round(float(el.get("stroke-width", "1")) * scale)),
                lineType=cv2.LINE_AA,
                shift=8,
            )
            a = mask.astype(np.float32) / 255 * opacity
            target[:, :, :3] = np.array(colors(stroke)) * a[:, :, None] + target[
                :, :, :3
            ] * (1 - a[:, :, None])
            target[:, :, 3] = a + target[:, :, 3] * (1 - a)
    alpha = canvas[:, :, 3:4]
    canvas[:, :, :3] = np.divide(
        canvas[:, :, :3], alpha, out=np.zeros_like(canvas[:, :, :3]), where=alpha > 0
    )
    out = io.BytesIO()
    Image.fromarray(np.clip(canvas * 255, 0, 255).astype(np.uint8), "RGBA").save(
        out, format="PNG", dpi=(options.dpi, options.dpi)
    )
    return out.getvalue()


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

    doc = ezdxf.new("R2010")
    doc.units = 4 if options.width_mm else 0
    width = float(root.get("width"))
    scale = options.width_mm / width if options.width_mm else 1
    space = doc.modelspace()

    def pt(z):
        return (z.real * scale, -z.imag * scale, 0)

    for el in root.findall(NS + "path"):
        if options.dxf_mode == "polyline":
            for ring in rings(el, step=0.5):
                if len(ring) > 1:
                    space.add_lwpolyline(
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
    if fmt not in {"svg", "pdf", "eps", "ai", "dxf", "png"}:
        raise ValueError("Unsupported export format.")
    if options.outline:
        for el in root.findall(NS + "path"):
            el.set("stroke", "#000000")
            el.set("stroke-width", "0.5")
            el.set("fill", "none")
    if fmt == "svg":
        if options.width_mm:
            ratio = float(root.get("height")) / float(root.get("width"))
            root.set("width", f"{options.width_mm:g}mm")
            root.set("height", f"{options.width_mm * ratio:g}mm")
        return serialize(root).encode()
    if fmt == "png":
        return render_png(root, options)
    if fmt in {"pdf", "ai"}:
        return vector_pdf(root, options)
    if fmt == "eps":
        return vector_eps(root, options)
    return cad_export(root, options)
