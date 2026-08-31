"""Tests for tracing cards back to their source sentences."""

from snip_occlusion import qgen_trace

SOURCE = """The criminal courts

Criminal cases are brought by the prosecution, representing the State,
against the defendant. The prosecution bears the burden of proof.

The Magistrates' Court

The Magistrates' Court is the lowest level of court in the hierarchy of
criminal courts. The Magistrates have the power to impose an unlimited
fine and a maximum prison sentence of 12 months. Appeals go to the
Crown Court."""


def test_matching_sentences_highlighted():
    card = {
        "front": "What sentencing powers do the Magistrates have?",
        "back": "An unlimited fine and a maximum prison sentence of "
        "12 months.",
    }
    html, matches, _n = qgen_trace.highlight_html(card, SOURCE)
    assert matches >= 1
    # the sentencing sentence is highlighted; unrelated ones are not
    assert "unlimited\nfine" not in html  # sanity: html is space-joined
    start = html.index(qgen_trace.HIGHLIGHT_STYLE)
    highlighted = html[start : html.index("</span>", start)]
    assert "unlimited" in highlighted
    assert "burden of proof" not in highlighted
    # full text is present either way
    assert "prosecution" in html and "hierarchy" in html


def test_unrelated_card_reports_no_match():
    card = {
        "front": "What is the priority of a second registered mortgage?",
        "back": "It ranks behind unless the lender agreed otherwise.",
    }
    html, matches, _n = qgen_trace.highlight_html(card, SOURCE)
    assert matches == 0
    assert qgen_trace.HIGHLIGHT_STYLE not in html


def test_best_single_sentence_fallback():
    # shares only 1-2 words with any sentence: highlight the best one
    card = {"front": "Who is the defendant?", "back": "The accused person."}
    html, matches, _n = qgen_trace.highlight_html(card, SOURCE)
    assert matches >= 1


def test_html_is_escaped_and_capped():
    source = " ".join(
        "The prosecution bears the burden of proof in sentence %d." % i
        for i in range(30)
    )
    card = {"front": "<b>Who bears the burden of proof?</b>", "back": "The prosecution."}
    html, matches, _n = qgen_trace.highlight_html(card, source)
    assert matches <= qgen_trace.MAX_HIGHLIGHTS
    assert "<b>" not in html.replace("<br>", "")  # user text escaped


def test_empty_inputs():
    assert qgen_trace.highlight_html({}, "")[1:] == (0, None)
    assert qgen_trace.highlight_html({"front": "Q", "back": "A"}, "")[1:] == (0, None)


def test_notes_traced_separately_in_orange():
    card = {
        "front": "Which court hears appeals from the Magistrates?",
        "back": "The Crown Court.",
        "notes": "Appeals go to the Crown Court.",
    }
    html, _m, notes_matches = qgen_trace.highlight_html(card, SOURCE)
    assert notes_matches >= 1
    start = html.index(qgen_trace.NOTE_HIGHLIGHT_STYLE)
    highlighted = html[start : html.index("</span>", start)]
    assert "Appeals" in highlighted


def test_invented_notes_report_zero_matches():
    card = {
        "front": "Who bears the burden of proof?",
        "back": "The prosecution.",
        "notes": "Woolmington v DPP [1935] established the golden thread.",
    }
    html, main_matches, notes_matches = qgen_trace.highlight_html(card, SOURCE)
    assert main_matches >= 1  # the Q/A is genuinely from the text
    assert notes_matches == 0  # the citation is not - likely invented
    assert qgen_trace.NOTE_HIGHLIGHT_STYLE not in html


def test_no_notes_reports_none():
    card = {"front": "Who prosecutes?", "back": "The prosecution."}
    _html, _m, notes_matches = qgen_trace.highlight_html(card, SOURCE)
    assert notes_matches is None
