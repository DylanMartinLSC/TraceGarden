"""Experimental CPU region merging, independently implemented from published math.

He, Kang & Morel, arXiv:2409.15940v1, equations 3.4, 3.10 and 3.11.
This is the discrete merging stage only, not their alternating affine flow.
Optional seed partition: Felzenszwalb & Huttenlocher, IJCV 2004, via scikit-image.
"""

import heapq

import numpy as np
from PIL import Image
from skimage.measure import label


def merge_regions(
    image,
    threshold,
    colors=128,
    mode="area",
    max_regions=50_000,
    seed_scale=0,
    seed_sigma=0.5,
):
    """Merge adjacent 4-connected regions in globally increasing cost order.

    Color distances use sum of squared RGB differences in byte units. The Area
    cost is min(area_a, area_b) * ||mean_a - mean_b||². The MS comparator divides
    the increase in squared reconstruction error by shared pixel-edge length.
    Statistics always use original pixels, not the seed palette centers.
    """
    if image.mode != "RGB" or mode not in {"area", "ms"}:
        raise ValueError("Region merging requires RGB and an area/ms criterion")
    if not np.isfinite(threshold) or threshold <= 0 or not 2 <= colors <= 256:
        raise ValueError("Choose a positive finite threshold and 2..256 seed colors")
    if (
        not np.isfinite(seed_scale)
        or seed_scale < 0
        or not np.isfinite(seed_sigma)
        or not 0 <= seed_sigma <= 2
    ):
        raise ValueError("Choose a finite nonnegative seed scale and sigma in 0..2")
    if seed_scale > 0:
        from skimage.segmentation import felzenszwalb

        # Efficient adaptive segmentation replaces fragment-prone color seeds.
        # min_size=1 adds no forced deletion of isolated accents. Split diagonal
        # contacts below so every seed obeys our four-connected region model.
        quantized = felzenszwalb(
            np.asarray(image),
            scale=seed_scale,
            sigma=seed_sigma,
            min_size=1,
            channel_axis=-1,
        )
    else:
        quantized = np.asarray(image.quantize(colors=colors, dither=Image.Dither.NONE))
    # background=-1 makes palette index zero an ordinary region.
    labels, count = label(quantized, background=-1, connectivity=1, return_num=True)
    stats = {
        "criterion": mode,
        "threshold": threshold,
        "seed_colors": colors,
        "seed_method": "felzenszwalb" if seed_scale > 0 else "quantized",
        "seed_scale": seed_scale,
        "seed_sigma": seed_sigma,
        "initial_regions": int(count),
        "applied": False,
    }
    if count > max_regions:
        return None, {**stats, "reason": "initial region budget exceeded"}
    labels = labels.astype(np.int32) - 1
    flat = labels.ravel()
    values = np.asarray(image).reshape(-1, 3)
    areas = np.bincount(flat, minlength=count).astype(np.int64)
    sums = np.stack(
        [np.bincount(flat, weights=values[:, c], minlength=count) for c in range(3)],
        axis=1,
    )
    means = sums / areas[:, None]
    parent = np.arange(count, dtype=np.int32)
    version = np.zeros(count, dtype=np.int64)
    neighbors = [{} for _ in range(count)]
    pairs = []
    for first, second in (
        (labels[:, :-1], labels[:, 1:]),
        (labels[:-1, :], labels[1:, :]),
    ):
        mask = first != second
        a, b = first[mask].astype(np.int64), second[mask].astype(np.int64)
        pairs.append(np.minimum(a, b) * count + np.maximum(a, b))
    keys, lengths = np.unique(np.concatenate(pairs), return_counts=True)
    for key, length in zip(keys.tolist(), lengths.tolist()):
        a, b = divmod(key, count)
        neighbors[a][b] = length
        neighbors[b][a] = length

    def cost(a, b):
        delta = means[a] - means[b]
        distance = float(delta @ delta)
        if mode == "area":
            return float(min(areas[a], areas[b])) * distance
        return (
            float(areas[a])
            * float(areas[b])
            / (areas[a] + areas[b])
            * distance
            / neighbors[a][b]
        )

    heap = []
    offers = 0

    def offer(a, b):
        nonlocal offers
        offers += 1
        if a > b:
            a, b = b, a
        value = cost(a, b)
        # Costs above threshold need no heap space; endpoint updates offer them
        # again if their value decreases. Versions invalidate stale entries.
        if value <= threshold:
            heapq.heappush(heap, (value, a, b, int(version[a]), int(version[b])))

    for a in range(count):
        for b in neighbors[a]:
            if a < b:
                offer(a, b)
    merges = 0
    while heap:
        if len(heap) > 250_000 or offers > 1_000_000:
            return None, {**stats, "reason": "merge work budget exceeded"}
        _, a, b, va, vb = heapq.heappop(heap)
        if (
            parent[a] != a
            or parent[b] != b
            or version[a] != va
            or version[b] != vb
            or b not in neighbors[a]
        ):
            continue
        # Keep the larger adjacency map to bound repeated neighbor movement.
        if len(neighbors[a]) < len(neighbors[b]):
            a, b = b, a
        parent[b] = a
        areas[a] += areas[b]
        sums[a] += sums[b]
        means[a] = sums[a] / areas[a]
        version[a] += 1
        version[b] += 1
        neighbors[a].pop(b)
        for other, length in neighbors[b].items():
            if other == a:
                continue
            neighbors[other].pop(b)
            combined = neighbors[a].get(other, 0) + length
            neighbors[a][other] = combined
            neighbors[other][a] = combined
        neighbors[b].clear()
        for other in neighbors[a]:
            offer(a, other)
        merges += 1
    # Pointer jumping maps every original component to its current root.
    roots = parent.copy()
    while not np.array_equal(roots, parent[roots]):
        roots = parent[roots]
    result = np.clip(means[roots][labels].round(), 0, 255).astype(np.uint8)
    return Image.fromarray(result), {
        **stats,
        "applied": True,
        "final_regions": int(count - merges),
        "merges": merges,
    }
