"""Pure-Python shape model shared by the editor canvas and note builder.

Coordinates are stored in image pixel space. `normalized_payload` converts to
fractions of the image size so the card templates can position masks with
percentage-based CSS and stay correct at any display size or device.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .consts import KIND_ERASE, KIND_PATCH, MASK_KINDS


def new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Shape:
    kind: str  # "rect" | "ellipse" | "erase" | "patch"
    x: float
    y: float
    w: float
    h: float
    id: str = field(default_factory=new_id)
    group: Optional[str] = None  # explicit group id, None = ungrouped
    color: Optional[str] = None  # fill color for erase shapes ("#rrggbb")
    sx: Optional[float] = None  # patch source rect origin in the image
    sy: Optional[float] = None

    def contains(self, px: float, py: float) -> bool:
        if not (self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h):
            return False
        if self.kind == "ellipse":
            rx, ry = self.w / 2.0, self.h / 2.0
            if rx <= 0 or ry <= 0:
                return False
            nx = (px - (self.x + rx)) / rx
            ny = (py - (self.y + ry)) / ry
            return nx * nx + ny * ny <= 1.0
        return True

    def intersects(self, x: float, y: float, w: float, h: float) -> bool:
        return not (
            self.x + self.w < x
            or x + w < self.x
            or self.y + self.h < y
            or y + h < self.y
        )

    def effective_group(self) -> str:
        """Group used for card generation: explicit group, or a singleton."""
        return self.group if self.group else "s:" + self.id

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "group": self.group,
        }
        if self.color:
            d["color"] = self.color
        if self.sx is not None:
            d["sx"] = self.sx
            d["sy"] = self.sy
        return d

    @staticmethod
    def from_dict(d: dict) -> "Shape":
        return Shape(
            kind=d["kind"],
            x=d["x"],
            y=d["y"],
            w=d["w"],
            h=d["h"],
            id=d.get("id") or new_id(),
            group=d.get("group"),
            color=d.get("color"),
            sx=d.get("sx"),
            sy=d.get("sy"),
        )


def mask_shapes(shapes: list) -> list:
    """Shapes that occlude content and generate cards."""
    return [s for s in shapes if s.kind in MASK_KINDS]


def erase_shapes(shapes: list) -> list:
    return [s for s in shapes if s.kind == KIND_ERASE]


def patch_shapes(shapes: list) -> list:
    return [s for s in shapes if s.kind == KIND_PATCH]


def layer_of(shape: Shape) -> int:
    """Paint order: erase fills at the bottom, patches above them (so a
    moved snippet can sit on covered-up text), masks on top."""
    if shape.kind == KIND_ERASE:
        return 0
    if shape.kind == KIND_PATCH:
        return 1
    return 2


def target_groups(shapes: list) -> list:
    """Unique card targets in creation order (one card per group)."""
    seen: list = []
    for s in mask_shapes(shapes):
        g = s.effective_group()
        if g not in seen:
            seen.append(g)
    return seen


def explicit_group_index(shapes: list) -> dict:
    """Map explicit group id -> 1-based badge number, in first-seen order."""
    order: dict = {}
    for s in shapes:
        if s.kind in MASK_KINDS and s.group and s.group not in order:
            order[s.group] = len(order) + 1
    return order


def normalized_payload(shapes: list, img_w: int, img_h: int) -> dict:
    """Mask shapes as fractions of the image size, for the card template."""
    out = []
    for s in mask_shapes(shapes):
        out.append(
            {
                "id": s.id,
                "kind": s.kind,
                "x": round(s.x / img_w, 5),
                "y": round(s.y / img_h, 5),
                "w": round(s.w / img_w, 5),
                "h": round(s.h / img_h, 5),
                "group": s.effective_group(),
            }
        )
    return {"version": 1, "shapes": out}


def payload_json(shapes: list, img_w: int, img_h: int) -> str:
    return json.dumps(
        normalized_payload(shapes, img_w, img_h), separators=(",", ":")
    )


def serialize(shapes: list) -> str:
    """Full editor state (including erase shapes) for undo snapshots."""
    return json.dumps([s.to_dict() for s in shapes], separators=(",", ":"))


def deserialize(data: str) -> list:
    return [Shape.from_dict(d) for d in json.loads(data)]


def clamp_rect(
    x: float, y: float, w: float, h: float, img_w: float, img_h: float
):
    """Clamp a rect (keeping its size where possible) inside the image."""
    w = min(w, img_w)
    h = min(h, img_h)
    x = min(max(x, 0.0), img_w - w)
    y = min(max(y, 0.0), img_h - h)
    return x, y, w, h
