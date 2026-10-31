"""Whole regular-star fitting and recognition, with explicit residual checks."""

import math
import numpy as np
from .svgdoc import rings
from .modeling import shape_path


def fit_star(el, tolerance=0.8):
    import cv2
    from scipy.optimize import least_squares

    contours = rings(el, step=1.5)
    if len(contours) != 1 or len(contours[0]) < 10:
        return False
    points = np.asarray(contours[0], np.float32)
    corners = cv2.approxPolyDP(points, max(0.5, tolerance), True).reshape(-1, 2)
    if len(corners) < 6 or len(corners) > 32 or len(corners) % 2:
        return False
    center = corners.mean(axis=0)
    order = np.argsort(np.arctan2(corners[:, 1] - center[1], corners[:, 0] - center[0]))
    corners = corners[order]
    radial = np.linalg.norm(corners - center, axis=1)
    if radial[::2].mean() < radial[1::2].mean():
        corners = np.roll(corners, -1, axis=0)
        radial = np.roll(radial, -1)
    inner = radial[1::2].mean() / max(radial[::2].mean(), 1e-8)
    if not 0.08 < inner < 0.85:
        return False
    count = len(corners)
    n = count // 2
    initial = [
        *center,
        float(radial[::2].mean()),
        float(radial[::2].mean()),
        inner,
        math.atan2(corners[0, 1] - center[1], corners[0, 0] - center[0]),
    ]

    def vertices(params):
        cx, cy, rx, ry, ratio, angle = params
        theta = angle + np.arange(count) * math.pi / n
        radius = np.where(np.arange(count) % 2, ratio, 1)
        return np.column_stack(
            [cx + rx * radius * np.cos(theta), cy + ry * radius * np.sin(theta)]
        )

    result = least_squares(
        lambda params: (vertices(params) - corners).ravel(),
        initial,
        bounds=([-1e5, -1e5, 1, 1, 0.05, -20], [1e5, 1e5, 1e5, 1e5, 0.95, 20]),
        max_nfev=100,
    )
    if np.max(np.linalg.norm(vertices(result.x) - corners, axis=1)) > tolerance * 1.5:
        return False
    cx, cy, rx, ry, ratio, angle = result.x
    # The SVG model has its first outer vertex along -Y before rotation.
    rotation = math.degrees(angle) + 90
    if abs(rx - ry) / max(rx, ry) > 0.03:
        # Anisotropic stars need their axes rotated before scaling; don't mislabel.
        return False
    path = shape_path(
        "star", cx, cy, 2 * (rx + ry) / 2, 2 * (rx + ry) / 2, rotation, 0, n, ratio
    )
    el.set("d", path.d())
    el.attrib.pop("transform", None)
    return True
