from __future__ import annotations

import io
import base64
import time
import xml.etree.ElementTree as ET
from typing import Literal

import vtracer
from PIL import (
    Image,
    ImageOps,
    ImageFilter,
    ImageEnhance,
    ImageCms,
    UnidentifiedImageError,
)
from pydantic import BaseModel, Field, field_validator
from .svgdoc import serialize

MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
NS = "{http://www.w3.org/2000/svg}"
ET.register_namespace("", NS[1:-1])


def pixels(image):
    method = getattr(image, "get_flattened_data", None)
    return method() if method else image.getdata()


class Options(BaseModel):
    preset: Literal["logo", "illustration", "photo", "ink", "pixel", "centerline"] = (
        "logo"
    )
    colors: int = Field(16, ge=2, le=256)
    speckle: int = Field(4, ge=0, le=64)
    corner: int = Field(60, ge=0, le=180)
    precision: int = Field(4, ge=1, le=8)
    threshold: int = Field(128, ge=0, le=255)
    max_size: int = Field(1600, ge=64, le=4096)
    smooth: bool = False
    remove_white: bool = False
    layering: Literal["stacked", "cutout", "mosaic"] = "stacked"
    layer_difference: int = Field(16, ge=0, le=255)
    geometry: bool = False
    gradients: bool = False
    rotation: Literal[0, 90, 180, 270] = 0
    flip: bool = False
    crop: tuple[int, int, int, int] | None = None
    contrast: float = Field(1, ge=0.25, le=4)
    palette: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("palette")
    @classmethod
    def valid_palette(cls, value):
        import re

        if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", v) for v in value):
            raise ValueError("Palette colors must be six-digit hex colors.")
        return value


def trace(data: bytes, options: Options) -> dict:
    started = time.perf_counter()
    if len(data) > MAX_BYTES:
        raise ValueError("Image exceeds the 25 MB limit.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ValueError("Image exceeds the 16 megapixel limit.")
            if source.format not in {"PNG", "JPEG", "WEBP", "BMP", "GIF", "TIFF"}:
                raise ValueError("Choose PNG, JPEG, WebP, BMP, GIF or TIFF.")
            original = source.size
            oriented = ImageOps.exif_transpose(source)
            profile = source.info.get("icc_profile")
            image = oriented.convert("RGBA")
            if profile:
                try:
                    rgb = ImageCms.profileToProfile(
                        oriented
                        if oriented.mode in {"RGB", "CMYK", "L"}
                        else oriented.convert("RGB"),
                        ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                        ImageCms.createProfile("sRGB"),
                        outputMode="RGB",
                    )
                    image = rgb.convert("RGBA")
                    image.putalpha(oriented.convert("RGBA").getchannel("A"))
                except (ValueError, OSError, ImageCms.PyCMSError) as exc:
                    raise ValueError(
                        "The embedded color profile could not be converted to sRGB."
                    ) from exc
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("This image could not be opened. Try a PNG or JPEG.") from exc
    if options.crop:
        x, y, w, h = options.crop
        if (
            min(x, y) < 0
            or min(w, h) <= 0
            or x + w > image.width
            or y + h > image.height
        ):
            raise ValueError("Crop must be inside the source image.")
        image = image.crop((x, y, x + w, y + h))
    if options.rotation:
        image = image.rotate(-options.rotation, expand=True)
    if options.flip:
        image = ImageOps.mirror(image)
    image.thumbnail((options.max_size, options.max_size), Image.Resampling.LANCZOS)
    reference_image = image.copy()
    alpha = image.getchannel("A")
    rgb = Image.new("RGB", image.size, "white")
    # Preserve unassociated RGB for translucent artwork; avoid a white matte.
    rgb.paste(image.convert("RGB"), mask=alpha.point(lambda a: 255 if a else 0))
    if options.contrast != 1:
        rgb = ImageEnhance.Contrast(rgb).enhance(options.contrast)
    if options.smooth:
        rgb = rgb.filter(ImageFilter.MedianFilter(3))
    if options.preset in {"ink", "centerline"}:
        rgb = (
            rgb.convert("L")
            .point(lambda p: 255 if p >= options.threshold else 0)
            .convert("RGB")
        )
    elif options.palette:
        from PIL import ImageColor

        palette = Image.new("P", (1, 1))
        values = [
            channel for color in options.palette for channel in ImageColor.getrgb(color)
        ]
        palette.putpalette(values + [0] * (768 - len(values)))
        # Fill unused entries with the last chosen color rather than introducing black.
        palette.putpalette(values + values[-3:] * ((768 - len(values)) // 3))
        rgb = rgb.quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB")
    elif options.preset != "photo":
        rgb = rgb.quantize(
            colors=options.colors, method=Image.Quantize.MEDIANCUT
        ).convert("RGB")
    image = rgb.convert("RGBA")
    image.putalpha(alpha)
    if options.remove_white:
        image.putdata(
            [(r, g, b, 0 if min(r, g, b) > 245 else a) for r, g, b, a in pixels(image)]
        )
    if options.layering == "mosaic" and options.preset != "centerline":
        from .mosaic import trace_mosaic

        if options.preset == "photo":
            quantized = rgb.quantize(colors=options.colors).convert("RGBA")
            quantized.putalpha(image.getchannel("A"))
        else:
            quantized = image
        root = trace_mosaic(quantized, tolerance=0.5)
    elif options.preset == "centerline":
        from .enhance import centerlines

        root = centerlines(rgb, options.threshold, options.speckle)
    else:
        svg = vtracer.convert_pixels_to_svg(
            list(pixels(image)),
            image.size,
            colormode="color",
            hierarchical=options.layering,
            mode="polygon" if options.preset == "pixel" else "spline",
            layer_difference=options.layer_difference,
            filter_speckle=options.speckle,
            color_precision=options.precision,
            corner_threshold=options.corner,
            length_threshold=4.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=3,
        )
        root = ET.fromstring(svg)
    root.set("viewBox", f"0 0 {image.width} {image.height}")
    root.set("role", "img")
    reconstructed = 0
    fitted_gradients = 0
    if (
        options.geometry
        and options.preset != "centerline"
        and options.layering != "mosaic"
    ):
        from .enhance import primitives

        reconstructed = primitives(root)
    if options.gradients and options.preset != "centerline":
        from .enhance import gradients

        fitted_gradients = gradients(root, rgb)
    if sum(alpha.histogram()[1:255]) and options.preset != "centerline":
        from .enhance import opacity_regions

        opacity_regions(root, alpha)
    paths = root.findall(f".//{NS}path")
    for i, path in enumerate(paths):
        path.set("id", f"p{i}")
    preview = io.BytesIO()
    reference_image.save(preview, format="PNG")
    return {
        "svg": serialize(root),
        "width": image.width,
        "height": image.height,
        "original": original,
        "paths": len(paths),
        "seconds": round(time.perf_counter() - started, 3),
        "palette": sorted({p.get("fill", "#000000") for p in paths}),
        "resized": original != image.size,
        "geometry": reconstructed,
        "gradients": fitted_gradients,
        "preview": "data:image/png;base64,"
        + base64.b64encode(preview.getvalue()).decode(),
    }


def export(svg: str, fmt: str, options=None) -> bytes:
    from .exporters import export_document

    return export_document(svg, fmt, options)
