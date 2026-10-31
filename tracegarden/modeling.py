"""Parameterized shape construction and reversible geometric corner controls."""

import math
import numpy as np
from svgpathtools import Path, Line, CubicBezier, Arc
from .svgdoc import absolute_path


def unit(z):
    return z / abs(z) if abs(z) > 1e-10 else 1 + 0j


def _intersection(p, d, q, e):
    matrix = np.array([[d.real, -e.real], [d.imag, -e.imag]])
    if abs(np.linalg.det(matrix)) < 1e-9:
        return None
    t = np.linalg.solve(matrix, [q.real - p.real, q.imag - p.imag])[0]
    return p + d * t


def sharp_path(path):
    result = []
    for segment in path:
        if isinstance(segment, Arc) and abs(segment.delta) < 170:
            corner = _intersection(
                segment.start,
                unit(segment.derivative(0)),
                segment.end,
                unit(segment.derivative(1)),
            )
            if (
                corner is not None
                and abs(corner - segment.start) < abs(segment.end - segment.start) * 5
            ):
                result.extend([Line(segment.start, corner), Line(corner, segment.end)])
                continue
        result.append(segment)
    # Collapse adjacent collinear lines, including the seam of closed contours.
    changed = True
    while changed and len(result) > 2:
        changed = False
        for i in range(len(result) - 1):
            a, b = result[i : i + 2]
            if (
                isinstance(a, Line)
                and isinstance(b, Line)
                and abs(unit(a.end - a.start) - unit(b.end - b.start)) < 1e-5
            ):
                result[i : i + 2] = [Line(a.start, b.end)]
                changed = True
                break
    if (
        len(result) > 2
        and isinstance(result[-1], Line)
        and isinstance(result[0], Line)
        and abs(
            unit(result[-1].end - result[-1].start)
            - unit(result[0].end - result[0].start)
        )
        < 1e-5
    ):
        result = [Line(result[-1].start, result[0].end), *result[1:-1]]
    return Path(*result)


def corner_data(el):
    corners = []
    offset = 0
    for sub in absolute_path(el).continuous_subpaths():
        path = sharp_path(sub)
        n = len(path)
        for i in range(n if path.isclosed() else max(0, n - 1)):
            a, b = path[i], path[(i + 1) % n]
            d, e = unit(a.derivative(1)), unit(b.derivative(0))
            angle = math.degrees(math.acos(max(-1, min(1, (d.conjugate() * e).real))))
            if angle > 8:
                point = a.end
                corners.append(
                    {"index": offset, "x": point.real, "y": point.imag, "angle": angle}
                )
                offset += 1
    return corners


def round_corners(el, radius, indices=None):
    output = []
    corner_index = 0
    for sub in absolute_path(el).continuous_subpaths():
        path = sharp_path(sub)
        n = len(path)
        if not n:
            continue
        cuts_start = [0.0] * n
        cuts_end = [1.0] * n
        bridges = {}
        for i in range(n if path.isclosed() else max(0, n - 1)):
            j = (i + 1) % n
            a, b = path[i], path[j]
            d, e = unit(a.derivative(1)), unit(b.derivative(0))
            angle = math.acos(max(-1, min(1, (d.conjugate() * e).real)))
            if angle < math.radians(8):
                continue
            index = corner_index
            corner_index += 1
            if radius <= 0 or (indices is not None and index not in indices):
                continue
            length_a = a.length()
            length_b = b.length()
            distance = min(
                radius * math.tan(min(angle, math.pi - 0.01) / 2),
                length_a * 0.45,
                length_b * 0.45,
            )
            if distance < 1e-8:
                continue
            ta = a.ilength(max(0, length_a - distance))
            tb = b.ilength(min(length_b, distance))
            cuts_end[i] = min(cuts_end[i], ta)
            cuts_start[j] = max(cuts_start[j], tb)
            start, end = a.point(ta), b.point(tb)
            actual_radius = distance / max(math.tan(angle / 2), 1e-6)
            sweep = (d.conjugate() * e).imag > 0
            if isinstance(a, Line) and isinstance(b, Line):
                bridges[i] = Arc(
                    start, complex(actual_radius, actual_radius), 0, False, sweep, end
                )
            else:
                k = min(distance, abs(end - start) * 0.55)
                bridges[i] = CubicBezier(
                    start,
                    start + unit(a.derivative(ta)) * k,
                    end - unit(b.derivative(tb)) * k,
                    end,
                )
        for i, seg in enumerate(path):
            if cuts_end[i] > cuts_start[i] + 1e-8:
                output.append(seg.cropped(cuts_start[i], cuts_end[i]))
            if i in bridges:
                output.append(bridges[i])
    return Path(*output)


def shape_path(
    kind,
    cx=64,
    cy=64,
    width=80,
    height=80,
    rotation=0,
    radius=0,
    sides=5,
    inner_ratio=0.45,
):
    if kind in {"circle", "ellipse"}:
        rx, ry = width / 2, (width if kind == "circle" else height) / 2
        path = Path(
            Arc(complex(rx, 0), complex(rx, ry), 0, False, True, complex(-rx, 0)),
            Arc(complex(-rx, 0), complex(rx, ry), 0, False, True, complex(rx, 0)),
        )
    else:
        if kind == "rectangle":
            points = [
                complex(-width / 2, -height / 2),
                complex(width / 2, -height / 2),
                complex(width / 2, height / 2),
                complex(-width / 2, height / 2),
            ]
        else:
            count = 2 * sides if kind == "star" else sides
            points = [
                complex(
                    math.cos(-math.pi / 2 + 2 * math.pi * i / count)
                    * width
                    / 2
                    * (inner_ratio if kind == "star" and i % 2 else 1),
                    math.sin(-math.pi / 2 + 2 * math.pi * i / count)
                    * height
                    / 2
                    * (inner_ratio if kind == "star" and i % 2 else 1),
                )
                for i in range(count)
            ]
        path = Path(*[Line(a, b) for a, b in zip(points, points[1:] + points[:1])])
        if radius:
            from xml.etree.ElementTree import Element

            path = round_corners(Element("path", {"d": path.d()}), radius)
    return path.rotated(rotation, origin=0j).translated(complex(cx, cy))


def fit_rotated_rectangle(el, tolerance=0.8):
    import cv2
    from .svgdoc import rings

    contours = rings(el, step=1.5)
    if len(contours) != 1 or len(contours[0]) < 8:
        return False
    pts = np.asarray(contours[0], np.float32)
    (cx, cy), (w, h), angle = cv2.minAreaRect(pts)
    if min(w, h) < 4:
        return False
    theta = math.radians(angle)
    local = (pts - [cx, cy]) @ np.array(
        [[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]]
    )
    area = abs(cv2.contourArea(pts))
    radius = math.sqrt(max(0, (w * h - area) / (4 - math.pi)))
    if not 1 < radius < min(w, h) / 2:
        return False
    q = np.abs(local) - np.array([w / 2 - radius, h / 2 - radius])
    residual = (
        np.linalg.norm(np.maximum(q, 0), axis=1)
        + np.minimum(np.maximum(q[:, 0], q[:, 1]), 0)
        - radius
    )
    if np.percentile(np.abs(residual), 95) > tolerance:
        return False
    path = shape_path("rectangle", cx, cy, w, h, angle, radius)
    el.set("d", path.d())
    el.attrib.pop("transform", None)
    return True
