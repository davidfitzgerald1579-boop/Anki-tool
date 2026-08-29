"""Interaction tests for the editor canvas (headless, offscreen Qt).

Mouse gestures are simulated by feeding QMouseEvents straight into the
canvas handlers, using view coordinates mapped from scene coordinates.
"""

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from snip_occlusion.consts import (
    DEFAULT_CONFIG,
    TOOL_ERASE,
    TOOL_RECT,
)
from snip_occlusion.editor_canvas import OcclusionCanvas
from snip_occlusion.shapes import Shape, target_groups
from tests.slide_fixture import BG, make_slide

NOMOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
LEFT = Qt.MouseButton.LeftButton


@pytest.fixture
def canvas(qapp):
    c = OcclusionCanvas(dict(DEFAULT_CONFIG))
    c.resize(900, 600)
    c.set_image(make_slide())
    c.show()
    qapp.processEvents()
    return c


def ev(canvas, etype, scene_x, scene_y, mods=NOMOD, button=LEFT):
    vp = QPointF(canvas.mapFromScene(QPointF(scene_x, scene_y)))
    if etype == QEvent.Type.MouseButtonRelease:
        buttons = Qt.MouseButton.NoButton
    else:
        buttons = LEFT
    return QMouseEvent(etype, vp, vp, button, buttons, mods)


def press(canvas, x, y, mods=NOMOD):
    canvas.mousePressEvent(ev(canvas, QEvent.Type.MouseButtonPress, x, y, mods))


def move(canvas, x, y, mods=NOMOD):
    canvas.mouseMoveEvent(ev(canvas, QEvent.Type.MouseMove, x, y, mods))


def release(canvas, x, y, mods=NOMOD):
    canvas.mouseReleaseEvent(
        ev(canvas, QEvent.Type.MouseButtonRelease, x, y, mods)
    )


def drag(canvas, x0, y0, x1, y1, mods=NOMOD):
    press(canvas, x0, y0, mods)
    move(canvas, (x0 + x1) / 2, (y0 + y1) / 2, mods)
    move(canvas, x1, y1, mods)
    release(canvas, x1, y1, mods)


def add_shape(canvas, x, y, w=60, h=30, group=None):
    s = Shape(kind="rect", x=x, y=y, w=w, h=h, group=group)
    canvas.shapes.append(s)
    return s


def test_draw_rect_via_mouse(canvas):
    canvas.set_tool(TOOL_RECT)
    drag(canvas, 100, 100, 220, 150)
    assert len(canvas.shapes) == 1
    s = canvas.shapes[0]
    assert s.kind == "rect"
    assert abs(s.x - 100) < 2 and abs(s.y - 100) < 2
    assert abs(s.w - 120) < 3 and abs(s.h - 50) < 3
    assert canvas.selection == {s.id}


def test_tiny_accidental_draw_is_discarded(canvas):
    canvas.set_tool(TOOL_RECT)
    drag(canvas, 100, 100, 103, 102)
    assert canvas.shapes == []


def test_click_below_drag_threshold_does_not_move(canvas):
    s = add_shape(canvas, 100, 100)
    press(canvas, 110, 110)
    move(canvas, 112, 111)  # under the 5px threshold
    release(canvas, 112, 111)
    assert (s.x, s.y) == (100, 100)


def test_drag_past_threshold_moves(canvas):
    s = add_shape(canvas, 100, 100)
    press(canvas, 110, 110)
    move(canvas, 140, 130)
    release(canvas, 140, 130)
    assert abs(s.x - 130) <= 1.5 and abs(s.y - 120) <= 1.5


def test_shift_click_toggles_selection_and_never_moves(canvas):
    a = add_shape(canvas, 100, 100)
    b = add_shape(canvas, 300, 100)
    press(canvas, 110, 110, SHIFT)
    # even a large motion with shift held must not drag the shape
    move(canvas, 200, 200, SHIFT)
    release(canvas, 200, 200, SHIFT)
    assert (a.x, a.y) == (100, 100)
    assert canvas.selection == {a.id}
    press(canvas, 310, 110, SHIFT)
    release(canvas, 310, 110, SHIFT)
    assert canvas.selection == {a.id, b.id}
    # shift-click a selected shape to deselect it
    press(canvas, 110, 110, SHIFT)
    release(canvas, 110, 110, SHIFT)
    assert canvas.selection == {b.id}


