"""Render the card templates in a real browser (as Anki's webview would),
verify mask geometry, and save screenshots to docs/.

Run from the repo root:  python3 tools/render_preview.py
"""

import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from snip_occlusion import template  # noqa: E402
from snip_occlusion.consts import MODE_HIDE_ALL, MODE_HIDE_ONE  # noqa: E402
from snip_occlusion.shapes import Shape, payload_json  # noqa: E402
from slide_fixture import make_slide  # noqa: E402

OUT = ROOT / "docs"
CHROMIUM = "/opt/pw-browsers/chromium"


def render_fields(tmpl: str, fields: dict) -> str:
    """Minimal stand-in for Anki's template renderer (only what we use)."""
    out = tmpl
    for name, value in fields.items():
        if value:
            out = re.sub(r"\{\{#%s\}\}" % name, "", out)
            out = re.sub(r"\{\{/%s\}\}" % name, "", out)
        else:
            out = re.sub(
                r"\{\{#%s\}\}.*?\{\{/%s\}\}" % (name, name),
                "",
                out,
                flags=re.S,
            )
        out = out.replace("{{%s}}" % name, value)
    return out


def build_page(side_tmpl: str, fields: dict, css: str) -> str:
    body = render_fields(side_tmpl, fields)
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        + css
        + "</style></head><body><div class='card'>"
        + body
        + "</div></body></html>"
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication.instance() or QApplication([])  # noqa: F841

    slide = make_slide()
    slide.save(str(OUT / "_slide.png"))
    img_w, img_h = slide.width(), slide.height()

    # masks mirroring how a student would occlude the fixture slide:
    # lines 1+3 grouped, line 2 on its own (the "middle box" case), plus an
    # ellipse
    shapes = [
        Shape(kind="rect", x=396, y=110, w=222, h=26, group="g1"),
        Shape(kind="rect", x=170, y=154, w=200, h=26),
        Shape(kind="rect", x=118, y=198, w=192, h=26, group="g1"),
        Shape(kind="ellipse", x=350, y=240, w=190, h=34),
    ]
    payload = payload_json(shapes, img_w, img_h)
    targets = ["g1", "s:" + shapes[1].id]

    css = template.build_css("#FFEBA2", "#FF7E7E")
    fields_base = {
        "Image": "<img src='_slide.png'>",
        "Header": "Administrative Court",
        "Footer": "Senior Courts Act 1981",
        "Masks": payload,
    }

    cases = [
        ("front_hag1", template.FRONT, MODE_HIDE_ALL, targets[0]),
        ("back_hag1", template.BACK, MODE_HIDE_ALL, targets[0]),
        ("front_hog1", template.FRONT, MODE_HIDE_ONE, targets[1]),
        ("back_hog1", template.BACK, MODE_HIDE_ONE, targets[1]),
    ]
    for name, tmpl, mode, target in cases:
        fields = dict(fields_base, Mode=mode, Target=target)
        (OUT / ("_%s.html" % name)).write_text(
            build_page(tmpl, fields, css), encoding="utf-8"
        )

    from playwright.sync_api import sync_playwright

    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": 900, "height": 700})
        for name, _tmpl, mode, target in cases:
            page.goto("file://" + str(OUT / ("_%s.html" % name)))
            page.wait_for_timeout(120)
            masks = page.query_selector_all(".io-mask")
            revealed = page.query_selector_all(".io-revealed")
            side = "q" if name.startswith("front") else "a"
            n_target = len(
                [s for s in shapes if (s.group or "s:" + s.id) == target]
            )
            n_other = len(shapes) - n_target
            if side == "q" and mode == MODE_HIDE_ALL:
                expect_masks, expect_rev = len(shapes), 0
            elif side == "q":
                expect_masks, expect_rev = n_target, 0
            elif mode == MODE_HIDE_ALL:
                expect_masks, expect_rev = n_other, n_target
            else:
                expect_masks, expect_rev = 0, n_target
            if len(masks) != expect_masks or len(revealed) != expect_rev:
                problems.append(
                    "%s: got %d masks / %d revealed, expected %d / %d"
                    % (name, len(masks), len(revealed), expect_masks, expect_rev)
                )
            # geometry: first shape's mask must sit over the image where the
            # normalized payload says it should
            img_box = page.query_selector("#io-wrap img").bounding_box()
            boxes = masks + revealed
            if boxes:
                s0 = shapes[0]
                found = False
                for b in [el.bounding_box() for el in boxes]:
                    ex = img_box["x"] + s0.x / img_w * img_box["width"]
                    ey = img_box["y"] + s0.y / img_h * img_box["height"]
                    if abs(b["x"] - ex) < 2 and abs(b["y"] - ey) < 2:
                        found = True
                if not found and any(
                    (s0.group or "s:" + s0.id) == target
                    or (side == "q" and mode == MODE_HIDE_ALL)
                    or (side == "a" and mode == MODE_HIDE_ALL)
                    for _ in [0]
                ):
                    problems.append("%s: shape 1 not positioned correctly" % name)
            page.screenshot(path=str(OUT / ("%s.png" % name)))
        browser.close()

    for f in OUT.glob("_*.html"):
        f.unlink()
    if problems:
        print("FAILED:")
        for pr in problems:
            print(" -", pr)
        sys.exit(1)
    print("Card rendering verified; screenshots written to docs/")


if __name__ == "__main__":
    main()
