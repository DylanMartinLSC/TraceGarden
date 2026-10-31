from xml.etree.ElementTree import Element
from tracegarden.modeling import shape_path
from tracegarden.repetition import repeated, apply_repeats
from tracegarden.svgdoc import absolute_path


def test_automatic_repeat_families_preserve_shared_holes():
    from tracegarden.repetition import normalize_repeats
    from tracegarden.svgdoc import NS, polygon
    from shapely.ops import unary_union
    from xml.etree.ElementTree import SubElement

    root = Element(NS + "svg", {"width": "240", "height": "180"})
    stars = [
        shape_path("star", x, y, size, size, angle, 0, 5, 0.45)
        for x, y, size, angle in [(55, 55, 60, 0), (155, 55, 40, 25), (90, 130, 50, 60)]
    ]
    background = "M0 0H240V180H0Z " + " ".join(p.reversed().d() + " Z" for p in stars)
    SubElement(root, NS + "path", {"d": background, "fill": "white"})
    for path in stars:
        SubElement(root, NS + "path", {"d": path.d() + " Z", "fill": "red"})
    assert normalize_repeats(root) == 2
    shapes = [polygon(p) for p in root.findall(NS + "path")]
    assert sum(s.area for s in shapes) - unary_union(shapes).area < 1e-5
    assert abs(unary_union(shapes).area - 240 * 180) < 1e-5


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