def test_plain_drag_moves_only_pressed_shape_even_when_many_selected(canvas):
    a = add_shape(canvas, 100, 100)
    b = add_shape(canvas, 300, 100)
    c = add_shape(canvas, 100, 300)
    canvas.selection = {a.id, b.id, c.id}
    press(canvas, 310, 110)  # press on b
    move(canvas, 360, 160)
    release(canvas, 360, 160)
    assert abs(b.x - 350) <= 1.5 and abs(b.y - 150) <= 1.5
    assert (a.x, a.y) == (100, 100)
    assert (c.x, c.y) == (100, 300)


def test_ctrl_drag_moves_whole_selection(canvas):
    a = add_shape(canvas, 100, 100)
    b = add_shape(canvas, 300, 100)
    canvas.selection = {a.id, b.id}
    press(canvas, 310, 110, CTRL)
    move(canvas, 330, 130, CTRL)
    release(canvas, 330, 130, CTRL)
    assert abs(a.x - 120) <= 1.5 and abs(a.y - 120) <= 1.5
    assert abs(b.x - 320) <= 1.5 and abs(b.y - 120) <= 1.5


def test_group_skipping_middle_box(canvas):
    top = add_shape(canvas, 100, 50)
    middle = add_shape(canvas, 100, 150)
    bottom = add_shape(canvas, 100, 250)
    # shift-click top and bottom only
    press(canvas, 110, 60, SHIFT)
    release(canvas, 110, 60, SHIFT)
    press(canvas, 110, 260, SHIFT)
    release(canvas, 110, 260, SHIFT)
    assert canvas.selection == {top.id, bottom.id}
    assert canvas.group_selected()
    assert top.group is not None and top.group == bottom.group
    assert middle.group is None
    groups = target_groups(canvas.shapes)
    assert len(groups) == 2  # grouped pair + middle singleton


def test_clicking_group_member_selects_only_that_shape(canvas):
    a = add_shape(canvas, 100, 100, group="g1")
    b = add_shape(canvas, 300, 100, group="g1")
    press(canvas, 110, 110)
    release(canvas, 110, 110)
    assert canvas.selection == {a.id}
    # and moving it moves only it, despite the shared group
    press(canvas, 110, 110)
    move(canvas, 150, 140)
    release(canvas, 150, 140)
    assert abs(a.x - 140) <= 1.5 and abs(a.y - 130) <= 1.5
    assert (b.x, b.y) == (300, 100)


def test_rubber_band_selection(canvas):
    a = add_shape(canvas, 100, 100)
    b = add_shape(canvas, 300, 100)
    add_shape(canvas, 100, 400)
    drag(canvas, 80, 80, 400, 160)
    assert canvas.selection == {a.id, b.id}


def test_undo_redo_move(canvas):
    s = add_shape(canvas, 100, 100)
    press(canvas, 110, 110)
    move(canvas, 160, 150)
    release(canvas, 160, 150)
    moved = (s.x, s.y)
    canvas.undo()
    s2 = canvas.shape_by_id(s.id)
    assert (s2.x, s2.y) == (100, 100)
    canvas.redo()
    s3 = canvas.shape_by_id(s.id)
    assert (s3.x, s3.y) == moved


def test_escape_cancels_but_is_swallowed(canvas):
    add_shape(canvas, 100, 100)
    canvas.select_all()
    e = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NOMOD)
    canvas.keyPressEvent(e)
    assert e.isAccepted()
    assert canvas.selection == set()


def test_erase_shape_gets_majority_color_and_bakes(canvas):
    canvas.set_tool(TOOL_ERASE)
    drag(canvas, 40, 115, 500, 140)  # cover a text line
    assert len(canvas.shapes) == 1
    s = canvas.shapes[0]
    assert s.kind == "erase"
    fill = s.color.lower()
    # majority colour of the fixture slide is the cream background
    br, bg_, bb = int(BG[1:3], 16), int(BG[3:5], 16), int(BG[5:7], 16)
    fr, fg, fb = int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16)
    assert abs(fr - br) <= 12 and abs(fg - bg_) <= 12 and abs(fb - bb) <= 12
    baked = canvas.bake_erasures()
    c = baked.pixelColor(270, 127)  # centre of the erased line
    assert abs(c.red() - fr) <= 2 and abs(c.green() - fg) <= 2
    # erase shapes never become cards
    assert target_groups(canvas.shapes) == []


def test_move_is_clamped_to_image(canvas):
    s = add_shape(canvas, 10, 10, w=50, h=30)
    press(canvas, 20, 20)
    move(canvas, -300, -300)
    release(canvas, -300, -300)
    assert s.x == 0 and s.y == 0
