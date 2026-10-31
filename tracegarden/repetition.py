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
