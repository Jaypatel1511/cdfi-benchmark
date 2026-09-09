"""What the rendered page says, and every way it said something untrue.

Six defects, all on the face of the document, all diagnosed in an earlier round
and deferred. Each has a gate here because each is the same class: a number or a
sentence that is individually defensible and collectively misleading.
"""
import re

import pytest

from cdfibenchmark.data.schema import (
    InstitutionProfile, ASSET_BUCKETS, HOUSE_ASSET_BUCKETS,
    BENCHMARKS, BenchmarkResult,
)
from cdfibenchmark.peers.selector import PeerGroup, HOUSE_MAX_PEERS
from cdfibenchmark.report.generator import (
    generate_report, _fmt_assets_mm, _printed_vs_median, _asset_bucket_line,
)
from cdfibenchmark.metrics.calculator import benchmark_institution


def _bank(cert, assets, **over):
    base = dict(
        cert=cert, name=f"Bank {cert}", city="Oakland", state="CA",
        report_date="20260630",
        total_assets=assets, total_deposits=assets * 0.85,
        net_loans=assets * 0.72, net_income=assets * 0.006,
        interest_income=assets * 0.031, interest_expense=assets * 0.006,
        non_interest_income=assets * 0.005, non_interest_expense=assets * 0.023,
        total_equity=assets * 0.11, tier1_ratio=11.2,
        gross_loans=assets * 0.73, non_current_loans=assets * 0.003,
        loan_loss_allowance=assets * 0.009,
        reported_nim=4.0003, reported_roaa=0.1406, reported_roae=1.51,
        reported_efficiency_ratio=76.0733,
    )
    base.update(over)
    return InstitutionProfile(**base)


def _group(peers, subject, **over):
    kw = dict(min_peers=10, target_report_date="20260630",
              subject_assets=subject.total_assets, universe_size=621,
              asset_tolerance=0.5, max_peers=HOUSE_MAX_PEERS)
    kw.update(over)
    return PeerGroup(peers, **kw)


# ── F2: the Status column never consults the peer columns ────────────────────
def test_the_report_says_status_ignores_the_peer_columns():
    """The clearest over-trust path in the document.

    Measured at 20260630, CERT 58490's NPL ratio is 2.53% against a 0.41% peer
    median — 6.2x the median and outside the peer IQR — while its reserve
    coverage is 22% of the peer median and below the 25th percentile. Both grade
    ADEQUATE, and both grades are individually CORRECT: the thresholds are
    absolute. That is the textbook credit-deterioration signature rendered as two
    yellow triangles in a table headed "Performance Summary", with Status sitting
    beside three peer columns it does not read.

    Nothing needed to change about the grades. What was missing is the sentence.
    """
    subject = _bank(58490, 2_027_009.0)
    peers = _group([_bank(9000 + i, 2_000_000.0 + i * 1_000) for i in range(20)],
                   subject)
    report = generate_report(subject, peers)

    summary = report[report.index("## Performance Summary"):
                     report.index("## Metric Detail")]
    assert "does **not** consult" in summary, (
        "the Performance Summary does not say that Status ignores the peer "
        "columns printed beside it"
    )
    for column in ("Peer Median", "25th", "75th"):
        assert column in summary
    assert "below the peer median" in summary and "STRONG" in summary, (
        "the note does not give the reader the case that actually bites"
    )


def test_the_status_note_is_inside_the_table_section_not_buried_at_the_end():
    """A caveat a reader meets after the table is a caveat they meet too late."""
    subject = _bank(58490, 2_027_009.0)
    peers = _group([_bank(9000 + i, 2_000_000.0) for i in range(20)], subject)
    report = generate_report(subject, peers)
    assert "How to read Status" in report, "the Status note is not rendered at all"
    note = report.index("How to read Status")
    assert report.index("## Performance Summary") < note < report.index("## Metric Detail")


# ── F3: printed arithmetic that does not add up ──────────────────────────────
def test_the_printed_vs_median_is_the_difference_of_the_printed_operands():
    """4 of 16 rows across two real subjects failed this at 20260630.

    CERT 16584's NIM printed 4.36%, a peer median of 3.94%, and "0.41% above
    median". Every number is correctly rounded from a correct raw value, and the
    line still asks a reader checking the tool's arithmetic to accept
    4.36 - 3.94 = 0.41.
    """
    subject = _bank(16584, 111_233.0, reported_nim=4.3594)
    peers = _group([_bank(9000 + i, 111_000.0, reported_nim=3.9448)
                    for i in range(20)], subject)
    report = generate_report(subject, peers)

    rows = re.findall(
        r"^\| (.+?) \| (-?[\d.]+)% \| (-?[\d.]+)% \|", report, re.M)
    assert rows, "no rendered metric rows were parsed out of the report"

    # The unit moved from `%` to `pp` in 0.3.2 (see the F1 block below); a tie
    # renders "— at the median" rather than picking a direction. This gate is
    # about the ARITHMETIC, so it reads whichever shape the line takes.
    detail = {label: (amount, above or below or at)
              for label, amount, above, below, at in re.findall(
        r"### (.+?)\n\n\*\*Institution Value:\*\* (?:-?[\d.]+)%\n"
        r"\*\*Peer Median:\*\* (?:-?[\d.]+)%\n"
        r"\*\*vs Peer Median:\*\* (-?[\d.]+) pp "
        r"(?:(above) median|(below) median|— (at) the median)", report)}
    assert detail, "no vs-median lines were parsed out of the report"

    checked = 0
    for label, inst_txt, median_txt in rows:
        if label not in detail:
            continue
        printed, direction = detail[label]
        implied = round(float(inst_txt) - float(median_txt), 2)
        signed = float(printed) * {"above": 1, "below": -1, "at": 0}[direction]
        assert signed == pytest.approx(implied, abs=1e-9), (
            f"{label}: the page prints {inst_txt}% and {median_txt}%, whose "
            f"difference is {implied:+.2f}, but states {signed:+.2f}"
        )
        checked += 1
    assert checked >= 5, f"only {checked} rows were actually checked"


