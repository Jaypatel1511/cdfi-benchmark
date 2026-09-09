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


def test_the_relative_gap_is_withheld_when_the_peer_median_is_not_positive():
    """A percentage OF a negative number reads as its own opposite.

    FDIC really publishes negative EEFFR -- it is their own arithmetic over
    negative noninterest expense. With a peer median of -700%, an institution
    at 74.84% is 774.84 pp ABOVE the median, while 774.84 / -700 = -110.7%
    would render "110.7% below". The pp figure and the relative figure would
    contradict each other on the same line. Withhold it and say why.
    """
    subject = _bank(58490, 2_027_009.0, reported_efficiency_ratio=74.84)
    peers = _group([_bank(9000 + i, 2_000_000.0,
                          reported_efficiency_ratio=-700.0)
                    for i in range(20)], subject)
    report = generate_report(subject, peers)
    eff = report[report.index("### Efficiency Ratio"):]
    eff = eff[:eff.index("\n###")] if "\n###" in eff else eff

    assert "774.84 pp above median" in eff, (
        f"the percentage-point gap must still be stated:\n{eff}"
    )
    assert "110.7" not in eff, (
        "a relative gap was computed against a non-positive peer median, "
        "which renders 'below' for a value that is above"
    )
    assert "peer median is not positive" in eff, (
        f"the line must say WHY the relative gap is absent:\n{eff}"
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
