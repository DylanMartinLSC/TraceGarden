"""Pinned native CPU engine adapter and shared whole-component regularization."""

import re
import xml.etree.ElementTree as ET
from collections import defaultdict

import vtracer
from svgpathtools import CubicBezier, Line, QuadraticBezier

from .svgdoc import NS, absolute_path
from .tuning import current


def native_trace(image, options, shared=False):
    tuning = current()
    config = vtracer.Config(
        hierarchical="cutout" if shared else options.layering,
        mode="pixel" if options.preset == "pixel" else "spline",
        filter_speckle=options.speckle,
        color_precision=options.precision if options.preset == "photo" else 8,
        layer_difference=options.layer_difference if options.preset == "photo" else 0,
        corner_threshold=options.corner,
        length_threshold=tuning.length_threshold,
        max_iterations=tuning.max_iterations,
        splice_threshold=tuning.splice_threshold,
        simplify=tuning.simplify if options.preset != "pixel" else None,
        path_precision=tuning.path_precision,
        optimize=1,
    )
    return ET.fromstring(
        config.convert_pixels(image.tobytes(), image.width, image.height)
    )


def _key(path):
    edges = []
    for seg in path:
        if isinstance(seg, Line):
            points = [seg.start, seg.end]
        elif isinstance(seg, CubicBezier):
            points = [seg.start, seg.control1, seg.control2, seg.end]
        elif isinstance(seg, QuadraticBezier):
            points = [seg.start, seg.control, seg.end]
        else:
            points = [seg.point(t) for t in [0, 0.25, 0.5, 0.75, 1]]
        forward = tuple(round(v, 3) for p in points for v in [p.real, p.imag])
        reverse = tuple(round(v, 3) for p in reversed(points) for v in [p.real, p.imag])
        edges.append(min(forward, reverse))
    return tuple(sorted(edges))


def regularize_shared(root, opaque=True):
    from .enhance import primitives

    paths = root.findall(NS + "path")
    pieces = {}
    groups = defaultdict(list)
    for index, el in enumerate(paths):
        subs = absolute_path(el).continuous_subpaths()
        pieces[index] = subs
        for j, sub in enumerate(subs):
            if sub and sub.isclosed():
                groups[_key(sub)].append((index, j, sub))
    count = 0
    for group in groups.values():
        _, _, template = group[0]
        if len(group) == 1 and opaque:
            # A canvas-touching face can also contain interior junction edges.
            # Only whole components reused by every neighbor may be replaced.
            continue
        temporary = ET.Element(NS + "svg")
        el = ET.SubElement(temporary, NS + "path", {"d": template.d() + " Z"})
        if not primitives(temporary):
            continue
        fitted = absolute_path(el)
        direction = template.area()
        for index, j, sub in group:
            pieces[index][j] = (
                fitted if direction * sub.area() >= 0 else fitted.reversed()
            )
        count += 1
    for index, el in enumerate(paths):
        data = " ".join(
            sub.d() + (" Z" if sub and sub.isclosed() else "") for sub in pieces[index]
        )
        # SVG path reconstruction otherwise expands every native three-decimal
        # coordinate into full Python floats, doubling download size needlessly.
        data = re.sub(
            r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?",
            lambda m: (
                format(round(float(m[0]), 3), ".3f").rstrip("0").rstrip(".")
                if "." in format(round(float(m[0]), 3), ".3f")
                else m[0]
            ),
            data,
        )
        el.set("d", data)
        el.attrib.pop("transform", None)
    return count
