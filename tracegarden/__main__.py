import argparse
import threading
import webbrowser
import uvicorn
import json
from pathlib import Path


def main():
    import sys
    import tempfile

    if sys.stdout is None or sys.stderr is None:
        log_dir = Path(tempfile.gettempdir()) / "TraceGarden"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "application.log"
        if log_file.exists() and log_file.stat().st_size > 5 * 1024**2:
            log_file.write_text("")
        stream = log_file.open("a", encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
    parser = argparse.ArgumentParser(description="Open your private vector studio")
    parser.add_argument("--port", type=int, default=8741)
    parser.add_argument("--no-browser", action="store_true")
    sub = parser.add_subparsers(dest="command")
    batch = sub.add_parser(
        "convert", help="Convert one or more images without opening the studio"
    )
    batch.add_argument("images", nargs="+", type=Path)
    batch.add_argument("--quality", choices=["fast", "high"], default=None)
    batch.add_argument("--output", type=Path, default=Path("vectors"))
    batch.add_argument(
        "--format",
        choices=["svg", "pdf", "eps", "ai", "dxf", "png", "jpg", "gif", "bmp", "tiff"],
        default="svg",
    )
    batch.add_argument(
        "--options", default="{}", help="Tracing options as a JSON object"
    )
    args = parser.parse_args()
    if args.command == "convert":
        from .core import trace, Options, export

        try:
            options = Options.model_validate_json(args.options)
            if args.quality is not None:
                options = options.model_copy(update={"quality": args.quality})
        except ValueError as exc:
            parser.error(str(exc))
        args.output.mkdir(parents=True, exist_ok=True)
        failed = False
        for i, path in enumerate(args.images):
            try:
                result = trace(path.read_bytes(), options)
                target = args.output / f"{i + 1:02d}-{path.stem}.{args.format}"
                target.write_bytes(export(result["svg"], args.format))
                print(
                    json.dumps(
                        {
                            "input": str(path),
                            "output": str(target),
                            "paths": result["paths"],
                            "seconds": result["seconds"],
                            "quality": result["quality"],
                            "warnings": result["warnings"],
                        }
                    )
                )
            except (OSError, ValueError) as exc:
                print(f"{path}: {exc}")
                failed = True
        if failed:
            raise SystemExit(1)
        return
    if not args.no_browser:
        threading.Timer(
            1.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")
        ).start()
    from .app import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port))
    app.state.server = server
    server.run()


if __name__ == "__main__":
    main()
