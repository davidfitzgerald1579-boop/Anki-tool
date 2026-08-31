"""OCR pipeline: extract searchable text from the baked card image.

The text goes into the note's "Search Text" field so Anki's search (and
deck-search add-ons) can find image-only cards. It is never displayed.

Backends, tried in order under "auto":

- windows: the OCR engine built into Windows 10/11 (Windows.Media.Ocr),
  driven through a bundled PowerShell script - zero installs for the user.
- tesseract: used if a tesseract binary is installed/configured; supports
  a user-words file to bias recognition toward legal vocabulary.

Neither engine is trainable, so accuracy work happens in two places we DO
control: a corrections map in the add-on config (misread -> correct word,
applied to every future card), and the "OCR preview" button in the dialog
for spot-checking what the engine reads on real slides.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from .qtshim import QImage, Qt

# Windows.Media.Ocr rejects very large bitmaps; downscale a COPY for OCR
# only (the card image itself is never touched).
_MAX_OCR_DIM = 2400

_ADDON_DIR = os.path.dirname(__file__)
_PS_SCRIPT = os.path.join(_ADDON_DIR, "ocr.ps1")

# Windows: stop the PowerShell child process flashing a console window
_CREATE_NO_WINDOW = 0x08000000


def available_backend(config: dict) -> str:
    """Which OCR backend would run: 'windows', 'tesseract', or 'none'."""
    choice = config.get("ocr_backend", "auto")
    if choice == "none":
        return "none"
    if choice in ("auto", "windows") and sys.platform == "win32":
        return "windows"
    tess = _tesseract_binary(config)
    if choice in ("auto", "tesseract") and tess:
        return "tesseract"
    return "none"


def _tesseract_binary(config: dict) -> str | None:
    configured = (config.get("tesseract_path") or "").strip()
    if configured and os.path.exists(configured):
        return configured
    return shutil.which("tesseract")


def _scaled_for_ocr(img: QImage) -> QImage:
    if max(img.width(), img.height()) > _MAX_OCR_DIM:
        return img.scaled(
            _MAX_OCR_DIM,
            _MAX_OCR_DIM,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return img


def _prepare_ocr_png(img: QImage, path: str) -> None:
    _scaled_for_ocr(img).save(path, "PNG")


def _run_windows(png_path: str) -> str:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            _PS_SCRIPT,
            png_path,
        ],
        capture_output=True,
        timeout=30,
        creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Windows OCR failed: %s" % proc.stderr.decode("utf-8", "replace")
        )
    return proc.stdout.decode("utf-8", "replace")


def _run_tesseract(png_path: str, config: dict) -> str:
    binary = _tesseract_binary(config)
    cmd = [binary, png_path, "stdout"]
    user_words = (config.get("tesseract_user_words") or "").strip()
    if user_words and os.path.exists(user_words):
        cmd += ["--user-words", user_words]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        timeout=60,
        creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "tesseract failed: %s" % proc.stderr.decode("utf-8", "replace")
        )
    return proc.stdout.decode("utf-8", "replace")


def _run_windows_words(png_path: str) -> list:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            _PS_SCRIPT,
            png_path,
            "-Words",
        ],
        capture_output=True,
        timeout=30,
        creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Windows OCR failed: %s" % proc.stderr.decode("utf-8", "replace")
        )
    words = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            words.append(
                {
                    "t": str(data["t"]),
                    "x": int(data["x"]),
                    "y": int(data["y"]),
                    "w": int(data["w"]),
                    "h": int(data["h"]),
                    "l": int(data["l"]),
                }
            )
        except (ValueError, KeyError, TypeError):
            continue
    return words


def _parse_tesseract_tsv(tsv: str) -> list:
    """Word boxes from `tesseract ... tsv` output (level-5 rows)."""
    words = []
    lines_seen: dict = {}
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        text = cols[11].strip()
        if not text:
            continue
        line_key = (cols[1], cols[2], cols[3], cols[4])  # page/block/par/line
        line_id = lines_seen.setdefault(line_key, len(lines_seen))
        try:
            words.append(
                {
                    "t": text,
                    "x": int(cols[6]),
                    "y": int(cols[7]),
                    "w": int(cols[8]),
                    "h": int(cols[9]),
                    "l": line_id,
                }
            )
        except ValueError:
            continue
    return words


def _run_tesseract_words(png_path: str, config: dict) -> list:
    binary = _tesseract_binary(config)
    proc = subprocess.run(
        [binary, png_path, "stdout", "tsv"],
        capture_output=True,
        timeout=60,
        creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "tesseract failed: %s" % proc.stderr.decode("utf-8", "replace")
        )
    return _parse_tesseract_tsv(proc.stdout.decode("utf-8", "replace"))


def extract_words(img: QImage, config: dict):
    """(word boxes, the scaled image they refer to) - ([], None) if
    the backend can't provide boxes.

    Each word is {"t": text, "x","y","w","h": box, "l": line index},
    in the coordinate space of the returned (possibly downscaled)
    image, so pixel colours can be sampled from it directly.
    """
    backend = available_backend(config)
    if backend == "none":
        return [], None
    scaled = _scaled_for_ocr(img)
    fd, png_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        scaled.save(png_path, "PNG")
        if backend == "windows":
            words = _run_windows_words(png_path)
        else:
            words = _run_tesseract_words(png_path, config)
    finally:
        try:
            os.unlink(png_path)
        except OSError:
            pass
    return words, scaled


def apply_corrections(text: str, corrections: dict) -> str:
    """Whole-word replacements from the config's ocr_corrections map.

    Keys are the misread strings, values the corrections, e.g.
    {"K80": "KBD", "UTlAC": "UTIAC"}. Applied to every card, so one fix
    during a review session repairs that misread forever.
    """
    for wrong, right in corrections.items():
        if not wrong:
            continue
        text = re.sub(
            r"(?<!\w)%s(?!\w)" % re.escape(wrong), right, text
        )
    return text


def _normalize(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def extract_text(img: QImage, config: dict) -> str:
    """OCR the image and return cleaned, corrected text ('' if no backend)."""
    backend = available_backend(config)
    if backend == "none":
        return ""
    fd, png_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        _prepare_ocr_png(img, png_path)
        if backend == "windows":
            raw = _run_windows(png_path)
        else:
            raw = _run_tesseract(png_path, config)
    finally:
        try:
            os.unlink(png_path)
        except OSError:
            pass
    corrections = config.get("ocr_corrections") or {}
    if isinstance(corrections, str):  # tolerate a JSON string in config
        try:
            corrections = json.loads(corrections)
        except ValueError:
            corrections = {}
    return apply_corrections(_normalize(raw), corrections)