def test_the_raw_difference_is_still_available_to_a_programmatic_consumer():
    """Fix the RENDERING, not the number. `vs_median` stays exact."""
    subject = _bank(16584, 111_233.0, reported_nim=4.3594)
    peers = _group([_bank(9000 + i, 111_000.0, reported_nim=3.9448)
                    for i in range(20)], subject)
    nim = next(r for r in benchmark_institution(subject, peers) if r.metric == "nim")
    assert nim.vs_median == pytest.approx(4.3594 - 3.9448)
    assert _printed_vs_median(nim) == pytest.approx(0.42)
    assert nim.vs_median != pytest.approx(_printed_vs_median(nim), abs=1e-9)


# ── F5: a financial document with no thousands separator ─────────────────────
@pytest.mark.parametrize("value_mm,expected", [
    (2027.009, "$2,027.0MM"),
    (4091315.0, "$4,091,315.0MM"),
    (111.233, "$111.2MM"),
    (0.0, "$0.0MM"),
])
def test_asset_figures_carry_a_thousands_separator(value_mm, expected):
    assert _fmt_assets_mm(value_mm) == expected


def test_a_missing_asset_figure_is_still_not_a_number():
    assert _fmt_assets_mm(None) == "N/A"
    assert _fmt_assets_mm(float("nan")) == "N/A"


# ── F6: ASSET_BUCKETS on the report face, unmarked ───────────────────────────
def test_the_asset_bucket_carries_its_boundaries_and_its_attribution():
    """"Large" is a supervisory word and this band is not any supervisory band.

    It was the only classifying constant naming something on the report face
    with no HOUSE marker, no boundaries and no attribution, while fifteen
    constants beside it carried all three.
    """
    line = _asset_bucket_line(_bank(1, 2_027_009.0))
    assert "Large" in line
    assert "HOUSE" in line, "the asset bucket is rendered without its attribution"
    assert "$1,000MM-$5,000MM" in line, (
        "the asset bucket is rendered without the boundaries it means"
    )
    for negative in ("FFIEC", "FDIC community-bank", "UBPR"):
        assert negative in line, f"the line does not say it is not a {negative} band"


def test_the_bucket_constant_is_named_house_like_every_other_house_constant():
    assert HOUSE_ASSET_BUCKETS is ASSET_BUCKETS, (
        "the back-compat alias no longer points at the same object"
    )


def test_an_unknown_bucket_renders_as_unavailable_not_as_a_band():
    line = _asset_bucket_line(_bank(1, float("nan")))
    assert "N/A" in line and "HOUSE" not in line


@pytest.mark.parametrize("assets,expected", [
    (-1.0, "unknown"),
    (-500_000.0, "unknown"),
    (0.0, "micro"),
    (49_999.0, "micro"),
    (5_000_000.0, "mega"),
    (1e12, "mega"),
])
def test_asset_bucket_does_not_answer_mega_for_everything_it_cannot_place(
        assets, expected):
    """The bare `return "mega"` fall-through was a claim about TWO sets.

    Above the top band it is right. Below the bottom band it was the worst
    available answer: a profile with negative total assets rendered
    "**Asset Bucket:** Mega" on the report face. Buckets are ordered, so falling
    off the bottom gets its own answer.
    """
    assert _bank(1, assets).asset_bucket == expected


# ── F7: the most prominently disclosed constant is the one that does nothing ─
def test_the_selection_basis_leads_with_the_breadth_that_actually_applies():
    """A reader of the old sentence over-estimated the group's breadth ~10x.

    It read "the 50 banks NEAREST the subject in total assets, out of 828 in a
    +/-50% asset window". Measured at 20260630: the tolerance is INERT for 4,232
    of 4,313 filers (98.1%), and for CERT 16584 the group is the identical 50
    CERTs at 0.5, 0.2, 0.1, 0.05 and 0.03 — it first bites at 0.02. The group's
    real breadth was -3.00%/+2.92%, and it is set by `max_peers`.
    """
    subject = _bank(16584, 111_233.0)
    peers = _group([_bank(9000 + i, 107_901.0 + i * 138.6) for i in range(50)],
                   subject, universe_size=828)
    basis = peers.selection_basis

    assert "50-bank cap, not by the window" in basis, (
        "the basis does not say what actually sets the group's breadth"
    )
    assert "does not bind" in basis, (
        "the basis does not say the asset window usually does nothing"
    )
    assert peers.realized_tolerance_text in basis and peers.realized_tolerance_text
    assert basis.index("They span") < basis.index("+/-50% asset window"), (
        "the window is still stated before the breadth that actually applies"
    )
    assert "HOUSE" in basis


