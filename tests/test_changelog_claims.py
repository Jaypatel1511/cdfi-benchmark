"""Every quantitative claim this cycle makes lives in CHANGELOG.md.

Rule (j3): GATE THE CHANGELOG, NOT ONLY THE README. The README is the surface
that renders on PyPI and it has had gates for two releases. The CHANGELOG is
where a release's *measurements* actually live -- reach counts, populations,
per-quarter tables -- and through 0.3.2 nothing checked a single one of them.
That is how the 0.3.2 entry came to open with "none of them changed a computed
number" while its own Tier 1 bullet, eighty lines below, said "grades move for
any bank between 8% and 9% at a report date before 2026-07-01".

TWO KINDS OF ASSERTION LIVE HERE, AND THE DIFFERENCE IS THE POINT
-----------------------------------------------------------------
* DERIVED. The Tier 1 re-grade is a MECHANISM, and the mechanism is put through
  the package's own `benchmark_for` / `BenchmarkResult.status` at each report
  date. Move `CBLR_LEVELS` and these go red without anyone editing a number.
  Rule (i): a gate that reads the same declaration the code reads certifies
  consistency, not truth -- so these read no constant the renderer reads; they
  grade values and compare the two REGIMES.
* PINNED. The population counts (how many filers sit in the band) cannot be
  derived without the FDIC universe, and a test must not hit the network. They
  are pinned as data with their retrieval date and the command that re-derives
  them, exactly like `LTD_PEER_VALUES`. The gate's job is to stop the PROSE and
  the PIN drifting apart, and to fail loudly if the mechanism they describe
  stops behaving that way.

`finditer`, never `search`: a prose gate that stops at the first hit passes on a
document whose second occurrence contradicts the first, which is precisely the
shape of the defect this module exists for. And `tests/` is excluded from every
scan, so a gate can hold what it forbids without matching its own text.
"""
import re

import pytest

from cdfibenchmark.data.schema import (
    BenchmarkResult, CBLR_LEVELS, GRADEABLE_BASES, BASIS_FDIC_LEVERAGE,
    benchmark_for, _cblr_at,
)

from . import _layout as layout

_needs_changelog = layout.needs("CHANGELOG.md")


def _changelog() -> str:
    return layout.SURFACES["CHANGELOG.md"].read_text()


def _prose(text: str) -> str:
    """Markdown hard-wrapped at ~78 columns, unwrapped into scannable prose.

    THIS FUNCTION EXISTS BECAUSE ITS ABSENCE PRODUCED A FALSE GREEN IN THIS
    VERY MODULE, on the first run. `test_the_retracted_summary_sentence...`
    scanned for

        "none of them changed a computed number"

    which the CHANGELOG carries as

        > findings are on the face of the document; none of them changed a computed
        > number."*

    -- split by a newline and a blockquote marker. `finditer` found ZERO
    occurrences and the gate passed by matching nothing. A prose gate that
    cannot see a wrapped sentence forbids nothing at all, which is the same
    false-green shape as the two the 0.3.2 round shipped from broken quoting.

    Blockquote markers, list indentation and single newlines collapse to one
    space; blank lines are preserved as paragraph breaks so a +/- window still
    means something.
    """
    text = re.sub(r"\n(?:[ \t]*>)+[ \t]?", "\n", text)   # blockquote markers
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)          # unwrap hard wraps
    return re.sub(r"[ \t]+", " ", text)


def _entry(text: str, version: str = "0.3.2") -> str:
    """Just this release's entry. Earlier entries carry their own headings and
    their own (correct, historical) numbers; a whole-file scan would conflate
    them -- and did, the first time this module's assertions were written."""
    start = text.index(f"## [{version}]")
    rest = text[start + 1:]
    m = re.search(r"^## \[", rest, re.M)
    return text[start:start + 1 + m.start()] if m else text[start:]


# ── F2: the period-aware Tier 1 band, re-derived ─────────────────────────────
#
# Re-measured live against api.fdic.gov on 2026-09-09 from Jay's macOS shell,
# over the ENTIRE filer universe at each REPDTE. Re-derive with:
#
#   filters=ASSET:[1 TO *] AND REPDTE:<repdte>, fields=CERT,REPDTE,RBC1AAJ
#   count rows with 8.0 <= RBC1AAJ < 9.0
#
#: (REPDTE, filers at that period, filers with 8.0 <= RBC1AAJ < 9.0).
TIER1_BAND_REACH = (
    ("20250331", 4536, 538),
    ("20250630", 4494, 505),
    ("20250930", 4452, 466),
    ("20251231", 4411, 469),
    ("20260331", 4353, 418),
    ("20260630", 4313, 386),
)
TIER1_BAND_RETRIEVED = "2026-09-09"

