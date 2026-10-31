"""Windows vector metafile interoperability for opaque solid-color artwork."""

from .svgdoc import NS, absolute_path, validate_svg


def create_metafile(svg):
    import ctypes
    from ctypes import wintypes

    from .exporters import colors, commands

    root = validate_svg(svg)
    paths = root.findall(NS + "path")
    if any(
        float(p.get("opacity", "1")) < 1
        or p.get("fill", "none").startswith("url(")
        or p.get("stroke", "none").startswith("url(")
        for p in paths
    ):
        return None  # PDF/SVG retain transparency and gradients without flattening.
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    pointer = ctypes.c_void_p
    declarations = {
        "CreateEnhMetaFileW": (
            [
                wintypes.HDC,
                wintypes.LPCWSTR,
                ctypes.POINTER(wintypes.RECT),
                wintypes.LPCWSTR,
            ],
            wintypes.HDC,
        ),
        "CloseEnhMetaFile": ([wintypes.HDC], wintypes.HANDLE),
        "DeleteEnhMetaFile": ([wintypes.HANDLE], wintypes.BOOL),
        "CreateSolidBrush": ([wintypes.DWORD], wintypes.HBRUSH),
        "CreatePen": ([ctypes.c_int, ctypes.c_int, wintypes.DWORD], wintypes.HANDLE),
        "SelectObject": ([wintypes.HDC, wintypes.HANDLE], wintypes.HANDLE),
        "GetStockObject": ([ctypes.c_int], wintypes.HANDLE),
        "DeleteObject": ([wintypes.HANDLE], wintypes.BOOL),
        "MoveToEx": (
            [wintypes.HDC, ctypes.c_int, ctypes.c_int, pointer],
            wintypes.BOOL,
        ),
        "LineTo": ([wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.BOOL),
        "PolyBezierTo": (
            [wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.DWORD],
            wintypes.BOOL,
        ),
        "SetWindowExtEx": (
            [wintypes.HDC, ctypes.c_int, ctypes.c_int, pointer],
            wintypes.BOOL,
        ),
        "SetViewportExtEx": (
            [wintypes.HDC, ctypes.c_int, ctypes.c_int, pointer],
            wintypes.BOOL,
        ),
    }
    for name, (args, result) in declarations.items():
        getattr(gdi, name).argtypes = args
        getattr(gdi, name).restype = result
    for name in [
        "BeginPath",
        "EndPath",
        "CloseFigure",
        "FillPath",
        "StrokePath",
        "StrokeAndFillPath",
    ]:
        getattr(gdi, name).argtypes = [wintypes.HDC]
        getattr(gdi, name).restype = wintypes.BOOL
    for name in ["SetMapMode", "SetPolyFillMode"]:
        getattr(gdi, name).argtypes = [wintypes.HDC, ctypes.c_int]
    width, height = float(root.get("width")), float(root.get("height"))
    frame = wintypes.RECT(0, 0, round(width * 2540 / 96), round(height * 2540 / 96))
    dc = gdi.CreateEnhMetaFileW(
        None, None, ctypes.byref(frame), "TraceGarden\0Vector artwork\0\0"
    )
    if not dc:
        raise OSError("Could not create the vector clipboard metafile.")
    handle = None
    try:
        gdi.SetMapMode(dc, 8)
        gdi.SetWindowExtEx(dc, round(width * 100), round(height * 100), None)
        gdi.SetViewportExtEx(dc, round(width), round(height), None)

        def colorref(value):
            r, g, b = [round(v * 255) for v in colors(value)]
            return r | (g << 8) | (b << 16)

        for el in paths:
            fill, stroke = el.get("fill", "black"), el.get("stroke", "none")
            brush = (
                gdi.CreateSolidBrush(colorref(fill))
                if fill != "none"
                else gdi.GetStockObject(5)
            )
            pen = (
                gdi.CreatePen(
                    0,
                    max(1, round(float(el.get("stroke-width", "1")) * 100)),
                    colorref(stroke),
                )
                if stroke != "none"
                else gdi.GetStockObject(8)
            )
            previous_brush = gdi.SelectObject(dc, brush)
            previous_pen = gdi.SelectObject(dc, pen)
            try:
                gdi.SetPolyFillMode(dc, 1 if el.get("fill-rule") == "evenodd" else 2)
                gdi.BeginPath(dc)
                for command, values in commands(absolute_path(el)):
                    coords = [round(v * 100) for v in values]
                    if command == "moveTo":
                        gdi.MoveToEx(dc, *coords, None)
                    elif command == "lineTo":
                        gdi.LineTo(dc, *coords)
                    elif command == "curveTo":
                        points = (wintypes.POINT * 3)(
                            *[wintypes.POINT(*coords[i : i + 2]) for i in [0, 2, 4]]
                        )
                        gdi.PolyBezierTo(dc, points, 3)
                    else:
                        gdi.CloseFigure(dc)
                gdi.EndPath(dc)
                if fill != "none" and stroke != "none":
                    gdi.StrokeAndFillPath(dc)
                elif fill != "none":
                    gdi.FillPath(dc)
                elif stroke != "none":
                    gdi.StrokePath(dc)
            finally:
                gdi.SelectObject(dc, previous_brush)
                gdi.SelectObject(dc, previous_pen)
                if fill != "none":
                    gdi.DeleteObject(brush)
                if stroke != "none":
                    gdi.DeleteObject(pen)
        handle = gdi.CloseEnhMetaFile(dc)
        dc = None
        if not handle:
            raise OSError("Could not finish the vector clipboard metafile.")
        return handle
    finally:
        if dc:
            abandoned = gdi.CloseEnhMetaFile(dc)
            if abandoned:
                gdi.DeleteEnhMetaFile(abandoned)