def test_the_realized_span_is_the_groups_own_range_not_the_window():
    subject = _bank(16584, 111_233.0)
    peers = _group([_bank(9000 + i, a) for i, a in
                    enumerate((107_901.0, 111_000.0, 114_484.0))], subject)
    assert peers.asset_span == (107_901.0, 114_484.0)
    assert peers.realized_tolerance_text == "-3.00%/+2.92%"


def test_an_empty_group_states_no_span_rather_than_a_fabricated_one():
    subject = _bank(16584, 111_233.0)
    peers = _group([], subject)
    assert peers.asset_span is None
    assert peers.realized_tolerance_text == ""
    assert "They span" not in peers.selection_basis


# ── F8: a caveat that is false of its own document ───────────────────────────
def test_a_zero_peer_group_does_not_claim_its_percentiles_are_unreliable():
    """At n=0 the document contains no percentiles at all.

    The small-n sentence — "Percentiles over so few peers are not a reliable
    benchmark" — was reused verbatim at zero peers, where every peer column reads
    N/A, nothing was computed, and STRONG still renders under the title "CDFI
    Peer Benchmarking Report". Reachable from an ordinary typo: a `report_date`
    on which no institution filed.
    """
    subject = _bank(16584, 111_233.0)
    peers = _group([], subject, target_report_date="20260515")
    caveats = peers.caveats
    assert len(caveats) >= 1
    joined = " ".join(caveats)
    assert "Percentiles over so few peers" not in joined, (
        "the small-n percentile caveat is being reused at zero peers, where the "
        "report contains no percentiles"
    )
    assert "NO peer met the selection criteria" in joined
    assert "no benchmarking has been performed" in joined
    assert "20260515" in joined, "the caveat does not name the period that found nothing"


def test_the_zero_peer_caveat_reaches_the_rendered_page():
    subject = _bank(16584, 111_233.0)
    report = generate_report(subject, _group([], subject,
                                             target_report_date="20260515"))
    assert "not a peer comparison" in report
    assert "Percentiles over so few peers" not in report


def test_a_small_but_nonzero_group_still_gets_the_small_n_caveat():
    """The n=0 branch must not swallow the case it was split off from."""
    subject = _bank(16584, 111_233.0)
    peers = _group([_bank(9000 + i, 111_000.0) for i in range(3)], subject)
    joined = " ".join(peers.caveats)
    assert "Percentiles over so few peers" in joined
    assert "NO peer met the selection criteria" not in joined


# ── B-A: degrading the row must not degrade it silently ──────────────────────
def test_peers_with_a_refused_value_are_counted_on_the_face():
    """What degrading gets wrong, gated.

    An out-of-band RBC1AAJ now yields None instead of aborting the peer group.
    The cost is that the value vanishes from the metric's median via `dropna()`,
    silently, exactly like a field FDIC never published. The group says how many
    peers that happened to and which field.
    """
    subject = _bank(16584, 111_233.0)
    peers = _group(
        [_bank(9000 + i, 111_000.0,
               tier1_ratio=None if i < 3 else 11.2,
               implausible_fields=("RBC1AAJ",) if i < 3 else ())
         for i in range(20)],
        subject,
    )
    joined = " ".join(peers.caveats)
    assert "RBC1AAJ on 3 peers" in joined, (
        "a refused peer value is not disclosed anywhere on the page"
    )
    assert "plausibility bound" in joined
    assert "this tool's judgement, not FDIC's" in joined, (
        "the caveat does not say whose judgement discarded a real filed value"
    )
    assert "RBC1AAJ on 3 peers" in generate_report(subject, peers)


def test_a_clean_group_says_nothing_about_refusals():
    subject = _bank(16584, 111_233.0)
    peers = _group([_bank(9000 + i, 111_000.0) for i in range(20)], subject)
    assert not any("plausibility bound" in c for c in peers.caveats)


def test_a_refused_subject_value_says_it_was_refused_on_the_page():
    """An absent value needs no explanation. A refused one does.

    FDIC published a number, and this tool decided not to show it. Left unsaid,
    that is indistinguishable from FDIC never publishing it — which is the same
    absence-reads-as-result failure the release exists to remove.
    """
    subject = _bank(16584, 111_233.0, tier1_ratio=None,
                    implausible_fields=("RBC1AAJ",))
    peers = _group([_bank(9000 + i, 111_000.0) for i in range(20)], subject)
    report = generate_report(subject, peers)

    detail = report[report.index("### Tier 1 Leverage Ratio"):]
    detail = detail[:detail.index("###", 5)]
    assert "**Not shown:**" in detail, (
        "a refused value renders as plain N/A, indistinguishable from a field "
        "FDIC never published"
    )
    assert "plausibility bound" in detail
    assert "this tool's own heuristic, not FDIC's" in detail
    assert "**Status:** N/A" in detail, "a refused value was still graded"


