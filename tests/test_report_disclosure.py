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

from cdfibenchmark.data.schema import InstitutionProfile
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
def test_house_thresholds_are_marked_house_on_the_report(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "this tool's own" in report.lower() or "house" in report.lower(), (
        "seven of eight thresholds are house rules of thumb rendered in the "
        "same column as a CFR citation, unmarked"
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