#: The five PRE-EFFECTIVE quarters the entry sums over. The CBLR level drops to
#: 8% for report dates on/after 20260701, so every quarter here is graded at 9%.
PRE_EFFECTIVE_QUARTERS = ("20250630", "20250930", "20251231",
                          "20260331", "20260630")


def _graded(value, report_date):
    """The package's own grade for a Tier 1 leverage ratio at a report date."""
    return BenchmarkResult(
        metric="tier1_ratio", institution_value=value, peer_median=None,
        peer_25th=None, peer_75th=None, peer_count=0,
        basis=BASIS_FDIC_LEVERAGE, report_date=report_date,
    ).status


def test_the_basis_this_module_grades_on_is_actually_gradeable():
    """Otherwise every `_graded` call below returns "N/A" and proves nothing."""
    assert BASIS_FDIC_LEVERAGE in GRADEABLE_BASES


@pytest.mark.parametrize("repdte", PRE_EFFECTIVE_QUARTERS)
def test_the_whole_band_regrades_at_every_pre_effective_quarter(repdte):
    """DERIVED, not declared: 0.3.2 moves this band from STRONG to ADEQUATE.

    0.3.1 graded every report against `good = 8` -- current law, the level the
    flat `_CBLR` string named (a constant 0.3.2 REMOVED; it is named here as
    history, and grepping the tree for it will correctly find nothing) -- so
    anything at or above 8.0 was STRONG. 0.3.2
    resolves the level to the report date, and every quarter here precedes
    2026-07-01, where the level in force is 9%.

    This is what makes the entry's headline claim a measurement rather than an
    assertion: the count is pinned, but that EVERY member of the band flips is
    derived from the package's own grader.
    """
    level, _ = _cblr_at(repdte)
    assert level == 9, (
        f"{repdte} is listed as pre-effective but the resolved CBLR level is "
        f"{level}%; PRE_EFFECTIVE_QUARTERS and CBLR_LEVELS disagree"
    )
    # Walk the band, including both edges and the value just under the top.
    for value in (8.0, 8.01, 8.5, 8.99, 8.999):
        old = "STRONG" if value >= 8 else "ADEQUATE"
        new = _graded(value, repdte)
        assert old == "STRONG", "premise: 0.3.1 graded the whole band STRONG"
        assert new == "ADEQUATE", (
            f"Tier 1 leverage {value}% at {repdte} grades {new} under the "
            f"period-aware band; the entry claims the whole band moves "
            f"STRONG -> ADEQUATE"
        )
    # And the band's exclusive upper edge must NOT move.
    assert _graded(9.0, repdte) == "STRONG", (
        f"9.0% at {repdte} must stay STRONG -- it is the qualifying level, so "
        f"the band that moves is [8.0, 9.0) and the entry says so"
    )


def test_no_grade_moves_once_the_lower_level_takes_effect():
    """The other half of the claim, and the reason the band is bounded in time."""
    eff = CBLR_LEVELS[-1][0]
    assert eff == "20260701", f"CBLR effective date moved to {eff}"
    for value in (8.0, 8.5, 8.99):
        assert _graded(value, "20260930") == "STRONG", (
            "after the effective date the 8% level applies and the band no "
            "longer re-grades; the entry's 'pre-effective' framing depends on it"
        )


def test_the_pinned_sum_is_derived_from_the_pinned_quarters_not_typed():
    """2,244 is an OUTPUT of the table above, never an input beside it."""
    by_date = dict((d, n) for d, _f, n in TIER1_BAND_REACH)
    missing = [q for q in PRE_EFFECTIVE_QUARTERS if q not in by_date]
    assert not missing, f"no pinned measurement for {missing}"
    total = sum(by_date[q] for q in PRE_EFFECTIVE_QUARTERS)
    assert total == 2244, (
        f"the pinned per-quarter counts sum to {total}, but the entry states "
        f"2,244 filer-quarters. One of them is wrong."
    )


