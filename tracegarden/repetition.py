"""Recognize repeated contours under translation, rotation and uniform scale."""

import math
import numpy as np
from .svgdoc import absolute_path, polygon


def normalized(el):
    shape = polygon(el)
    if shape.is_empty or shape.area < 4:
        return None
    path = absolute_path(el)
    subs = path.continuous_subpaths()
    if len(subs) != 1 or not path.isclosed():
        return None
    center = complex(shape.centroid.x, shape.centroid.y)
    scale = math.sqrt(shape.area)
    points = (
        np.array(
            [
                [z.real, z.imag]
                for z in [
                    path.point(t) - center
                    for t in np.linspace(0, 1, 64, endpoint=False)
                ]
            ]
        )
        / scale
    )
    return points, center, scale


def align(reference, candidate):
    best = (float("inf"), None)
    for q in [candidate, candidate[::-1]]:
        for shift in range(len(q)):
            target = np.roll(q, shift, axis=0)
            u, _, vt = np.linalg.svd(reference.T @ target)
            rotation = u @ vt
            if np.linalg.det(rotation) < 0:
                continue
            error = float(
                np.sqrt(((reference @ rotation - target) ** 2).sum(axis=1).mean())
            )
            if error < best[0]:
                best = (error, rotation)
    return best


def repeated(paths, template_index, threshold=0.03):
    base = normalized(paths[template_index])
    if base is None:
        raise ValueError("Choose a single closed contour as the repeat template.")
    points, center, scale = base
    matches = []
    for index, el in enumerate(paths):
        value = normalized(el)
        if value is None:
            continue
        candidate, candidate_center, candidate_scale = value
        # Fast normalized bounds rejection avoids fitting clearly dissimilar shapes.
        if (
            abs(
                np.linalg.norm(points, axis=1).mean()
                - np.linalg.norm(candidate, axis=1).mean()
            )
            > 0.1
        ):
            continue
        error, rotation = align(points, candidate)
        if error <= threshold:
            angle = math.degrees(math.atan2(rotation[0, 1], rotation[0, 0]))
            matches.append(
                {
                    "index": index,
                    "error": error,
                    "rotation": angle,
                    "scale": candidate_scale / scale,
                    "center": [candidate_center.real, candidate_center.imag],
                }
            )
    return matches


def apply_repeats(paths, indices):
    base = normalized(paths[indices[0]])
    if base is None:
        raise ValueError("The repeat template must be a single closed contour.")
    points, center, scale = base
    template = absolute_path(paths[indices[0]]).translated(-center)
    for index in indices[1:]:
        candidate = normalized(paths[index])
        if candidate is None:
            continue
        other, target_center, target_scale = candidate
        error, rotation = align(points, other)
        if rotation is None or error > 0.15:
            raise ValueError(
                "Selected shapes are too different to normalize as repeats."
            )
        angle = math.degrees(math.atan2(rotation[0, 1], rotation[0, 0]))
        path = (
            template.scaled(target_scale / scale, origin=0j)
            .rotated(angle, origin=0j)
            .translated(target_center)
        )
        paths[index].set("d", path.d() + " Z")
        paths[index].attrib.pop("transform", None)


def normalize_repeats(root, threshold=0.012):
    """Find repeat families, preserving any matching neighboring hole contours.

    Descriptor screening bounds the expensive cyclic alignment search. Each
    accepted family uses one vector model with independent rigid transforms.
    """
    from scipy.spatial import cKDTree
    from .svgdoc import NS
    from .engine import _key

    paths = root.findall(NS + "path")
    if len(paths) > 1000:
        return 0
    candidates = []
    descriptors = []
    for index, el in enumerate(paths):
        path = absolute_path(el)
        if len(path) > 80 or len(path.continuous_subpaths()) != 1:
            continue
        item = normalized(el)
        if item is None:
            continue
        points, center, scale = item
        radii = np.linalg.norm(points, axis=1)
        descriptors.append(np.quantile(radii, [0, 0.15, 0.3, 0.5, 0.7, 0.85, 1]))
        candidates.append((index, item, path))
    if len(candidates) < 2:
        return 0
    tree = cKDTree(descriptors)
    used = set()
    replacements = {}
    count = 0
    for i, (index, (points, center, scale), path) in enumerate(candidates):
        if i in used:
            continue
        for j in tree.query_ball_point(descriptors[i], 0.045):
            if j <= i or j in used:
                continue
            other_index, (other, target, target_scale), other_path = candidates[j]
            error, rotation = align(points, other)
            if rotation is None or error > threshold:
                continue
            angle = math.degrees(math.atan2(rotation[0, 1], rotation[0, 0]))
            model = (
                path.translated(-center)
                .scaled(target_scale / scale, origin=0j)
                .rotated(angle, origin=0j)
                .translated(target)
            )
            # Bound actual displacement too: the same normalized tolerance must
            # not allow a large motif to move many visible source pixels.
            if error * target_scale > 0.6:
                continue
            replacements[_key(other_path)] = (other_path.area(), model)
            used.add(j)
            count += 1
    for el in paths:
        changed = False
        subs = []
        for sub in absolute_path(el).continuous_subpaths():
            match = replacements.get(_key(sub))
            if match:
                direction, model = match
                sub = model if direction * sub.area() >= 0 else model.reversed()
                changed = True
            subs.append(sub)
        if changed:
            el.set("d", " ".join(s.d() + (" Z" if s.isclosed() else "") for s in subs))
            el.attrib.pop("transform", None)
    return count
