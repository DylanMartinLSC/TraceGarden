"""Explicit desktop clipboard export; no native writes occur during conversion."""

from __future__ import annotations

import io
import platform
import shutil
import struct
import subprocess
import tempfile
import time
from pathlib import Path

from .svgdoc import serialize, validate_svg


def _windows_clipboard(svg, png=None):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalFree.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    formats = [
        (13, (svg + "\0").encode("utf-16le")),
        (user32.RegisterClipboardFormatW("image/svg+xml"), svg.encode() + b"\0"),
    ]
    # A real CF_HDROP file lets Explorer and desktop design apps paste artwork.
    folder = Path(tempfile.gettempdir()) / "TraceGarden-clipboard"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.svg"):
        if time.time() - old.stat().st_mtime > 86400:
            old.unlink(missing_ok=True)
    target = folder / f"artwork-{time.time_ns()}.svg"
    target.write_text(svg, encoding="utf-8")
    dropfiles = struct.pack("<IiiII", 20, 0, 0, 0, 1) + (str(target) + "\0\0").encode(
        "utf-16le"
    )
    formats.append((15, dropfiles))
    if png:
        from PIL import Image

        source = Image.open(io.BytesIO(png)).convert("RGBA")
        matte = Image.new("RGB", source.size, "white")
        matte.paste(source, mask=source.getchannel("A"))
        bmp = io.BytesIO()
        matte.save(bmp, format="BMP")
        formats.append((8, bmp.getvalue()[14:]))
    blocks = []
    try:
        for fmt, data in formats:
            handle = kernel.GlobalAlloc(0x0002, len(data))
            if not handle:
                raise OSError("Could not allocate clipboard memory.")
            pointer = kernel.GlobalLock(handle)
            if not pointer:
                kernel.GlobalFree(handle)
                raise OSError("Could not lock clipboard memory.")
            ctypes.memmove(pointer, data, len(data))
            kernel.GlobalUnlock(handle)
            blocks.append([fmt, handle])
        window = user32.CreateWindowExW(
            0, "STATIC", "TraceGarden clipboard", 0, 0, 0, 0, 0, None, None, None, None
        )
        if not window:
            raise OSError("Could not create a clipboard owner window.")
        if not user32.OpenClipboard(window):
            user32.DestroyWindow(window)
            raise OSError("The clipboard is busy. Try again.")
        try:
            if not user32.EmptyClipboard():
                raise OSError("Could not clear the clipboard.")
            for block in blocks:
                if not user32.SetClipboardData(*block):
                    raise OSError("Could not transfer clipboard data.")
                block[1] = (
                    None  # Windows owns the allocation after successful transfer.
                )
        finally:
            user32.CloseClipboard()
            user32.DestroyWindow(window)
    finally:
        for _, handle in blocks:
            if handle:
                kernel.GlobalFree(handle)
    return {
        "formats": ["SVG", "Unicode text", "file drop"] + (["bitmap"] if png else []),
        "temporary_file": str(target),
    }


def copy_vector(svg):
    clean = serialize(validate_svg(svg))
    system = platform.system()
    if system == "Windows":
        from .exporters import export_document

        return _windows_clipboard(clean, export_document(clean, "png"))
    if system == "Darwin":
        return _mac_clipboard(clean)
    if shutil.which("wl-copy"):
        subprocess.run(
            ["wl-copy", "--type", "image/svg+xml"], input=clean.encode(), check=True
        )
        return {"formats": ["SVG"]}
    if shutil.which("xclip"):
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/svg+xml"],
            input=clean.encode(),
            check=True,
        )
        return {"formats": ["SVG"]}
    raise ValueError(
        "No desktop clipboard provider is installed. Use Copy SVG text or download the file."
    )


def _mac_clipboard(svg):
    """Use the system pasteboard, including the public SVG vector type."""
    import ctypes

    ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value

    def send(receiver, selector, *args):
        call = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            *[ctypes.c_void_p for _ in args],
        )(address)
        return call(receiver, objc.sel_registerName(selector.encode()), *args)

    def string(value):
        data = ctypes.c_char_p(value.encode("utf-8"))
        return send(
            objc.objc_getClass(b"NSString"),
            "stringWithUTF8String:",
            ctypes.cast(data, ctypes.c_void_p),
        )

    pool = send(objc.objc_getClass(b"NSAutoreleasePool"), "new")
    try:
        board = send(objc.objc_getClass(b"NSPasteboard"), "generalPasteboard")
        send(board, "clearContents")
        for mime in ["public.svg-image", "image/svg+xml", "public.utf8-plain-text"]:
            if not send(board, "setString:forType:", string(svg), string(mime)):
                raise OSError("Could not write the macOS pasteboard.")
    finally:
        send(pool, "drain")
    return {"formats": ["SVG", "Unicode text"]}
