"""Native CPU cutout contours must retain shared component topology."""

import io

from PIL import Image, ImageDraw
from shapely.ops import unary_union
from svgpathtools import Arc

from tracegarden.core import Options, trace
from tracegarden.svgdoc import NS, absolute_path, polygon, validate_svg


def test_native_circle_models_reuse_hole_with_no_coverage_change():
    image = Image.new("RGB", (128, 128), "white")
    ImageDraw.Draw(image).ellipse((20, 20, 108, 108), fill="red")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    result = trace(buffer.getvalue(), Options(preset="auto", geometry=True, speckle=0))
    paths = validate_svg(result["svg"]).findall(NS + "path")
    assert result["analysis"]["layout"] == "native"
    assert len(paths) == 2
    curves = [[s for s in absolute_path(p) if isinstance(s, Arc)] for p in paths]
    assert len(curves[0]) == len(curves[1]) == 2
    for curve in curves[0]:
        assert any(
            abs(curve.point(0.25) - other.point(0.75)) < 1e-8 for other in curves[1]
        )
    shapes = [polygon(p) for p in paths]
    assert sum(s.area for s in shapes) - unary_union(shapes).area < 1e-6
    assert abs(unary_union(shapes).area - 128**2) < 1e-6
    assert len(result["svg"]) < 1000


def test_native_junction_does_not_regularize_only_one_side():
    image = Image.new("RGB", (128, 128), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 118, 118), fill="red")
    draw.rectangle((64, 0, 127, 127), fill="blue")
    draw.ellipse((24, 40, 48, 64), fill="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    result = trace(buffer.getvalue(), Options(preset="auto", geometry=True, speckle=0))
    shapes = [polygon(p) for p in validate_svg(result["svg"]).findall(NS + "path")]
    assert sum(s.area for s in shapes) - unary_union(shapes).area < 0.02
    assert abs(unary_union(shapes).area - 128**2) < 0.02
