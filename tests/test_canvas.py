"""Interaction tests for the editor canvas (headless, offscreen Qt).

Mouse gestures are simulated by feeding QMouseEvents straight into the
canvas handlers, using view coordinates mapped from scene coordinates.
"""

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from snip_occlusion.consts import (
    DEFAULT_CONFIG,
    SNAP_WORD,
    TOOL_ERASE,
    TOOL_HIGHLIGHT,
    TOOL_PATCH,
    TOOL_RECT,
    TOOL_SELECT,
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
    baked = canvas.bake_image()
    c = baked.pixelColor(270, 127)  # centre of the erased line
    assert abs(c.red() - fr) <= 2 and abs(c.green() - fg) <= 2
    # erase shapes never become cards
    assert target_groups(canvas.shapes) == []


def test_patch_tool_cuts_moves_and_bakes_pixel_exact(canvas):
    # snip out a piece of the title text
    canvas.set_tool(TOOL_PATCH)
    drag(canvas, 100, 60, 300, 100)
    assert len(canvas.shapes) == 1
    p = canvas.shapes[0]
    assert p.kind == "patch"
    assert p.sx == p.x and p.sy == p.y  # starts on top of its source
    assert canvas.tool == TOOL_SELECT  # auto-switch so it can be dragged
    assert canvas.selection == {p.id}

    # remember what the source pixels look like
    src_x, src_y = int(p.sx) + 5, int(p.sy) + 5
    src_color = canvas.image.pixelColor(src_x, src_y)

    # drag it 200px down, then cover the original area
    press(canvas, p.x + 10, p.y + 10)
    move(canvas, p.x + 10, p.y + 210)
    release(canvas, p.x + 10, p.y + 210)
    assert abs(p.y - (p.sy + 200)) <= 1.5
    assert p.sx is not None and p.sy is not None  # source unchanged

    canvas.set_tool(TOOL_ERASE)
    drag(canvas, 90, 50, 320, 110)
    erase = [s for s in canvas.shapes if s.kind == "erase"][0]

    baked = canvas.bake_image()
    # the patch destination shows the original source pixels exactly
    moved = baked.pixelColor(int(p.x) + 5, int(p.y) + 5)
    assert moved.rgb() == src_color.rgb()
    # the original spot is covered by the erase fill, not the old pixels
    covered = baked.pixelColor(src_x, src_y)
    assert covered.name() == erase.color

    # patches never generate cards and cannot be grouped
    assert target_groups(canvas.shapes) == []
    canvas.selection = {p.id, erase.id}
    assert not canvas.group_selected()


def test_patch_has_no_resize_handles(canvas):
    canvas.set_tool(TOOL_PATCH)
    drag(canvas, 100, 100, 200, 150)
    p = canvas.shapes[0]
    assert canvas.selection == {p.id}
    from PyQt6.QtCore import QPointF as _P

    assert canvas.handle_at(_P(100, 100)) is None  # corner of the patch


def test_handles_only_visible_on_hover(canvas):
    s = add_shape(canvas, 100, 100)
    canvas.selection = {s.id}
    assert not canvas.handles_visible
    move(canvas, 110, 110)  # hover over the selected shape
    assert canvas.handles_visible
    move(canvas, 500, 400)  # hover empty space
    assert not canvas.handles_visible


def test_fit_follows_resize_until_user_zooms(canvas, qapp):
    fit_scale = canvas.view_scale()
    canvas.resize(500, 350)
    qapp.processEvents()
    assert canvas.view_scale() < fit_scale  # refit to the smaller window
    # corners of the image stay visible after refit
    tl = canvas.mapFromScene(QPointF(0, 0))
    br = canvas.mapFromScene(
        QPointF(canvas.image.width(), canvas.image.height())
    )
    vp = canvas.viewport().rect()
    assert vp.contains(tl) and vp.contains(br)

    canvas.zoom(2.0)
    zoomed = canvas.view_scale()
    canvas.resize(900, 600)
    qapp.processEvents()
    assert abs(canvas.view_scale() - zoomed) < 1e-6  # manual zoom preserved
    canvas.fit()  # F re-engages fit mode
    canvas.resize(700, 500)
    qapp.processEvents()
    tl = canvas.mapFromScene(QPointF(0, 0))
    assert canvas.viewport().rect().contains(tl)


def test_patch_can_be_parked_outside_the_image(canvas):
    canvas.set_tool(TOOL_PATCH)
    drag(canvas, 100, 100, 250, 140)
    p = canvas.shapes[0]
    # zoom out so the parking area around the slide is on screen (a drag
    # that leaves the widget becomes a drag-and-drop to the queue instead)
    canvas.zoom(0.5)
    # drag it far left, well past the image edge
    press(canvas, p.x + 10, p.y + 10)
    move(canvas, p.x - 220, p.y + 10)
    release(canvas, p.x - 220, p.y + 10)
    assert p.x < -100  # allowed off the image, onto the canvas
    assert canvas.patches_outside_image() == [p]
    # masks are still confined to the image (see clamp test below)
    press(canvas, p.x + 5, p.y + 5)
    move(canvas, 150, 120)
    release(canvas, 150, 120)
    assert canvas.patches_outside_image() == []


def test_fit_keeps_parked_patch_visible(canvas, qapp):
    canvas.set_tool(TOOL_PATCH)
    drag(canvas, 100, 100, 250, 140)
    p = canvas.shapes[0]
    canvas.zoom(0.5)
    press(canvas, p.x + 10, p.y + 10)
    move(canvas, p.x - 200, p.y + 10)
    release(canvas, p.x - 200, p.y + 10)
    assert p.x < -50  # actually parked outside before fitting
    canvas.fit()
    qapp.processEvents()
    vp = canvas.viewport().rect()
    assert vp.contains(canvas.mapFromScene(QPointF(p.x, p.y)))
    assert vp.contains(
        canvas.mapFromScene(QPointF(canvas.image.width(), 0))
    )


def test_resize_works_inside_box_tool(canvas):
    s = add_shape(canvas, 100, 100, w=80, h=40)
    canvas.selection = {s.id}
    canvas.set_tool(TOOL_RECT)
    # grab the bottom-right handle without leaving the Box tool
    press(canvas, 180, 140)
    move(canvas, 240, 170)
    release(canvas, 240, 170)
    assert abs((s.x + s.w) - 240) <= 2 and abs((s.y + s.h) - 170) <= 2
    assert len(canvas.shapes) == 1  # resized, not drew a new box
    # drawing away from the handles still draws
    drag(canvas, 300, 300, 380, 340)
    assert len(canvas.shapes) == 2


def test_take_patch_extracts_exact_pixels_and_removes_shape(canvas):
    canvas.set_tool(TOOL_PATCH)
    drag(canvas, 100, 100, 300, 160)
    p = canvas.shapes[0]
    img = canvas.take_patch(p.id)
    assert img.width() == round(p.w) and img.height() == round(p.h)
    assert img.pixelColor(10, 10) == canvas.image.pixelColor(
        round(p.sx) + 10, round(p.sy) + 10
    )
    assert canvas.shapes == []  # removed from the canvas
    canvas.undo()
    assert len(canvas.shapes) == 1  # but restorable


def test_highlight_draws_straight_band_and_bakes_multiply(canvas):
    canvas.set_tool(TOOL_HIGHLIGHT)
    drag(canvas, 40, 115, 500, 140)  # across a text line
    assert len(canvas.shapes) == 1
    s = canvas.shapes[0]
    assert s.kind == "highlight"
    baked = canvas.bake_image()
    # background inside the band takes the highlight colour (multiply)
    bg_px = baked.pixelColor(450, 127)  # background area inside the band
    hl = canvas.highlight_fill
    hr, hg = int(hl[1:3], 16), int(hl[3:5], 16)
    assert abs(bg_px.red() - hr) < 30 and abs(bg_px.green() - hg) < 40
    assert bg_px.blue() < 160  # clearly tinted, no longer near-white
    # highlights never become cards and cannot be grouped
    assert target_groups(canvas.shapes) == []
    other = add_shape(canvas, 100, 300)
    canvas.selection = {s.id, other.id}
    assert not canvas.group_selected()


def test_double_click_word_creates_snapped_mask(canvas):
    from PyQt6.QtGui import QMouseEvent

    # double-click inside a word of the fixture's first body line
    vp = QPointF(canvas.mapFromScene(QPointF(70, 122)))
    ev2 = QMouseEvent(
        QEvent.Type.MouseButtonDblClick, vp, vp, LEFT, LEFT, NOMOD
    )
    canvas.mouseDoubleClickEvent(ev2)
    assert len(canvas.shapes) == 1
    s = canvas.shapes[0]
    assert s.kind == "rect" and s.snap == SNAP_WORD
    assert canvas.selection == {s.id}
    # covers the word fully with padding, inside a sane line height
    assert s.h < 40 and s.w > 5
    assert s.y < 122 < s.y + s.h
    assert target_groups(canvas.shapes) == [s.effective_group()]  # is a card


def test_double_click_in_highlighter_tool_highlights_word(canvas):
    from PyQt6.QtGui import QMouseEvent

    canvas.set_tool(TOOL_HIGHLIGHT)
    vp = QPointF(canvas.mapFromScene(QPointF(70, 122)))
    ev2 = QMouseEvent(
        QEvent.Type.MouseButtonDblClick, vp, vp, LEFT, LEFT, NOMOD
    )
    canvas.mouseDoubleClickEvent(ev2)
    assert len(canvas.shapes) == 1
    s = canvas.shapes[0]
    assert s.kind == "highlight"  # highlighted, not blocked out
    assert s.snap == SNAP_WORD  # side handles still snap by word
    assert target_groups(canvas.shapes) == []  # never a card
    # baked pixels: the band's background is tinted yellow (multiply), so
    # its brightest pixel is yellowish, no longer near-white
    baked = canvas.bake_image()
    brightest = None
    for yy in range(int(s.y), int(s.y + s.h)):
        for xx in range(int(s.x), int(s.x + s.w)):
            c = baked.pixelColor(xx, yy)
            if brightest is None or c.red() + c.green() > (
                brightest.red() + brightest.green()
            ):
                brightest = c
    assert brightest.red() > 200 and brightest.blue() < 180  # yellow tint


def test_word_box_resize_snaps_to_whole_words(canvas):
    s = canvas.create_word_box(70, 122)
    assert s is not None
    orig_right = s.x + s.w
    # drag the right handle far right: box must land exactly on a word
    # boundary (right edge sits in a gap - no ink at the edge column)
    press(canvas, s.x + s.w, s.y + s.h / 2)
    move(canvas, s.x + 260, s.y + s.h / 2)
    release(canvas, s.x + 260, s.y + s.h / 2)
    assert s.x + s.w > orig_right + 20  # grew by at least one word
    import snip_occlusion.wordsnap as ws

    line = ws.analyze_line(canvas.image, s.x + s.w / 2, s.y + s.h / 2)
    for x0, x1 in line.runs:
        # every word is either fully inside or fully outside the box
        inside = x0 >= s.x and x1 <= s.x + s.w
        outside = x1 < s.x or x0 > s.x + s.w
        assert inside or outside


def test_copy_paste_places_clone_beside_original(canvas):
    a = add_shape(canvas, 100, 100, w=80, h=40, group="g1")
    canvas.selection = {a.id}
    canvas.copy_selection()
    canvas.paste_clipboard()
    assert len(canvas.shapes) == 2
    clone = [s for s in canvas.shapes if s.id != a.id][0]
    assert clone.id != a.id
    assert (clone.w, clone.h) == (a.w, a.h)
    assert clone.group != "g1"  # pasted box is not sucked into the group
    # near but NOT overlapping
    assert not clone.intersects(a.x, a.y, a.w, a.h)
    assert abs(clone.x - a.x) <= a.w + 20 and abs(clone.y - a.y) <= a.h + 20
    # a second paste lands beside the first clone, not on top of it
    canvas.paste_clipboard()
    assert len(canvas.shapes) == 3
    c2 = canvas.shapes[-1]
    assert not c2.intersects(clone.x, clone.y, clone.w, clone.h)
    assert not c2.intersects(a.x, a.y, a.w, a.h)


def test_copy_paste_preserves_internal_grouping(canvas):
    a = add_shape(canvas, 100, 100, group="g1")
    b = add_shape(canvas, 300, 100, group="g1")
    c = add_shape(canvas, 100, 200)
    canvas.selection = {a.id, b.id, c.id}
    canvas.copy_selection()
    canvas.paste_clipboard()
    clones = [s for s in canvas.shapes if s.id not in {a.id, b.id, c.id}]
    assert len(clones) == 3
    grouped = [s for s in clones if s.group]
    lone = [s for s in clones if not s.group]
    assert len(grouped) == 2 and len(lone) == 1
    assert grouped[0].group == grouped[1].group
    assert grouped[0].group != "g1"  # a fresh group, not joined to the old


def _rendered_color_at(canvas, scene_x, scene_y):
    """Colour of the rendered viewport at a scene point."""
    img = canvas.grab().toImage()
    dpr = img.devicePixelRatio()
    vp = canvas.mapFromScene(QPointF(scene_x, scene_y))
    return img.pixelColor(int(vp.x() * dpr), int(vp.y() * dpr))


def test_xray_mode_shows_text_under_all_boxes(canvas, qapp):
    # a mask over a text-free part of the pink callout (y 382..406)
    s = add_shape(canvas, 60, 382, w=200, h=24)
    canvas.resetTransform()  # 1:1 so sampled pixels are exact
    canvas.centerOn(160, 394)
    canvas.show()
    qapp.processEvents()
    covered = _rendered_color_at(canvas, 160, 394)
    # opaque: the mask colour, nothing pink shows through
    assert abs(covered.red() - 0xFF) < 25 and abs(covered.green() - 0xEB) < 30
    canvas.toggle_xray()
    assert canvas.xray
    revealed = _rendered_color_at(canvas, 160, 394)
    # see-through: the pink callout (#f8d7da) is visible again
    assert abs(revealed.red() - 0xF8) < 25
    assert abs(revealed.green() - 0xD7) < 30
    assert abs(revealed.blue() - 0xDA) < 30
    canvas.toggle_xray()
    assert not canvas.xray
    back = _rendered_color_at(canvas, 160, 394)
    assert abs(back.green() - 0xEB) < 30  # opaque again


def test_peek_shows_under_one_box_only(canvas, qapp):
    a = add_shape(canvas, 60, 382, w=100, h=24)  # over pink callout
    b = add_shape(canvas, 200, 382, w=100, h=24)  # also over the callout
    canvas.resetTransform()
    canvas.centerOn(180, 394)
    canvas.show()
    qapp.processEvents()
    canvas.toggle_peek(a.id)
    assert a.id in canvas.peek_ids
    under_a = _rendered_color_at(canvas, 110, 394)
    under_b = _rendered_color_at(canvas, 250, 394)
    assert abs(under_a.red() - 0xF8) < 25 and abs(under_a.blue() - 0xDA) < 30
    assert abs(under_b.green() - 0xEB) < 30  # b stays opaque
    canvas.toggle_peek(a.id)
    assert a.id not in canvas.peek_ids
    # peeking is view-only: cards and baked image are unaffected
    canvas.toggle_peek(b.id)
    assert len(target_groups(canvas.shapes)) == 2
    # deleting a shape cleans up its peek state
    canvas.selection = {b.id}
    canvas.delete_selected()
    assert b.id not in canvas.peek_ids


def test_box_tool_moves_existing_mask_without_drawing(canvas):
    s = add_shape(canvas, 100, 100, w=80, h=40)
    canvas.set_tool(TOOL_RECT)
    press(canvas, 140, 120)  # dead centre of the box
    move(canvas, 190, 160)
    release(canvas, 190, 160)
    assert len(canvas.shapes) == 1  # moved, did not draw a new box
    assert abs(s.x - 150) <= 1.5 and abs(s.y - 140) <= 1.5


def test_box_tool_draws_over_highlight_without_moving_it(canvas):
    from snip_occlusion.shapes import Shape

    hl = Shape(kind="highlight", x=50, y=100, w=500, h=40)
    canvas.shapes.append(hl)
    canvas.set_tool(TOOL_RECT)
    drag(canvas, 100, 110, 260, 130)  # starts ON the highlight
    assert len(canvas.shapes) == 2  # a mask was drawn
    assert (hl.x, hl.y) == (50, 100)  # the highlight did not move
    mask = [s for s in canvas.shapes if s.kind == "rect"][0]
    assert abs(mask.x - 100) < 3


def test_small_selected_box_centre_press_moves_not_resizes(canvas):
    canvas.resetTransform()  # 1:1 so screen px == scene px
    s = add_shape(canvas, 100, 100, w=26, h=12)
    canvas.selection = {s.id}
    press(canvas, 113, 106)  # centre: must be move territory, not a handle
    assert canvas.gesture is not None
    assert canvas.gesture["type"] == "maybe-move"
    move(canvas, 143, 126)
    release(canvas, 143, 126)
    assert abs(s.x - 130) <= 1.5 and abs(s.y - 120) <= 1.5
    assert (s.w, s.h) == (26, 12)


def test_word_box_centre_drag_moves_smoothly(canvas):
    s = canvas.create_word_box(70, 122)
    assert s is not None
    orig = (s.x, s.y, s.w, s.h)
    press(canvas, s.x + s.w / 2, s.y + s.h / 2)
    move(canvas, s.x + s.w / 2 + 60, s.y + s.h / 2 + 40)
    release(canvas, s.x + s.w / 2 + 60, s.y + s.h / 2 + 40)
    assert abs(s.x - (orig[0] + 60)) <= 2 and abs(s.y - (orig[1] + 40)) <= 2
    assert (s.w, s.h) == (orig[2], orig[3])  # a move, not a snap-resize


def test_word_box_vertical_resize_is_free(canvas):
    canvas.resetTransform()
    canvas.centerOn(120, 122)
    s = canvas.create_word_box(70, 122)
    assert s is not None
    orig = (s.x, s.y, s.w, s.h)
    press(canvas, s.x + s.w / 2, s.y)  # top-middle handle
    assert canvas.gesture and canvas.gesture["type"] == "resize"
    move(canvas, s.x + s.w / 2, s.y - 15)
    release(canvas, s.x + s.w / 2, s.y - 15)
    assert s.h > orig[3] + 10  # grew upward freely
    assert abs(s.x - orig[0]) <= 1.5 and abs(s.w - orig[2]) <= 1.5


def test_move_is_clamped_to_image(canvas):
    s = add_shape(canvas, 10, 10, w=50, h=30)
    press(canvas, 20, 20)
    move(canvas, -300, -300)
    release(canvas, -300, -300)
    assert s.x == 0 and s.y == 0
