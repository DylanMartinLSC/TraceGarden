import io
import xml.etree.ElementTree as ET
import pytest
from PIL import Image, ImageDraw
from tracegarden.core import trace, export, Options, NS


def fixture_image(mode="RGBA", size=(128, 128)):
    im = Image.new(mode, size, "white")
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 100, 100), fill="red")
    d.rectangle((40, 40, 70, 70), fill="black")
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


@pytest.mark.parametrize("preset", ["logo", "illustration", "photo", "ink", "pixel"])
def test_trace_presets(preset):
    r = trace(fixture_image(), Options(preset=preset))
    root = ET.fromstring(r["svg"])
    assert root.get("viewBox") == "0 0 128 128"
    assert r["paths"] >= 2
    assert "<image" not in r["svg"]
    assert r["seconds"] >= 0


@pytest.mark.parametrize(
    "fmt,header",
    [
        ("svg", b"<svg"),
        ("pdf", b"%PDF"),
        ("eps", b"%!PS"),
        ("dxf", b"  0"),
        ("png", b"\x89PNG"),
    ],
)
def test_exports(fmt, header):
    svg = trace(fixture_image(), Options())["svg"]
    result = export(svg, fmt)
    assert result.startswith(header)
    if fmt == "dxf":
        import ezdxf

        doc = ezdxf.read(io.StringIO(result.decode()))
        assert len(doc.modelspace().query("LINE SPLINE ARC")) >= 2


def test_transparency():
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((10, 10, 40, 40), fill="red")
    b = io.BytesIO()
    im.save(b, format="PNG")
    r = trace(b.getvalue(), Options(speckle=0))
    assert len(ET.fromstring(r["svg"]).findall(NS + "path")) == 1


def test_remove_white_and_resize():
    r = trace(fixture_image(), Options(remove_white=True, max_size=64))
    assert r["width"] == 64 and r["resized"]
    assert "#FFFFFF" not in r["palette"]


@pytest.mark.parametrize("data", [b"", b"not an image", b"<svg/>"])
def test_invalid_input(data):
    with pytest.raises(ValueError):
        trace(data, Options())


def test_oversized_input(monkeypatch):
    import tracegarden.core as core

    monkeypatch.setattr(core, "MAX_BYTES", 2 * 1024 * 1024)
    with pytest.raises(ValueError, match="2 MB"):
        trace(b"0" * (2 * 1024 * 1024 + 1), Options())


@pytest.mark.parametrize(
    "svg",
    [
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
        "<!DOCTYPE svg><svg/>",
        '<svg xmlns="http://www.w3.org/2000/svg"><path fill="url(https://example.org/x)"/></svg>',
    ],
)
def test_reject_unsafe_svg(svg):
    with pytest.raises(ValueError):
        export(svg, "pdf")


def test_unsupported_format():
    with pytest.raises(ValueError):
        export(trace(fixture_image(), Options())["svg"], "unknown")


def test_visual_fidelity_and_holes():
    import numpy as np

    source = fixture_image()
    result = trace(source, Options(colors=8, speckle=0))
    rendered = Image.open(io.BytesIO(export(result["svg"], "png"))).convert("RGB")
    original = Image.open(io.BytesIO(source)).convert("RGB")
    error = (
        np.abs(
            np.asarray(original, dtype=float) - np.asarray(rendered, dtype=float)
        ).mean()
        / 255
    )
    assert error < 0.06, f"Flat artwork reconstruction error {error:.3f}"
    assert rendered.getpixel((55, 55)) == (0, 0, 0)
    assert rendered.getpixel((5, 5)) == (255, 255, 255)
