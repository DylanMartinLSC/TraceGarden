import argparse
import threading
import webbrowser
import uvicorn
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Open your private vector studio")
    parser.add_argument("--port", type=int, default=8741)
    parser.add_argument("--no-browser", action="store_true")
    sub = parser.add_subparsers(dest="command")
    batch = sub.add_parser(
        "convert", help="Convert one or more images without opening the studio"
    )
    batch.add_argument("images", nargs="+", type=Path)
    batch.add_argument("--output", type=Path, default=Path("vectors"))
    batch.add_argument(
        "--format", choices=["svg", "pdf", "eps", "ai", "dxf", "png"], default="svg"
    )
    batch.add_argument(
        "--options", default="{}", help="Tracing options as a JSON object"
    )
    args = parser.parse_args()
    if args.command == "convert":
        from .core import trace, Options, export

        try:
            options = Options.model_validate_json(args.options)
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
    uvicorn.run("tracegarden.app:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
