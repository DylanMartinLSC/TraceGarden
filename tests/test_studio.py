import io
import time
import numpy as np
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from tracegarden.app import app
from tracegarden.core import trace, Options, export
from tracegarden.exporters import ExportOptions
from tracegarden.svgdoc import validate_svg, EditRequest, edit_vector, NS, polygon
from test_core import fixture_image


def svg(paths):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">{paths}</svg>'


OVERLAP = svg(
    '<path d="M10 10H70V70H10Z" fill="#ff0000"/><path d="M40 40H100V100H40Z" fill="#00ff00"/>'
)


@pytest.mark.parametrize(
    "op,area", [("union", 6300), ("subtract", 2700), ("intersect", 900)]
)
def test_boolean_geometry(op, area):
    result = edit_vector(EditRequest(svg=OVERLAP, operation=op, indices=[0, 1]))["svg"]
    root = validate_svg(result)
    assert len(root.findall(NS + "path")) == 1
    assert polygon(root.find(NS + "path")).area == pytest.approx(area)


def test_nodes_and_compound_guard():
    result = edit_vector(
        EditRequest(
            svg=OVERLAP,
            operation="set-nodes",
            indices=[0],
            points=[[10, 10], [70, 10], [70, 70], [10, 70]],
        )
    )
    assert "L70.000" in result["svg"]
    shape = svg('<path d="M0 0H100V100H0Z M20 20H50V50H20Z" fill="#000000"/>')
    with pytest.raises(ValueError, match="Split"):
        edit_vector(
            EditRequest(
                svg=shape, operation="set-nodes", indices=[0], points=[[0, 0], [1, 1]]
            )
        )
    split = edit_vector(EditRequest(svg=shape, operation="split", indices=[0]))
    assert len(validate_svg(split["svg"]).findall(NS + "path")) == 2


def test_crop_rotate_palette():
    result = trace(
        fixture_image(),
        Options(crop=(0, 0, 120, 60), rotation=90, palette=["#ff0000", "#ffffff"]),
    )
    assert (result["width"], result["height"]) == (60, 120)
    assert set(result["palette"]) <= {"#FF0000", "#FFFFFF"}
    with pytest.raises(ValueError, match="Crop"):
        trace(fixture_image(), Options(crop=(0, 0, 999, 999)))


def test_geometry_reconstruction_and_exact_dxf_arcs():
    im = Image.new("RGB", (256, 256), "white")
    ImageDraw.Draw(im).ellipse((48, 48, 208, 208), fill="black")
    b = io.BytesIO()
    im.save(b, format="PNG")
    r = trace(b.getvalue(), Options(geometry=True, speckle=0, precision=8))
    assert r["geometry"] >= 1
    assert " A" in r["svg"]
    import ezdxf

    doc = ezdxf.read(io.StringIO(export(r["svg"], "dxf").decode()))
    assert len(doc.modelspace().query("ARC")) >= 2


def test_linear_gradient_quality_and_exports():
    w = 128
    rgb = np.zeros((w, w, 3), np.uint8)
    rgb[:, :, 0] = np.arange(w)[None, :] * 2
    rgb[:, :, 1] = 100
    rgb[:, :, 2] = 200
    im = Image.fromarray(rgb)
    b = io.BytesIO()
    im.save(b, format="PNG")
    r = trace(b.getvalue(), Options(preset="photo", gradients=True, precision=3))
    assert r["gradients"] >= 1
    root = validate_svg(r["svg"])
    assert root.find(NS + "defs") is not None
    rendered = np.asarray(
        Image.open(io.BytesIO(export(r["svg"], "png"))).convert("RGB")
    )
    mae = np.abs(rendered.astype(float) - rgb).mean() / 255
    assert mae < 0.06
    pdf = export(r["svg"], "pdf")
    eps = export(r["svg"], "eps")
    assert pdf.startswith(b"%PDF") and b"/ShadingType 2" in eps
    assert export(r["svg"], "ai").startswith(b"%PDF")


