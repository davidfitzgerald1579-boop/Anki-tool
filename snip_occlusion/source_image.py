"""The full snip behind a batch of AI card suggestions.

When a suggested card is added as a text note, the snip it was
generated from goes along in the note's Source field, so the whole
slide can be pulled up during review ("Reveal source" on the card
back). One SourceImage is shared by every suggestion from the same
snip and is written to the media collection at most once - lazily,
when the first card that uses it is added - so skipped suggestions
never cost a media file.

No aqt imports (only qtshim + a `col` parameter), so this stays
testable outside Anki like notes.py.
"""

from __future__ import annotations

import uuid

from .qtshim import *  # noqa: F401,F403


class SourceImage:
    def __init__(self, image):
        self._image = image  # QImage; only ever read, never modified
        self._fname: str | None = None

    def media_fname(self, col) -> str | None:
        """The image's filename in the media collection, writing it on
        first use. None when there is no usable image."""
        if self._fname is not None:
            return self._fname
        img = self._image
        if img is None or img.isNull():
            return None
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        ok = img.save(buf, "PNG")
        buf.close()
        if not ok:
            return None
        self._fname = col.media.write_data(
            "snip-occlusion-src-%s.png" % uuid.uuid4().hex[:10],
            bytes(buf.data()),
        )
        return self._fname

    def html(self, col) -> str:
        """Field-ready HTML embedding the image ('' when unusable)."""
        fname = self.media_fname(col)
        return '<img src="%s">' % fname if fname else ""


def as_field_html(source, col) -> str:
    """Source-field HTML for whatever provenance a card carries.

    `source` is None (no snip - e.g. pasted-lesson cards), a ready
    HTML string (a redeploy reusing the original note's source), or a
    SourceImage (written to media on this first use).
    """
    if source is None:
        return ""
    if isinstance(source, str):
        return source
    return source.html(col)
