import io
import numpy as np
from PIL import Image, ImageDraw
from shapely.ops import unary_union
from svgpathtools import CubicBezier, Arc
from tracegarden.core import Options, trace, export
from tracegarden.svgdoc import NS, validate_svg, polygon, absolute_path


def image_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_smooth_shared_boundary_reused_in_both_regions():
    image = Image.new("RGB", (192, 192), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.ellipse((32, 32, 160, 160), fill="#ff0000")
    result = trace(image_bytes(image), Options(layering="smooth", colors=2, speckle=0))
    root = validate_svg(result["svg"])
    paths = root.findall(NS + "path")
    assert len(paths) == 2
    curves = [
        [seg for seg in absolute_path(path) if isinstance(seg, (CubicBezier, Arc))]
        for path in paths
    ]
    assert len(curves[0]) >= 2 and len(curves[1]) >= 2
    for seg in curves[0]:
        assert any(
            abs(seg.start - other.end) < 1e-8
            and abs(seg.point(0.25) - other.point(0.75)) < 1e-8
            and abs(seg.point(0.75) - other.point(0.25)) < 1e-8
            and abs(seg.end - other.start) < 1e-8
            for other in curves[1]
        )
    shapes = [polygon(path) for path in paths]
    assert shapes[0].intersection(shapes[1]).area < 1e-5
    assert abs(unary_union(shapes).area - 192 * 192) < 1e-5
    old = trace(image_bytes(image), Options(layering="mosaic", colors=2, speckle=0))
    assert len(result["svg"]) < len(old["svg"])


def test_smooth_shared_junction_and_nested_holes():
    image = Image.new("RGB", (128, 128), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 118, 118), fill="red")
    draw.rectangle((64, 0, 127, 127), fill="blue")
    draw.ellipse((24, 40, 48, 64), fill="white")
    result = trace(image_bytes(image), Options(layering="smooth", colors=3, speckle=0))
    root = validate_svg(result["svg"])
    shapes = [polygon(p) for p in root.findall(NS + "path")]
    assert any("C" in p.get("d") for p in root.findall(NS + "path"))
    assert sum(s.area for s in shapes) - unary_union(shapes).area < 0.001
    assert abs(unary_union(shapes).area - 128 * 128) < 0.01


def test_spatially_varying_alpha_is_not_collapsed_to_one_opacity():
    values = np.zeros((32, 64, 4), np.uint8)
    values[:, :, :3] = [220, 40, 80]
    values[:, :, 3] = np.arange(64, dtype=np.uint8)[None, :] * 4
    result = trace(image_bytes(Image.fromarray(values)), Options(colors=2, speckle=0))
    rendered = np.asarray(Image.open(io.BytesIO(export(result["svg"], "png"))))
    assert result["full_alpha"]
    assert len(np.unique(rendered[16, :, 3])) > 40
    assert np.abs(rendered[16, :, 3].astype(float) - values[16, :, 3]).mean() < 3


def test_auto_palette_background_and_mirror_analysis():
    im = Image.new("RGB", (96, 64), "#aaccbb")
    draw = ImageDraw.Draw(im)
    draw.rectangle((24, 16, 71, 47), fill="#225588")
    result = trace(
        image_bytes(im), Options(preset="auto", background="auto", symmetry="auto")
    )
    assert result["analysis"]["colors"] <= 4
    assert result["background"]["pixels"] > 0
    assert "horizontal" in result["symmetry"]
    rendered = Image.open(io.BytesIO(export(result["svg"], "png")))
    assert rendered.getpixel((0, 0))[3] == 0
    assert rendered.getpixel((40, 30))[3] > 250


def test_parametric_rotated_rounded_star_and_corner_controls():
    from tracegarden.modeling import shape_path, corner_data
    from tracegarden.svgdoc import EditRequest, edit_vector

    star = shape_path("star", 64, 64, 80, 80, 27, 3, 5, 0.45)
    assert star.isclosed()
    assert any(type(s).__name__ == "Arc" for s in star)
    source = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><path d="M20 20H100V100H20Z" fill="#ff0000"/></svg>'
    rounded = edit_vector(
        EditRequest(svg=source, operation="round-corners", indices=[0], radius=10)
    )["svg"]
    root = validate_svg(rounded)
    assert (
        sum(type(s).__name__ == "Arc" for s in absolute_path(root.find(NS + "path")))
        == 4
    )
    assert len(corner_data(root.find(NS + "path"))) == 4
    sharp = edit_vector(
        EditRequest(svg=rounded, operation="round-corners", indices=[0], radius=0)
    )["svg"]
    assert abs(polygon(validate_svg(sharp).find(NS + "path")).area - 6400) < 1e-5
    individual = edit_vector(
        EditRequest(
            svg=source,
            operation="round-corners",
            indices=[0],
            radius=10,
            corner_indices=[1],
        )
    )["svg"]
    assert (
        sum(
            type(s).__name__ == "Arc"
            for s in absolute_path(validate_svg(individual).find(NS + "path"))
        )
        == 1
    )
