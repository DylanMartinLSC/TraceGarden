"""Fit each edge of a planar region graph once, then reuse it in both faces."""

from collections import defaultdict
import math
import numpy as np
from svgpathtools import CubicBezier, Line, Path
from .svgdoc import NS, absolute_path, NUMBER


def _unit(v):
    size = np.linalg.norm(v)
    return v / size if size > 1e-12 else np.array([1.0, 0.0])


def fit_curve(points, tolerance=0.7, depth=0):
    """Chord-parameterized least-squares cubics with recursive error bounds."""
    p = np.asarray(points, float)
    if len(p) < 2:
        return []
    chord = p[-1] - p[0]
    length = np.linalg.norm(chord)
    if (
        length > 1e-9
        and np.max(
            np.abs(((p[:, 0] - p[0, 0]) * chord[1] - (p[:, 1] - p[0, 1]) * chord[0]))
            / length
        )
        < 1e-6
    ):
        return [Line(complex(*p[0]), complex(*p[-1]))]
    if len(p) == 2:
        return [Line(complex(*p[0]), complex(*p[-1]))]
    distances = np.linalg.norm(np.diff(p, axis=0), axis=1)
    total = distances.sum()
    if total < 1e-9:
        return []
    t = np.r_[0, np.cumsum(distances)] / total
    tangent0 = _unit(p[min(3, len(p) - 1)] - p[0])
    tangent1 = _unit(p[max(0, len(p) - 4)] - p[-1])
    b0 = (1 - t) ** 3
    b1 = 3 * t * (1 - t) ** 2
    b2 = 3 * t * t * (1 - t)
    b3 = t**3
    residual = p - (b0 + b1)[:, None] * p[0] - (b2 + b3)[:, None] * p[-1]
    matrix = np.stack([b1[:, None] * tangent0, b2[:, None] * tangent1], axis=2).reshape(
        -1, 2
    )
    alpha = np.linalg.lstsq(matrix, residual.reshape(-1), rcond=None)[0]
    alpha = np.clip(alpha, 0, total * 0.8)
    c1 = p[0] + tangent0 * alpha[0]
    c2 = p[-1] + tangent1 * alpha[1]
    fitted = (
        b0[:, None] * p[0] + b1[:, None] * c1 + b2[:, None] * c2 + b3[:, None] * p[-1]
    )
    error = np.linalg.norm(fitted - p, axis=1)
    split = int(np.argmax(error))
    if error[split] <= tolerance or depth >= 20:
        return [
            CubicBezier(complex(*p[0]), complex(*c1), complex(*c2), complex(*p[-1]))
        ]
    split = max(1, min(len(p) - 2, split))
    return fit_curve(p[: split + 1], tolerance, depth + 1) + fit_curve(
        p[split:], tolerance, depth + 1
    )


def _corner_vertices(vertices, closed):
    p = np.asarray(vertices, float)
    n = len(p)
    if n < 4:
        return set(range(n))
    result = set()
    for i in range(n):
        if not closed and (i == 0 or i == n - 1):
            result.add(i)
            continue

        def away(direction):
            j = i
            distance = 0
            for _ in range(n - 1):
                k = (j + direction) % n
                if not closed and not 0 <= j + direction < n:
                    break
                distance += np.linalg.norm(p[k] - p[j])
                j = k
                if distance >= 4:
                    break
            return p[j]

        a = p[i] - away(-1)
        b = away(1) - p[i]
        angle = math.acos(float(np.clip(_unit(a) @ _unit(b), -1, 1)))
        if angle > math.pi / 4:
            result.add(i)
    return result


