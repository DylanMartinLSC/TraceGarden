"""Spawned CPU benchmark: wall time, sampled peak process-tree RSS and image MAE."""

import io
import json
import multiprocessing as mp
import platform
import statistics
import time
from pathlib import Path
import numpy as np
import psutil
from PIL import Image, ImageDraw


def fixture(name, size):
    image = Image.new("RGB", (size, size), "#f4dfaa")
    d = ImageDraw.Draw(image)
    if name in {"logo", "mosaic"}:
        d.ellipse((size // 5, size // 5, size * 4 // 5, size * 4 // 5), fill="#315d45")
        d.rectangle(
            (size // 3, size // 3, size * 2 // 3, size * 2 // 3), fill="#d98743"
        )
    elif name == "gradient":
        pixels = np.empty((size, size, 3), np.uint8)
        pixels[:, :, 0] = np.linspace(30, 220, size).astype(np.uint8)[None, :]
        pixels[:, :, 1] = 100
        pixels[:, :, 2] = 180
        image = Image.fromarray(pixels)
    elif name == "centerline":
        for y in range(size // 8, size, size // 8):
            d.line(
                (size // 8, y, size * 7 // 8, y),
                fill="black",
                width=max(3, size // 100),
            )
    else:
        rng = np.random.default_rng(42)
        pixels = rng.integers(0, 256, (size // 8, size // 8, 3), dtype=np.uint8)
        image = Image.fromarray(pixels).resize((size, size), Image.Resampling.BICUBIC)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def worker(connection, data, config):
    from tracegarden.core import trace, Options, export

    started = time.perf_counter()
    result = trace(data, Options(**config))
    seconds = time.perf_counter() - started
    original = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=float)
    rendered = Image.open(io.BytesIO(export(result["svg"], "png"))).convert("RGBA")
    white = Image.new("RGB", rendered.size, "white")
    white.paste(rendered, mask=rendered.getchannel("A"))
    mae = float(np.abs(original - np.asarray(white, dtype=float)).mean() / 255)
    connection.send(
        {
            "seconds": round(seconds, 4),
            "mae": round(mae, 5),
            "paths": result["paths"],
            "svg_bytes": len(result["svg"].encode()),
            "geometry": result["geometry"],
            "gradients": result["gradients"],
        }
    )
    connection.close()


def main():
    rows = []
    for name in ["logo", "gradient", "mosaic", "centerline", "textured"]:
        for size in [512, 1024]:
            config = {
                "geometry": name == "logo",
                "gradients": name == "gradient",
                "preset": "photo"
                if name in {"gradient", "textured"}
                else "centerline"
                if name == "centerline"
                else "logo",
                "layering": "mosaic" if name == "mosaic" else "stacked",
                "colors": 16,
                "precision": 3 if name == "gradient" else 6,
            }
            results = []
            peaks = []
            wall = []
            data = fixture(name, size)
            for _ in range(3):
                parent, child = mp.get_context("spawn").Pipe(duplex=False)
                process = mp.get_context("spawn").Process(
                    target=worker, args=(child, data, config)
                )
                started = time.perf_counter()
                process.start()
                child.close()
                peak = 0
                try:
                    while not parent.poll():
                        if not process.is_alive():
                            raise RuntimeError("Benchmark worker stopped")
                        if time.perf_counter() - started > 120:
                            raise RuntimeError("Benchmark timed out")
                        try:
                            peak = max(
                                peak, psutil.Process(process.pid).memory_info().rss
                            )
                        except psutil.NoSuchProcess:
                            pass
                        time.sleep(0.01)
                    results.append(parent.recv())
                    wall.append(time.perf_counter() - started)
                    peaks.append(peak / 1024**2)
                finally:
                    process.join(3)
                    if process.is_alive():
                        process.terminate()
                        process.join()
                    parent.close()
            row = {
                "case": name,
                "size": size,
                "runs": 3,
                "trace_median_s": round(
                    statistics.median(r["seconds"] for r in results), 4
                ),
                "process_wall_median_s": round(statistics.median(wall), 4),
                "peak_rss_mib": round(max(peaks), 1),
                "mae": results[-1]["mae"],
                "paths": results[-1]["paths"],
                "svg_bytes": results[-1]["svg_bytes"],
                "config": config,
            }
            rows.append(row)
            print(row, flush=True)
    report = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "notes": "Three fresh spawned workers per case. Trace time excludes imports/startup; process wall includes startup and quality rendering. Peak RSS sampled every 10ms includes imports, tracing and quality rendering, may miss brief peaks. MAE normalized RGB vs white-composited render; centerline is intentionally a one-pixel skeleton, so MAE is not directly comparable. Seeded synthetic textures are not photographs. No commercial comparison.",
        "results": rows,
    }
    Path("benchmarks/studio-results.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    mp.freeze_support()
    main()