def test_an_absent_subject_value_does_not_claim_it_was_refused():
    subject = _bank(16584, 111_233.0, tier1_ratio=None)
    peers = _group([_bank(9000 + i, 111_000.0) for i in range(20)], subject)
    report = generate_report(subject, peers)
    detail = report[report.index("### Tier 1 Leverage Ratio"):]
    detail = detail[:detail.index("###", 5)]
    assert "**Not shown:**" not in detail
    assert "no value was reported" in detail


# ── F1 (0.3.2): a difference of two percentages is PERCENTAGE POINTS ─────────
#
# `**vs Peer Median:** {_fmt_pct(abs(vs_printed))} {direction} median` rendered
# the arithmetic difference of two percentages and appended a `%`. Measured on
# the 0.3.1 artifact (CERT 34352 @ 20260630), all 8 of 8 metric blocks: the
# sentence is sometimes near the relative figure and sometimes off by an order
# of magnitude, WITH NOTHING ON THE LINE SAYING WHICH CASE THE READER IS IN.
#
#     metric      inst     median   rendered as            true relative gap
#     NIM         2.67%    3.70%    "1.03% below median"    27.8% below
#     ROAA        0.32%    1.17%    "0.85% below median"    72.6% below
#     ROAE        2.50%   11.57%    "9.07% below median"    78.4% below
#     LTD        95.25%   85.19%   "10.06% above median"    11.8% above
#
# A banker reading "ROAA 0.85% below median" concludes a near-miss. The bank
# earns less than a third of its peer group's ROAA.
#
# Third appearance of this family, after cdfi-loan-pricing's dollars-as-percent
# inflated 100x and cdfi-stress-tester's basis points. The portfolio's unit
# discriminator -- dollars scale with the amount, rates do not -- carries the
# stated limit "it cannot separate PERCENT from RATIO", and a percentage-point
# difference labelled as a percent is exactly that unresolved case.
#
# GROUND TRUTH INDEPENDENT OF THE DECLARATION. Every expected number below is
# typed as a literal, computed by hand from the two printed operands. A gate
# that derived its expectation from the same formatter the renderer uses would
# certify consistency, not truth.

_VS_LINE = re.compile(
    r"\*\*vs Peer Median:\*\* (-?[\d.]+) pp (above|below|at) (?:the )?median"
    r"(?: \((-?[\d.]+)% (?:above|below)\))?"
)


def _roaa_specimen():
    """inst ROAA 0.32%, peer median 1.17% -- the 0.3.1 artifact's own worst row.

    By hand, from the two operands the page prints:
        pp gap        0.32 - 1.17            = -0.85         -> "0.85 pp below"
        relative gap  -0.85 / 1.17 * 100     = -72.649...%   -> "(72.6% below)"
    The two differ by 85x. Nothing on the old line told the reader that.
    """
    subject = _bank(34352, 1_562_007.0, reported_roaa=0.324864010816794)
    peers = _group([_bank(9000 + i, 1_562_000.0, reported_roaa=1.17)
                    for i in range(20)], subject)
    return generate_report(subject, peers)


def _roaa_block(report):
    start = report.index("### Return on Average Assets")
    return report[start:report.index("\n###", start + 1)] \
        if "\n###" in report[start + 1:] else report[start:]


def test_the_vs_median_line_states_percentage_points_not_percent():
    """The blocker. 0.85 is a percentage-POINT gap; the page called it 0.85%."""
    block = _roaa_block(_roaa_specimen())
    assert "0.85 pp below median" in block, (
        f"the vs-median line does not state the gap in percentage points.\n"
        f"Rendered block was:\n{block}"
    )
    assert "**vs Peer Median:** 0.85% below" not in block, (
        "the pp difference is still rendered with a bare % sign"
    )


def test_the_vs_median_line_also_states_the_relative_gap():
    """0.85 pp and 72.6% are both true and mean opposite things to a reader.

    The binding requirement is that a reader can tell, FROM THE LINE ALONE,
    what unit the number is in. Two labelled numbers do that; one unlabelled
    one is what shipped.
    """
    block = _roaa_block(_roaa_specimen())
    assert "(72.6% below)" in block, (
        f"the vs-median line does not state the relative gap.\n"
        f"Rendered block was:\n{block}"
    )


def test_the_pp_figure_and_the_relative_figure_are_different_numbers():
    """The whole point of rendering both, on the row where it bites hardest.

    Red-proving this is one edit: render the relative figure in the pp slot.
    """
    block = _roaa_block(_roaa_specimen())
    m = _VS_LINE.search(block)
    assert m, f"the vs-median line did not parse:\n{block}"
    pp, relative = float(m.group(1)), float(m.group(3))
    assert pp == 0.85, f"pp gap should be 0.85, page says {pp}"
    assert relative == 72.6, f"relative gap should be 72.6, page says {relative}"
    assert relative / pp > 10, (
        f"on this specimen the two figures must diverge by more than 10x "
        f"({relative} vs {pp}); if they do not, the specimen no longer "
        f"exercises the defect this gate exists for"
    )


def test_every_metric_block_renders_both_figures():
    """Not one row. All of them -- the defect was 8 of 8."""
    report = _roaa_specimen()
    blocks = re.findall(r"\*\*vs Peer Median:\*\* .*", report)
    assert len(blocks) >= 5, f"only {len(blocks)} vs-median lines rendered"
    for line in blocks:
        assert " pp " in line, f"no percentage-point unit on: {line}"


