"""Card template (front/back/CSS) for the Snip Occlusion note type.

Masks are stored as normalized JSON in the Masks field and rendered at review
time as percentage-positioned divs over the image, so cards look right at any
window size and on AnkiDroid / AnkiMobile without any add-on installed on the
reviewing device.

Modes:
- hag1 "Hide All, Guess One": question masks every shape and highlights the
  target group; answer reveals the target, other masks stay (click to peek).
- hog1 "Hide One, Guess One": question masks only the target group; answer
  reveals it.
"""

_SHARED_JS = """
<script>
(function () {
  function txt(id) {
    var e = document.getElementById(id);
    return e ? e.textContent.replace(/\\s+/g, " ").trim() : "";
  }
  var wrap = document.getElementById("io-wrap");
  var raw = document.getElementById("io-payload");
  if (!wrap || !raw) { return; }
  var img = wrap.querySelector("img");
  if (!img) { return; }
  var data;
  try { data = JSON.parse(raw.textContent); } catch (e) { return; }
  var target = txt("io-target");
  var mode = txt("io-mode") || "hag1";
  var side = window.IO_SIDE || "q";
  var old = wrap.querySelectorAll(".io-box");
  for (var i = 0; i < old.length; i++) {
    old[i].parentNode.removeChild(old[i]);
  }
  var shapes = (data && data.shapes) || [];
  for (var j = 0; j < shapes.length; j++) {
    var s = shapes[j];
    var isTarget = s.group === target;
    var cls = null;
    if (side === "q") {
      if (mode === "hag1") {
        cls = isTarget ? "io-box io-mask io-target" : "io-box io-mask";
      } else if (isTarget) {
        cls = "io-box io-mask io-target";
      }
    } else {
      if (isTarget) {
        cls = "io-box io-revealed";
      } else if (mode === "hag1") {
        cls = "io-box io-mask io-peekable";
      }
    }
    if (!cls) { continue; }
    var d = document.createElement("div");
    d.className = cls + (s.kind === "ellipse" ? " io-ellipse" : "");
    d.style.left = (s.x * 100) + "%";
    d.style.top = (s.y * 100) + "%";
    d.style.width = (s.w * 100) + "%";
    d.style.height = (s.h * 100) + "%";
    if (cls.indexOf("io-peekable") >= 0) {
      d.addEventListener("click", function (ev) {
        ev.target.classList.toggle("io-peek");
      });
    }
    wrap.appendChild(d);
  }
})();
</script>
"""

_BODY = """{{#Header}}<div class="io-header">{{Header}}</div>{{/Header}}
<div class="io-wrap" id="io-wrap">{{Image}}</div>
%(extra)s
<div id="io-payload" style="display:none">{{Masks}}</div>
<div id="io-target" style="display:none">{{Target}}</div>
<div id="io-mode" style="display:none">{{Mode}}</div>
<script>window.IO_SIDE = "%(side)s";</script>
"""

FRONT = (_BODY % {"side": "q", "extra": ""}) + _SHARED_JS

BACK = (
    _BODY
    % {
        "side": "a",
        "extra": '{{#Footer}}<div class="io-footer">{{Footer}}</div>{{/Footer}}',
    }
    + _SHARED_JS
    + """
<div class="io-hint">Click a mask to peek underneath.</div>
"""
)

_CSS = """.card {
  font-family: arial, sans-serif;
  font-size: 20px;
  text-align: center;
  color: black;
  background-color: white;
}
.io-wrap {
  position: relative;
  display: inline-block;
  max-width: 100%%;
  line-height: 0;
}
.io-wrap img {
  max-width: 100%%;
  height: auto;
  display: block;
}
.io-box {
  position: absolute;
  box-sizing: border-box;
}
.io-mask {
  background: %(mask_fill)s;
  border: 1px solid rgba(0, 0, 0, 0.35);
}
.io-mask.io-target {
  background: %(target_fill)s;
  border-color: rgba(0, 0, 0, 0.5);
}
.io-ellipse {
  border-radius: 50%%;
}
.io-revealed {
  background: transparent;
  border: 2px dashed #2f9e44;
}
.io-peekable {
  cursor: pointer;
}
.io-peek {
  opacity: 0.12;
}
.io-header {
  font-size: 1.05em;
  font-weight: 600;
  margin-bottom: 6px;
}
.io-footer {
  margin-top: 10px;
  font-size: 0.95em;
  color: #555;
}
.io-hint {
  margin-top: 8px;
  font-size: 0.7em;
  color: #999;
}
.night_mode .io-footer { color: #aaa; }
.night_mode .io-hint { color: #777; }
"""


def build_css(mask_fill: str, target_fill: str) -> str:
    return _CSS % {"mask_fill": mask_fill, "target_fill": target_fill}


# ------------------------------------------------ simple text card ("Basic")

BASIC_FRONT = "{{Front}}"

# The full snip the card was generated from, tucked behind a "Reveal
# source" button on the back. <details>/<summary> needs no JavaScript,
# so it works on AnkiDroid and AnkiMobile exactly like on desktop.
# Appended to the back template of pre-existing note types by
# notes.ensure_basic_note_type, so keep it self-contained.
BASIC_SOURCE_BLOCK = """{{#Source}}<details class="sn-source">
<summary>&#128269; Reveal source</summary>
<div class="sn-source-wrap">{{Source}}</div>
</details>{{/Source}}
"""

BASIC_BACK = (
    """{{FrontSide}}
<hr id=answer>
{{Back}}
{{#Notes}}<div class="sn-notes">{{Notes}}</div>{{/Notes}}
"""
    + BASIC_SOURCE_BLOCK
)

BASIC_SOURCE_CSS = """.sn-source {
  margin-top: 16px;
}
.sn-source summary {
  display: inline-block;
  list-style: none;
  cursor: pointer;
  font-size: 0.7em;
  color: #666;
  border: 1px solid #bbb;
  border-radius: 6px;
  padding: 4px 12px;
  -webkit-user-select: none;
  user-select: none;
}
.sn-source summary::-webkit-details-marker { display: none; }
.sn-source[open] summary { color: #333; border-color: #888; }
.sn-source .sn-source-wrap { margin-top: 10px; line-height: 0; }
.sn-source img { max-width: 100%; height: auto; }
.night_mode .sn-source summary { color: #aaa; border-color: #555; }
.night_mode .sn-source[open] summary { color: #ddd; border-color: #888; }
"""

BASIC_CSS = (
    """.card {
  font-family: arial, sans-serif;
  font-size: 20px;
  text-align: center;
  color: black;
  background-color: white;
}
.sn-notes {
  margin-top: 18px;
  padding-top: 10px;
  border-top: 1px dashed #bbb;
  font-size: 0.8em;
  color: #666;
}
.night_mode .sn-notes { color: #aaa; border-top-color: #555; }
"""
    + BASIC_SOURCE_CSS
)
