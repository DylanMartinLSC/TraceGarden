"""Deterministic CPU image analysis and editable automatic preprocessing."""

import numpy as np
from PIL import Image, ImageColor
from .tuning import current


def alpha_coverage(image):
    """Separate narrow pixel-coverage antialiasing from genuine region opacity."""
    import cv2

    alpha = np.asarray(image.getchannel("A"))
    partial = (alpha > 0) & (alpha < 255)
    if not partial.any() or not (alpha == 255).any():
        return image, False
    distance = cv2.distanceTransform((alpha > 0).astype(np.uint8), cv2.DIST_L2, 3)
    if (
        partial.sum() > alpha.size * 0.2
        or float(distance[partial].max()) > current().alpha_width
    ):
        return image, False
    from scipy.ndimage import distance_transform_edt

    rgba = np.array(image.convert("RGBA"))
    indices = distance_transform_edt(
        alpha < 255, return_distances=False, return_indices=True
    )
    rgba[partial, :3] = rgba[indices[0][partial], indices[1][partial], :3]
    rgba[:, :, 3] = np.where(alpha >= 128, 255, 0).astype(np.uint8)
    normalized = Image.fromarray(rgba)
    return normalized, True


def analyze(image):
    import cv2

    sample = image.copy()
    sample.thumbnail((320, 320))
    rgb = sample.convert("RGB")
    values = np.asarray(rgb, dtype=np.uint8)
    # A low-strength bilateral pass rejects compression noise while retaining edges.
    clean = cv2.bilateralFilter(values, 5, current().bilateral_sigma, 2)
    # Estimate palette from flat interiors, not the much larger population of
    # blended edge pixels. Small real accents must survive automatic selection.
    spread = cv2.dilate(clean, np.ones((3, 3), np.uint8)).astype(int) - cv2.erode(
        clean, np.ones((3, 3), np.uint8)
    ).astype(int)
    interior = clean[spread.max(axis=2) < 24]
    if len(interior) > clean.size // 30:
        bins = interior.astype(np.int32) // 16
        packed = bins[:, 0] * 256 + bins[:, 1] * 16 + bins[:, 2]
        histogram = np.bincount(packed, minlength=4096)
        sums = np.array(
            [
                np.bincount(packed, weights=interior[:, c], minlength=4096)
                for c in range(3)
            ]
        ).T
        seeds = []
        seed_labs = []
        for index in np.argsort(histogram)[::-1]:
            if histogram[index] < max(2, len(interior) * 0.0001) or len(seeds) >= 64:
                break
            color = np.uint8(sums[index] / histogram[index])
            lab = cv2.cvtColor(color.reshape(1, 1, 3), cv2.COLOR_RGB2LAB)[0, 0].astype(
                float
            )
            if (
                not seed_labs
                or min(np.linalg.norm(lab - other) for other in seed_labs)
                > current().palette_distance
            ):
                seeds.append(color)
                seed_labs.append(lab)
        core_palette = Image.new("P", (1, 1))
        colors = np.asarray(seeds, dtype=np.uint8).ravel().tolist()
        core_palette.putpalette(colors + colors[-3:] * ((768 - len(colors)) // 3))
        quant = Image.fromarray(clean).quantize(
            palette=core_palette, dither=Image.Dither.NONE
        )
    else:
        quant = Image.fromarray(clean).quantize(colors=64)
    counts = np.bincount(np.asarray(quant).ravel(), minlength=256)
    palette = np.array(quant.getpalette(), dtype=np.uint8).reshape(-1, 3)
    indices = np.flatnonzero(counts)
    clusters = [
        {"rgb": palette[i].astype(float), "weight": float(counts[i]), "members": [i]}
        for i in indices
    ]
    top_mass = sum(sorted(counts, reverse=True)[:10]) / counts.sum()
    while len(clusters) > 2:
        rgb_array = np.array([c["rgb"] for c in clusters], np.uint8)
        lab = (
            cv2.cvtColor(rgb_array.reshape(1, -1, 3), cv2.COLOR_RGB2LAB)
            .reshape(-1, 3)
            .astype(float)
        )
        distances = ((lab[:, None] - lab[None, :]) ** 2).sum(axis=2)
        np.fill_diagonal(distances, np.inf)
        i, j = np.unravel_index(distances.argmin(), distances.shape)
        if distances[i, j] > current().palette_distance**2:
            break
        if i > j:
            i, j = j, i
        a, b = clusters[i], clusters[j]
        weight = a["weight"] + b["weight"]
        clusters[i] = {
            "rgb": (a["rgb"] * a["weight"] + b["rgb"] * b["weight"]) / weight,
            "weight": weight,
            "members": a["members"] + b["members"],
        }
        clusters.pop(j)
    # Remove low-mass colors explainable as a blend between two large flat colors.
    major = [c for c in clusters if c["weight"] > counts.sum() * 0.015]
    selected = []
    for c in clusters:
        mixed = False
        coherent = (
            cv2.distanceTransform(
                np.isin(np.asarray(quant), c["members"]).astype(np.uint8),
                cv2.DIST_L2,
                3,
            ).max()
            > 1.8
        )
        if c["weight"] < counts.sum() * 0.04 and not coherent:
            for ai, aa in enumerate(major):
                for bb in major[ai + 1 :]:
                    if aa is c or bb is c:
                        continue
                    d = bb["rgb"] - aa["rgb"]
                    den = float(d @ d)
                    if den < 900:
                        continue
                    t = float((c["rgb"] - aa["rgb"]) @ d / den)
                    if (
                        0.04 < t < 0.96
                        and np.linalg.norm(aa["rgb"] + t * d - c["rgb"]) < 8
                    ):
                        mixed = True
                        break
                if mixed:
                    break
        if not mixed and (
            c["weight"] > counts.sum() * 0.001
            or coherent
            and c["weight"] > counts.sum() * 0.0001
        ):
            selected.append(c)
    if len(selected) < 2:
        selected = sorted(clusters, key=lambda c: -c["weight"])[:2]
    colors = []
    for c in selected:
        color = np.clip(c["rgb"].round(), 0, 255).astype(int)
        if color.min() > 245:
            color[:] = 255
        if color.max() < 8:
            color[:] = 0
        colors.append("#" + "".join(f"{v:02x}" for v in color))
    merged_mass = (
        sum(sorted([c["weight"] for c in clusters], reverse=True)[:10]) / counts.sum()
    )
    if (
        len(clusters) > 24
        and merged_mass < 0.9
        and len(interior) / len(clean.reshape(-1, 3)) < 0.35
    ):
        return {
            "preset": "photo",
            "colors": 64,
            "palette": [],
            "palette_error": 0,
            "flat_color_mass": round(float(merged_mass), 4),
        }
    colors = list(dict.fromkeys(colors))
    return {
        "preset": "logo" if len(colors) <= 16 else "illustration",
        "colors": max(2, len(colors)),
        "palette": colors,
        "palette_error": 0,
        "flat_color_mass": round(float(top_mass), 4),
    }


def color_coverage(image, reference):
    """Collapse narrow blended edge colors, keeping their positions in reference."""
    import cv2

    rgb = np.asarray(image).copy()
    raw = np.asarray(reference.convert("RGB"), dtype=float)
    colors, labels, counts = np.unique(
        rgb.reshape(-1, 3), axis=0, return_inverse=True, return_counts=True
    )
    if not 2 < len(colors) <= 64:
        return image, 0
    labels = labels.reshape(rgb.shape[:2])
    total = labels.size
    bases = sorted(
        [i for i, n in enumerate(counts) if n > total * 0.04], key=lambda i: -counts[i]
    )[:12]
    nearby = {
        i: cv2.dilate((labels == i).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        for i in bases
    }
    changed = 0
    for index, count in enumerate(counts):
        if count > total * 0.04:
            continue
        mask = labels == index
        if not mask.any():
            continue
        distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
        if distance[mask].max() > 2.2:
            continue
        for ai, a in enumerate(bases):
            for b in bases[ai + 1 :]:
                delta = colors[b].astype(float) - colors[a]
                denominator = float(delta @ delta)
                if denominator < 900:
                    continue
                mix = float(
                    (colors[index].astype(float) - colors[a]) @ delta / denominator
                )
                residual = np.linalg.norm(colors[a] + delta * mix - colors[index])
                if not 0.03 < mix < 0.97 or residual > 5:
                    continue
                eligible = mask & nearby[a] & nearby[b]
                if eligible.sum() < count * 0.8:
                    continue
                t = (raw[eligible] - colors[a]) @ delta / denominator
                rgb[eligible] = np.where((t >= 0.5)[:, None], colors[b], colors[a])
                changed += int(eligible.sum())
                mask[eligible] = False
                if not mask.any():
                    break
            if not mask.any():
                break
    return Image.fromarray(rgb), changed


def remove_background(image, mode="auto", color="#ffffff", tolerance=18):
    import cv2

    rgba = np.array(image.convert("RGBA"))
    rgb = rgba[:, :, :3]
    if mode == "auto":
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        quant = (
            Image.fromarray(border.reshape(1, -1, 3)).quantize(colors=4).convert("RGB")
        )
        values, counts = np.unique(
            np.asarray(quant).reshape(-1, 3), axis=0, return_counts=True
        )
        background = values[int(counts.argmax())]
    else:
        background = np.array(ImageColor.getrgb(color), dtype=np.uint8)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(float)
    ref = cv2.cvtColor(np.uint8([[background]]), cv2.COLOR_RGB2LAB)[0, 0].astype(float)
    candidate = np.linalg.norm(lab - ref, axis=2) <= tolerance
    _, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=4)
    edge = np.unique(np.r_[labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    edge = edge[edge != 0]
    mask = np.isin(labels, edge)
    rgba[mask, 3] = 0
    return Image.fromarray(rgba), {
        "color": "#" + "".join(f"{v:02x}" for v in background),
        "pixels": int(mask.sum()),
    }


def symmetry(image, mode="auto", order=2):
    rgba = np.array(image.convert("RGBA"), dtype=float)
    sample = image.copy()
    sample.thumbnail((128, 128))
    small = np.asarray(sample.convert("RGBA"), dtype=float)
    detected = []
    if mode in {"auto", "horizontal", "both"}:
        error = np.abs(small - small[:, ::-1]).mean() / 255
        if mode != "auto" or error < 0.012:
            rgba = (rgba + rgba[:, ::-1]) / 2
            detected.append("horizontal")
    if mode in {"auto", "vertical", "both"}:
        error = np.abs(small - small[::-1]).mean() / 255
        if mode != "auto" or error < 0.012:
            rgba = (rgba + rgba[::-1]) / 2
            detected.append("vertical")
    if mode == "auto" and np.std(small[:, :, :3]) > 1:
        for candidate in [8, 6, 5, 4, 3, 2]:
            rotated = np.asarray(
                sample.convert("RGBA").rotate(
                    360 / candidate,
                    resample=Image.Resampling.BICUBIC,
                    fillcolor=tuple(np.asarray(sample.convert("RGBA"))[0, 0]),
                ),
                dtype=float,
            )
            if np.abs(small - rotated).mean() / 255 < 0.012:
                mode = "rotational"
                order = candidate
                break
    if mode == "rotational":
        values = [rgba]
        for i in range(1, order):
            values.append(
                np.asarray(
                    image.rotate(
                        360 * i / order,
                        resample=Image.Resampling.BICUBIC,
                        fillcolor=tuple(np.asarray(image.convert("RGBA"))[0, 0]),
                    ),
                    dtype=float,
                )
            )
        rgba = np.mean(values, axis=0)
        detected.append(f"rotation-{order}")
    return Image.fromarray(np.clip(rgba, 0, 255).round().astype(np.uint8)), detected
