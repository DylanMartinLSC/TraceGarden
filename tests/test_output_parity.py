import io
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw
from svgpathtools import Line, QuadraticBezier
from test_parity import image_bytes

from tracegarden.core import Options, export, trace
from tracegarden.exporters import ExportOptions
from tracegarden.modeling import shape_path
from tracegarden.svgdoc import NS, absolute_path, validate_svg


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


def test_gradient_region_replaces_quantization_bands_without_erasing_details():
    import resvg_py

    source = '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><defs><linearGradient id="g"><stop stop-color="#163d7a"/><stop offset="1" stop-color="#e87540"/></linearGradient></defs><rect x="24" y="24" width="208" height="208" rx="24" fill="url(#g)"/></svg>'
    data = resvg_py.svg_to_bytes(svg_string=source)
    result = trace(
        data,
        Options(preset="logo", colors=32, gradients=True, geometry=True, speckle=0),
    )
    assert result["paths"] == 1 and result["gradients"] == 1
    assert len(result["svg"]) < 2500
    detailed = source.replace(
        "</svg>", '<path d="M80 80H176V176H80Z" fill="black"/></svg>'
    )
    result = trace(
        resvg_py.svg_to_bytes(svg_string=detailed),
        Options(preset="logo", colors=32, gradients=True, speckle=0),
    )
    assert result["paths"] > 1
    rendered = Image.open(io.BytesIO(export(result["svg"], "png"))).convert("RGBA")
    assert max(rendered.getpixel((128, 128))[:3]) < 10


def test_independent_pdf_reader_finds_vector_gradient_and_alpha():
    from pypdf import PdfReader

    source = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="64"><defs><linearGradient id="g0" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="128" y2="0"><stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff"/></linearGradient></defs><path d="M0 0H128V64H0Z" fill="url(#g0)" opacity="0.5"/></svg>'
    reader = PdfReader(io.BytesIO(export(source, "pdf", ExportOptions(width_mm=50.8))))
    page = reader.pages[0]
    assert abs(float(page.mediabox.width) - 144) < 0.01
    assert abs(float(page.mediabox.height) - 72) < 0.01
    resources = page["/Resources"].get_object()
    assert "/Shading" in resources
    assert any(
        float(state.get_object().get("/ca", 1)) == 0.5
        for state in resources["/ExtGState"].values()
    )
    assert not resources.get("/XObject")
    operations = [op for _, op in page.get_contents().operations]
    assert b"sh" in operations and b"m" in operations