def test_a_value_at_the_printed_median_is_not_called_below_it():
    """`"above" if vs_printed > 0 else "below"` called a tie a shortfall.

    Reachable well short of exact equality: both operands are rounded to 2 dp
    before subtracting, so a bank genuinely ABOVE its peer median by less than
    half a basis point printed "0.00% below median" -- a directional falsehood.
    """
    subject = _bank(34352, 1_562_007.0, reported_nim=3.7012)
    peers = _group([_bank(9000 + i, 1_562_000.0, reported_nim=3.70)
                    for i in range(20)], subject)
    report = generate_report(subject, peers)
    nim = report[report.index("### Net Interest Margin"):]
    nim = nim[:nim.index("\n###")] if "\n###" in nim else nim

    assert "0.00 pp below median" not in nim, (
        "a value at the printed median is still described as below it"
    )
    assert "at the median" in nim, (
        f"a tie should say so in words. Rendered block was:\n{nim}"
    )


# ── F1 (0.3.3 BLOCKER): one reason sentence served three different cases ─────
#
# Through 0.3.2 the withheld-relative-gap line read, for every case:
#
#     "relative gap not shown: the peer median is not positive, so a
#      percentage of it would read as its own opposite"
#
# That is TRUE of a negative median and FALSE of the other two. A zero median
# has no sign to invert -- the ratio is undefined, not inverted. And a median
# that merely ROUNDS to zero at the 2 dp the page prints IS positive, so the
# sentence denied a fact about the peer group in order to explain a rounding
# decision.
#
# Every count below was measured LIVE against api.fdic.gov on 2026-09-09 from
# Jay's macOS shell, over the ENTIRE filer universe at each REPDTE (not a
# sample), driving the package's own peer selection -- the +/-50% asset window,
# `_nearest_by_assets`, HOUSE_MAX_PEERS -- and the package's own metric
# properties. The replication was validated end-to-end against live
# `build_peer_group` + `benchmark_institution` on CERTs 16583, 13986 and 29966
# at 20260630: identical peer counts and identical medians on every metric.
#
# A cell is counted only where the renderer actually reaches the sentence: the
# subject's own value is present, and the printed difference is non-zero (a tie
# takes the "at the median" branch and never calls `_relative_gap`).

#: (REPDTE, negative-median cells, zero-median cells, rounds-to-zero cells).
#: Filer universe sizes: 4,313 / 4,353 / 4,411 / 4,452 / 4,494 / 4,536.
RELATIVE_GAP_REACH = (
    ("20260630", 0, 3, 0),
    ("20260331", 10, 4, 0),
    ("20251231", 0, 7, 0),
    ("20250930", 0, 15, 0),
    ("20250630", 0, 9, 0),
    ("20250331", 0, 4, 7),
)

#: Retrieval date for RELATIVE_GAP_REACH and every specimen below.
RELATIVE_GAP_REACH_RETRIEVED = "2026-09-09"


def test_every_withheld_case_in_the_measured_population_is_live():
    """No sentence is written for a case that never fires, and none is missing.

    The point of splitting one sentence into three is that all three cases are
    REAL. If a column here were all zeroes, that sentence would be decoration
    and this gate says so.
    """
    for i, name in enumerate(("negative", "zero", "rounds-to-zero"), start=1):
        total = sum(row[i] for row in RELATIVE_GAP_REACH)
        assert total > 0, (
            f"the {name} case is written for but was measured 0 times across "
            f"{len(RELATIVE_GAP_REACH)} quarters -- either the sweep is wrong "
            f"or the sentence serves nothing"
        )


def test_the_release_period_is_dominated_by_the_case_the_old_sentence_got_wrong():
    """Why this blocked a release rather than waiting for 0.3.3.

    At 20260630 -- the period every worked example in the README and CHANGELOG
    uses -- the case the 0.3.2 sentence was RIGHT about fires zero times, and
    the case it was WRONG about fires three. The shipped sentence was false
    every single time it rendered at the release period.
    """
    at_release = dict((row[0], row) for row in RELATIVE_GAP_REACH)["20260630"]
    _, negative, zero, rounds_to_zero = at_release
    assert negative == 0, (
        f"the sweep says the negative case fires {negative} times at 20260630; "
        f"this gate's premise was that it fires 0"
    )
    assert zero + rounds_to_zero > 0, (
        "no false-sentence case fires at the release period, which would mean "
        "the blocker was not reachable on shipped output"
    )


# ── One specimen per live case, driven through the real renderer ─────────────
#
# Each specimen's FDIC inputs are the values FDIC actually published for that
# CERT at that REPDTE, so the median is DERIVED by the package from real data
# rather than declared here. Rule (i): none of these gates asserts a rendered
# string against a constant copied from the renderer -- they assert the
# sentence BY ITS MEANING (which word must and must not appear, and which
# arithmetic must not).


def _npl_bank(cert, non_current, gross, **over):
    """A peer whose npl_ratio comes from real NCLNLS / LNLSGR dollars."""
    return _bank(cert, 9_316.0, non_current_loans=non_current,
                 gross_loans=gross, **over)


def _detail_block(report, heading):
    block = report[report.index(heading):]
    return block[:block.index("\n###")] if "\n###" in block else block


