"""Split a pasted document into model-sized chunks for card generation.

Long study texts (a whole lesson/element) can't go to a local model in
one prompt: prompt processing is slow on CPU and one giant prompt yields
few, shallow cards. Instead the text is split into sections - breaking
preferentially at headings (short lines with no closing punctuation) -
and each chunk is sent to the model separately, so cards stream in
section by section and coverage stays deep.
"""

from __future__ import annotations

import re

TARGET_CHARS = 1400  # aim for chunks around this size
HARD_CHARS = 2600  # never grow a chunk past this by adding a paragraph


def _is_heading(paragraph: str) -> bool:
    return (
        "\n" not in paragraph
        and len(paragraph) < 70
        and not paragraph.rstrip().endswith((".", "!", "?", ":", ";", ","))
    )


def split_into_chunks(
    text: str, target: int = TARGET_CHARS, hard: int = HARD_CHARS
) -> list:
    """Split `text` into chunks of roughly `target` characters.

    Prefers to start a new chunk at a heading once the current chunk has
    reached half the target; always breaks before exceeding `hard`. A
    heading is kept with the section that follows it.
    """
    paragraphs = [
        p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()
    ]
    chunks: list = []
    current = ""
    for paragraph in paragraphs:
        if current and (
            (_is_heading(paragraph) and len(current) >= target // 2)
            or len(current) + len(paragraph) + 2 > hard
        ):
            chunks.append(current)
            current = ""
        current = paragraph if not current else current + "\n\n" + paragraph
    if current:
        chunks.append(current)
    return chunks
