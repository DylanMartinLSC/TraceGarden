"""Rounded and stretched star recognition with independent raster reconstruction."""

import io

import numpy as np
import pytest
import resvg_py
from PIL import Image
from svgpathtools import Arc

from tracegarden.core import Options, export, trace
from tracegarden.modeling import shape_path
from tracegarden.svgdoc import NS, absolute_path, validate_svg


@pytest.mark.parametrize(
    "sides,width,height,rotation,radius", [(5, 140, 110, 27, 4), (6, 140, 140, 13, 5)]
)
def test_recognize_rounded_rotated_star_from_raster(
    sides, width, height, rotation, radius
):
    path = shape_path("star", 100, 100, width, height, rotation, radius, sides, 0.45)
    source = f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><path d="{path.d()}Z" fill="#ee3344"/></svg>'
    data = resvg_py.svg_to_bytes(svg_string=source)
    result = trace(data, Options(preset="auto", geometry=True, speckle=0))
    assert result["geometry"] >= 1
    paths = validate_svg(result["svg"]).findall(NS + "path")
    assert sum(isinstance(s, Arc) for p in paths for s in absolute_path(p)) == 2 * sides
    expected = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"), float) / 255
    actual = (
        np.asarray(
            Image.open(io.BytesIO(export(result["svg"], "png"))).convert("RGBA"), float
        )
        / 255
    )
    assert abs(expected[:, :, 3] - actual[:, :, 3]).mean() < 0.012
