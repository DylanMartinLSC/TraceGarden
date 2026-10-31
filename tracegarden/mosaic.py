"""Shared pixel-edge coverage tracing with topology-preserving simplification.

Each region starts on the same pixel boundaries as its neighbor. GEOS coverage
simplification processes both sides together so shared edges remain coincident.
"""

import xml.etree.ElementTree as ET
from collections import defaultdict
import numpy as np
from shapely.geometry import Polygon
from shapely import make_valid, coverage_simplify, coverage_is_valid
from shapely.ops import unary_union
from .svgdoc import NS, polygon_d


def trace_mosaic(image, tolerance=0.6):
    data = np.asarray(image)
    h, w = data.shape[:2]
    packed = (
        (data[:, :, 3].astype(np.int64) << 24)
        | (data[:, :, 0].astype(np.int64) << 16)
        | (data[:, :, 1].astype(np.int64) << 8)
        | data[:, :, 2].astype(np.int64)
    )
    packed[data[:, :, 3] == 0] = -1
    padded = np.pad(packed, 1, constant_values=-2)
    graph = defaultdict(lambda: defaultdict(list))
    edges = 0
    # Clockwise pixel edges, interior on the right (in image coordinates).
    for neighbor, offsets in [
        (padded[:-2, 1:-1], (0, 0, 1, 0)),
        (padded[1:-1, 2:], (1, 0, 1, 1)),
        (padded[2:, 1:-1], (1, 1, 0, 1)),
        (padded[1:-1, :-2], (0, 1, 0, 0)),
    ]:
        yy, xx = np.where((packed != neighbor) & (packed >= 0))
        edges += len(xx)
        if edges > 2_000_000:
            raise ValueError(
                "Shared-boundary trace is too complex. Reduce image size or palette size."
            )
        ax, ay, bx, by = offsets
        for y, x in zip(yy.tolist(), xx.tolist()):
            graph[int(packed[y, x])][(x + ax, y + ay)].append((x + bx, y + by))
    shapes = []
    colors = []
    for color, links in graph.items():
        rings = []
        while links:
            start = next(iter(links))
            current = start
            previous = (start[0] - 1, start[1])
            points = [start]
            while True:
                candidates = links[current]
                incoming = (current[0] - previous[0], current[1] - previous[1])

                # At diagonal contacts, take the tight right turn to keep contours separate.
                def priority(end):
                    dx, dy = end[0] - current[0], end[1] - current[1]
                    cross = incoming[0] * dy - incoming[1] * dx
                    dot = incoming[0] * dx + incoming[1] * dy
                    return 0 if cross > 0 else 1 if dot > 0 else 2 if cross < 0 else 3

                nxt = min(candidates, key=priority)
                candidates.remove(nxt)
                if not candidates:
                    del links[current]
                previous, current = current, nxt
                points.append(current)
                if current == start:
                    break
                if current not in links:
                    raise ValueError("Could not close a shared-boundary region.")
            if len(points) >= 4:
                rings.append(points)
        exteriors = []
        holes = []
        for ring in rings:
            area = (
                sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2
            )
            if area > 0:
                exteriors.append(Polygon(ring))
            elif area < 0:
                holes.append(Polygon(ring))
        assigned = [[] for _ in exteriors]
        for hole in holes:
            candidates = [
                (p.area, i)
                for i, p in enumerate(exteriors)
                if p.area > hole.area and p.covers(hole.representative_point())
            ]
            if candidates:
                assigned[min(candidates)[1]].append(hole)
        shape = make_valid(
            unary_union(
                [
                    p.difference(unary_union(assigned[i]))
                    for i, p in enumerate(exteriors)
                ]
            )
        )
        # Grouping disconnected shapes by color reduces SVG and keeps palette editing simple.
        if not shape.is_empty:
            shapes.append(shape)
            colors.append(color)
    if shapes and coverage_is_valid(shapes):
        shapes = list(
            coverage_simplify(shapes, tolerance=tolerance, simplify_boundary=True)
        )
    root = ET.Element(
        NS + "svg",
        {
            "width": str(w),
            "height": str(h),
            "viewBox": f"0 0 {w} {h}",
            "version": "1.1",
            "role": "img",
        },
    )
    for shape, color in zip(shapes, colors):
        node = ET.SubElement(
            root,
            NS + "path",
            {
                "d": polygon_d(shape),
                "fill": f"#{color & 0xFFFFFF:06X}",
                "fill-rule": "evenodd",
            },
        )
        if color >> 24 != 255:
            node.set("opacity", str(round((color >> 24) / 255, 6)))
    return root
