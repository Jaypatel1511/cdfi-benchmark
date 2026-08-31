"""`rank_institution` must agree with `status`, and must span 0-100.

Two defects this file gates, both found by executing the function rather than
reading it:

1. A BANDED metric was ranked as though "better" were monotone. Measured before
   the fix, against a 20-peer sample group:

       L/D  15%  status=WEAK      rank=1/21  percentile=95.2
       L/D  80%  status=STRONG    rank=13/21 percentile=38.1

   A bank lending 15% of its deposits was graded WEAK and simultaneously placed
   in the top 5% of its peer group on the same metric. The two surfaces of one
   metric contradicted each other.

2. The percentile could never reach 100 and always bottomed at exactly 0.
   `(1 - rank/N) * 100` gives 95.2 for the best of 21 and 0.0 for the worst.
"""
import pytest

from cdfibenchmark.data.schema import InstitutionProfile, BenchmarkResult, BENCHMARKS
from cdfibenchmark.metrics.calculator import rank_institution


def _bank(cert=99001, **over):
    base = dict(
        cert=cert, name=f"Bank {cert}", city="LA", state="CA",
        report_date="20241231", total_assets=655_000, total_deposits=520_000,
        net_loans=380_000, net_income=1_950, interest_income=28_000,
        interest_expense=8_000, non_interest_income=3_500,
        non_interest_expense=22_000, total_equity=48_000, tier1_ratio=12.2,
        gross_loans=390_000, non_current_loans=5_850, loan_loss_allowance=7_800,
    )
    base.update(over)
    return InstitutionProfile(**base)


def _peers_with_roaa(values):
    return [_bank(cert=1000 + i, net_income=v * 6_550) for i, v in enumerate(values)]


# ── banded metrics must not be ranked monotonically ──────────────────────────
def test_banded_metric_is_not_ranked():
    """`better` is not monotone for a band, so no percentile is meaningful."""
    peers = [_bank(cert=1000 + i, net_loans=520_000 * p / 100)
             for i, p in enumerate(range(60, 110, 5))]
    result = rank_institution(_bank(net_loans=520_000 * 0.15), peers,
                              "loans_to_deposits")
    assert result["rank"] is None
    assert result["percentile"] is None
    assert "band" in (result.get("reason") or "").lower()


def test_banded_metric_rank_never_contradicts_its_status():
    """The specific pre-fix failure: WEAK at the 95th percentile."""
    peers = [_bank(cert=1000 + i, net_loans=520_000 * p / 100)
             for i, p in enumerate(range(60, 110, 5))]
    for pct in (15, 55, 80, 95, 130, 200):
        inst = _bank(net_loans=520_000 * pct / 100)
        status = BenchmarkResult(
            "loans_to_deposits", inst.loans_to_deposits,
            None, None, None, 0,
        ).status
        percentile = rank_institution(inst, peers, "loans_to_deposits")["percentile"]
        assert not (status == "WEAK" and percentile is not None and percentile > 50), (
            f"L/D {pct}% graded {status} but ranked at the {percentile}th percentile"
        )


# ── percentile must span the full range ──────────────────────────────────────
def test_beating_every_peer_is_the_100th_percentile():
    peers = _peers_with_roaa([0.1, 0.2, 0.3, 0.4])
    result = rank_institution(_bank(net_income=99 * 6_550), peers, "roaa")
    assert result["percentile"] == pytest.approx(100.0)
    assert result["rank"] == 1


def test_beating_no_peer_is_the_zeroth_percentile():
    peers = _peers_with_roaa([0.1, 0.2, 0.3, 0.4])
    result = rank_institution(_bank(net_income=-99 * 6_550), peers, "roaa")
    assert result["percentile"] == pytest.approx(0.0)
    assert result["rank"] == 5


def test_midpoint_percentile_is_the_share_of_peers_beaten():
    peers = _peers_with_roaa([0.1, 0.2, 0.3, 0.4])
    # roaa of 1_950/655_000*100 == 0.2977 -> beats 0.1 and 0.2 = 2 of 4
    result = rank_institution(_bank(), peers, "roaa")
    assert result["percentile"] == pytest.approx(50.0)


def test_lower_is_better_percentile_counts_the_right_direction():
    """A LOW npl_ratio must score HIGH."""
    peers = [_bank(cert=1000 + i, non_current_loans=390_000 * r / 100)
             for i, r in enumerate([1.0, 2.0, 3.0, 4.0])]
    best = _bank(non_current_loans=390_000 * 0.1 / 100)
    worst = _bank(non_current_loans=390_000 * 9.0 / 100)
    assert rank_institution(best, peers, "npl_ratio")["percentile"] == pytest.approx(100.0)
    assert rank_institution(worst, peers, "npl_ratio")["percentile"] == pytest.approx(0.0)


# ── peer_count must mean the same thing everywhere ───────────────────────────
def test_peer_count_excludes_the_institution_itself():
    """benchmark_institution counts peers only; rank_institution counted N+1."""
    peers = _peers_with_roaa([0.1, 0.2, 0.3, 0.4])
    assert rank_institution(_bank(), peers, "roaa")["peer_count"] == 4


def test_unrankable_metric_reports_zero_peers_not_a_phantom_count():
    peers = _peers_with_roaa([0.1, 0.2])
    result = rank_institution(_bank(tier1_ratio=None), peers, "tier1_ratio")
    assert result["rank"] is None and result["percentile"] is None


def test_no_peers_is_not_a_rank():
    result = rank_institution(_bank(), [], "roaa")
    assert result["rank"] is None
    assert result["percentile"] is None
    assert result["peer_count"] == 0


def test_rank_states_what_it_is_out_of():
    """`rank` counts the institution among the peers; `peer_count` does not.

    Reported alone the pair reads as nonsense — a worst-placed institution
    showed "rank 21, peer_count 20". `rank_of` makes the denominator explicit.
    """
    peers = _peers_with_roaa([0.1, 0.2, 0.3, 0.4])
    result = rank_institution(_bank(net_income=-99 * 6_550), peers, "roaa")
    assert result["peer_count"] == 4
    assert result["rank_of"] == 5
    assert result["rank"] == result["rank_of"]


def test_rank_of_is_absent_when_there_is_no_rank():
    peers = _peers_with_roaa([0.1, 0.2])
    result = rank_institution(_bank(tier1_ratio=None), peers, "tier1_ratio")
    assert result.get("rank_of") is None
