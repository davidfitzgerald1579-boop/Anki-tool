from PyQt6.QtGui import QColor

from snip_occlusion.color_utils import local_background, majority_color
from tests.slide_fixture import BG, CALLOUT, make_slide


def close(a: QColor, b: QColor, tol: int = 12) -> bool:
    return (
        abs(a.red() - b.red()) <= tol
        and abs(a.green() - b.green()) <= tol
        and abs(a.blue() - b.blue()) <= tol
    )


def test_majority_color_is_slide_background(qapp):
    img = make_slide()
    assert close(majority_color(img), QColor(BG))


def test_local_background_on_callout_box(qapp):
    img = make_slide()
    # text inside the pink callout (y 340..410, x 40..420): local sampling
    # should return the callout colour, not the slide background
    c = local_background(img, 60, 355, 200, 25)
    assert close(c, QColor(CALLOUT))


def test_local_background_on_main_body(qapp):
    img = make_slide()
    c = local_background(img, 60, 115, 300, 20)
    assert close(c, QColor(BG))
