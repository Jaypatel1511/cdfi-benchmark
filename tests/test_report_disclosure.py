"""What the rendered report must say about its own warrant.

`generate_report` printed the institution's Report Date and the peer group
SIZE and nothing else about the peer group — no peer period, no note when the
same-state constraint had been dropped, no note when the group was below the
requested floor. It also printed a "Benchmark: Strong >= N%" line for every
metric with no indication that seven of the eight thresholds are this tool's
own rules of thumb and one is a CFR citation.

A grade is only as good as its warrant. If the warrant cannot be seen on the
rendered surface, the reader cannot tell a measured, cited, single-period
comparison from an estimated, house-thresholded, mixed-period one.
"""
import pytest
from unittest.mock import patch

from cdfibenchmark.data.schema import BENCHMARKS, InstitutionProfile
from cdfibenchmark.peers.selector import build_peer_group, build_sample_peer_group
from cdfibenchmark.report.generator import generate_report, summary_table


def _peer(cert, repdte="20260331", state="CA"):
    return InstitutionProfile(
        cert=cert, name=f"Peer {cert}", city="LA", state=state,
        report_date=repdte, total_assets=655_000, total_deposits=520_000,
        net_loans=380_000, net_income=1_950, interest_income=28_000,
        interest_expense=8_000, non_interest_income=3_500,
        non_interest_expense=22_000, total_equity=48_000, tier1_ratio=12.0,
        gross_loans=390_000, non_current_loans=5_850, loan_loss_allowance=7_800,
    )


@pytest.fixture
def q1_institution():
    return _peer(57543, repdte="20260331")


# ── peer period must be on the face ──────────────────────────────────────────
def test_report_renders_the_peer_period(q1_institution):
    rows = [_peer(c) for c in range(1, 21)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        peers = build_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "Peer Report Date" in report or "Peer Period" in report, (
        "the report shows the institution's period and the peer COUNT, but "
        "never the peers' own period"
    )
    assert "20260331" in report


def test_report_discloses_a_dropped_state_constraint(q1_institution):
    state_rows = [_peer(c, state="CA") for c in range(1, 4)]
    national_rows = [_peer(c, state="TX") for c in range(50, 70)]

    def fake(**kw):
        return state_rows if kw.get("state") else national_rows

    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               side_effect=fake):
        peers = build_peer_group(q1_institution, same_state=True, min_peers=10)
    report = generate_report(q1_institution, peers)
    assert "NATIONAL" in report.upper(), (
        "same-state was requested, a national group was returned, and the "
        "report said nothing"
    )


