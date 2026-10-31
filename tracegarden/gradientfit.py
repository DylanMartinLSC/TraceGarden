"""Recognize a whole linear-gradient region before retaining quantized bands."""

import numpy as np
from PIL import Image

from .engine import native_trace
from .svgdoc import NS


def whole_linear_region(reference, options):
    import cv2

    from .enhance import gradients, primitives

    rgba = np.asarray(reference.convert("RGBA"))
    rgb = rgba[:, :, :3].astype(float)
    alpha = rgba[:, :, 3]
    mask = alpha > 127
    opaque = bool(np.all(alpha == 255))
    if opaque:
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        background = np.median(border, axis=0)
        if np.mean(np.linalg.norm(border - background, axis=1) < 8) > 0.95:
            mask = np.linalg.norm(rgb - background, axis=2) > 10
    if mask.sum() < 100:
        return None
    interior = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    yy, xx = np.where(interior & (alpha > 240))
    if len(xx) < 100:
        return None
    stride = max(1, len(xx) // 12000)
    yy = yy[::stride]
    xx = xx[::stride]
    design = np.column_stack(
        [xx / reference.width, yy / reference.height, np.ones(len(xx))]
    )
    values = rgb[yy, xx]
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    errors = np.linalg.norm(design @ coefficients - values, axis=1)
    if (
        np.mean(values.var(axis=0)) < 120
        or np.mean(errors**2) > 12
        or np.percentile(errors, 95) > 8
    ):
        return None
    # A one-axis color change distinguishes a linear gradient from a two-axis
    # color field. Reject instead of silently dropping its second direction.
    singular = np.linalg.svd(coefficients[:2], compute_uv=False)
    if singular[1] > max(2, singular[0] * 0.025):
        return None
    solid = np.zeros_like(rgba)
    solid[:, :, :3] = [80, 100, 120]
    solid[:, :, 3] = mask.astype(np.uint8) * 255
    root = native_trace(Image.fromarray(solid), options, shared=True)
    if options.geometry:
        primitives(root)
    count = gradients(root, reference)
    if count != len(root.findall(NS + "path")):
        return None
    if opaque and not mask.all():
        # Preserve a real opaque paper/background behind the fitted region.
        from xml.etree.ElementTree import Element

        color = "#" + "".join(f"{round(c):02x}" for c in background)
        root.insert(
            1,
            Element(
                NS + "path",
                {"d": f"M0 0H{reference.width}V{reference.height}H0Z", "fill": color},
            ),
        )
    return root, count
