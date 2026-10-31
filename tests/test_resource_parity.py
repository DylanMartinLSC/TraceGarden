import io
from PIL import Image
from tracegarden.core import Options, trace


def test_large_jpeg_uses_draft_decode_and_preserves_source_dimensions():
    source = Image.new("RGB", (4200, 4100), "#226644")
    output = io.BytesIO()
    source.save(output, format="JPEG")
    result = trace(output.getvalue(), Options(max_size=256))
    assert result["original"] == (4200, 4100)
    assert max(result["width"], result["height"]) == 256


def test_explicit_processing_memory_budget():
    source = Image.new("RGB", (1000, 1000), "red")
    output = io.BytesIO()
    source.save(output, format="PNG")
    result = trace(output.getvalue(), Options(max_size=16384, memory_limit_mib=128))
    assert max(result["width"], result["height"]) < 900
    assert result["warnings"]