@_needs_changelog
def test_the_changelog_states_every_pinned_tier1_figure():
    """The prose and the pin must not drift. Uses `finditer`, not `search`.

    A `search` would stop at the first match and pass on an entry whose second
    mention of the same quarter contradicts the first -- which is the exact
    shape of the defect that opened the 0.3.2 entry.
    """
    entry = _entry(_changelog())
    for repdte, filers, band in TIER1_BAND_REACH:
        assert repdte in entry, f"the entry does not name {repdte}"
        for value in (f"{filers:,}", str(band)):
            hits = list(re.finditer(rf"(?<![\d,.]){re.escape(value)}(?![\d,.])",
                                    entry))
            assert hits, (
                f"the entry does not state {value} for {repdte}; the pinned "
                f"measurement and the prose have drifted"
            )
    hits = list(re.finditer(r"(?<![\d,.])2,244(?![\d,.])", entry))
    assert hits, "the entry does not state the 2,244 filer-quarter total"


@_needs_changelog
def test_the_retracted_summary_sentence_is_gone_or_marked_false():
    """0.3.2 opened by contradicting its own body. It must not still do that.

    "none of them changed a computed number" may survive only inside an
    explicit retraction -- and a retraction must say the thing is wrong within
    sight of it, not two sections away.
    """
    entry = _prose(_entry(_changelog()))
    claim = "none of them changed a computed number"
    for m in re.finditer(re.escape(claim), entry):
        window = entry[max(0, m.start() - 700):m.end() + 700]
        assert re.search(r"\bwrong\b|\bretract|\bcorrection\b", window, re.I), (
            "the entry still asserts that no finding changed a computed "
            "number, with nothing near it saying that is false. Its own Tier 1 "
            "bullet says grades move."
        )


@_needs_changelog
def test_the_prose_unwrapper_can_see_a_hard_wrapped_sentence():
    """Holds the fix for this module's own false green.

    Without `_prose`, the retraction gate below scanned for a sentence the
    CHANGELOG wraps across two lines, found nothing, and passed. This asserts
    the unwrapper sees it -- so the gate that forbids it is forbidding
    something.
    """
    raw = _entry(_changelog())
    claim = "none of them changed a computed number"
    assert claim not in raw, (
        "the claim is no longer hard-wrapped in the document, so this gate no "
        "longer proves the unwrapper is load-bearing -- pick a wrapped "
        "sentence that is still there, or delete this gate deliberately"
    )
    assert claim in _prose(raw), (
        "the unwrapper cannot see a sentence the CHANGELOG hard-wraps, so "
        "every prose gate in this module is passing by matching nothing"
    )


@_needs_changelog
def test_the_entry_states_that_grades_move():
    """The positive form of the gate above: the correction must SAY the thing."""
    entry = _prose(_entry(_changelog()))
    assert list(re.finditer(r"STRONG\s*(?:→|->|to)\s*ADEQUATE", entry)), (
        "the entry never states the direction the Tier 1 grades move in"
    )


# ── The relative-gap reach, and the two counts the audit close measured ──────
#
# Same sweep, same date, same universe. A cell counts only where the renderer
# reaches the sentence: the subject's value is present and the printed
# difference is non-zero. Validated end-to-end against live `build_peer_group`
# + `benchmark_institution` on CERTs 16583 / 13986 / 29966 at 20260630.

#: (REPDTE, negative-median cells, zero-median cells, rounds-to-zero cells).
RELATIVE_GAP_REACH = (
    ("20260630", 0, 3, 0),
    ("20260331", 10, 4, 0),
    ("20251231", 0, 7, 0),
    ("20250930", 0, 15, 0),
    ("20250630", 0, 9, 0),
    ("20250331", 0, 4, 7),
)

#: (REPDTE, cells rendering a relative magnitude of exactly 0.0 beside a
#: direction word). New in 0.3.2; fixed at the audit close.
ZERO_MAGNITUDE_REACH = (("20260630", 14), ("20260331", 15),
                        ("20251231", 20), ("20250331", 13))

#: (REPDTE, subject-metric cells with 0 < peer_count < 10 while the GROUP
#: itself clears the 10-peer floor, so no caveat is rendered, subjects).
#: The F4 known issue. NOT fixed this round -- disclosed.
THIN_METRIC_CELLS = (("20260630", 45, 17), ("20260331", 45, 18),
                     ("20251231", 42, 18), ("20250930", 47, 20),
                     ("20250630", 42, 19), ("20250331", 44, 17))