def test_report_discloses_an_undersized_peer_group(q1_institution):
    rows = [_peer(c) for c in range(1, 4)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        peers = build_peer_group(q1_institution, min_peers=10)
    report = generate_report(q1_institution, peers)
    assert "below the requested minimum" in report


def test_report_discloses_a_mixed_period_peer_group(q1_institution):
    rows = [_peer(c, repdte="20260331") for c in range(1, 11)]
    rows += [_peer(c, repdte="20251231") for c in range(50, 60)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        peers = build_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "NOT all at one reporting period" in report


def test_clean_peer_group_renders_no_caveats(q1_institution):
    rows = [_peer(c) for c in range(1, 21)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        peers = build_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "below the requested minimum" not in report
    assert "NOT all at one reporting period" not in report


# ── the basis must be on the face ────────────────────────────────────────────
def test_ungraded_flow_metric_states_why_it_is_not_graded(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "NOT annualized" in report, (
        "a Q1 YTD proxy is rendered ungraded with no stated reason"
    )


def test_report_states_the_basis_of_each_metric(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "**Basis:**" in report


def test_nim_computed_over_total_assets_says_so(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "not FDIC NIMY" in report


# ── house thresholds must not read as standards ──────────────────────────────
#: The exact attribution `_threshold_line` appends to a HOUSE benchmark. Pinned
#: as a literal, and asserted ON the Benchmark line, because the substring test
#: it replaces was satisfied from anywhere in the document.
_HOUSE_THRESHOLD_MARK = "**this tool's own threshold (HOUSE)**"


def _benchmark_lines(report):
    return [ln.strip() for ln in report.splitlines()
            if ln.strip().startswith("**Benchmark:**")]


def test_house_thresholds_are_marked_house_on_the_report(q1_institution):
    """THIS GATE COULD NOT BE MADE TO FAIL, AND THAT IS WHAT IT NOW FIXES.

    It read `"this tool's own" in report.lower() or "house" in report.lower()`
    -- a substring anywhere in the whole rendered document, standing in for "the
    threshold lines carry their attribution". The report says "this tool's own"
    in several unrelated places, so the assertion was satisfied without the
    threshold attribution existing at all. Measured, python3.10, deleting only
    the thing the gate names -- the HOUSE branch of `_threshold_line` at
    `cdfibenchmark/report/generator.py:116`, reduced to
    `" - not a regulatory or supervisory standard"`:

        PYTHONPATH=. pytest tests -q   ->  330 passed, 3 skipped
                                           (byte-identical to control)

    What kept it green was `cdfibenchmark/peers/selector.py:159`, a sentence
    about PEER-GROUP SELECTION -- "...nearest-neighbour selection are this
    tool's own choices (HOUSE)..." -- which appears on every report and has
    nothing to do with thresholds. That is the same class as the credit-union
    assertion this release deleted: a limb true of the artifact for an unrelated
    reason. For contrast the SIZE-BAND attribution was already gated properly,
    on its own line, by
    `test_report_face_claims.py::test_the_asset_bucket_carries_its_boundaries_and_its_attribution`.

    So the question is now asked where it means something. The scan is scoped to
    the `**Benchmark:**` lines; the marker is the literal attribution rather
    than a word that also appears in the size band and the selection basis; and
    how many lines must carry it is DERIVED from BENCHMARKS rather than typed
    here, so citing or adding a threshold cannot leave a stale count behind.

    NO `cdfibenchmark/` CHANGE WAS NEEDED, which is why this release is still a
    PATCH. The rendered page already distinguishes in words the three HOUSE
    attributions it carries -- threshold, size band, selection basis. Only the
    test was asking the cheap question.

    Red-proof of the replacement, same mutation, python3.10:

        PYTHONPATH=. pytest tests -q   ->  1 failed, 329 passed, 3 skipped
    """
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    lines = _benchmark_lines(report)

    house_metrics = sorted(
        m for m, cfg in BENCHMARKS.items()
        if cfg.get("source") == "HOUSE"
        and cfg.get("good") is not None and cfg.get("warning") is not None
    )
    assert house_metrics, (
        "BENCHMARKS declares no HOUSE-sourced graded threshold at all, so this "
        "gate would have nothing to look for and would pass having certified "
        "nothing. Either the table changed or this gate is now vacuous."
    )
    assert len(lines) == len(BENCHMARKS), (
        f"the report renders {len(lines)} `**Benchmark:**` lines for "
        f"{len(BENCHMARKS)} entries in BENCHMARKS. A threshold whose line never "
        f"renders cannot be checked for its attribution, and its absence is "
        f"invisible to a scan of the lines that DID render."
    )

    marked = [ln for ln in lines if _HOUSE_THRESHOLD_MARK in ln]
    assert len(marked) == len(house_metrics), (
        f"{len(house_metrics)} of the {len(BENCHMARKS)} thresholds are HOUSE "
        f"rules of thumb ({', '.join(house_metrics)}), but {len(marked)} of the "
        f"{len(lines)} rendered `**Benchmark:**` lines carry "
        f"{_HOUSE_THRESHOLD_MARK!r}. A house threshold rendered in the same "
        f"column as a CFR citation without that marker reads as a standard."
        + "\nLines:\n  " + "\n  ".join(lines)
    )

    for line in lines:
        if _HOUSE_THRESHOLD_MARK in line:
            continue
        assert any(tok in line for tok in ("CFR", "USC", "FFIEC", "FDIC")), (
            f"this `**Benchmark:**` line is neither marked HOUSE nor carries a "
            f"citation naming an instrument, so it renders as a standard with "
            f"no warrant: {line!r}"
        )


def test_cited_threshold_shows_its_citation(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "12 CFR 324.12" in report


# ── summary_table must expose the same facts ─────────────────────────────────
def test_summary_table_carries_basis_and_source(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    df = summary_table(q1_institution, peers)
    assert "basis" in df.columns
    assert "threshold_source" in df.columns