#: CERT 16583 (STATE BANK OF BURRTON) @ 20260630 -- the live zero-median
#: specimen. Its 19-bank peer group holds four banks with an NPL ratio at all;
#: three report zero non-current loans, so the median is exactly 0.00%.
#: (CERT, NCLNLS $k, LNLSGR $k) as FDIC published them.
ZERO_MEDIAN_PEERS = (
    (29966, 83.0, 6226.0),
    (13986, 0.0, 2241.0),
    (17982, 0.0, 3053.0),
    (17138, 0.0, 9755.0),
)
#: CERT 16583's own NCLNLS / LNLSGR at that period -> 2.53%.
ZERO_MEDIAN_SUBJECT = (16583, 173.0, 6834.0)

#: CERT 9349 @ 20250331 -- the live ROUNDS-TO-ZERO specimen (finding D1). Its
#: 44 valued peers have a median NPL ratio of 0.0024260067928190197%, which is
#: genuinely POSITIVE and rounds to 0.00% at the 2 dp the page prints. It is
#: set by CERT 10200's ONE thousand dollars of non-current loans against
#: $20,610k of gross loans. Backed by 44 peers, not a thin group.
ROUNDS_TO_ZERO_PEERS = (
    (14344, 423.0, 21607.0), (29774, 163.0, 24877.0), (29627, 0.0, 32464.0),
    (31409, 586.0, 35860.0), (6084, 0.0, 16146.0), (5196, 397.0, 16065.0),
    (1675, 0.0, 17861.0), (10077, 4.0, 12881.0), (18463, 0.0, 19974.0),
    (10843, 138.0, 16660.0), (15098, 0.0, 16844.0), (57363, 1446.0, 22684.0),
    (13611, 0.0, 16035.0), (10200, 1.0, 20610.0), (9752, 0.0, 14065.0),
    (31774, 94.0, 33355.0), (10463, 0.0, 29170.0), (23826, 0.0, 1365.0),
    (30065, 364.0, 36945.0), (27716, 0.0, 30995.0), (5142, 321.0, 12760.0),
    (4494, 0.0, 25073.0), (17450, 40.0, 30578.0), (13931, 397.0, 11012.0),
    (14853, 0.0, 24755.0), (10704, 0.0, 8878.0), (29059, 274.0, 26872.0),
    (59330, 0.0, 2985.0), (17551, 954.0, 14732.0), (15762, 434.0, 24194.0),
    (27841, 0.0, 31530.0), (29582, 0.0, 12480.0), (17160, 9.0, 3638.0),
    (18568, 0.0, 17519.0), (13582, 1290.0, 20569.0), (11731, 95.0, 23254.0),
    (17174, 55.0, 19710.0), (6198, 0.0, 18305.0), (8323, 0.0, 23480.0),
    (30176, 0.0, 35370.0), (9295, 0.0, 12555.0), (4122, 59.0, 16332.0),
    (12745, 170.0, 29640.0), (15767, 0.0, 15915.0),
)
#: CERT 9349's own NCLNLS / LNLSGR at that period -> 0.167%.
ROUNDS_TO_ZERO_SUBJECT = (9349, 39.0, 23320.0)

#: CERT 34065 @ 20260331 -- the live NEGATIVE-median specimen. FDIC's published
#: ROE for its four peers; the median is -0.50%. This is the one case the 0.3.2
#: sentence was right about, kept as a real specimen rather than the synthetic
#: -700% efficiency ratio the gate used before.
NEGATIVE_MEDIAN_PEER_ROE = ((57834, -0.27), (28722, -201.12),
                            (57150, -0.73), (34331, 3.14))
#: CERT 34065's own published ROE at that period.
NEGATIVE_MEDIAN_SUBJECT_ROE = (34065, 0.13)


def _zero_median_report():
    cert, ncl, gross = ZERO_MEDIAN_SUBJECT
    subject = _npl_bank(cert, ncl, gross)
    peers = _group([_npl_bank(c, n, g) for c, n, g in ZERO_MEDIAN_PEERS],
                   subject)
    return generate_report(subject, peers)


def _rounds_to_zero_report():
    cert, ncl, gross = ROUNDS_TO_ZERO_SUBJECT
    subject = _npl_bank(cert, ncl, gross, report_date="20250331")
    peers = _group([_npl_bank(c, n, g, report_date="20250331")
                    for c, n, g in ROUNDS_TO_ZERO_PEERS],
                   subject, target_report_date="20250331")
    return generate_report(subject, peers)


def _negative_median_report():
    cert, roe = NEGATIVE_MEDIAN_SUBJECT_ROE
    subject = _bank(cert, 9_316.0, reported_roae=roe, report_date="20260331")
    peers = _group([_bank(c, 9_316.0, reported_roae=v, report_date="20260331")
                    for c, v in NEGATIVE_MEDIAN_PEER_ROE],
                   subject, target_report_date="20260331")
    return generate_report(subject, peers)


