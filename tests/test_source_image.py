"""SourceImage: lazy, write-once saving of the snip behind AI cards."""

import tempfile
from pathlib import Path

import pytest
from anki.collection import Collection
from PyQt6.QtGui import QImage

from snip_occlusion.source_image import SourceImage, as_field_html


@pytest.fixture
def col():
    tmp = tempfile.mkdtemp()
    c = Collection(str(Path(tmp) / "collection.anki2"))
    yield c
    c.close()


def make_image(w=60, h=40, color=0xFF3366CC):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(color)
    return img


def test_written_to_media_once_and_shared(qapp, col):
    src = SourceImage(make_image())
    fname = src.media_fname(col)
    assert fname and fname.startswith("snip-occlusion-src-")
    assert fname.endswith(".png")
    # the PNG really landed in the media folder and decodes back
    path = Path(col.media.dir()) / fname
    assert path.exists()
    round_trip = QImage(str(path))
    assert (round_trip.width(), round_trip.height()) == (60, 40)
    # every later call (another card from the same snip) reuses the file
    assert src.media_fname(col) == fname
    assert src.html(col) == '<img src="%s">' % fname
    assert len(list(Path(col.media.dir()).glob("*.png"))) == 1


def test_null_or_missing_image_yields_nothing(qapp, col):
    assert SourceImage(None).media_fname(col) is None
    assert SourceImage(None).html(col) == ""
    assert SourceImage(QImage()).html(col) == ""  # isNull() image
    assert list(Path(col.media.dir()).glob("*.png")) == []


def test_rewritten_for_a_different_collection(qapp, col):
    # a profile switch hands the same cached SourceImage a different
    # collection: the PNG must be written there too, never cited broken
    src = SourceImage(make_image())
    fname1 = src.media_fname(col)
    assert (Path(col.media.dir()) / fname1).exists()

    tmp2 = tempfile.mkdtemp()
    col2 = Collection(str(Path(tmp2) / "collection.anki2"))
    try:
        fname2 = src.media_fname(col2)
        assert fname2 and (Path(col2.media.dir()) / fname2).exists()
        # whichever collection asks, the name handed out exists THERE
        again = src.media_fname(col)
        assert again and (Path(col.media.dir()) / again).exists()
    finally:
        col2.close()


def test_as_field_html_for_each_provenance_kind(qapp, col):
    # no provenance (e.g. a pasted-lesson card)
    assert as_field_html(None, col) == ""
    # ready HTML (a redeploy keeping the original note's source)
    ready = '<img src="existing.png">'
    assert as_field_html(ready, col) == ready
    # a live snip: written to media on first use
    html = as_field_html(SourceImage(make_image()), col)
    assert html.startswith('<img src="snip-occlusion-src-')