def test_centerline_open_strokes():
    im = Image.new("RGB", (128, 128), "white")
    ImageDraw.Draw(im).line((20, 64, 108, 64), fill="black", width=7)
    b = io.BytesIO()
    im.save(b, format="PNG")
    r = trace(b.getvalue(), Options(preset="centerline", speckle=0))
    paths = validate_svg(r["svg"]).findall(NS + "path")
    assert paths and all(p.get("fill") == "none" for p in paths)
    assert all("Z" not in p.get("d") for p in paths)
    assert r["paths"] < 5


def test_centerline_single_pixel_skeleton():
    im = Image.new("RGB", (64, 64), "white")
    ImageDraw.Draw(im).ellipse((10, 10, 50, 50), fill="black")
    out = io.BytesIO()
    im.save(out, format="PNG")
    result = trace(out.getvalue(), Options(preset="centerline", speckle=0))
    assert result["paths"] >= 1


def test_print_size_and_cmyk_pdf():
    import ezdxf

    doc = ezdxf.read(
        io.StringIO(export(OVERLAP, "dxf", ExportOptions(width_mm=128)).decode())
    )
    assert doc.units == 4
    assert len(doc.modelspace().query("LINE")) == 8
    pdf = export(OVERLAP, "pdf", ExportOptions(width_mm=100, color_space="cmyk"))
    assert pdf.startswith(b"%PDF")


@pytest.mark.parametrize(
    "bad",
    [
        svg('<image href="file:///etc/passwd"/>'),
        svg('<path d="M0 0" fill="url(#g9)"/>'),
        svg('<path d="M0 0" transform="scale(1000000000)"/>'),
        svg('<path d="M1e999 0"/>'),
        svg('<path d="M0 0 nonsense"/>'),
        '<svg xmlns="http://www.w3.org/2000/svg" width="999999" height="999999"/>',
        '<!DOCTYPE svg [<!ENTITY a "x">]><svg>&a;</svg>',
    ],
)
def test_svg_import_guards(bad):
    with pytest.raises(ValueError):
        validate_svg(bad)


def test_job_lifecycle_and_cancellation():
    with TestClient(app) as client:
        r = client.post("/api/jobs", files={"file": ("test.png", fixture_image())})
        assert r.status_code == 202
        ident = r.json()["id"]
        started = time.monotonic()
        while True:
            state = client.get("/api/jobs/" + ident).json()
            if state["state"] in {"complete", "failed"}:
                break
            assert time.monotonic() - started < 30
            time.sleep(0.1)
        assert state["state"] == "complete", state
        assert "<svg" in state["result"]["svg"]
        assert client.delete("/api/jobs/" + ident).status_code == 200
        assert client.get("/api/jobs/" + ident).status_code == 404
        ident = client.post(
            "/api/jobs", files={"file": ("test.png", fixture_image())}
        ).json()["id"]
        r = client.delete("/api/jobs/" + ident)
        assert r.status_code == 200
        assert r.json()["state"] == "cancelled"
        assert client.get("/api/jobs/" + ident).status_code == 404


def test_bad_job_and_edit_api():
    with TestClient(app) as client:
        assert (
            client.post("/api/jobs", files={"file": ("a.png", b"")}).status_code == 400
        )
        assert (
            client.post(
                "/api/edit",
                json={"svg": OVERLAP, "operation": "union", "indices": [0, 1]},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/edit",
                json={"svg": OVERLAP, "operation": "union", "indices": [999]},
            ).status_code
            == 400
        )
        assert (
            client.post("/api/validate-svg", json={"svg": svg("<script/>")}).status_code
            == 400
        )


