"""Whole rounded and stretched star models fitted to observed contour geometry."""

import math

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from svgpathtools import Line

from .modeling import shape_path
from .svgdoc import absolute_path


def fit_rounded_star(el, tolerance=0.8):
    import cv2

    contours = absolute_path(el).continuous_subpaths()
    if len(contours) != 1 or not contours[0].isclosed():
        return False
    values = np.concatenate(
        [
            s.point(np.linspace(0, 1, max(3, min(2000, int(s.length() / 0.7) + 1))))
            for s in contours[0]
        ]
    )
    points = np.column_stack([values.real, values.imag]).astype(np.float32)
    hull_area = cv2.contourArea(cv2.convexHull(points))
    area = abs(cv2.contourArea(points))
    if not hull_area or not 0.25 < area / hull_area < 0.88:
        return False
    # Stable concave vertices survive rounding; their number supplies the model
    # order. Do not try arbitrary high-order shapes on ordinary curved artwork.
    approx = cv2.approxPolyDP(points, max(1.0, tolerance * 2), True).reshape(-1, 2)
    if not 6 <= len(approx) <= 48:
        return False
    before = approx - np.roll(approx, 1, axis=0)
    after = np.roll(approx, -1, axis=0) - approx
    turns = before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0]
    concave = min(int(sum(turns > 0.1)), int(sum(turns < -0.1)))
    if not 3 <= concave <= 12:
        return False
    center = points.mean(axis=0)
    delta = points - center
    radial = np.linalg.norm(delta, axis=1)
    eigenvalues, axes = np.linalg.eigh(np.cov(delta.T))
    normalized = (delta @ axes) / np.sqrt(np.maximum(eigenvalues, 1e-8))
    theta = 2 * math.pi / concave
    rotation_matrix = np.array(
        [[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]]
    )
    # A regular star has repeated radial lobes, even after stretching. This
    # inexpensive symmetry test avoids nonlinear fitting on arbitrary mascots.
    symmetry_error = cKDTree(normalized).query(normalized @ rotation_matrix)[0]
    if np.percentile(symmetry_error, 95) > 0.14:
        return False
    major = axes[:, -1]
    angle = math.degrees(math.atan2(major[1], major[0]))
    extent = float(radial.max())
    tree = cKDTree(points)
    observed = points[:: max(1, len(points) // 240)]

    def model(parameters):
        x, y, w, h, rotation, ratio, radius = parameters
        return shape_path("star", x, y, w, h, rotation, radius, concave, ratio)

    def sample(path):
        result = []
        for segment in path:
            count = max(3, int(segment.length() / 1.0) + 1)
            values = segment.point(np.linspace(0, 1, min(count, 180)))
            result.extend(np.column_stack([values.real, values.imag]))
        return np.asarray(result)

    def distances(path, query):
        z = query[:, 0] + 1j * query[:, 1]
        errors = []
        for s in path:
            if isinstance(s, Line):
                edge = s.end - s.start
                t = np.clip(
                    ((z - s.start) * edge.conjugate()).real / (abs(edge) ** 2), 0, 1
                )
                error = abs(z - s.start - t * edge)
            else:
                phase = np.angle((z - s.center) / (s.start - s.center))
                phase = (phase if s.delta >= 0 else -phase) % (2 * math.pi)
                error = np.where(
                    phase <= abs(math.radians(s.delta)) + 1e-8,
                    abs(abs(z - s.center) - abs(s.start - s.center)),
                    np.minimum(abs(z - s.start), abs(z - s.end)),
                )
            errors.append(error)
        return np.min(errors, axis=0)

    def fixed_residual(parameters):
        path = model(parameters)
        return distances(path, observed)

    try:
        candidates = []
        for rotation in [angle, angle + 180]:
            initial = [
                *center,
                extent * 2.08,
                extent * 1.9,
                rotation,
                0.48,
                max(0.3, extent * 0.035),
            ]
            bounds = (
                [
                    center[0] - extent * 0.3,
                    center[1] - extent * 0.3,
                    extent,
                    extent,
                    rotation - 45,
                    0.15,
                    0.01,
                ],
                [
                    center[0] + extent * 0.3,
                    center[1] + extent * 0.3,
                    extent * 3,
                    extent * 3,
                    rotation + 45,
                    0.8,
                    extent * 0.2,
                ],
            )
            candidates.append(
                least_squares(
                    fixed_residual, initial, bounds=bounds, diff_step=1e-4, max_nfev=70
                )
            )
        result = min(candidates, key=lambda r: np.mean(r.fun**2))
        path = model(result.x)
        samples = sample(path)
        errors = np.concatenate([distances(path, points), tree.query(samples)[0]])
    except (ValueError, AssertionError, ZeroDivisionError):
        return False
    if np.percentile(errors, 95) > tolerance or errors.max() > tolerance * 3:
        return False
    el.set("d", path.d() + " Z")
    el.attrib.pop("transform", None)
    return True
