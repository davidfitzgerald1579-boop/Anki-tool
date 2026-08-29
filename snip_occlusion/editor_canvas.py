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
from .color_utils import local_background, majority_color
from .consts import (
    GROUP_PALETTE,
    KIND_ELLIPSE,
    KIND_ERASE,
    KIND_PATCH,
    KIND_RECT,
    MASK_KINDS,
    MIN_SHAPE_PX,
    TOOL_ERASE,
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
        return QRectF(0, 0, c.image.width(), c.image.height())

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

            fill = QColor(c.mask_fill)  # fully opaque: masks must hide text
            painter.setBrush(QBrush(fill))
            pen = QPen(QColor(0, 0, 0, 110), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            if s.kind == KIND_ELLIPSE:
                painter.drawEllipse(rect)
            else:
                painter.drawRect(rect)

            if s.group:
                idx = badge_order.get(s.group, 1)
                self._paint_badge(painter, rect, idx, scale)

        # selection outlines
        sel_pen = QPen(QColor("#1a73e8"), 2)
        sel_pen.setCosmetic(True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(sel_pen)
        for s in c.shapes:
            if s.id in c.selection:
                rect = QRectF(s.x, s.y, s.w, s.h)
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

    def _paint_badge(
        self, painter: QPainter, rect: QRectF, idx: int, scale: float
    ) -> None:
        color = QColor(GROUP_PALETTE[(idx - 1) % len(GROUP_PALETTE)])
        r = 9.0 / scale
        cx = rect.x() + r + 2.0 / scale
        cy = rect.y() + r + 2.0 / scale
        painter.save()
        painter.setBrush(QBrush(color))
        pen = QPen(QColor(255, 255, 255, 220), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawEllipse(QPointF(cx, cy), r, r)
        painter.setPen(QPen(QColor("#ffffff")))
        f = painter.font()
        f.setPixelSize(max(2, int(11.0 / scale)))
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(
            QRectF(cx - r, cy - r, 2 * r, 2 * r),
            Qt.AlignmentFlag.AlignCenter,
            str(idx),
        )
        painter.restore()


class OcclusionCanvas(QGraphicsView):
    shapes_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    tool_changed = pyqtSignal(str)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.mask_fill = config.get("mask_fill", "#FFEBA2")
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
        self._group_counter = 0
        self._undo: list = []
        self._redo: list = []
        self._last_undo_tag: str | None = None
        self._pan_origin: QPoint | None = None
        self._user_zoomed = False

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._overlay = _OverlayItem(self)

        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setBackgroundBrush(QBrush(QColor("#3b3b3b")))
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
        self._overlay = _OverlayItem(self)
        self._scene.addItem(self._overlay)
        self._scene.setSceneRect(
            QRectF(0, 0, self.image.width(), self.image.height())
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

    def group_selected(self) -> bool:
        members = [
            s
            for s in self.shapes
            if s.id in self.selection and s.kind in MASK_KINDS
        ]
        if len(members) < 2:
            return False
        self.push_undo()
        self._group_counter += 1
        gid = "g%d" % self._group_counter
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

    def nudge_selection(self, dx: float, dy: float) -> None:
        if not self.selection or self.image is None:
            return
        self.push_undo(tag="nudge")
        for s in self.shapes:
            if s.id in self.selection:
                s.x, s.y, s.w, s.h = sh.clamp_rect(
                    s.x + dx,
                    s.y + dy,
                    s.w,
                    s.h,
                    self.image.width(),
                    self.image.height(),
                )
        self._emit_changed()

    def _emit_changed(self) -> None:
        self.shapes_changed.emit()
        self.selection_changed.emit()
        self.viewport().update()

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
        self.fitInView(
            self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
        )
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

        if self.tool in (TOOL_RECT, TOOL_ERASE, TOOL_PATCH):
            kind = {
                TOOL_RECT: KIND_RECT,
                TOOL_ERASE: KIND_ERASE,
                TOOL_PATCH: KIND_PATCH,
            }[self.tool]
            self.gesture = {
                "type": "draw",
                "kind": kind,
                "origin": pos,
                "rect": QRectF(pos, pos),
            }
            event.accept()
            return

        # select tool
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
            event.accept()
            return

        s = self.shape_at(pos)
        if s is not None:
            if shift:
                # Shift+click ONLY toggles selection - it can never drag, so
                # building up a group selection can't nudge shapes around.
                if s.id in self.selection:
                    self.selection.discard(s.id)
                else:
                    self.selection.add(s.id)
                self.selection_changed.emit()
                self.viewport().update()
                event.accept()
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
            dx = pos.x() - g["press"].x()
            dy = pos.y() - g["press"].y()
            for sid, (ox, oy) in g["orig"].items():
                s = self.shape_by_id(sid)
                if s is None:
                    continue
                s.x, s.y, s.w, s.h = sh.clamp_rect(
                    ox + dx,
                    oy + dy,
                    s.w,
                    s.h,
                    self.image.width(),
                    self.image.height(),
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
        # double-click an erase rect to re-pick its colour
        if self.image is None:
            return
        pos = self.mapToScene(event.position().toPoint())
        s = self.shape_at(pos)
        if s is not None and s.kind == KIND_ERASE:
            self._erase_color_menu(s, event.globalPosition().toPoint())
        event.accept()

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
        if s.kind == KIND_PATCH:
            menu = QMenu(self)
            act_home = menu.addAction("Snap back to original position")
            act_del = menu.addAction("Delete\tDel")
            chosen = menu.exec(event.globalPos())
            if chosen == act_home:
                self.push_undo()
                s.x, s.y = s.sx or 0, s.sy or 0
                self._emit_changed()
            elif chosen == act_del:
                self.delete_selected()
            return
        menu = QMenu(self)
        act_group = menu.addAction("Group selected\tG")
        act_ungroup = menu.addAction("Ungroup\tU")
        act_del = menu.addAction("Delete\tDel")
        act_group.setEnabled(
            len([i for i in self.selection if self.shape_by_id(i)]) >= 2
        )
        chosen = menu.exec(event.globalPos())
        if chosen == act_group:
            self.group_selected()
        elif chosen == act_ungroup:
            self.ungroup_selected()
        elif chosen == act_del:
            self.delete_selected()

    def _erase_color_menu(self, s: sh.Shape, global_pos) -> None:
        menu = QMenu(self)
        act_majority = menu.addAction("Fill with slide's majority colour")
        act_local = menu.addAction("Sample background around this box")
        act_pick = menu.addAction("Choose colour…")
        menu.addSeparator()
        act_del = menu.addAction("Delete\tDel")
        chosen = menu.exec(global_pos)
        if chosen == act_majority:
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
        if self.tool != TOOL_SELECT:
            self._set_handles_visible(False)
            return
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
        if s is not None and s.id in self.selection:
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
        s.x, s.y = x0, y0
        s.w, s.h = max(x1 - x0, MIN_SHAPE_PX), max(y1 - y0, MIN_SHAPE_PX)

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
            else:
                fill = QColor(self.mask_fill)
                fill.setAlpha(180)  # see-through while aiming; opaque once placed
                painter.setBrush(QBrush(fill))
                pen = QPen(QColor(0, 0, 0, 130), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(r)
