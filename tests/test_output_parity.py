import io
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
from svgpathtools import QuadraticBezier, Line
from tracegarden.core import trace, Options, export
from tracegarden.svgdoc import validate_svg, absolute_path, NS
from tracegarden.exporters import ExportOptions
from tracegarden.modeling import shape_path
from test_parity import image_bytes


def test_all_advertised_bitmap_outputs_and_curve_compatibility():
    image = Image.new("RGB", (64, 64), "white")
    ImageDraw.Draw(image).ellipse((8, 8, 56, 56), fill="red")
    svg = trace(image_bytes(image), Options())["svg"]
    for fmt in ["png", "jpg", "gif", "bmp", "tiff"]:
        result = Image.open(io.BytesIO(export(svg, fmt)))
        assert result.size == (64, 64)
    quad = validate_svg(
        export(svg, "svg", ExportOptions(curve_mode="quadratic")).decode()
    )
    assert all(
        isinstance(s, (Line, QuadraticBezier))
        for el in quad.findall(NS + "path")
        for s in absolute_path(el)
    )
    grouped = ET.fromstring(export(svg, "svg", ExportOptions(grouping="color")))
    assert len(grouped.findall(NS + "g")) >= 2


def test_dxf_ellipses_and_r12_compatibility():
    import ezdxf

    shape = shape_path("ellipse", 64, 64, 90, 50, 33).d()
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><path d="{shape}" fill="#000000"/></svg>'
    doc = ezdxf.read(io.StringIO(export(svg, "dxf").decode()))
    assert len(doc.modelspace().query("ELLIPSE")) == 2
    legacy = ezdxf.read(
        io.StringIO(export(svg, "dxf", ExportOptions(compatibility="legacy")).decode())
    )
    assert legacy.dxfversion == "AC1009"
    assert len(legacy.modelspace().query("POLYLINE")) >= 1
