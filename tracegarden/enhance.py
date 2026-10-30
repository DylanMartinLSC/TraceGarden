"""CPU geometry reconstruction, gradients, and centerline extraction."""

from __future__ import annotations
import math
import xml.etree.ElementTree as ET
import numpy as np
from .svgdoc import NS, absolute_path, rings


def primitives(root, tolerance=0.8):
    import cv2

    count = 0
    for el in root.findall(NS + "path"):
        contours = rings(el, step=2)
        if len(contours) != 1 or len(contours[0]) < 8:
            continue
        pts = np.array(contours[0], np.float32)
        if np.linalg.norm(pts[0] - pts[-1]) > 0.1:
            continue
        area = abs(cv2.contourArea(pts))
        if area < 64:
            continue
        (cx, cy), (w, h), angle = cv2.fitEllipse(pts)
        if min(w, h) > 2:
            theta = math.radians(angle)
            centered = pts - [cx, cy]
            local = centered @ np.array(
                [
                    [math.cos(theta), -math.sin(theta)],
                    [math.sin(theta), math.cos(theta)],
                ]
            )
            residual = (
                np.abs(
                    np.sqrt((local[:, 0] / (w / 2)) ** 2 + (local[:, 1] / (h / 2)) ** 2)
                    - 1
                )
                * min(w, h)
                / 2
            )
            if (
                np.percentile(residual, 95) < tolerance
                and abs(math.pi * w * h / 4 - area) / area < 0.025
            ):
                # Exact circular or elliptical arc segments, not polygon facsimiles.
                if abs(w - h) < 2 * tolerance:
                    w = h = (w + h) / 2
                dx, dy = math.cos(theta) * w / 2, math.sin(theta) * w / 2
                el.set(
                    "d",
                    f"M{cx + dx:.4f} {cy + dy:.4f} A{w / 2:.4f} {h / 2:.4f} {angle:.4f} 1 0 {cx - dx:.4f} {cy - dy:.4f} A{w / 2:.4f} {h / 2:.4f} {angle:.4f} 1 0 {cx + dx:.4f} {cy + dy:.4f} Z",
                )
                el.attrib.pop("transform", None)
                count += 1
                continue
        rect = cv2.minAreaRect(pts)
        box = cv2.boxPoints(rect)
        rectarea = rect[1][0] * rect[1][1]
        # Area agreement and boundary agreement prevent fitting arbitrary shapes.
        distances = [
            abs(cv2.pointPolygonTest(box, tuple(map(float, p)), True)) for p in pts
        ]
        if (
            rectarea > 0
            and abs(rectarea - area) / area < 0.015
            and np.percentile(distances, 95) < tolerance
        ):
            el.set("d", "M" + " L".join(f"{x:.3f} {y:.3f}" for x, y in box) + " Z")
            el.attrib.pop("transform", None)
            count += 1
            continue
        # Axis-aligned rounded rectangles: recover a common circular corner radius.
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        bw, bh = float(x1 - x0), float(y1 - y0)
        radius = math.sqrt(max(0, (bw * bh - area) / (4 - math.pi)))
        if 1 < radius < min(bw, bh) / 2:
            center = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
            q = np.abs(pts - center) - np.array([bw / 2 - radius, bh / 2 - radius])
            sdf = (
                np.linalg.norm(np.maximum(q, 0), axis=1)
                + np.minimum(np.maximum(q[:, 0], q[:, 1]), 0)
                - radius
            )
            if np.percentile(np.abs(sdf), 95) < tolerance:
                r = radius
                el.set(
                    "d",
                    f"M{x0 + r:.3f} {y0:.3f} H{x1 - r:.3f} A{r:.3f} {r:.3f} 0 0 1 {x1:.3f} {y0 + r:.3f} V{y1 - r:.3f} A{r:.3f} {r:.3f} 0 0 1 {x1 - r:.3f} {y1:.3f} H{x0 + r:.3f} A{r:.3f} {r:.3f} 0 0 1 {x0:.3f} {y1 - r:.3f} V{y0 + r:.3f} A{r:.3f} {r:.3f} 0 0 1 {x0 + r:.3f} {y0:.3f} Z",
                )
                el.attrib.pop("transform", None)
                count += 1
                continue
        corners = cv2.approxPolyDP(pts, tolerance * 0.8, True).reshape(-1, 2)
        if 3 <= len(corners) <= 24:
            residual = [
                abs(cv2.pointPolygonTest(corners, tuple(map(float, p)), True))
                for p in pts
            ]
            if (
                np.percentile(residual, 95) < tolerance
                and abs(abs(cv2.contourArea(corners)) - area) / area < 0.02
            ):
                el.set(
                    "d", "M" + " L".join(f"{x:.3f} {y:.3f}" for x, y in corners) + " Z"
                )
                el.attrib.pop("transform", None)
                count += 1
    return count


