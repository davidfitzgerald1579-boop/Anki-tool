"""The occlusion editor canvas.

A QGraphicsView showing the snipped image with mask/erase shapes painted by a
single overlay item. Shapes are plain dataclasses (see shapes.py); all mouse
and keyboard handling lives here, which is what lets us fix the interaction
problems of SVG-edit-based occlusion editors:

- A drag only starts after the cursor travels `drag_threshold_px`, so
  clicking a shape (with or without Shift) never nudges it.
- Shift+click purely toggles selection; it can never move a shape.
- Dragging a shape moves ONLY that shape, even when several are selected.
  Hold Ctrl while dragging to deliberately move the whole selection.
- Groups are explicit id sets, not geometric containers: any combination of
  shapes can be grouped, including a box sandwiched between two others.
"""

from __future__ import annotations

import math

from .qtshim import *  # noqa: F401,F403
from . import shapes as sh
from . import wordsnap
from .color_utils import local_background, majority_color
from .consts import (
    GROUP_PALETTE,
    HIGHLIGHT_QUICK_COLORS,
    KIND_ELLIPSE,
    KIND_ERASE,
    KIND_HIGHLIGHT,
    KIND_PATCH,
    KIND_RECT,
    MASK_KINDS,
    MIN_SHAPE_PX,
    SNAP_WORD,
    TOOL_ERASE,
    TOOL_HIGHLIGHT,
    TOOL_PATCH,
    TOOL_RECT,
    TOOL_SELECT,
)

HANDLE_SCREEN_PX = 8  # on-screen size of resize handles
# handle codes: combination of edges
H_TL, H_T, H_TR, H_R, H_BR, H_B, H_BL, H_L = range(8)
HANDLE_CURSORS = {
    H_TL: Qt.CursorShape.SizeFDiagCursor,
    H_BR: Qt.CursorShape.SizeFDiagCursor,
    H_TR: Qt.CursorShape.SizeBDiagCursor,
    H_BL: Qt.CursorShape.SizeBDiagCursor,
    H_T: Qt.CursorShape.SizeVerCursor,
    H_B: Qt.CursorShape.SizeVerCursor,
    H_L: Qt.CursorShape.SizeHorCursor,
    H_R: Qt.CursorShape.SizeHorCursor,
}


