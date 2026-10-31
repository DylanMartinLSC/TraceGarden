from xml.etree.ElementTree import Element
from tracegarden.modeling import shape_path
from tracegarden.repetition import repeated, apply_repeats
from tracegarden.svgdoc import absolute_path


def test_rotated_repeated_star_recognition():
    paths = [
        Element("path", {"d": shape_path("star", x, y, w, w, angle, 0, 5, 0.45).d()})
        for x, y, w, angle in [(50, 50, 60, 0), (150, 50, 40, 25), (80, 150, 80, 60)]
    ]
    paths.append(Element("path", {"d": shape_path("rectangle", 150, 150, 40, 70).d()}))
    matches = repeated(paths, 0)
    assert {m["index"] for m in matches} == {0, 1, 2}
    apply_repeats(paths, [0, 1, 2])
    assert all(absolute_path(p).isclosed() for p in paths)