def test_a_zero_peer_median_says_the_ratio_is_undefined_not_that_a_sign_inverts():
    """THE BLOCKER. Live on CERT 16583 @ 20260630, peer NPL median 0.00%.

    A zero median has NO SIGN. Nothing about it can "read as its own opposite",
    and telling a reader it does is a false statement about their peer group on
    a page whose entire 0.3.2 round was convened to stop false statements.
    """
    npl = _detail_block(_zero_median_report(), "### Non-Performing Loan Ratio")

    assert "0.00%" in npl, (
        f"the specimen no longer produces a zero peer median:\n{npl}"
    )
    assert "undefined" in npl, (
        f"the zero case must say the ratio is UNDEFINED:\n{npl}"
    )
    assert "opposite" not in npl, (
        f"the page tells the reader a percentage of a ZERO median would read "
        f"as its own opposite. Zero has no sign to invert:\n{npl}"
    )
    assert "not positive" not in npl, (
        f"'not positive' is the collapsed sentence this gate exists to keep "
        f"out of the zero case:\n{npl}"
    )


def test_a_negative_peer_median_does_say_the_sign_would_invert():
    """The one case the old sentence was right about — it must KEEP its reason.

    CERT 34065 @ 20260331: peers' published ROE median is -0.50% and the
    subject is at 0.13%, which is 0.63 pp ABOVE. 0.63 / -0.50 = -126%, so a
    relative figure would render "126.0% below" on the same line as "above".
    """
    roae = _detail_block(_negative_median_report(),
                         "### Return on Average Equity (ROAE)")

    assert "opposite" in roae, (
        f"the negative case lost the reason that is true of it:\n{roae}"
    )
    assert "undefined" not in roae, (
        f"a negative median is not undefined — it is invertible, which is a "
        f"different objection:\n{roae}"
    )
    assert "126.0" not in roae and "126%" not in roae, (
        f"a relative gap was computed against a negative peer median:\n{roae}"
    )
    assert " above median" in roae, (
        f"the percentage-point gap and its direction must still be stated:\n"
        f"{roae}"
    )


def test_a_median_that_only_rounds_to_zero_is_not_called_not_positive():
    """D1. Live on CERT 9349 @ 20250331 — 7 cells that quarter.

    The peer median NPL ratio is 0.0024260067928190197%, set by ONE peer's
    single thousand dollars of non-current loans. It is positive. The page
    rounds it to 0.00% for display and then, through 0.3.2, told the reader it
    "is not positive" — a false statement about a 44-bank peer group, not a
    thin one.

    Withholding the relative figure here is right: a ratio against 0.0024% is
    not informative. The REASON is what had to change.
    """
    npl = _detail_block(_rounds_to_zero_report(), "### Non-Performing Loan Ratio")

    assert "not positive" not in npl, (
        f"the page says a POSITIVE peer median is not positive:\n{npl}"
    )
    assert "opposite" not in npl, (
        f"there is no sign to invert on a positive median:\n{npl}"
    )
    assert "undefined" not in npl, (
        f"the ratio is defined here — it is merely uninformative:\n{npl}"
    )
    assert "rounds to" in npl, (
        f"the rounds-to-zero case must say the median ROUNDS to zero at the "
        f"printed precision:\n{npl}"
    )


def test_the_three_withheld_reasons_are_three_different_sentences():
    """The defect in one line: one sentence cannot be true of three cases.

    Collapsing the branches back to a single shared reason — the mutation this
    gate is red-proved with — makes two of these three equal.
    """
    reasons = []
    for report, heading in (
        (_zero_median_report(), "### Non-Performing Loan Ratio"),
        (_rounds_to_zero_report(), "### Non-Performing Loan Ratio"),
        (_negative_median_report(), "### Return on Average Equity (ROAE)"),
    ):
        block = _detail_block(report, heading)
        line = [ln for ln in block.splitlines()
                if ln.startswith("**vs Peer Median:**")]
        assert line, f"no vs-median line rendered:\n{block}"
        assert "relative gap not shown" in line[0], (
            f"this specimen no longer withholds the relative gap:\n{line[0]}"
        )
        reasons.append(line[0].split("relative gap not shown:", 1)[1].strip())

    assert len(set(reasons)) == 3, (
        f"three distinct cases produced {len(set(reasons))} distinct "
        f"reasons:\n" + "\n".join(reasons)
    )


def test_a_missing_operand_cannot_reach_the_relative_gap_at_all():
    """`_relative_gap`'s stated PRECONDITION, held rather than asserted.

    Its two `_is_missing` guards were unreachable from the only caller, and an
    unreachable branch is not a defect — but a REASON STRING serving a branch
    that cannot fire is a comment pretending to be behaviour. The guards are
    gone; this is what now holds the precondition.

    `_printed_vs_median` is the only producer of `vs_printed`, and
    `generate_report` renders nothing unless it is present.
    """
    subject = _bank(34352, 1_562_007.0)
    for kwargs in ({"peer_median": None}, {"peer_median": float("nan")},
                   {"institution_value": None},
                   {"institution_value": float("nan")}):
        base = dict(metric="npl_ratio", institution_value=1.0, peer_median=1.0,
                    peer_25th=None, peer_75th=None, peer_count=1)
        base.update(kwargs)
        vs = _printed_vs_median(BenchmarkResult(**base))
        assert vs is None or vs != vs, (
            f"_printed_vs_median returned a usable {vs!r} for {kwargs}, so a "
            f"missing operand CAN reach _relative_gap and its precondition is "
            f"false"
        )


