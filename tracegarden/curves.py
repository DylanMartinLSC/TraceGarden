"""Compatibility conversion with bounded quadratic and polyline approximations."""

from svgpathtools import QuadraticBezier, Line, Path
from .svgdoc import NS, absolute_path


def quadratic(segment, tolerance=0.15, depth=0):
    if isinstance(segment, (Line, QuadraticBezier)):
        return [segment]
    c = (3 * segment.control1 - segment.start + 3 * segment.control2 - segment.end) / 4
    result = QuadraticBezier(segment.start, c, segment.end)
    if (
        max(
            abs(result.point(t) - segment.point(t))
            for t in [0.125, 0.25, 0.5, 0.75, 0.875]
        )
        < tolerance
        or depth >= 12
    ):
        return [result]
    a, b = segment.split(0.5)
    return quadratic(a, tolerance, depth + 1) + quadratic(b, tolerance, depth + 1)


def convert_curves(root, mode):
    from .exporters import cubics

    for el in root.findall(NS + "path"):
        pieces = []
        for sub in absolute_path(el).continuous_subpaths():
            output = []
            for seg in sub:
                for s in cubics(seg):
                    if mode == "quadratic":
                        output.extend(quadratic(s))
                    elif mode == "polyline":
                        n = max(1, min(4096, int(s.length() / 0.5) + 1))
                        output.extend(
                            Line(s.point(i / n), s.point((i + 1) / n)) for i in range(n)
                        )
                    else:
                        output.append(s)
            pieces.append(Path(*output).d() + (" Z" if sub.isclosed() else ""))
        el.set("d", " ".join(pieces))
        el.attrib.pop("transform", None)