def test_shared_boundaries_no_overlap_or_gaps():
    from shapely.ops import unary_union

    im = Image.new("RGB", (64, 64), "red")
    d = ImageDraw.Draw(im)
    d.rectangle((32, 0, 63, 63), fill="green")
    d.rectangle((10, 10, 20, 20), fill="blue")
    b = io.BytesIO()
    im.save(b, format="PNG")
    root = validate_svg(
        trace(b.getvalue(), Options(layering="mosaic", colors=3))["svg"]
    )
    shapes = [polygon(el) for el in root.findall(NS + "path")]
    for i, a in enumerate(shapes):
        for other in shapes[i + 1 :]:
            assert a.intersection(other).area < 1e-6
    assert unary_union(shapes).area == pytest.approx(64 * 64)
    assert any(
        a.boundary.intersection(other.boundary).length > 10
        for i, a in enumerate(shapes)
        for other in shapes[i + 1 :]
    )


def test_shared_boundaries_nested_island():
    im = Image.new("RGB", (64, 64), "red")
    d = ImageDraw.Draw(im)
    d.rectangle((10, 10, 50, 50), fill="blue")
    d.rectangle((20, 20, 40, 40), fill="red")
    b = io.BytesIO()
    im.save(b, format="PNG")
    result = trace(b.getvalue(), Options(layering="mosaic", colors=2))
    rendered = Image.open(io.BytesIO(export(result["svg"], "png"))).convert("RGB")
    assert rendered.getpixel((30, 30)) == (255, 0, 0)
    assert rendered.getpixel((15, 15)) == (0, 0, 255)


def test_uniform_partial_alpha():
    im = Image.new("RGBA", (64, 64))
    ImageDraw.Draw(im).rectangle((10, 10, 50, 50), fill=(255, 0, 0, 128))
    b = io.BytesIO()
    im.save(b, format="PNG")
    result = trace(b.getvalue(), Options(speckle=0))
    rendered = Image.open(io.BytesIO(export(result["svg"], "png")))
    r, g, b, a = rendered.getpixel((30, 30))
    assert r > 250 and g < 5 and b < 5 and 125 <= a <= 130


def test_bezier_controls_preserve_curves():
    source = svg('<path d="M0 0 C0 50 100 50 100 0" fill="none" stroke="#000000"/>')
    controls = edit_vector(EditRequest(svg=source, operation="curves", indices=[0]))[
        "points"
    ]
    assert controls == [[0, 0], [0, 50], [100, 50], [100, 0]]
    controls[1][1] = 70
    result = edit_vector(
        EditRequest(svg=source, operation="set-curves", indices=[0], points=controls)
    )["svg"]
    assert "C" in result and "70" in result


def test_physical_png_and_svg_export():
    png = export(OVERLAP, "png", ExportOptions(width_mm=25.4, dpi=200))
    im = Image.open(io.BytesIO(png))
    assert im.size == (200, 200)
    assert abs(im.info["dpi"][0] - 200) < 0.1
    assert b"25.4mm" in export(OVERLAP, "svg", ExportOptions(width_mm=25.4))
    with pytest.raises(ValueError, match="megapixel"):
        export(OVERLAP, "png", ExportOptions(width_mm=5000, dpi=1200))


def test_worker_timeout_and_queue_admission():
    import asyncio
    from tracegarden.jobs import JobManager

    async def exercise():
        manager = JobManager(timeout=0.001)
        job = manager.submit(fixture_image(), Options())
        await job.task
        assert job.state == "failed" and "time limit" in job.error
        assert job.process is None
        await manager.close()
        manager = JobManager()
        for _ in range(20):
            manager.submit(b"x", Options())
        with pytest.raises(ValueError, match="full"):
            manager.submit(b"x", Options())
        await manager.close()
        assert all(
            j.process is None and j.state == "cancelled" for j in manager.jobs.values()
        )

    asyncio.run(exercise())


def test_cli_batch_partial_failure(tmp_path):
    import subprocess
    import sys

    good = tmp_path / "logo.png"
    good.write_bytes(fixture_image())
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"invalid")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tracegarden",
            "convert",
            str(good),
            str(bad),
            "--output",
            str(tmp_path / "vectors"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert (tmp_path / "vectors" / "01-logo.svg").read_text().startswith("<svg")
    assert "could not be opened" in result.stdout
