"""Independent-renderer reconstruction corpus, generated from known vector truth.

All generated artwork is dedicated to CC0 by TraceGarden contributors. This is
not a commercial-engine comparison and is not used for machine-learning training.
"""

import io
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image
import resvg_py
from scipy.ndimage import distance_transform_edt, binary_erosion
from tracegarden.core import trace, Options
from tracegarden.svgdoc import NS, validate_svg, absolute_path


def fixtures():
    for size in [64, 128, 256]:
        bodies = {
            "circle": '<circle cx="64.3" cy="63.8" r="39.4" fill="#124f83"/>',
            "ellipse": '<ellipse cx="64" cy="64" rx="43" ry="23" transform="rotate(31 64 64)" fill="#e76a40"/>',
            "rounded-rectangle": '<rect x="20" y="34" width="88" height="60" rx="11" transform="rotate(23 64 64)" fill="#315d45"/>',
            "star": '<path d="M64 12L76 45L111 46L84 68L93 104L64 83L35 104L44 68L17 46L52 45Z" fill="#7d369a"/>',
            "thin-feature": '<path d="M10 64H118 M64 10V118" fill="none" stroke="#124f83" stroke-width="1.2"/>',
            "nested-holes": '<path d="M12 12H116V116H12Z M32 32H96V96H32Z M48 48H80V80H48Z" fill="#315d45" fill-rule="evenodd"/>',
            "adjacent-regions": '<path d="M0 0H128V128H0Z" fill="#f1d8a2"/><path d="M0 0H64C112 24 16 96 64 128H0Z" fill="#315d45"/>',
            "opacity-bands": "".join(
                f'<rect x="{i * 8}" width="8" height="128" fill="#ac3655" opacity="{(i + 1) / 16}"/>'
                for i in range(16)
            ),
            "faint-corner": '<path d="M0 0H128V128H0Z" fill="#eeeeee"/><path d="M24 24H104V104H24Z" fill="#dddddd"/>',
            "text-outlines": '<rect width="128" height="128" fill="white"/><path d="M12 28H42V36H22V52H39V60H22V88H12Z M54 28H85V36H64V52H82V60H64V80H85V88H54Z M94 28H104V80H119V88H94Z" fill="#202020"/>',
            "scan-lines": '<rect width="128" height="128" fill="#fffdf4"/><path d="M12 16H115M12 30H92M12 44H110M12 58H80M12 72H117M12 86H90M12 100H108" stroke="#343434" stroke-width="2"/><path d="M15 118L28 109L39 115L51 105L63 117L78 110" fill="none" stroke="#555555" stroke-width="1.2"/>',
            "gradient": '<defs><linearGradient id="g"><stop stop-color="#163d7a"/><stop offset="1" stop-color="#e87540"/></linearGradient></defs><rect x="12" y="12" width="104" height="104" rx="12" fill="url(#g)"/>',
        }
        for name, body in bodies.items():
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 128 128">{body}</svg>'
            yield name, size, svg


def render(svg):
    return (
        np.asarray(
            Image.open(
                io.BytesIO(
                    resvg_py.svg_to_bytes(svg_string=svg, skip_system_fonts=True)
                )
            ).convert("RGBA"),
            dtype=float,
        )
        / 255
    )


def metrics(gold, actual):
    # Compare premultiplied color and alpha: transparent RGB is not visible error.
    g = gold.copy()
    a = actual.copy()
    g[:, :, :3] *= g[:, :, 3:]
    a[:, :, :3] *= a[:, :, 3:]
    mae = float(np.abs(g - a).mean())

    def boundary(im):
        mask = np.linalg.norm(im[:, :, :3], axis=2) + im[:, :, 3] > 0.05
        # Include visible interior color changes as well as the silhouette.
        edges = mask ^ binary_erosion(mask)
        edges[1:] |= np.linalg.norm(im[1:] - im[:-1], axis=2) > 0.025
        edges[:, 1:] |= np.linalg.norm(im[:, 1:] - im[:, :-1], axis=2) > 0.025
        return edges

    x, y = boundary(g), boundary(a)
    distance = (
        0
        if not x.any() and not y.any()
        else float(np.hypot(*x.shape))
        if not x.any() or not y.any()
        else float(
            (
                distance_transform_edt(~x)[y].mean()
                + distance_transform_edt(~y)[x].mean()
            )
            / 2
        )
    )
    return round(mae, 6), round(distance, 4)


def main():
    root = Path("work/parity-corpus")
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, size, source in fixtures():
        png = resvg_py.svg_to_bytes(svg_string=source, skip_system_fonts=True)
        options = Options(
            preset="logo",
            colors=32 if name == "gradient" else 16 if name == "thin-feature" else 4,
            speckle=0,
            layering="smooth",
            max_size=1024,
            geometry=True,
            gradients=name == "gradient",
        )
        started = time.perf_counter()
        result = trace(png, options)
        seconds = time.perf_counter() - started
        mae, boundary = metrics(render(source), render(result["svg"]))
        parsed = validate_svg(result["svg"])
        segments = sum(len(absolute_path(p)) for p in parsed.findall(NS + "path"))
        row = {
            "case": name,
            "size": size,
            "mae_rgba_premultiplied": mae,
            "boundary_mean_px": boundary,
            "paths": result["paths"],
            "segments": segments,
            "svg_bytes": len(result["svg"].encode()),
            "seconds": round(seconds, 4),
        }
        rows.append(row)
        print(row, flush=True)
        (root / f"{name}-{size}-source.svg").write_text(source)
        (root / f"{name}-{size}-output.svg").write_text(result["svg"])
    report = {
        "license": "CC0-1.0 (generated fixtures)",
        "renderer": "resvg_py " + resvg_py.__version__,
        "notes": "Known-vector truth rendered by an independent Rust SVG engine, traced from raster, and compared as premultiplied RGBA and symmetric mean boundary distance. Small synthetic acceptance corpus, not a paid-engine comparison or a general quality guarantee.",
        "results": rows,
    }
    Path("benchmarks/parity-results.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