class _OverlayItem(QGraphicsItem):
    """Single item that paints every shape plus selection/gesture chrome."""

    def __init__(self, canvas: "OcclusionCanvas"):
        super().__init__()
        self.canvas = canvas
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(10)

    def boundingRect(self) -> QRectF:
        c = self.canvas
        if c.image is None:
            return QRectF()
        # covers the whole scene: patches may be parked outside the image
        return c._scene.sceneRect()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        c = self.canvas
        if c.image is None:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        scale = c.view_scale()
        badge_order = sh.explicit_group_index(c.shapes)

        for s in c.ordered_shapes():
            rect = QRectF(s.x, s.y, s.w, s.h)
            if s.kind == KIND_ERASE:
                if c.xray or s.id in c.peek_ids:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                else:
                    painter.setBrush(QBrush(QColor(s.color or "#ffffff")))
                pen = QPen(QColor(120, 120, 120, 180), 1, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawRect(rect)
                continue

            if s.kind == KIND_PATCH:
                # pixel-exact copy from the ORIGINAL image, so quality is
                # identical to the snip and unaffected by cover-ups below it
                painter.drawImage(
                    rect, c.image, QRectF(s.sx or 0, s.sy or 0, s.w, s.h)
                )
                pen = QPen(QColor(70, 130, 220, 200), 1, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
                continue

            if s.kind == KIND_HIGHLIGHT:
                # multiply, like real highlighter ink: the background takes
                # the colour, dark text stays dark and readable
                painter.save()
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Multiply
                )
                painter.fillRect(rect, QColor(s.color or c.highlight_fill))
                painter.restore()
                continue

            # see-through mode (global toggle or per-box peek): outline
            # only, so the text underneath stays readable while editing
            see_through = c.xray or s.id in c.peek_ids
            if see_through:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            else:
                painter.setBrush(QBrush(QColor(c.mask_fill)))  # opaque
            if s.group:
                # group membership is shown by a bold shared outline colour
                idx = badge_order.get(s.group, 1)
                pen = QPen(
                    QColor(GROUP_PALETTE[(idx - 1) % len(GROUP_PALETTE)]), 3
                )
            else:
                pen = QPen(QColor(0, 0, 0, 190 if see_through else 110), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            if s.kind == KIND_ELLIPSE:
                painter.drawEllipse(rect)
            else:
                painter.drawRect(rect)

        # selection outlines: white halo + bold blue, so selection stands
        # out clearly against both the masks and any group colour
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for s in c.shapes:
            if s.id in c.selection:
                rect = QRectF(s.x, s.y, s.w, s.h)
                for color, width in (("#ffffff", 6), ("#1a73e8", 3)):
                    pen = QPen(QColor(color), width)
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                    if s.kind == KIND_ELLIPSE:
                        painter.drawEllipse(rect)
                    else:
                        painter.drawRect(rect)

        # resize handles: only while hovering the single selected shape
        # (or mid-resize), so they don't clutter the view
        single = c.single_selected()
        if (
            single is not None
            and single.kind != KIND_PATCH
            and (c.handles_visible or (c.gesture or {}).get("type") == "resize")
        ):
            hs = HANDLE_SCREEN_PX / scale
            painter.setBrush(QBrush(QColor("#ffffff")))
            hpen = QPen(QColor("#1a73e8"), 1)
            hpen.setCosmetic(True)
            painter.setPen(hpen)
            for hr in c.handle_rects(single, hs):
                painter.drawRect(hr)

        # rubber-band rectangle
        if c.gesture and c.gesture.get("type") == "rubber":
            r = c.gesture["rect"]
            pen = QPen(QColor("#1a73e8"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(26, 115, 232, 30)))
            painter.drawRect(r)

PATCH_MIME = "application/x-snip-occlusion-patch"


class OcclusionCanvas(QGraphicsView):
    shapes_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    tool_changed = pyqtSignal(str)
    send_patch_to_new_card = pyqtSignal(str)  # patch id (context menu path)
    xray_changed = pyqtSignal(bool)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.mask_fill = config.get("mask_fill", "#FFEBA2")
        self.highlight_fill = config.get("highlight_fill", "#ffe94d")
        self.drag_threshold = float(config.get("drag_threshold_px", 5))
        self.nudge_step = int(config.get("nudge_step", 1))
        self.nudge_step_large = int(config.get("nudge_step_large", 10))

        self.image: QImage | None = None
        self.majority: QColor = QColor("#ffffff")
        self.erase_color_override: QColor | None = None
        self.shapes: list = []
        self.selection: set = set()
        self.tool: str = TOOL_SELECT
        self.gesture: dict | None = None
        self.handles_visible: bool = False
        self.xray: bool = False  # global see-through: outlines only
        self.peek_ids: set = set()  # per-box see-through (right-click)
        self._group_counter = 0
        self._undo: list = []
        self._redo: list = []
        self._last_undo_tag: str | None = None
        self._pan_origin: QPoint | None = None
        self._user_zoomed = False
        self._shape_clipboard: str | None = None
        self._clipboard_bbox: QRectF | None = None  # where the copy came from
        self._paste_anchor: QRectF | None = None  # where the last paste went
        self._last_word_click: tuple | None = None
        self._own_clipboard_write = False  # debug images we put on clipboard

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._overlay = _OverlayItem(self)

        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setBackgroundBrush(QBrush(QColor("#ece5d8")))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ image

    def set_image(self, img: QImage) -> None:
        self.image = img.convertToFormat(QImage.Format.Format_RGB32)
        self.majority = majority_color(self.image)
        self.erase_color_override = None
        self.shapes = []
        self.selection = set()
        self.gesture = None
        self.peek_ids = set()
        self._group_counter = 0
        self._undo = []
        self._redo = []
        self._scene.clear()  # deletes old items
        self._pixmap_item = self._scene.addPixmap(QPixmap.fromImage(self.image))
        self._pixmap_item.setZValue(0)
        # smooth scaling: the default (fast/nearest-neighbour) looks
        # pixelated at any zoom other than exactly 100%
        self._pixmap_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self._user_zoomed = False
        # a subtle frame so the slide edge is visible against the canvas
        frame_pen = QPen(QColor("#c9c0b0"), 1)
        frame_pen.setCosmetic(True)
        self._scene.addRect(
            QRectF(0, 0, self.image.width(), self.image.height()), frame_pen
        ).setZValue(1)
        self._overlay = _OverlayItem(self)
        self._scene.addItem(self._overlay)
        # scene extends well past the image so snip patches can be parked
        # anywhere on the surrounding canvas while rearranging the slide
        mx = max(240.0, self.image.width() * 0.5)
        my = max(240.0, self.image.height() * 0.5)
        self._scene.setSceneRect(
            QRectF(
                -mx, -my, self.image.width() + 2 * mx, self.image.height() + 2 * my
            )
        )
        self.fit()
        self.shapes_changed.emit()
        self.selection_changed.emit()

    def has_image(self) -> bool:
        return self.image is not None

    def has_shapes(self) -> bool:
        return bool(self.shapes)

    def default_erase_color(self, s: sh.Shape) -> str:
        if self.erase_color_override is not None:
            return self.erase_color_override.name()
        if self.config.get("erase_color_mode", "majority") == "local":
            return local_background(self.image, s.x, s.y, s.w, s.h).name()
        return self.majority.name()

    def ordered_shapes(self) -> list:
        """Shapes in paint order: erases, then patches, then masks."""
        return sorted(self.shapes, key=sh.layer_of)

    def bake_image(self) -> QImage:
        """Copy of the image with erase fills and patches applied.

        Patches are drawn from the ORIGINAL image at integer positions with
        no scaling, so the moved snippet is pixel-identical to the source.
        """
        img = self.image.copy()
        painter = QPainter(img)
        for s in sh.erase_shapes(self.shapes):
            painter.fillRect(
                QRectF(s.x, s.y, s.w, s.h), QColor(s.color or "#ffffff")
            )
        for s in sh.patch_shapes(self.shapes):
            painter.drawImage(
                QPoint(round(s.x), round(s.y)),
                self.image,
                QRect(
                    round(s.sx or 0), round(s.sy or 0), round(s.w), round(s.h)
                ),
            )
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Multiply
        )
        for s in sh.highlight_shapes(self.shapes):
            painter.fillRect(
                QRectF(s.x, s.y, s.w, s.h),
                QColor(s.color or self.highlight_fill),
            )
        painter.end()
        return img

    # ------------------------------------------------------------------ tools

    def set_tool(self, tool: str) -> None:
        if tool == self.tool:
            return
        self.tool = tool
        self.gesture = None
        if tool == TOOL_SELECT:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.tool_changed.emit(tool)
        self.viewport().update()

    # -------------------------------------------------------------- selection

    def single_selected(self) -> sh.Shape | None:
        if len(self.selection) != 1:
            return None
        sid = next(iter(self.selection))
        return self.shape_by_id(sid)

    def shape_by_id(self, sid: str) -> sh.Shape | None:
        for s in self.shapes:
            if s.id == sid:
                return s
        return None

    def select_all(self) -> None:
        self.selection = {s.id for s in self.shapes}
        self.selection_changed.emit()
        self.viewport().update()

    def clear_selection(self) -> None:
        if self.selection:
            self.selection = set()
            self.selection_changed.emit()
            self.viewport().update()

    # ----------------------------------------------------------------- edits

    def delete_selected(self) -> None:
        if not self.selection:
            return
        self.push_undo()
        self.shapes = [s for s in self.shapes if s.id not in self.selection]
        self.selection = set()
        self._emit_changed()

    def _new_group_id(self) -> str:
        # skip ids already in use (shapes can arrive via undo/paste with
        # group ids the counter never saw)
        used = {s.group for s in self.shapes if s.group}
        while True:
            self._group_counter += 1
            gid = "g%d" % self._group_counter
            if gid not in used:
                return gid

    def group_selected(self) -> bool:
        members = [
            s
            for s in self.shapes
            if s.id in self.selection and s.kind in MASK_KINDS
        ]
        if len(members) < 2:
            return False
        self.push_undo()
        gid = self._new_group_id()
        for s in members:
            s.group = gid
        self._emit_changed()
        return True

    def ungroup_selected(self) -> None:
        changed = False
        for s in self.shapes:
            if s.id in self.selection and s.group:
                if not changed:
                    self.push_undo()
                    changed = True
                s.group = None
        if changed:
            self._emit_changed()

    def move_bounds(self, s: sh.Shape):
        """Where a shape may be moved: patches roam the whole canvas so they
        can be parked out of the way; masks/erases must stay on the image."""
        if s.kind == KIND_PATCH:
            r = self._scene.sceneRect()
            return r.left(), r.top(), r.right(), r.bottom()
        return 0.0, 0.0, float(self.image.width()), float(self.image.height())

    def extract_patch_image(self, patch_id: str):
        """The patch's pixels, cropped 1:1 from the ORIGINAL image."""
        s = self.shape_by_id(patch_id)
        if s is None or s.kind != KIND_PATCH or self.image is None:
            return None
        return self.image.copy(
            QRect(round(s.sx or 0), round(s.sy or 0), round(s.w), round(s.h))
        )

    def take_patch(self, patch_id: str):
        """Extract a patch's pixels and remove the patch from the canvas
        (used when a snip is sent to a new card). Undo-able."""
        img = self.extract_patch_image(patch_id)
        if img is None:
            return None
        self.push_undo()
        self.shapes = [s for s in self.shapes if s.id != patch_id]
        self.selection.discard(patch_id)
        self._emit_changed()
        return img

    def patches_outside_image(self) -> list:
        """Patches that are not fully inside the image (would be cut off)."""
        img = QRectF(0, 0, self.image.width(), self.image.height())
        return [
            s
            for s in sh.patch_shapes(self.shapes)
            if not img.contains(QRectF(s.x, s.y, s.w, s.h))
        ]

    def nudge_selection(self, dx: float, dy: float) -> None:
        if not self.selection or self.image is None:
            return
        self.push_undo(tag="nudge")
        for s in self.shapes:
            if s.id in self.selection:
                s.x, s.y, s.w, s.h = sh.clamp_rect_in(
                    s.x + dx, s.y + dy, s.w, s.h, *self.move_bounds(s)
                )
        self._emit_changed()

    def _emit_changed(self) -> None:
        self.peek_ids &= {s.id for s in self.shapes}
        self.shapes_changed.emit()
        self.selection_changed.emit()
        self.viewport().update()

    # -------------------------------------------------------- see-through

    def set_xray(self, on: bool) -> None:
        if on != self.xray:
            self.xray = on
            self.xray_changed.emit(on)
            self.viewport().update()

    def toggle_xray(self) -> None:
        self.set_xray(not self.xray)

    def toggle_peek(self, shape_id: str) -> None:
        if shape_id in self.peek_ids:
            self.peek_ids.discard(shape_id)
        else:
            self.peek_ids.add(shape_id)
        self.viewport().update()

    def copy_wordsnap_debug(self) -> None:
        """Copy an annotated view of the last word-detection to the
        clipboard: blue = detected line, red = detected words, green cross
        = the click. For diagnosing double-click misfires on real slides."""
        if self.image is None or self._last_word_click is None:
            return
        cx, cy = self._last_word_click
        line = wordsnap.analyze_line(self.image, cx, cy)
        img = self.image.copy()
        p = QPainter(img)
        if line is not None:
            pen = QPen(QColor("#1a73e8"), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(
                QRectF(1, line.top - 1, img.width() - 3, line.height + 2)
            )
            p.setPen(QPen(QColor("#e6194b"), 2))
            for rx0, rx1 in line.runs:
                p.drawRect(
                    QRectF(rx0 - 1, line.top - 3, rx1 - rx0 + 3, line.height + 6)
                )
        p.setPen(QPen(QColor("#00a000"), 3))
        p.drawLine(QPointF(cx - 12, cy), QPointF(cx + 12, cy))
        p.drawLine(QPointF(cx, cy - 12), QPointF(cx, cy + 12))
        p.end()
        y0 = max(0, int(cy) - wordsnap.BAND_HALF - 20)
        y1 = min(img.height(), int(cy) + wordsnap.BAND_HALF + 20)
        self._own_clipboard_write = True
        QApplication.clipboard().setImage(
            img.copy(0, y0, img.width(), y1 - y0)
        )
        QToolTip.showText(
            QCursor.pos(),
            "Word-detection debug image copied to clipboard — paste it "
            "into the chat.",
            self,
        )

    # ------------------------------------------------------------ copy/paste

    def copy_selection(self) -> None:
        sel = [s for s in self.shapes if s.id in self.selection]
        if not sel:
            return
        self._shape_clipboard = sh.serialize(sel)
        xs = [s.x for s in sel]
        ys = [s.y for s in sel]
        bbox = QRectF(
            min(xs),
            min(ys),
            max(s.x + s.w for s in sel) - min(xs),
            max(s.y + s.h for s in sel) - min(ys),
        )
        self._clipboard_bbox = bbox
        self._paste_anchor = QRectF(bbox)

    def paste_clipboard(self) -> None:
        """Paste copied shapes near — but not overlapping — the originals.

        Repeated pastes chain off the previous paste, so Ctrl+V twice gives
        two boxes side by side rather than two stacked clones.
        """
        if not self._shape_clipboard or self.image is None:
            return
        clones = sh.deserialize(self._shape_clipboard)
        if not clones:
            return
        # place beside the LAST paste (or the original, for the first one),
        # translating the clones from where they were copied
        step_x, step_y = self._paste_offset(self._paste_anchor)
        dx = self._paste_anchor.x() + step_x - self._clipboard_bbox.x()
        dy = self._paste_anchor.y() + step_y - self._clipboard_bbox.y()
        group_map: dict = {}
        for s in clones:
            s.id = sh.new_id()
            if s.group:
                if s.group not in group_map:
                    group_map[s.group] = self._new_group_id()
                s.group = group_map[s.group]
            s.x, s.y, s.w, s.h = sh.clamp_rect_in(
                s.x + dx, s.y + dy, s.w, s.h, *self.move_bounds(s)
            )
        self.push_undo()
        self.shapes.extend(clones)
        self.selection = {s.id for s in clones}
        xs = [s.x for s in clones]
        ys = [s.y for s in clones]
        self._paste_anchor = QRectF(
            min(xs),
            min(ys),
            max(s.x + s.w for s in clones) - min(xs),
            max(s.y + s.h for s in clones) - min(ys),
        )
        self._emit_changed()

    def _paste_offset(self, anchor: QRectF):
        """Offset placing the paste beside the anchor: right, below, left,
        above — whichever keeps it fully on the image."""
        gap = 14.0
        img = QRectF(0, 0, self.image.width(), self.image.height())
        for dx, dy in (
            (anchor.width() + gap, 0.0),
            (0.0, anchor.height() + gap),
            (-(anchor.width() + gap), 0.0),
            (0.0, -(anchor.height() + gap)),
        ):
            if img.contains(anchor.translated(dx, dy)):
                return dx, dy
        return gap, gap  # cramped image: nudge diagonally, clamped later

    # ------------------------------------------------------------------ undo

    def push_undo(self, tag: str | None = None) -> None:
        # coalesce runs of arrow-key nudges into a single undo step
        if tag == "nudge" and self._last_undo_tag == "nudge":
            return
        self._undo.append(sh.serialize(self.shapes))
        if len(self._undo) > 100:
            self._undo.pop(0)
        self._redo = []
        self._last_undo_tag = tag

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(sh.serialize(self.shapes))
        self.shapes = sh.deserialize(self._undo.pop())
        ids = {s.id for s in self.shapes}
        self.selection &= ids
        self._last_undo_tag = None
        self._emit_changed()

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(sh.serialize(self.shapes))
        self.shapes = sh.deserialize(self._redo.pop())
        ids = {s.id for s in self.shapes}
        self.selection &= ids
        self._last_undo_tag = None
        self._emit_changed()

    # ------------------------------------------------------------------ zoom

    def view_scale(self) -> float:
        return max(self.transform().m11(), 0.01)

    def fit(self) -> None:
        if self.image is None:
            return
        # fit the image plus any patches parked outside it, so nothing the
        # user is working with ever disappears off screen
        rect = QRectF(0, 0, self.image.width(), self.image.height())
        for s in sh.patch_shapes(self.shapes):
            rect = rect.united(QRectF(s.x, s.y, s.w, s.h))
        pad = 12.0
        rect = rect.adjusted(-pad, -pad, pad, pad)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._user_zoomed = False

    def zoom(self, factor: float) -> None:
        new_scale = self.view_scale() * factor
        if 0.05 <= new_scale <= 16:
            self.scale(factor, factor)
            self._user_zoomed = True

    def resizeEvent(self, event) -> None:
        # keep the image fit-to-window (including on maximize/fullscreen)
        # until the user explicitly zooms
        super().resizeEvent(event)
        if self.image is not None and not self._user_zoomed:
            self.fit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.image is not None and not self._user_zoomed:
            self.fit()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom(1.15 if delta > 0 else 1 / 1.15)
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------- hit tests

    def shape_at(self, pos: QPointF) -> sh.Shape | None:
        for s in reversed(self.ordered_shapes()):  # topmost first
            if s.contains(pos.x(), pos.y()):
                return s
        return None

    def handle_rects(self, s: sh.Shape, size: float) -> list:
        x0, y0 = s.x, s.y
        x1, y1 = s.x + s.w, s.y + s.h
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        pts = [
            (x0, y0),
            (xm, y0),
            (x1, y0),
            (x1, ym),
            (x1, y1),
            (xm, y1),
            (x0, y1),
            (x0, ym),
        ]
        half = size / 2
        return [QRectF(px - half, py - half, size, size) for px, py in pts]

    def handle_at(self, pos: QPointF) -> int | None:
        s = self.single_selected()
        if s is None or s.kind == KIND_PATCH:
            # patches can be moved but never resized: resizing would
            # resample the pixels and lose the 1:1 snip quality
            return None
        size = HANDLE_SCREEN_PX / self.view_scale() * 1.5  # generous hit area
        # the centre of a shape is ALWAYS move territory: on a small box
        # (e.g. a word box) the handle zones would otherwise blanket the
        # whole surface and make it impossible to grab and move
        mx = min(size / 2, s.w / 3)
        my = min(size / 2, s.h / 3)
        inner = QRectF(s.x + mx, s.y + my, s.w - 2 * mx, s.h - 2 * my)
        if inner.contains(pos):
            return None
        for code, hr in enumerate(self.handle_rects(s, size)):
            if hr.contains(pos):
                return code
        return None

    # ------------------------------------------------------------ mouse input

    def mousePressEvent(self, event) -> None:
        if self.image is None:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_origin = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        mods = event.modifiers()
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

        # resize handles win in EVERY tool, so a box can be reshaped right
        # from the draw tool without switching back to Select first
        handle = self.handle_at(pos)
        if handle is not None:
            s = self.single_selected()
            self.gesture = {
                "type": "resize",
                "shape": s,
                "handle": handle,
                "orig": (s.x, s.y, s.w, s.h),
                "moved": False,
            }
            if s.snap == SNAP_WORD:
                # cache the word layout of the shape's text line once, so
                # the resize can snap edge drags to whole words live
                self.gesture["wordline"] = wordsnap.analyze_line(
                    self.image, s.x + s.w / 2, s.y + s.h / 2
                )
            event.accept()
            return

        if self.tool in (TOOL_RECT, TOOL_ERASE, TOOL_PATCH, TOOL_HIGHLIGHT):
            # click-and-hold on a shape of the tool's own kind grabs and
            # moves it instead of drawing on top of it; other kinds are
            # ignored so e.g. a mask can still be drawn over a highlight
            grabs = {
                TOOL_RECT: MASK_KINDS,
                TOOL_ERASE: (KIND_ERASE,),
                TOOL_PATCH: (KIND_PATCH,),
                TOOL_HIGHLIGHT: (KIND_HIGHLIGHT,),
            }[self.tool]
            hit = self.shape_at(pos)
            if hit is not None and hit.kind in grabs:
                self._press_on_shape(hit, pos, shift, ctrl)
                event.accept()
                return
            kind = {
                TOOL_RECT: KIND_RECT,
                TOOL_ERASE: KIND_ERASE,
                TOOL_PATCH: KIND_PATCH,
                TOOL_HIGHLIGHT: KIND_HIGHLIGHT,
            }[self.tool]
            self.gesture = {
                "type": "draw",
                "kind": kind,
                "origin": pos,
                "rect": QRectF(pos, pos),
            }
            event.accept()
            return

        s = self.shape_at(pos)
        if s is not None:
            self._press_on_shape(s, pos, shift, ctrl)
            event.accept()
            return

        # empty area: rubber-band selection
        self.gesture = {
            "type": "rubber",
            "origin": pos,
            "rect": QRectF(pos, pos),
            "additive": shift,
        }
        event.accept()

    def _press_on_shape(
        self, s: sh.Shape, pos: QPointF, shift: bool, ctrl: bool
    ) -> None:
        if shift:
            # Shift+click ONLY toggles selection - it can never drag, so
            # building up a group selection can't nudge shapes around.
            if s.id in self.selection:
                self.selection.discard(s.id)
            else:
                self.selection.add(s.id)
            self.selection_changed.emit()
            self.viewport().update()
            return
        if s.id not in self.selection:
            self.selection = {s.id}
            self.selection_changed.emit()
            self.viewport().update()
        # Plain drag moves only the pressed shape; Ctrl+drag moves the
        # whole selection deliberately.
        ids = sorted(self.selection) if ctrl else [s.id]
        self.gesture = {
            "type": "maybe-move",
            "press": pos,
            "ids": ids,
            "orig": {
                sid: (
                    self.shape_by_id(sid).x,
                    self.shape_by_id(sid).y,
                )
                for sid in ids
                if self.shape_by_id(sid)
            },
            "moved": False,
        }

    def mouseMoveEvent(self, event) -> None:
        if self._pan_origin is not None:
            delta = event.position().toPoint() - self._pan_origin
            self._pan_origin = event.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        if self.image is None:
            super().mouseMoveEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        g = self.gesture
        if g is None:
            self._update_hover_cursor(pos)
            super().mouseMoveEvent(event)
            return

        if g["type"] == "draw":
            g["rect"] = self._clamped_rect(QRectF(g["origin"], pos).normalized())
            self._preview_draw(g)
        elif g["type"] == "maybe-move":
            # the anti-nudge fix: nothing moves until the cursor has
            # travelled the configured threshold
            if self._dist(pos, g["press"]) >= self.drag_threshold:
                self.push_undo()
                g["type"] = "move"
        if g["type"] == "move":
            # dragging a lone patch off the window hands it over as a
            # drag-and-drop payload, so it can be dropped on a queued card
            if self._maybe_start_patch_drag(g, event):
                event.accept()
                return
            dx = pos.x() - g["press"].x()
            dy = pos.y() - g["press"].y()
            for sid, (ox, oy) in g["orig"].items():
                s = self.shape_by_id(sid)
                if s is None:
                    continue
                s.x, s.y, s.w, s.h = sh.clamp_rect_in(
                    ox + dx, oy + dy, s.w, s.h, *self.move_bounds(s)
                )
            g["moved"] = True
            self.viewport().update()
        elif g["type"] == "resize":
            if not g["moved"]:
                self.push_undo()
                g["moved"] = True
            self._apply_resize(g, pos)
            self.viewport().update()
        elif g["type"] == "rubber":
            g["rect"] = QRectF(g["origin"], pos).normalized()
            self.viewport().update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.MiddleButton
            and self._pan_origin is not None
        ):
            self._pan_origin = None
            self.viewport().setCursor(
                Qt.CursorShape.ArrowCursor
                if self.tool == TOOL_SELECT
                else Qt.CursorShape.CrossCursor
            )
            event.accept()
            return
        g = self.gesture
        if g is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self.gesture = None

        if g["type"] == "draw":
            r = g["rect"]
            if r.width() >= MIN_SHAPE_PX and r.height() >= MIN_SHAPE_PX:
                self.push_undo()
                s = sh.Shape(
                    kind=g["kind"],
                    x=r.x(),
                    y=r.y(),
                    w=r.width(),
                    h=r.height(),
                )
                if s.kind == KIND_ERASE:
                    s.color = self.default_erase_color(s)
                elif s.kind == KIND_PATCH:
                    # integer source rect = clean pixel copy, no resampling
                    s.x, s.y = float(round(s.x)), float(round(s.y))
                    s.w, s.h = float(round(s.w)), float(round(s.h))
                    s.sx, s.sy = s.x, s.y
                self.shapes.append(s)
                self.selection = {s.id}
                if s.kind == KIND_PATCH:
                    # switch straight to select so the cutout can be dragged
                    # out of the way immediately
                    self.set_tool(TOOL_SELECT)
                self._emit_changed()
            else:
                self.viewport().update()
        elif g["type"] == "rubber":
            r = g["rect"]
            hits = {
                s.id
                for s in self.shapes
                if s.intersects(r.x(), r.y(), r.width(), r.height())
                and r.width() >= 2
                and r.height() >= 2
            }
            if g["additive"]:
                self.selection |= hits
            else:
                self.selection = hits
            self.selection_changed.emit()
            self.viewport().update()
        elif g["type"] in ("move", "resize"):
            self._last_undo_tag = None
            self.shapes_changed.emit()
            self.viewport().update()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.image is None:
            return
        pos = self.mapToScene(event.position().toPoint())
        s = self.shape_at(pos)
        if s is not None and s.kind == KIND_ERASE:
            # double-click an erase rect to re-pick its colour
            self._erase_color_menu(s, event.globalPosition().toPoint())
        elif s is not None and s.kind == KIND_HIGHLIGHT:
            self._highlight_color_menu(s, event.globalPosition().toPoint())
        elif s is None:
            # double-click a word on the slide: occlude exactly that word
            self.create_word_box(pos.x(), pos.y())
        event.accept()

    def create_word_box(self, cx: float, cy: float) -> sh.Shape | None:
        """Mask box snapped to the word under (cx, cy); see wordsnap.py."""
        self._last_word_click = (cx, cy)  # for the Ctrl+D debug snapshot
        found = wordsnap.word_box_at(self.image, cx, cy)
        if found is None:
            return None
        (x, y, w, h), _line = found
        self.push_undo()
        s = sh.Shape(kind=KIND_RECT, x=x, y=y, w=w, h=h, snap=SNAP_WORD)
        self.shapes.append(s)
        self.selection = {s.id}
        self._emit_changed()
        return s

    def contextMenuEvent(self, event) -> None:
        if self.image is None:
            return
        pos = self.mapToScene(event.pos())
        s = self.shape_at(pos)
        if s is None:
            return
        if s.id not in self.selection:
            self.selection = {s.id}
            self.selection_changed.emit()
            self.viewport().update()
        if s.kind == KIND_ERASE:
            self._erase_color_menu(s, event.globalPos())
            return
        if s.kind == KIND_HIGHLIGHT:
            self._highlight_color_menu(s, event.globalPos())
            return
        if s.kind == KIND_PATCH:
            menu = QMenu(self)
            act_send = menu.addAction("Send to new card")
            act_home = menu.addAction("Snap back to original position")
            act_del = menu.addAction("Delete\tDel")
            chosen = menu.exec(event.globalPos())
            if chosen == act_send:
                self.send_patch_to_new_card.emit(s.id)
            elif chosen == act_home:
                self.push_undo()
                s.x, s.y = s.sx or 0, s.sy or 0
                self._emit_changed()
            elif chosen == act_del:
                self.delete_selected()
            return
        menu = QMenu(self)
        act_peek = menu.addAction(
            "Stop peeking" if s.id in self.peek_ids else "Peek underneath"
        )
        menu.addSeparator()
        act_group = menu.addAction("Group selected\tG")
        act_ungroup = menu.addAction("Ungroup\tU")
        act_del = menu.addAction("Delete\tDel")
        act_group.setEnabled(
            len([i for i in self.selection if self.shape_by_id(i)]) >= 2
        )
        chosen = menu.exec(event.globalPos())
        if chosen == act_peek:
            self.toggle_peek(s.id)
        elif chosen == act_group:
            self.group_selected()
        elif chosen == act_ungroup:
            self.ungroup_selected()
        elif chosen == act_del:
            self.delete_selected()

    def _highlight_color_menu(self, s: sh.Shape, global_pos) -> None:
        menu = QMenu(self)
        quick = []
        for label, color in HIGHLIGHT_QUICK_COLORS:
            act = menu.addAction(label)
            pix = QPixmap(14, 14)
            pix.fill(QColor(color))
            act.setIcon(QIcon(pix))
            quick.append((act, color))
        act_pick = menu.addAction("Choose colour…")
        menu.addSeparator()
        act_del = menu.addAction("Delete\tDel")
        chosen = menu.exec(global_pos)
        for act, color in quick:
            if chosen == act:
                self.push_undo()
                s.color = color
                self._emit_changed()
                return
        if chosen == act_pick:
            c = QColorDialog.getColor(
                QColor(s.color or self.highlight_fill), self
            )
            if c.isValid():
                self.push_undo()
                s.color = c.name()
                self._emit_changed()
        elif chosen == act_del:
            self.delete_selected()

    def _erase_color_menu(self, s: sh.Shape, global_pos) -> None:
        menu = QMenu(self)
        act_peek = menu.addAction(
            "Stop peeking" if s.id in self.peek_ids else "Peek underneath"
        )
        menu.addSeparator()
        act_majority = menu.addAction("Fill with slide's majority colour")
        act_local = menu.addAction("Sample background around this box")
        act_pick = menu.addAction("Choose colour…")
        menu.addSeparator()
        act_del = menu.addAction("Delete\tDel")
        chosen = menu.exec(global_pos)
        if chosen == act_peek:
            self.toggle_peek(s.id)
        elif chosen == act_majority:
            self.push_undo()
            s.color = self.majority.name()
            self._emit_changed()
        elif chosen == act_local:
            self.push_undo()
            s.color = local_background(self.image, s.x, s.y, s.w, s.h).name()
            self._emit_changed()
        elif chosen == act_pick:
            c = QColorDialog.getColor(QColor(s.color or "#ffffff"), self)
            if c.isValid():
                self.push_undo()
                s.color = c.name()
                self._emit_changed()
        elif chosen == act_del:
            self.delete_selected()

    # ------------------------------------------------------------- key input

    def keyPressEvent(self, event) -> None:
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        step = self.nudge_step_large if shift else self.nudge_step

        if key == Qt.Key.Key_Escape:
            # swallow Esc so it can't close the dialog by accident
            self.gesture = None
            self.clear_selection()
            self.set_tool(TOOL_SELECT)
            event.accept()
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        elif ctrl and key == Qt.Key.Key_Z and shift:
            self.redo()
        elif ctrl and key == Qt.Key.Key_Z:
            self.undo()
        elif ctrl and key == Qt.Key.Key_Y:
            self.redo()
        elif ctrl and key == Qt.Key.Key_A:
            self.select_all()
        elif ctrl and key == Qt.Key.Key_C:
            self.copy_selection()
        elif ctrl and key == Qt.Key.Key_V:
            self.paste_clipboard()
        elif key == Qt.Key.Key_G:
            self.group_selected()
        elif key == Qt.Key.Key_U:
            self.ungroup_selected()
        elif key == Qt.Key.Key_S:
            self.set_tool(TOOL_SELECT)
        elif key == Qt.Key.Key_R:
            self.set_tool(TOOL_RECT)
        elif key == Qt.Key.Key_C:
            self.set_tool(TOOL_ERASE)
        elif key == Qt.Key.Key_P:
            self.set_tool(TOOL_PATCH)
        elif key == Qt.Key.Key_H:
            self.set_tool(TOOL_HIGHLIGHT)
        elif key == Qt.Key.Key_T:
            self.toggle_xray()
        elif ctrl and key == Qt.Key.Key_D:
            self.copy_wordsnap_debug()
        elif key == Qt.Key.Key_F or key == Qt.Key.Key_0:
            self.fit()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom(1.15)
        elif key == Qt.Key.Key_Minus:
            self.zoom(1 / 1.15)
        elif key == Qt.Key.Key_Left:
            self.nudge_selection(-step, 0)
        elif key == Qt.Key.Key_Right:
            self.nudge_selection(step, 0)
        elif key == Qt.Key.Key_Up:
            self.nudge_selection(0, -step)
        elif key == Qt.Key.Key_Down:
            self.nudge_selection(0, step)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    # ---------------------------------------------------------------- helpers

    def _maybe_start_patch_drag(self, g: dict, event) -> bool:
        if len(g["ids"]) != 1:
            return False
        s = self.shape_by_id(g["ids"][0])
        if s is None or s.kind != KIND_PATCH:
            return False
        if self.viewport().rect().contains(event.position().toPoint()):
            return False
        # put the patch back where the drag started; the drop decides its fate
        ox, oy = g["orig"][s.id]
        s.x, s.y = ox, oy
        self.gesture = None
        self.viewport().update()

        img = self.extract_patch_image(s.id)
        mime = QMimeData()
        mime.setData(PATCH_MIME, s.id.encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        if img is not None:
            drag.setPixmap(
                QPixmap.fromImage(img).scaledToWidth(
                    min(160, max(40, img.width())),
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        drag.exec(Qt.DropAction.MoveAction)
        return True

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return math.hypot(a.x() - b.x(), a.y() - b.y())

    def _clamped_rect(self, r: QRectF) -> QRectF:
        img = QRectF(0, 0, self.image.width(), self.image.height())
        return r.intersected(img)

    def _preview_draw(self, g: dict) -> None:
        # the draw gesture is painted straight from the gesture dict
        self.viewport().update()

    def _update_hover_cursor(self, pos: QPointF) -> None:
        # handles are live in every tool, so hovering the selected shape's
        # edge always offers a resize
        handle = self.handle_at(pos)
        if handle is not None:
            self._set_handles_visible(True)
            self.viewport().setCursor(HANDLE_CURSORS[handle])
            return
        s = self.shape_at(pos)
        single = self.single_selected()
        self._set_handles_visible(
            s is not None and single is not None and s.id == single.id
        )
        if self.tool != TOOL_SELECT:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        elif s is not None and s.id in self.selection:
            self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def _set_handles_visible(self, visible: bool) -> None:
        if visible != self.handles_visible:
            self.handles_visible = visible
            self.viewport().update()

    def _apply_resize(self, g: dict, pos: QPointF) -> None:
        s: sh.Shape = g["shape"]
        ox, oy, ow, oh = g["orig"]
        x0, y0, x1, y1 = ox, oy, ox + ow, oy + oh
        h = g["handle"]
        px = min(max(pos.x(), 0), self.image.width())
        py = min(max(pos.y(), 0), self.image.height())
        if h in (H_TL, H_L, H_BL):
            x0 = px
        if h in (H_TR, H_R, H_BR):
            x1 = px
        if h in (H_TL, H_T, H_TR):
            y0 = py
        if h in (H_BL, H_B, H_BR):
            y1 = py
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0

        line = g.get("wordline")
        if (
            s.snap == SNAP_WORD
            and line is not None
            and h in (H_L, H_R, H_TL, H_TR, H_BL, H_BR)
        ):
            # word boxes resize word-by-word HORIZONTALLY: every word the
            # drag touches is covered completely, none half-covered. The
            # vertical extent stays under the user's control (top/bottom
            # handles resize freely, side handles leave height alone).
            bx, _by, bw, _bh = wordsnap.snap_box(
                line, x0, x1, anchor_cx=ox + ow / 2
            )
            s.x, s.w = bx, bw
        else:
            s.x = x0
            s.w = max(x1 - x0, MIN_SHAPE_PX)
        s.y = y0
        s.h = max(y1 - y0, MIN_SHAPE_PX)

    # Public paint hook: draw the in-progress shape via the overlay
    def draw_gesture_shape(self, painter: QPainter) -> None:
        pass

    def drawForeground(self, painter: QPainter, rect) -> None:
        # in-progress draw preview
        g = self.gesture
        if g and g["type"] == "draw":
            r = g["rect"]
            if g["kind"] == KIND_ERASE:
                color = (
                    self.erase_color_override.name()
                    if self.erase_color_override is not None
                    else self.majority.name()
                )
                painter.setBrush(QBrush(QColor(color)))
                pen = QPen(QColor(120, 120, 120, 200), 1, Qt.PenStyle.DashLine)
            elif g["kind"] == KIND_PATCH:
                # selection-marquee look while choosing what to snip out
                painter.setBrush(QBrush(QColor(70, 130, 220, 40)))
                pen = QPen(QColor(70, 130, 220), 1, Qt.PenStyle.DashLine)
            elif g["kind"] == KIND_HIGHLIGHT:
                fill = QColor(self.highlight_fill)
                fill.setAlpha(120)
                painter.setBrush(QBrush(fill))
                pen = QPen(QColor(0, 0, 0, 60), 1)
            else:
                fill = QColor(self.mask_fill)
                fill.setAlpha(180)  # see-through while aiming; opaque once placed
                painter.setBrush(QBrush(fill))
                pen = QPen(QColor(0, 0, 0, 130), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(r)