def gradients(root, image):
    """Fit a linear RGB plane per visible region; accept only a substantial improvement."""
    import cv2

    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    paths = root.findall(NS + "path")
    if len(paths) > 1500:
        return 0
    # Visible ownership avoids fitting foreground colors into a stacked background.
    scale = min(1, 256 / max(w, h))
    sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
    small = cv2.resize(rgb, (sw, sh), interpolation=cv2.INTER_AREA).astype(float)
    owner = np.full((sh, sw), -1, np.int32)
    for i, el in enumerate(paths):
        mask = np.zeros((sh, sw), np.uint8)
        contours = [
            np.rint(np.array(r) * scale).astype(np.int32)
            for r in rings(el, step=3)
            if len(r) >= 3
        ]
        if contours:
            cv2.fillPoly(mask, contours, 1)
        owner[mask > 0] = i
    defs = ET.Element(NS + "defs")
    count = 0
    for i, el in enumerate(paths):
        yy, xx = np.where(owner == i)
        if len(xx) < 50:
            continue
        sample = small[yy, xx]
        design = np.column_stack(
            [xx / max(1, sw - 1), yy / max(1, sh - 1), np.ones(len(xx))]
        )
        coef = np.linalg.lstsq(design, sample, rcond=None)[0]
        before = ((sample - sample.mean(axis=0)) ** 2).mean()
        after = ((sample - design @ coef) ** 2).mean()
        if before < 100 or after > before * 0.25 or after > 180:
            continue
        # Find the main color-change direction and constrain colors to one axis.
        u, s, v = np.linalg.svd(coef[:2], full_matrices=False)
        direction = u[:, 0]
        projection = design[:, :2] @ direction
        lo, hi = projection.min(), projection.max()
        if hi - lo < 0.02:
            continue
        t = (projection - lo) / (hi - lo)
        colors = np.linalg.lstsq(np.column_stack([1 - t, t]), sample, rcond=None)[0]
        fit = (1 - t[:, None]) * colors[0] + t[:, None] * colors[1]
        if ((sample - fit) ** 2).mean() > before * 0.25:
            continue
        center = design[:, :2].mean(axis=0)
        start = center + direction * (lo - center @ direction)
        end = center + direction * (hi - center @ direction)
        ident = f"g{count}"
        grad = ET.SubElement(
            defs,
            NS + "linearGradient",
            {
                "id": ident,
                "gradientUnits": "userSpaceOnUse",
                "x1": str(round(start[0] * w, 3)),
                "y1": str(round(start[1] * h, 3)),
                "x2": str(round(end[0] * w, 3)),
                "y2": str(round(end[1] * h, 3)),
            },
        )
        for offset, color in zip(["0", "1"], colors):
            value = "#" + "".join(
                f"{int(c):02x}" for c in np.clip(color, 0, 255).round()
            )
            ET.SubElement(grad, NS + "stop", {"offset": offset, "stop-color": value})
        # Gradient coordinates are in document space; bake path translations.
        el.set("d", absolute_path(el).d())
        el.attrib.pop("transform", None)
        el.set("fill", f"url(#{ident})")
        count += 1
    if count:
        root.insert(0, defs)
    return count


def centerlines(image, threshold, speckle):
    from skimage.morphology import skeletonize
    import cv2

    mask = np.asarray(image.convert("L")) < threshold
    if speckle:
        _, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask.astype(np.uint8), connectivity=8
        )
        keep = stats[:, cv2.CC_STAT_AREA] >= max(2, speckle * speckle)
        keep[0] = False
        mask = keep[labels]
    skeleton = skeletonize(mask)
    coords = {tuple(p) for p in np.argwhere(skeleton)}

    def neighbors(p):
        y, x = p
        return [
            (y + dy, x + dx)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if (dy or dx) and (y + dy, x + dx) in coords
        ]

    visited = set()
    polylines = []
    # First traverse junctions/endpoints, then any closed cycles.
    ordered = sorted(coords, key=lambda p: (len(neighbors(p)) == 2, p))
    for start in ordered:
        if not neighbors(start):
            polylines.append([start, (start[0], start[1] + 0.01)])
        for nxt in neighbors(start):
            edge = tuple(sorted([start, nxt]))
            if edge in visited:
                continue
            points = [start]
            prev = start
            cur = nxt
            visited.add(edge)
            while True:
                points.append(cur)
                choices = [
                    p
                    for p in neighbors(cur)
                    if p != prev and tuple(sorted([cur, p])) not in visited
                ]
                if len(neighbors(cur)) != 2 or not choices:
                    break
                p = choices[0]
                visited.add(tuple(sorted([cur, p])))
                prev, cur = cur, p
                if cur == start:
                    points.append(cur)
                    break
            if len(points) > 1:
                polylines.append(points)
    root = ET.Element(
        NS + "svg",
        {
            "width": str(image.width),
            "height": str(image.height),
            "viewBox": f"0 0 {image.width} {image.height}",
            "version": "1.1",
            "role": "img",
        },
    )
    from shapely.geometry import LineString

    for points in polylines:
        xy = list(
            LineString([(x + 0.5, y + 0.5) for y, x in points]).simplify(0.4).coords
        )
        ET.SubElement(
            root,
            NS + "path",
            {
                "d": "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in xy),
                "fill": "none",
                "stroke": "#000000",
                "stroke-width": "1",
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
            },
        )
    return root


def opacity_regions(root, alpha):
    """Keep uniform region translucency; anti-aliased edges do not set region alpha."""
    import cv2

    values = np.asarray(alpha)
    h, w = values.shape
    for el in root.findall(NS + "path"):
        contours = [
            np.rint(np.array(r)).astype(np.int32)
            for r in rings(el, step=2)
            if len(r) >= 3
        ]
        mask = np.zeros((h, w), np.uint8)
        if not contours:
            continue
        cv2.fillPoly(mask, contours, 1)
        mask = cv2.erode(mask, np.ones((3, 3), np.uint8))
        samples = values[(mask > 0) & (values > 0)]
        if samples.size:
            value = float(np.median(samples)) / 255
            if value < 0.999:
                el.set("opacity", f"{value:.4f}")
