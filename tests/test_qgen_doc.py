"""Tests for splitting pasted documents into generation chunks."""

from snip_occlusion import qgen_doc

SAMPLE = """The criminal courts

In this element you will explore the nature of the criminal law and the
structure of the criminal court system.

What is criminal law?

Criminal law is part of public law, that is to say the law which concerns
the relationship between the individual and the State.

Criminal cases are brought by the prosecution, representing the State,
against the defendant (sometimes referred to as 'the accused').

Standard and burden of proof

The standard of proof means the level of certainty to which a party must
prove their case in order to succeed at trial.

In criminal law, the standard of proof is "beyond reasonable doubt".

With some exceptions, the prosecution, as initiator of the action, bears
the burden of proof in criminal proceedings.

The Magistrates' Court

The Magistrates' Court is the lowest level of court in the hierarchy of
criminal courts. Virtually all criminal cases start in the Magistrates'
Court, and around 95% will end there.

The Magistrates have the power to impose an unlimited fine and/or impose
a maximum prison sentence of 12 months for a single either way offence.
"""


def test_chunks_cover_all_text_and_break_at_headings():
    chunks = qgen_doc.split_into_chunks(SAMPLE, target=400, hard=800)
    assert len(chunks) >= 2
    joined = "\n\n".join(chunks)
    # nothing lost: every paragraph survives somewhere
    for fragment in (
        "beyond reasonable doubt",
        "Magistrates' Court is the lowest level",
        "unlimited fine",
        "part of public law",
    ):
        assert fragment in joined
    # headings start sections rather than dangling at a chunk's end
    for chunk in chunks:
        assert not chunk.rstrip().endswith("The Magistrates' Court")
    # a heading is kept with the text that follows it
    for chunk in chunks:
        if "Standard and burden of proof" in chunk:
            assert "level of certainty" in chunk


def test_chunks_respect_hard_cap():
    text = "\n\n".join("Sentence %d about the law." % i for i in range(200))
    chunks = qgen_doc.split_into_chunks(text, target=300, hard=500)
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(chunks).count("Sentence") == 200


def test_single_oversized_paragraph_is_one_chunk():
    text = "word " * 1000  # no paragraph breaks to split at
    chunks = qgen_doc.split_into_chunks(text.strip())
    assert len(chunks) == 1


def test_empty_and_whitespace():
    assert qgen_doc.split_into_chunks("") == []
    assert qgen_doc.split_into_chunks("  \n\n  ") == []


def test_heading_detection():
    assert qgen_doc._is_heading("The Crown Court")
    assert not qgen_doc._is_heading("This is a sentence about the court.")
    assert not qgen_doc._is_heading("A heading would not end like this:")
