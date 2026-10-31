"""Validate our editable SVG subset and perform vector geometry operations."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring
from svgpathtools import parse_path, Line, CubicBezier, Path as SVGPath
from pydantic import BaseModel, Field
from typing import Literal

NS = "{http://www.w3.org/2000/svg}"
NUMBER = re.compile(r"[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?")
COLOR = re.compile(r"^(#[\da-fA-F]{6}|none|black|white|url\(#g\d+\))$")
TAGS = {"svg", "path", "defs", "linearGradient", "stop"}
ATTRS = {
    "width",
    "height",
    "viewBox",
    "version",
    "role",
    "d",
    "fill",
    "transform",
    "stroke",
    "stroke-width",
    "fill-rule",
    "opacity",
    "id",
    "x1",
    "x2",
    "y1",
    "y2",
    "gradientUnits",
    "offset",
    "stop-color",
    "stroke-linecap",
    "stroke-linejoin",
}


def serialize(root):
    ET.register_namespace("", NS[1:-1])
    return ET.tostring(root, encoding="unicode")


def validate_svg(svg: str):
    if len(svg.encode()) > 20_000_000:
        raise ValueError("Vector document exceeds 20 MB.")
    try:
        root = fromstring(svg)
    except Exception as exc:
        raise ValueError("Invalid vector document.") from exc
    if root.tag != NS + "svg":
        raise ValueError("Expected an SVG document.")
    width = float(root.get("width", "0"))
    height = float(root.get("height", "0"))
    if not all(math.isfinite(x) and 0 < x <= 32768 for x in (width, height)):
        raise ValueError("Vector dimensions must be between 1 and 32768 pixels.")
    if width * height > 100_000_000:
        raise ValueError("Vector canvas exceeds 100 megapixels.")
    if root.get("viewBox"):
        values = [float(x) for x in NUMBER.findall(root.get("viewBox"))]
        if values != [0, 0, width, height]:
            raise ValueError("Vector viewBox must match its dimensions.")
    if len(list(root.iter())) > 100_000:
        raise ValueError("Too many vector elements.")
    for el in root.iter():
        if el.tag not in {NS + t for t in TAGS} or any(
            k not in ATTRS for k in el.attrib
        ):
            raise ValueError("Unsupported vector element or attribute.")
        for name, value in el.attrib.items():
            if name in {"fill", "stroke", "stop-color"}:
                if not COLOR.fullmatch(value):
                    raise ValueError(
                        "Only solid colors and internal gradients are supported."
                    )
            elif name == "transform":
                if not re.fullmatch(r"\s*translate\(\s*[-+\deE.,\s]+\)\s*", value):
                    raise ValueError("Only translate transforms are supported.")
                if len(NUMBER.findall(value)) not in {1, 2}:
                    raise ValueError("Invalid translation.")
            elif name == "d":
                if (
                    re.search(r"[^MmLlHhVvCcSsQqTtAaZz\deE.,+\-\s]", value)
                    or len(value) > 2_000_000
                ):
                    raise ValueError("Invalid or oversized path.")
            elif name in {"opacity", "offset"}:
                if not 0 <= float(value) <= 1:
                    raise ValueError("Opacity and offsets must be between 0 and 1.")
            elif name == "id" and not re.fullmatch(r"[pg]\d+", value):
                raise ValueError("Invalid vector identifier.")
            elif "url(" in value.lower() or "javascript:" in value.lower():
                raise ValueError("External references are not supported.")
        for name in {
            "d",
            "transform",
            "x1",
            "x2",
            "y1",
            "y2",
            "stroke-width",
        } & el.attrib.keys():
            if any(
                not math.isfinite(float(v)) or abs(float(v)) > 1_000_000
                for v in NUMBER.findall(el.get(name))
            ):
                raise ValueError("Invalid vector coordinates.")
        if el.tag == NS + "path" and el.get("d"):
            try:
                path = parse_path(el.get("d"))
                if len(path) > 100_000:
                    raise ValueError("Too many path segments.")
            except Exception as exc:
                raise ValueError("Invalid path geometry.") from exc
    for el in root:
        if el.tag not in {NS + "path", NS + "defs"}:
            raise ValueError("Invalid document structure.")
    for defs in root.findall(NS + "defs"):
        if any(el.tag != NS + "linearGradient" for el in defs):
            raise ValueError("Invalid gradient definitions.")
        for grad in defs:
            if any(el.tag != NS + "stop" for el in grad):
                raise ValueError("Invalid gradient stops.")
            if (
                len(grad) != 2
                or [s.get("offset") for s in grad] != ["0", "1"]
                or grad.get("gradientUnits") != "userSpaceOnUse"
            ):
                raise ValueError(
                    "Gradients require two endpoint stops in document coordinates."
                )
    ids = [el.get("id") for el in root.iter() if el.get("id")]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate vector identifiers.")
    gradients = {g.get("id") for g in root.findall(f"{NS}defs/{NS}linearGradient")}
    for el in root.findall(NS + "path"):
        fill = el.get("fill", "")
        if fill.startswith("url(") and fill[5:-1] not in gradients:
            raise ValueError("Missing gradient definition.")
        if el.get("stroke", "").startswith("url("):
            raise ValueError("Gradient strokes are not supported.")
    return root


def absolute_path(el):
    p = parse_path(el.get("d", ""))
    values = [float(v) for v in NUMBER.findall(el.get("transform", ""))]
    if values:
        p = p.translated(complex(values[0], values[1] if len(values) > 1 else 0))
    return p


def rings(el, step=1.5):
    result = []
    for path in absolute_path(el).continuous_subpaths():
        points = []
        for seg in path:
            n = (
                1
                if isinstance(seg, Line)
                else min(4096, max(4, math.ceil(seg.length(error=1e-3) / step)))
            )
            points.extend(
                (seg.point(i / n).real, seg.point(i / n).imag) for i in range(n)
            )
        if path:
            points.append((path.end.real, path.end.imag))
        if len(points) > 1:
            result.append(points)
    return result


def polygon(el):
    from shapely.geometry import Polygon
    from shapely import make_valid

    # SVG evenodd: XOR nested rings, preserving holes regardless of winding.
    pieces = []
    for ring in rings(el):
        if len(ring) >= 4:
            pieces.append(make_valid(Polygon(ring)))
    # Balanced parity reduction avoids repeatedly rebuilding a large exterior
    # when a face contains thousands of holes (quadratic sequential XOR).
    while len(pieces) > 1:
        pieces = [
            pieces[i].symmetric_difference(pieces[i + 1])
            if i + 1 < len(pieces)
            else pieces[i]
            for i in range(0, len(pieces), 2)
        ]
    return make_valid(pieces[0]) if pieces else Polygon()


def polygon_d(geom):
    from shapely.geometry.polygon import orient

    out = []
    polygons = (
        [geom]
        if geom.geom_type == "Polygon"
        else [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
    )
    for poly in polygons:
        poly = orient(poly, sign=1.0)
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)
            out.append("M" + " L".join(f"{x:.3f} {y:.3f}" for x, y in pts) + " Z")
    return " ".join(out)


class EditRequest(BaseModel):
    svg: str
    operation: Literal[
        "nodes",
        "set-nodes",
        "curves",
        "set-curves",
        "union",
        "subtract",
        "intersect",
        "split",
        "simplify",
        "outline",
        "reverse",
        "corner-info",
        "round-corners",
        "shape",
        "similar",
        "repeat",
    ]
    indices: list[int] = Field(default_factory=list, max_length=500)
    points: list[list[float]] = Field(default_factory=list, max_length=10000)
    tolerance: float = Field(1.0, ge=0.05, le=20)
    radius: float = Field(8, ge=0, le=1000)
    corner_indices: list[int] | None = None
    shape_type: Literal["circle", "ellipse", "rectangle", "star", "polygon"] = (
        "rectangle"
    )
    center: tuple[float, float] = (64, 64)
    size: tuple[float, float] = (80, 80)
    rotation: float = Field(0, ge=-360, le=360)
    sides: int = Field(5, ge=3, le=32)
    inner_ratio: float = Field(0.45, ge=0.05, le=0.95)


def edit_vector(req: EditRequest):
    root = validate_svg(req.svg)
    paths = root.findall(NS + "path")
    if not req.indices or any(i < 0 or i >= len(paths) for i in req.indices):
        raise ValueError("Select one or more valid shapes.")
    chosen = [paths[i] for i in sorted(set(req.indices))]
    if req.operation == "similar":
        from .repetition import repeated

        return {"matches": repeated(paths, req.indices[0])}
    if req.operation == "repeat":
        from .repetition import apply_repeats

        apply_repeats(paths, sorted(set(req.indices)))
    if req.operation == "corner-info":
        from .modeling import corner_data

        return {"corners": corner_data(chosen[0])}
    if req.operation == "round-corners":
        from .modeling import round_corners

        for el in chosen:
            el.set("d", round_corners(el, req.radius, req.corner_indices).d())
            el.attrib.pop("transform", None)
    if req.operation == "shape":
        from .modeling import shape_path

        if (
            min(req.size) <= 0
            or max(req.size) > 16000
            or any(
                not math.isfinite(v) or abs(v) > 100000
                for v in [*req.center, *req.size]
            )
        ):
            raise ValueError("Invalid shape dimensions.")
        for el in chosen:
            el.set(
                "d",
                shape_path(
                    req.shape_type,
                    *req.center,
                    *req.size,
                    req.rotation,
                    req.radius,
                    req.sides,
                    req.inner_ratio,
                ).d(),
            )
            el.attrib.pop("transform", None)
    if req.operation == "nodes":
        subpaths = rings(chosen[0], step=max(2, req.tolerance * 3))
        return {"subpaths": subpaths}
    if req.operation == "curves":
        from .exporters import cubics

        subpaths = absolute_path(chosen[0]).continuous_subpaths()
        if len(subpaths) != 1:
            raise ValueError("Split this compound shape before editing curves.")
        points = []
        for seg in subpaths[0]:
            for s in cubics(seg):
                if isinstance(s, Line):
                    s = CubicBezier(
                        s.start,
                        s.start + (s.end - s.start) / 3,
                        s.start + (s.end - s.start) * 2 / 3,
                        s.end,
                    )
                points.extend(
                    [[z.real, z.imag] for z in [s.start, s.control1, s.control2, s.end]]
                )
        return {"points": points}
    if req.operation == "set-curves":
        if (
            not req.points
            or len(req.points) % 4
            or any(
                len(p) != 2 or any(not math.isfinite(v) or abs(v) > 100000 for v in p)
                for p in req.points
            )
        ):
            raise ValueError("Curve controls require groups of four finite x,y points.")
        if len(absolute_path(chosen[0]).continuous_subpaths()) != 1:
            raise ValueError("Split this compound shape first.")
        curves = []
        for i in range(0, len(req.points), 4):
            pts = [complex(*p) for p in req.points[i : i + 4]]
            if curves:
                pts[0] = curves[-1].end
            curves.append(CubicBezier(*pts))
        if absolute_path(chosen[0]).isclosed():
            curves[-1] = CubicBezier(
                curves[-1].start,
                curves[-1].control1,
                curves[-1].control2,
                curves[0].start,
            )
        chosen[0].set("d", SVGPath(*curves).d())
        chosen[0].attrib.pop("transform", None)
    elif req.operation == "set-nodes":
        if len(req.points) < 2 or any(
            len(p) != 2 or any(not math.isfinite(v) or abs(v) > 100000 for v in p)
            for p in req.points
        ):
            raise ValueError("Provide at least two finite nodes.")
        # This operation edits a selected single contour; do not silently discard holes.
        if len(absolute_path(chosen[0]).continuous_subpaths()) != 1:
            raise ValueError("Split this compound shape before editing nodes.")
        was_closed = absolute_path(chosen[0]).isclosed()
        chosen[0].set(
            "d",
            "M"
            + " L".join(f"{x:.3f} {y:.3f}" for x, y in req.points)
            + (" Z" if was_closed else ""),
        )
        chosen[0].attrib.pop("transform", None)
    elif req.operation in {"union", "subtract", "intersect"}:
        if len(chosen) < 2:
            raise ValueError("Select at least two shapes.")
        shape = polygon(chosen[0])
        for el in chosen[1:]:
            other = polygon(el)
            shape = (
                shape.union(other)
                if req.operation == "union"
                else shape.difference(other)
                if req.operation == "subtract"
                else shape.intersection(other)
            )
        chosen[0].set("d", polygon_d(shape))
        chosen[0].attrib.pop("transform", None)
        chosen[0].set("fill-rule", "evenodd")
        for el in chosen[1:]:
            root.remove(el)
    elif req.operation == "split":
        for el in chosen:
            for part in absolute_path(el).continuous_subpaths():
                node = ET.SubElement(
                    root,
                    NS + "path",
                    {
                        k: v
                        for k, v in el.attrib.items()
                        if k not in {"id", "d", "transform"}
                    },
                )
                node.set("d", part.d())
            root.remove(el)
    elif req.operation == "simplify":
        from shapely.geometry import LineString

        for el in chosen:
            pieces = []
            for ring in rings(el):
                pts = list(
                    LineString(ring)
                    .simplify(req.tolerance, preserve_topology=True)
                    .coords
                )
                pieces.append(
                    "M"
                    + " L".join(f"{x:.3f} {y:.3f}" for x, y in pts)
                    + (" Z" if ring[0] == ring[-1] else "")
                )
            el.set("d", " ".join(pieces))
            el.attrib.pop("transform", None)
    elif req.operation == "outline":
        for el in chosen:
            el.set(
                "stroke",
                el.get("fill")
                if COLOR.fullmatch(el.get("fill", "")) and el.get("fill") != "none"
                else "#000000",
            )
            el.set("fill", "none")
            el.set("stroke-width", "1")
    elif req.operation == "reverse":
        for el in chosen:
            el.set("d", absolute_path(el).reversed().d())
            el.attrib.pop("transform", None)
    for i, el in enumerate(root.findall(NS + "path")):
        el.set("id", f"p{i}")
    return {"svg": serialize(root)}
