"""Desktop acceptance probe. Run in disposable CI desktops, not user sessions."""

import platform
import subprocess

from tracegarden.desktop import copy_vector

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><path d="M2 2H30V30H2Z" fill="#ff0000"/></svg>'
result = copy_vector(SVG)
system = platform.system()
if system == "Windows":
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("user32")
    kernel = ctypes.WinDLL("kernel32")
    api.GetClipboardData.argtypes = [wintypes.UINT]
    api.GetClipboardData.restype = wintypes.HANDLE
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    assert api.OpenClipboard(None)
    try:
        handle = api.GetClipboardData(api.RegisterClipboardFormatW("image/svg+xml"))
        pointer = kernel.GlobalLock(handle)
        try:
            text = ctypes.string_at(pointer).decode()
            assert "<path" in text and "#ff0000" in text
        finally:
            kernel.GlobalUnlock(handle)
        assert api.IsClipboardFormatAvailable(15)  # Explorer file paste
        assert api.IsClipboardFormatAvailable(8)  # Bitmap fallback
        assert api.IsClipboardFormatAvailable(
            api.RegisterClipboardFormatW("Portable Document Format")
        )
        metafile = api.GetClipboardData(14)
        assert metafile
        gdi = ctypes.WinDLL("gdi32")
        gdi.GetEnhMetaFileBits.argtypes = [
            wintypes.HANDLE,
            wintypes.UINT,
            ctypes.c_void_p,
        ]
        size = gdi.GetEnhMetaFileBits(metafile, 0, None)
        buffer = ctypes.create_string_buffer(size)
        assert gdi.GetEnhMetaFileBits(metafile, size, buffer) == size
        assert buffer.raw[40:44] == b" EMF"
    finally:
        api.CloseClipboard()
elif system == "Darwin":
    # pbpaste independently reads the plaintext fallback from the same pasteboard.
    assert "<path" in subprocess.check_output(["pbpaste"]).decode()
    assert "PDF" in result["formats"]
    pdf_descriptor = subprocess.check_output(
        ["osascript", "-e", "the clipboard as «class PDF »"]
    ).decode()
    assert "25504446" in pdf_descriptor.upper()
else:
    text = subprocess.check_output(
        ["xclip", "-selection", "clipboard", "-t", "image/svg+xml", "-o"]
    ).decode()
    assert "<path" in text and "#ff0000" in text
print("Desktop clipboard round-trip passed:", result["formats"])
