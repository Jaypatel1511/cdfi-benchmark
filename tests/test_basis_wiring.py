"""The basis must survive the trip from the API row to the rendered grade.

A correct basis on InstitutionProfile is worth nothing if benchmark_institution
drops it, or if the parser never asks the API for the published ratios in the
first place. These are the through-function gates.
"""
import pytest
from cdfibenchmark.data import fdic
from cdfibenchmark.data.fdic import _parse_institution
from cdfibenchmark.data.schema import (
    InstitutionProfile, BASIS_FDIC, GRADEABLE_BASES,
)
from cdfibenchmark.metrics.calculator import benchmark_institution


# ── the parser must READ the published ratios ────────────────────────────────
def test_parse_institution_reads_the_published_fdic_ratios():
    row = {
        "CERT": 34352, "NAME": "City First Bank NA", "CITY": "Washington",
        "STALP": "DC", "REPDTE": "20260630",
        "ASSET": 1562007, "DEP": 1182800, "LNLSNET": 1126539,
        "NETINC": 2345, "INTINC": 34011, "EINTEXP": 15521,
        "NONII": 1541, "NONIX": 15143, "EQ": 120000,
        "NIMY": 2.672758390736365, "ROA": 0.324864010816794, "ROE": 2.5,
        "EEFFR": 74.83899955069641, "EAMINTAN": 152,
    }
    inst = _parse_institution(row)
    assert inst.reported_nim == pytest.approx(2.672758390736365)
    assert inst.reported_roaa == pytest.approx(0.324864010816794)
    assert inst.reported_roae == pytest.approx(2.5)
    assert inst.reported_efficiency_ratio == pytest.approx(74.83899955069641)
    assert inst.intangible_amortization == pytest.approx(152)
    assert inst.metric_basis("nim") == BASIS_FDIC


def test_parse_institution_absent_published_ratios_stay_none():
    """A row without the ratio fields must not fabricate them."""
    row = {
        "CERT": 1, "REPDTE": "20260331", "ASSET": 100, "DEP": 80,
        "LNLSNET": 60, "NETINC": 1, "INTINC": 5, "EINTEXP": 2,
        "NONII": 1, "NONIX": 3, "EQ": 10,
    }
    inst = _parse_institution(row)
    assert inst.reported_nim is None
    assert inst.reported_roaa is None
    assert inst.reported_roae is None
    assert inst.reported_efficiency_ratio is None
    assert inst.intangible_amortization is None


# ── the fetchers must REQUEST them ───────────────────────────────────────────
@pytest.mark.parametrize("field", ["NIMY", "ROA", "ROE", "EEFFR", "EAMINTAN"])
def test_both_financial_fetchers_request_the_published_ratio_fields(field):
    """A field the request never asks for can never arrive in the response."""
    import inspect
    src = inspect.getsource(fdic)
    assert src.count(f'"{field}"') >= 1, f"{field} is never requested"


# ── benchmark_institution must CARRY the basis ───────────────────────────────
def _q1_inst():
    return InstitutionProfile(
        cert=1, name="Q1 Bank", city="LA", state="CA", report_date="20260331",
        total_assets=1_424_577, total_deposits=1_100_000, net_loans=770_000,
        net_income=1_232, interest_income=16_208, interest_expense=7_182,
        non_interest_income=590, non_interest_expense=7_881,
        total_equity=120_000, tier1_ratio=12.2,
        gross_loans=1_068_771, non_current_loans=11_461,
        loan_loss_allowance=9_509,
    )


def test_benchmark_results_carry_the_basis(sample_peers):
    results = benchmark_institution(_q1_inst(), sample_peers)
    for r in results:
        assert r.basis, f"{r.metric} result carries no basis"


def test_benchmark_results_carry_the_threshold_source(sample_peers):
    results = benchmark_institution(_q1_inst(), sample_peers)
    for r in results:
        assert r.source, f"{r.metric} result carries no threshold source"


def test_q1_flow_metrics_are_not_graded_end_to_end(sample_peers):
    """The whole point: a Q1 YTD proxy reaches the report ungraded."""
    results = {r.metric: r for r in benchmark_institution(_q1_inst(), sample_peers)}
    for m in ("nim", "roaa", "roae"):
        assert results[m].status == "N/A", (
            f"{m} graded {results[m].status} from a Q1 YTD proxy"
        )
        assert results[m].institution_value is not None, (
            f"{m} value was erased instead of merely ungraded"
        )


def test_period_neutral_metrics_still_graded_at_q1(sample_peers):
    results = {r.metric: r for r in benchmark_institution(_q1_inst(), sample_peers)}
    for m in ("efficiency_ratio", "loans_to_deposits", "npl_ratio",
              "reserve_coverage", "tier1_ratio"):
        assert results[m].status != "N/A", f"{m} wrongly degraded at Q1"


def test_fdic_sourced_flow_metrics_are_graded_at_q1(sample_peers):
    """Supplying FDIC's published ratio restores the grade at any period."""
    inst = _q1_inst()
    inst.reported_nim = 2.7244
    inst.reported_roaa = 0.3559
    inst.reported_roae = 2.63
    results = {r.metric: r for r in benchmark_institution(inst, sample_peers)}
    for m in ("nim", "roaa", "roae"):
        assert results[m].basis in GRADEABLE_BASES
        assert results[m].status != "N/A", f"{m} not graded despite FDIC source"
