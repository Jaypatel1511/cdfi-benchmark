"""What the rendered page says, and every way it said something untrue.

Six defects, all on the face of the document, all diagnosed in an earlier round
and deferred. Each has a gate here because each is the same class: a number or a
sentence that is individually defensible and collectively misleading.
"""
import re

import pytest

from cdfibenchmark.data.schema import (
    InstitutionProfile, ASSET_BUCKETS, HOUSE_ASSET_BUCKETS,
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

    detail = {label: (amount, direction) for label, amount, direction in re.findall(
        r"### (.+?)\n\n\*\*Institution Value:\*\* (?:-?[\d.]+)%\n"
        r"\*\*Peer Median:\*\* (?:-?[\d.]+)%\n"
        r"\*\*vs Peer Median:\*\* (-?[\d.]+)% (above|below) median", report)}
    assert detail, "no vs-median lines were parsed out of the report"

    checked = 0
    for label, inst_txt, median_txt in rows:
        if label not in detail:
            continue
        printed, direction = detail[label]
        implied = round(float(inst_txt) - float(median_txt), 2)
        signed = float(printed) * (1 if direction == "above" else -1)
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