def test_a_relative_gap_that_rounds_to_zero_does_not_carry_a_direction_word():
    """The unknown unknown of this round, and it is NEW IN 0.3.2.

    0.3.2 fixed exactly this defect on the pp half of the line — a magnitude of
    zero paired with a direction word — and introduced the relative half
    without extending the rule to it. The two halves round to different places
    (`_PCT_DP` and `_REL_DP`) from different quantities, so the relative figure
    reaches zero on its own while the pp figure does not:

        **vs Peer Median:** 0.01 pp below median (0.0% below)

    One half states a gap; the other states there is none; both say "below".

    Measured live over the whole filer universe, every metric: 14 cells at
    20260630, 15 at 20260331, 20 at 20251231, 13 at 20250331.
    """
    subject = _bank(34352, 1_562_007.0, reported_efficiency_ratio=87.20)
    peers = _group([_bank(9000 + i, 1_562_000.0,
                          reported_efficiency_ratio=87.19)
                    for i in range(20)], subject)
    eff = _detail_block(generate_report(subject, peers),
                        "### Efficiency Ratio")

    assert "0.01 pp above median" in eff, (
        f"the specimen no longer produces a 0.01 pp gap:\n{eff}"
    )
    for wrong in ("(0.0% above)", "(0.0% below)"):
        assert wrong not in eff, (
            f"the line states a relative magnitude of zero and a direction in "
            f"the same breath: {wrong}\n{eff}"
        )
    assert "rounds to 0.0%" in eff, (
        f"a relative gap that rounds away must say so rather than be dressed "
        f"as a direction:\n{eff}"
    )


# ── F5 (0.3.2): the banded threshold prose overlaps itself ───────────────────
#
# The rendered Benchmark line for loans-to-deposits read:
#
#   Strong 50%-80% | Adequate up to 95% | Weak below 50% (under-deployed) or
#   above 95%
#
# "Adequate up to 95%" spans 0-95%, which overlaps BOTH the Strong band and the
# Weak floor. It resolves only because Weak names the below-50 case afterwards,
# so a reader has to hold three clauses at once and let the third correct the
# second. Cosmetic next to F1 -- but it is a threshold line in a graded report,
# and the code grades ADEQUATE only on (80, 95].
def _ltd_band_line():
    subject = _bank(34352, 1_562_007.0)
    peers = _group([_bank(9000 + i, 1_562_000.0) for i in range(20)], subject)
    report = generate_report(subject, peers)
    block = report[report.index("### Loans-to-Deposits"):]
    block = block[:block.index("\n###")] if "\n###" in block else block
    line = next(l for l in block.splitlines() if l.startswith("**Benchmark:**"))
    return line


def test_the_banded_prose_does_not_span_the_bands_beside_it():
    line = _ltd_band_line()
    assert "Adequate up to 95%" not in line, (
        f"the Adequate clause still spans 0-95%, overlapping Strong and the "
        f"Weak floor:\n{line}"
    )
    assert "Adequate 80%-95%" in line, f"the Adequate band is not stated:\n{line}"


def test_every_band_the_prose_states_grades_the_way_the_prose_says():
    """Ground truth from the grader, not from the sentence describing it.

    Red-proving this is one edit: widen either stated bound by a point.
    """
    line = _ltd_band_line()
    strong = re.search(r"Strong (\d+)%-(\d+)%", line)
    adequate = re.search(r"Adequate (\d+)%-(\d+)%", line)
    weak = re.search(r"Weak below (\d+)% \(under-deployed\) or above (\d+)%", line)
    assert strong and adequate and weak, f"the band line did not parse:\n{line}"

    s_lo, s_hi = int(strong.group(1)), int(strong.group(2))
    a_lo, a_hi = int(adequate.group(1)), int(adequate.group(2))
    w_lo, w_hi = int(weak.group(1)), int(weak.group(2))

    # The three clauses must partition the line, meeting only at shared bounds.
    assert s_hi == a_lo, f"Strong ends at {s_hi} but Adequate starts at {a_lo}"
    assert a_hi == w_hi, f"Adequate ends at {a_hi} but Weak starts above {w_hi}"
    assert s_lo == w_lo, f"Strong starts at {s_lo} but Weak is below {w_lo}"

    cfg = BENCHMARKS["loans_to_deposits"]

    def grade(value):
        return BenchmarkResult(
            metric="loans_to_deposits", institution_value=value,
            peer_median=None, peer_25th=None, peer_75th=None, peer_count=0,
            lower_is_better=cfg.get("lower_is_better", False),
        ).status

    # Interiors, not just endpoints: an endpoint-only check passes on a band
    # that is stated backwards.
    assert grade((s_lo + s_hi) / 2) == "STRONG", "the stated Strong interior is not STRONG"
    assert grade((a_lo + a_hi) / 2) == "ADEQUATE", "the stated Adequate interior is not ADEQUATE"
    assert grade(w_lo - 0.01) == "WEAK", "below the stated floor is not WEAK"
    assert grade(w_hi + 0.01) == "WEAK", "above the stated ceiling is not WEAK"
    # And the bounds themselves fall where the prose puts them.
    assert grade(s_lo) == "STRONG" and grade(s_hi) == "STRONG"
    assert grade(a_hi) == "ADEQUATE"