@_needs_changelog
def test_the_changelog_states_the_relative_gap_reach():
    entry = _entry(_changelog())
    for repdte, neg, zero, r2z in RELATIVE_GAP_REACH:
        assert repdte in entry, f"the entry does not name {repdte}"
        for value in (neg, zero, r2z):
            if value == 0:
                continue
            assert list(re.finditer(rf"(?<![\d,.]){value}(?![\d,.])", entry)), (
                f"the entry does not state {value} anywhere, but the pinned "
                f"sweep records it for {repdte}"
            )


def test_the_release_period_row_is_what_makes_this_a_blocker():
    """DERIVED from the pin: at 20260630 the old sentence was ALWAYS false.

    If the negative case were live at the release period, the shipped sentence
    would have been true some of the time and this would be a 0.3.3 item.
    """
    row = dict((r[0], r) for r in RELATIVE_GAP_REACH)["20260630"]
    _, negative, zero, rounds_to_zero = row
    assert negative == 0, (
        f"the pin says the negative case fires {negative} times at 20260630; "
        f"the entry's blocker argument assumes 0"
    )
    assert zero + rounds_to_zero > 0, (
        "no false-sentence case fires at the release period, so the entry's "
        "claim that it was false every time it rendered is unsupported"
    )


@_needs_changelog
def test_the_changelog_discloses_the_per_metric_peer_count_issue():
    """F4 is NOT fixed this round, so the disclosure carries the whole weight.

    It must name the mechanism, the specimen and the count -- a known-issues
    heading with no numbers in it is not a disclosure.
    """
    entry = _entry(_changelog())
    assert "### Known issues" in entry, (
        "the entry has no Known issues section, so the per-metric peer_count "
        "defect ships undisclosed"
    )
    known = entry[entry.index("### Known issues"):]
    assert "peer_count" in known, "the disclosure does not name the mechanism"
    assert "16583" in known, "the disclosure does not name the specimen"
    assert list(re.finditer(r"(?<![\d,.])60\.24(?![\d,.])", known)), (
        "the disclosure does not state the one-bank median it turns on"
    )
    cells, subjects = dict((r[0], r[1:]) for r in THIN_METRIC_CELLS)["20260630"]
    for value in (cells, subjects):
        assert list(re.finditer(rf"(?<![\d,.]){value}(?![\d,.])", known)), (
            f"the disclosure does not state {value}, which is the measured "
            f"reach at 20260630"
        )


@_needs_changelog
def test_the_changelog_does_not_claim_peer_count_was_fixed():
    """Disclosing an issue and claiming it fixed are opposite acts."""
    known = _entry(_changelog())
    known = known[known.index("### Known issues"):]
    for m in re.finditer(r"peer_count", known):
        window = known[max(0, m.start() - 300):m.end() + 300]
        assert not re.search(r"\bnow (?:rendered|shown|displayed)\b", window), (
            "the Known issues section reads as though peer_count is now "
            "rendered; it is not, and rendering it is 0.3.3's work"
        )


@_needs_changelog
def test_the_changelog_states_the_zero_magnitude_reach():
    entry = _entry(_changelog())
    for repdte, cells in ZERO_MAGNITUDE_REACH:
        assert list(re.finditer(rf"(?<![\d,.]){cells}(?![\d,.])", entry)), (
            f"the entry does not state {cells}, the measured zero-magnitude "
            f"reach at {repdte}"
        )


# ── The scan discipline itself ───────────────────────────────────────────────

def test_this_module_never_scans_the_tests_tree():
    """Rule (j3)'s second half, held rather than remembered.

    Every scan above opens exactly one file: CHANGELOG.md, via
    `layout.SURFACES`. A gate that walked the repo would match its own pinned
    numbers and the strings it forbids, and would pass for that reason.
    """
    import inspect
    import tests.test_changelog_claims as me
    src = inspect.getsource(me)
    for m in re.finditer(r"layout\.SURFACES\[[\"']([^\"']+)[\"']\]", src):
        assert m.group(1) == "CHANGELOG.md", (
            f"this module opens {m.group(1)}, which widens its scan beyond the "
            f"one document it declares"
        )
    assert not re.search(r"\brglob\b|\bwalk\b|\bglob\(", src), (
        "this module walks the tree; a CHANGELOG gate must read the CHANGELOG"
    )
