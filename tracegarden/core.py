from __future__ import annotations

import base64
import io
import time
import xml.etree.ElementTree as ET
from typing import Literal

from PIL import (
    Image,
    ImageCms,
    ImageEnhance,
    ImageFilter,
    ImageOps,
    UnidentifiedImageError,
)
from pydantic import BaseModel, Field, field_validator

from .svgdoc import serialize

MAX_BYTES = 100 * 1024 * 1024
MAX_PIXELS = 100_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
NS = "{http://www.w3.org/2000/svg}"
ET.register_namespace("", NS[1:-1])


def pixels(image):
    method = getattr(image, "get_flattened_data", None)
    return method() if method else image.getdata()


class Options(BaseModel):
    preset: Literal[
        "auto", "logo", "illustration", "photo", "ink", "pixel", "centerline"
    ] = "logo"
    colors: int = Field(16, ge=2, le=256)
    speckle: int = Field(4, ge=0, le=64)
    corner: int = Field(60, ge=0, le=180)
    precision: int = Field(4, ge=1, le=8)
    threshold: int = Field(128, ge=0, le=255)
    max_size: int = Field(1600, ge=64, le=16384)
    memory_limit_mib: int = Field(1024, ge=128, le=32768)
    timeout_seconds: int = Field(120, ge=10, le=3600)
    smooth: bool = False
    remove_white: bool = False
    layering: Literal["auto", "native", "stacked", "cutout", "mosaic", "smooth"] = (
        "stacked"
    )
    layer_difference: int = Field(16, ge=0, le=255)
    geometry: bool = False
    gradients: bool = False
    rotation: Literal[0, 90, 180, 270] = 0
    flip: bool = False
    crop: tuple[int, int, int, int] | None = None
    contrast: float = Field(1, ge=0.25, le=4)
    palette: list[str] = Field(default_factory=list, max_length=64)
    background: Literal["keep", "auto", "color"] = "keep"
    background_color: str = "#ffffff"
    background_tolerance: float = Field(18, ge=0, le=120)
    symmetry: Literal[
        "none", "auto", "horizontal", "vertical", "both", "rotational"
    ] = "none"
    symmetry_order: int = Field(2, ge=2, le=16)
    normalize_repeats: bool = False

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
        raise ValueError(f"Image exceeds the {MAX_BYTES // 1024 // 1024} MB limit.")
    warnings = []
    memory_side = max(64, int((options.memory_limit_mib * 1024**2 / 200) ** 0.5))
    effective_size = min(options.max_size, memory_side)
    if effective_size < options.max_size:
        warnings.append(
            f"Trace size limited to {effective_size} pixels by the selected memory budget."
        )
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ValueError("Image exceeds the 100 megapixel source limit.")
            if source.format not in {"PNG", "JPEG", "WEBP", "BMP", "GIF", "TIFF"}:
                raise ValueError("Choose PNG, JPEG, WebP, BMP, GIF or TIFF.")
            original = source.size
            if source.format == "JPEG" and not options.crop:
                source.draft("RGB", (effective_size, effective_size))
            if source.width * source.height * 10 > options.memory_limit_mib * 1024**2:
                raise ValueError(
                    "Source decoding exceeds the selected memory budget. Increase the budget or use a smaller source image."
                )
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
    del source, oriented
    image.thumbnail((effective_size, effective_size), Image.Resampling.LANCZOS)
    reference_image = image.copy()
    explicit_palette = bool(options.palette)
    automatic_layout = options.layering == "auto" or (
        options.preset == "auto" and "layering" not in options.model_fields_set
    )
    analysis = {}
    if options.preset == "auto":
        from .intelligence import analyze

        analysis = analyze(image)
        options = options.model_copy(
            update={
                "preset": analysis["preset"],
                "colors": analysis["colors"],
                "palette": options.palette or analysis.get("palette", []),
            }
        )
    if automatic_layout:
        options = options.model_copy(
            update={"layering": "stacked" if options.preset == "photo" else "native"}
        )
        analysis["layout"] = options.layering
    removed = {}
    detected_symmetry = []
    if options.background != "keep":
        from .intelligence import remove_background

        try:
            image, removed = remove_background(
                image,
                options.background,
                options.background_color,
                options.background_tolerance,
            )
        except (ValueError, TypeError) as exc:
            raise ValueError("Choose a valid background color.") from exc
    if options.symmetry != "none":
        from .intelligence import symmetry

        image, detected_symmetry = symmetry(
            image, options.symmetry, options.symmetry_order
        )
    background_preview = None
    if removed.get("pixels", 0):
        prepared = io.BytesIO()
        image.save(prepared, format="PNG")
        background_preview = (
            "data:image/png;base64," + base64.b64encode(prepared.getvalue()).decode()
        )
    alpha = image.getchannel("A")
    rgb = Image.new("RGB", image.size, "white")
    # Preserve unassociated RGB for translucent artwork; avoid a white matte.
    rgb.paste(image.convert("RGB"), mask=alpha.point(lambda a: 255 if a else 0))
    if options.contrast != 1:
        rgb = ImageEnhance.Contrast(rgb).enhance(options.contrast)
    if options.smooth:
        rgb = rgb.filter(ImageFilter.MedianFilter(3))
    fitting_reference = rgb.convert("RGBA")
    fitting_reference.putalpha(alpha)
    from .tuning import current

    region_image = None
    tuning = current()
    if tuning.region_merge_threshold > 0:
        if (
            options.preset in {"logo", "illustration", "photo"}
            and not explicit_palette
            and alpha.getextrema() == (255, 255)
        ):
            from .regions import merge_regions

            region_image, analysis["region_merging"] = merge_regions(
                rgb,
                tuning.region_merge_threshold,
                tuning.region_seed_colors,
                tuning.region_merge_mode,
            )
        else:
            analysis["region_merging"] = {
                "applied": False,
                "reason": "requires opaque color artwork without an explicit palette",
            }
    if region_image is not None:
        rgb = region_image
    elif options.preset in {"ink", "centerline"}:
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
    subpixel_pixels = 0
    if options.preset in {"logo", "illustration"} and options.layering == "smooth":
        from .intelligence import color_coverage

        rgb, subpixel_pixels = color_coverage(rgb, fitting_reference)
    image = rgb.convert("RGBA")
    image.putalpha(alpha)
    if options.remove_white:
        image.putdata(
            [(r, g, b, 0 if min(r, g, b) > 245 else a) for r, g, b, a in pixels(image)]
        )
    from .intelligence import alpha_coverage

    image, antialias_modelled = alpha_coverage(image)
    full_alpha = bool(sum(image.getchannel("A").histogram()[1:255]))
    if (
        options.layering in {"mosaic", "smooth"} or full_alpha
    ) and options.preset != "centerline":
        from .mosaic import trace_mosaic

        if options.preset == "photo" and not full_alpha:
            quantized = rgb.quantize(colors=options.colors).convert("RGBA")
            quantized.putalpha(image.getchannel("A"))
        else:
            quantized = image
        root = trace_mosaic(quantized, tolerance=0.5)
        if options.layering == "smooth":
            from .shared import smooth_shared

            smooth_shared(root, tolerance=0.7, image=fitting_reference)
    elif options.preset == "centerline":
        from .enhance import centerlines

        root = centerlines(rgb, options.threshold, options.speckle)
    else:
        from .engine import native_trace

        root = native_trace(image, options, shared=options.layering == "native")
    root.set("viewBox", f"0 0 {image.width} {image.height}")
    root.set("role", "img")
    reconstructed = 0
    fitted_gradients = 0
    if (
        options.geometry
        and options.preset != "centerline"
        and options.layering not in {"mosaic", "smooth", "native"}
    ):
        from .enhance import primitives

        reconstructed = primitives(root)
    if options.geometry and options.layering == "native" and not full_alpha:
        from .engine import regularize_shared

        reconstructed = regularize_shared(
            root, opaque=image.getchannel("A").getextrema() == (255, 255)
        )
    if options.gradients and options.preset != "centerline":
        from .enhance import gradients
        from .gradientfit import whole_linear_region

        whole = whole_linear_region(fitting_reference, options)
        if whole:
            root, fitted_gradients = whole
            root.set("viewBox", f"0 0 {image.width} {image.height}")
            root.set("role", "img")
        else:
            fitted_gradients = gradients(root, fitting_reference)
    normalized_repeats = 0
    if options.normalize_repeats and options.preset != "centerline":
        from .repetition import normalize_repeats

        normalized_repeats = normalize_repeats(root)
    if (
        sum(alpha.histogram()[1:255])
        and not full_alpha
        and options.preset != "centerline"
    ):
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
        "warnings": warnings,
        "analysis": analysis,
        "background": removed,
        "background_preview": background_preview,
        "symmetry": detected_symmetry,
        "repeats": normalized_repeats,
        "full_alpha": full_alpha,
        "antialias_modelled": antialias_modelled,
        "subpixel_pixels": subpixel_pixels,
        "preview": "data:image/png;base64,"
        + base64.b64encode(preview.getvalue()).decode(),
    }


def export(svg: str, fmt: str, options=None) -> bytes:
    from .exporters import export_document

    return export_document(svg, fmt, options)