def smooth_shared(root, tolerance=0.7, image=None):
    rgba_source = None
    if image is not None:
        rgba_source = np.asarray(image.convert("RGBA"), dtype=np.float32)
        rgba_source[:, :, :3] *= rgba_source[:, :, 3:] / 255
    paths = root.findall(NS + "path")
    faces = []
    adjacency = defaultdict(set)
    owners = defaultdict(set)
    for face_index, el in enumerate(paths):
        contours = []
        for sub in absolute_path(el).continuous_subpaths():
            vertices = [(round(s.start.real, 3), round(s.start.imag, 3)) for s in sub]
            if len(vertices) < 3:
                continue
            contours.append(vertices)
            for a, b in zip(vertices, vertices[1:] + vertices[:1]):
                if a != b:
                    adjacency[a].add(b)
                    adjacency[b].add(a)
                    owners[tuple(sorted([a, b]))].add(face_index)
        faces.append(contours)
    anchors = {v for v, neighbors in adjacency.items() if len(neighbors) != 2}
    for contours in faces:
        for vertices in contours:
            anchors.update(vertices[i] for i in _corner_vertices(vertices, True))
    # Closed components need deterministic anchors even if there are no junctions/corners.
    seen = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        pending = [start]
        component = []
        while pending:
            vertex = pending.pop()
            if vertex in seen:
                continue
            seen.add(vertex)
            component.append(vertex)
            pending.extend(adjacency[vertex] - seen)
        if not any(v in anchors for v in component):
            ordered = [min(component)]
            previous = None
            cur = ordered[0]
            while True:
                nxt = next((v for v in sorted(adjacency[cur]) if v != previous), None)
                if nxt is None or nxt == ordered[0]:
                    break
                ordered.append(nxt)
                previous, cur = cur, nxt
            anchors.update(ordered[i * len(ordered) // 4] for i in range(4))
    chains = []
    edge_map = {}
    visited = set()

    def edge(a, b):
        return tuple(sorted([a, b]))

    for start in sorted(anchors):
        for neighbor in sorted(adjacency[start]):
            if edge(start, neighbor) in visited:
                continue
            points = [start, neighbor]
            visited.add(edge(start, neighbor))
            previous = start
            cur = neighbor
            while cur not in anchors:
                nxt = next((v for v in sorted(adjacency[cur]) if v != previous), None)
                if nxt is None:
                    break
                visited.add(edge(cur, nxt))
                points.append(nxt)
                previous, cur = cur, nxt
            local_tolerance = tolerance
            fitting_points = np.asarray(points, float)
            incident = owners[edge(points[0], points[1])]
            if 1 <= len(incident) <= 2:
                colors = []
                for index in sorted(incident):
                    color = paths[index].get("fill", "#000000")
                    colors.append(
                        np.array(
                            [int(color[i : i + 2], 16) for i in (1, 3, 5)]
                            + [255 * float(paths[index].get("opacity", "1"))]
                        )
                    )
                if len(colors) == 1:
                    if image is None or image.getchannel("A").getextrema() == (
                        255,
                        255,
                    ):
                        colors.append(colors[0].copy())
                    else:
                        colors.append(np.array([0.0, 0.0, 0.0, 0.0]))
                colors = [
                    c * np.array([c[3] / 255, c[3] / 255, c[3] / 255, 1])
                    for c in colors
                ]
                difference = colors[1] - colors[0]
                contrast = np.linalg.norm(difference[:3])
                local_tolerance = tolerance * (0.5 + 1.5 * math.exp(-contrast / 24))
                if image is not None and float(difference @ difference) > 100:
                    import cv2

                    rgba = rgba_source
                    for point_index in range(1, len(points) - 1):
                        tangent = (
                            fitting_points[point_index + 1]
                            - fitting_points[point_index - 1]
                        )
                        normal = _unit(np.array([-tangent[1], tangent[0]]))
                        distances = np.linspace(-1.5, 1.5, 13)
                        samples = (
                            fitting_points[point_index] + distances[:, None] * normal
                        )
                        sampled = cv2.remap(
                            rgba,
                            (samples[:, 0] - 0.5).astype(np.float32).reshape(1, -1),
                            (samples[:, 1] - 0.5).astype(np.float32).reshape(1, -1),
                            cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE,
                        ).reshape(-1, 4)
                        coverage = (sampled - colors[0]) @ difference / (
                            difference @ difference
                        ) - 0.5
                        crossings = np.where(coverage[:-1] * coverage[1:] < 0)[0]
                        if len(crossings):
                            k = min(crossings, key=lambda k: abs(distances[k]))
                            shift = distances[k] - coverage[k] * (
                                distances[k + 1] - distances[k]
                            ) / (coverage[k + 1] - coverage[k])
                            fitting_points[point_index] += normal * np.clip(
                                shift, -0.6, 0.6
                            )
            ident = len(chains)
            segments = fit_curve(fitting_points, local_tolerance)
            chains.append((points, segments))
            for a, b in zip(points, points[1:]):
                edge_map[(a, b)] = (ident, True)
                edge_map[(b, a)] = (ident, False)
    old = [el.get("d") for el in paths]
    curve_count = 0
    whole_models = {}
    for el, contours in zip(paths, faces):
        pieces = []
        for vertices in contours:
            start = next((i for i, v in enumerate(vertices) if v in anchors), None)
            if start is None:
                raise ValueError("Could not anchor a shared boundary.")
            vertices = vertices[start:] + vertices[:start]
            vertices.append(vertices[0])
            output = []
            i = 0
            while i < len(vertices) - 1:
                entry = edge_map.get((vertices[i], vertices[i + 1]))
                if entry is None:
                    raise ValueError("Incomplete shared boundary graph.")
                ident, forward = entry
                points, segments = chains[ident]
                if not forward:
                    segments = [s.reversed() for s in reversed(segments)]
                output.extend(segments)
                i += len(points) - 1
            key = frozenset(edge(a, b) for a, b in zip(vertices, vertices[1:]))
            area = sum(
                a[0] * b[1] - b[0] * a[1] for a, b in zip(vertices, vertices[1:])
            )
            if all(len(adjacency[v]) == 2 for v in vertices[:-1]):
                if key not in whole_models:
                    import xml.etree.ElementTree as ET
                    from .enhance import primitives

                    temporary = ET.Element(NS + "svg")
                    node = ET.SubElement(
                        temporary, NS + "path", {"d": Path(*output).d() + " Z"}
                    )
                    fitted = primitives(temporary, tolerance=0.85)
                    whole_models[key] = (absolute_path(node) if fitted else None, area)
                model, model_area = whole_models[key]
                if model is not None:
                    output = list(model if area * model_area > 0 else model.reversed())
            curve_count += sum(isinstance(s, CubicBezier) for s in output)
            pieces.append(Path(*output).d() + " Z")

        def number(match):
            value = round(float(match.group()), 4)
            return "0" if value == 0 else f"{value:.4f}".rstrip("0").rstrip(".")

        el.set("d", NUMBER.sub(number, " ".join(pieces)))
        el.attrib.pop("transform", None)
    # Reject a fit that changes face validity or creates significant overlap.
    from .svgdoc import polygon
    from shapely.ops import unary_union

    shapes = [polygon(el) for el in paths]
    union = unary_union(shapes)
    overlap = sum(p.area for p in shapes) - union.area
    if any(not p.is_valid for p in shapes) or overlap > 1e-3:
        for el, d in zip(paths, old):
            el.set("d", d)
        return 0
    return curve_count
