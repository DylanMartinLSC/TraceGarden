"""Offscreen Windows GDI acceptance; never changes the user's clipboard."""

import platform
import struct
import pytest

pytestmark = pytest.mark.skipif(
    platform.system() != "Windows", reason="Windows GDI vector format"
)


def test_metafile_replays_as_red_vector_shape_on_white_background():
    import ctypes
    from ctypes import wintypes
    from tracegarden.emf import create_metafile

    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><path d="M8 8H56V56H8Z" fill="#ff0000"/></svg>'
    handle = create_metafile(svg)
    assert handle
    gdi = ctypes.WinDLL("gdi32")
    declarations = {
        "CreateCompatibleDC": ([wintypes.HDC], wintypes.HDC),
        "CreateDIBSection": (
            [
                wintypes.HDC,
                ctypes.c_void_p,
                wintypes.UINT,
                ctypes.POINTER(ctypes.c_void_p),
                wintypes.HANDLE,
                wintypes.DWORD,
            ],
            wintypes.HANDLE,
        ),
        "SelectObject": ([wintypes.HDC, wintypes.HANDLE], wintypes.HANDLE),
        "PatBlt": (
            [
                wintypes.HDC,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.DWORD,
            ],
            wintypes.BOOL,
        ),
        "PlayEnhMetaFile": (
            [wintypes.HDC, wintypes.HANDLE, ctypes.POINTER(wintypes.RECT)],
            wintypes.BOOL,
        ),
        "GetPixel": ([wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.DWORD),
        "DeleteObject": ([wintypes.HANDLE], wintypes.BOOL),
        "DeleteDC": ([wintypes.HDC], wintypes.BOOL),
        "DeleteEnhMetaFile": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (args, result) in declarations.items():
        getattr(gdi, name).argtypes = args
        getattr(gdi, name).restype = result
    dc = gdi.CreateCompatibleDC(None)
    header = ctypes.create_string_buffer(
        struct.pack("<IiiHHIIiiII", 40, 64, -64, 1, 32, 0, 64 * 64 * 4, 0, 0, 0, 0)
    )
    bits = ctypes.c_void_p()
    bitmap = gdi.CreateDIBSection(dc, header, 0, ctypes.byref(bits), None, 0)
    assert dc and bitmap
    previous = gdi.SelectObject(dc, bitmap)
    try:
        assert gdi.PatBlt(dc, 0, 0, 64, 64, 0x00FF0062)
        assert gdi.PlayEnhMetaFile(
            dc, handle, ctypes.byref(wintypes.RECT(0, 0, 64, 64))
        )
        assert gdi.GetPixel(dc, 32, 32) == 0x0000FF
        assert gdi.GetPixel(dc, 2, 2) == 0xFFFFFF
    finally:
        gdi.SelectObject(dc, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)
        gdi.DeleteEnhMetaFile(handle)
