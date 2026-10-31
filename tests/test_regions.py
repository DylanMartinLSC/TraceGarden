"""Published merge criteria, sparse graph updates and opt-in integration."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from tracegarden.core import Options, trace
from tracegarden.regions import merge_regions
from tracegarden.tuning import experimental_tuning


def test_thin_high_contrast_line_survives_while_isolated_noise_merges():
    image = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.line((10, 5, 10, 58), fill=(50, 50, 50), width=1)
    draw.point((40, 40), fill=(200, 200, 200))
    actual, stats = merge_regions(image, 10_000)
    assert actual.getpixel((10, 20)) == (50, 50, 50)
    assert actual.getpixel((40, 40)) == (255, 255, 255)
    assert stats["final_regions"] == 2
    repeated, other = merge_regions(image, 10_000)
    assert actual.tobytes() == repeated.tobytes() and stats == other


@pytest.mark.parametrize("mode", ["area", "ms"])
@pytest.mark.parametrize("threshold", [1000, 10_000, 50_000])
def test_heap_agrees_with_exhaustive_adjacent_region_search(mode, threshold):
    # Each seed is one pixel. Independent slow oracle rebuilds ALL region pairs
    # and statistics after every merge, detecting stale heap/adjacency mistakes.
    values = np.random.default_rng(57).integers(0, 256, (4, 4, 3), dtype=np.uint8)
    image = Image.fromarray(values)
    actual, _ = merge_regions(image, threshold, colors=256, mode=mode)
    groups = [{i} for i in range(16)]
    rgb = values.reshape(-1, 3).astype(float)
    while True:
        choices = []
        for a, first in enumerate(groups):
            for b in range(a + 1, len(groups)):
                second = groups[b]
                boundary = sum(
                    1
                    for i in first
                    for j in second
                    if (i // 4 == j // 4 and abs(i - j) == 1) or abs(i - j) == 4
                )
                if not boundary:
                    continue
                delta = rgb[list(first)].mean(0) - rgb[list(second)].mean(0)
                distance = float(delta @ delta)
                na, nb = len(first), len(second)
                cost = (
                    min(na, nb) * distance
                    if mode == "area"
                    else na * nb / (na + nb) * distance / boundary
                )
                choices.append((cost, a, b))
        if not choices or min(choices)[0] > threshold:
            break
        _, a, b = min(choices)
        groups[a] |= groups.pop(b)
    expected = np.empty((16, 3), np.uint8)
    for group in groups:
        expected[list(group)] = rgb[list(group)].mean(0).round().astype(np.uint8)
    np.testing.assert_array_equal(np.asarray(actual), expected.reshape(4, 4, 3))


def test_original_means_and_explicit_region_budget():
    image = Image.fromarray(np.array([[[10, 20, 30], [30, 40, 50]]], np.uint8))
    result, stats = merge_regions(image, 5000)
    np.testing.assert_array_equal(np.asarray(result), [[[20, 30, 40], [20, 30, 40]]])
    assert stats["final_regions"] == 1
    result, stats = merge_regions(image, 5000, max_regions=1)
    assert result is None and not stats["applied"] and "budget" in stats["reason"]
    for threshold in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            merge_regions(image, threshold)


def test_opt_in_preserves_transparency_and_explicit_palette():
    image = Image.new("RGBA", (24, 24), (180, 30, 60, 100))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    settings = Options(preset="auto", layering="auto")
    control = trace(buffer.getvalue(), settings)
    with experimental_tuning({"region_merge_threshold": 1024}):
        actual = trace(buffer.getvalue(), settings)
    assert actual["svg"] == control["svg"]
    assert not actual["analysis"]["region_merging"]["applied"]
    image = Image.new("RGB", (24, 24), "white")
    image.save(buffer := io.BytesIO(), "PNG")
    settings = Options(preset="logo", palette=["#ffffff", "#000000"])
    control = trace(buffer.getvalue(), settings)
    with experimental_tuning({"region_merge_threshold": 1024}):
        actual = trace(buffer.getvalue(), settings)
    assert actual["svg"] == control["svg"]
    assert not actual["analysis"]["region_merging"]["applied"]


def test_region_integration_is_disabled_by_default_and_records_application():
    image = Image.new("RGB", (32, 32), "white")
    ImageDraw.Draw(image).rectangle((8, 8, 24, 24), fill="black")
    image.save(buffer := io.BytesIO(), "PNG")
    settings = Options(preset="auto", layering="auto")
    control = trace(buffer.getvalue(), settings)
    assert "region_merging" not in control["analysis"]
    with experimental_tuning({"region_merge_threshold": 1024}):
        actual = trace(buffer.getvalue(), settings)
    assert actual["analysis"]["region_merging"]["applied"]
    assert trace(buffer.getvalue(), settings)["svg"] == control["svg"]
