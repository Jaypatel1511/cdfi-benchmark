"""Period basis and denominator basis of the flow metrics.

Through 0.2.1, `nim`, `roaa` and `roae` divided FDIC call-report YTD *flow*
items (INTINC, EINTEXP, NETINC) by point-in-time *stocks*, then graded the
result against annual-basis thresholds (3.5 / 1.0 / 10). At a Q1 REPDTE the
flow covers three months, so a healthy bank read roughly 4x low and graded
WEAK. Measured against FDIC's own published series for CERT 34352:

    REPDTE    package computed   FDIC publishes   ratio
    20260331  nim   0.6336       NIMY  2.7244     4.30x
    20260331  roaa  0.0865       ROA   0.3559     4.12x
    20260331  roae  0.6563       ROE   2.6300     4.01x

Two further defects stack on top of the period effect:

  * NIM's denominator is TOTAL assets. FDIC's NIMY -- and the 3.5% threshold
    calibrated to it -- is over average EARNING assets, a strictly smaller
    denominator, so the computed proxy is biased low even at a Q4 REPDTE
    (1.09x residual at 20251231).
  * `efficiency_ratio` claimed in-code to match FDIC EEFFR but omitted the
    amortization-of-intangibles / goodwill-impairment subtraction from its
    numerator. Measured: at 20250930 the package read 191.06% where FDIC
    publishes 88.33%.

The ruling: prefer FDIC's published, correctly-denominated ratio; when it is
absent, render the computed value with its basis on its face and DO NOT grade
an estimate against a threshold calibrated to a different measurement.
"""
import pytest
from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult, GRADEABLE_BASES,
)


def _inst(**over):
    base = dict(
        cert=1, name="Basis Bank", city="LA", state="CA",
        report_date="20260331",
        total_assets=1_424_577, total_deposits=1_100_000, net_loans=1_059_262,
        net_income=1_232,
        interest_income=16_208, interest_expense=7_182,
        non_interest_income=590, non_interest_expense=7_881,
        total_equity=120_000,
        gross_loans=1_068_771, non_current_loans=11_461,
        loan_loss_allowance=9_509,
    )
    base.update(over)
    return InstitutionProfile(**base)


# ── quarter parsing ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("repdte,quarter", [
    ("20260331", 1), ("20260630", 2), ("20260930", 3), ("20251231", 4),
    ("", None), ("garbage", None),
])
def test_fiscal_quarter_parsed_from_report_date(repdte, quarter):
    assert _inst(report_date=repdte).fiscal_quarter == quarter


# ── FDIC-published values are preferred ──────────────────────────────────────
def test_reported_ratios_override_the_computed_proxy():
    """When FDIC publishes the ratio, that measurement is the metric."""
    inst = _inst(reported_nim=2.7244, reported_roaa=0.3559, reported_roae=2.63)
    assert inst.nim == pytest.approx(2.7244)
    assert inst.roaa == pytest.approx(0.3559)
    assert inst.roae == pytest.approx(2.63)


def test_reported_ratios_are_gradeable():
    inst = _inst(reported_nim=2.7244, reported_roaa=0.3559, reported_roae=2.63)
    for m in ("nim", "roaa", "roae"):
        assert inst.metric_basis(m) in GRADEABLE_BASES, (
            f"{m} sourced from FDIC must be gradeable"
        )


# ── computed fallback is NOT graded ──────────────────────────────────────────
def test_computed_q1_flow_metrics_are_not_gradeable():
    """A Q1 YTD proxy must not be graded against an annual-basis threshold."""
    inst = _inst(report_date="20260331")
    for m in ("nim", "roaa", "roae"):
        assert inst.metric_basis(m) not in GRADEABLE_BASES, (
            f"{m} computed from Q1 YTD flows was marked gradeable"
        )


def test_computed_nim_is_never_gradeable_even_at_q4():
    """NIM over TOTAL assets is not NIMY, whatever the period.

    The 3.5% threshold is calibrated to average EARNING assets. A full-year
    computation fixes the period and leaves the denominator wrong.
    """
    inst = _inst(report_date="20251231")
    assert inst.metric_basis("nim") not in GRADEABLE_BASES


def test_computed_roaa_roae_are_gradeable_at_a_full_year_report_date():
    """At Q4 the YTD flow covers the full year, so the period objection lifts."""
    inst = _inst(report_date="20251231")
    for m in ("roaa", "roae"):
        assert inst.metric_basis(m) in GRADEABLE_BASES


def test_period_neutral_metrics_are_always_gradeable():
    """Stock ratios and the efficiency ratio carry no period error at all."""
    inst = _inst(report_date="20260331", tier1_ratio=12.2)
    for m in ("efficiency_ratio", "loans_to_deposits", "npl_ratio",
              "reserve_coverage", "tier1_ratio"):
        assert inst.metric_basis(m) in GRADEABLE_BASES, f"{m} not gradeable"


# ── the grade actually degrades ──────────────────────────────────────────────
def test_ungradeable_basis_yields_na_status_not_a_grade():
    r = BenchmarkResult(
        metric="roaa", institution_value=0.0865,
        peer_median=None, peer_25th=None, peer_75th=None, peer_count=0,
        basis="computed from YTD flows through Q1 — not annualized",
    )
    assert r.status == "N/A", (
        "a non-annualized YTD proxy was graded against an annual threshold"
    )


def test_ungradeable_basis_still_reports_its_value():
    """Degrade the GRADE, not the number — the measured value is still shown."""
    r = BenchmarkResult(
        metric="roaa", institution_value=0.0865,
        peer_median=None, peer_25th=None, peer_75th=None, peer_count=0,
        basis="computed from YTD flows through Q1 — not annualized",
    )
    assert r.institution_value == pytest.approx(0.0865)


# ── efficiency ratio == FDIC EEFFR ───────────────────────────────────────────
def test_efficiency_ratio_subtracts_intangible_amortization_like_eeffr():
    """EEFFR = (NONIX - EAMINTAN) / ((INTINC - EINTEXP) + NONII) * 100.

    Verified against the live FDIC API for CERT 34352 at five REPDTEs; the
    formula reproduces FDIC's published EEFFR to 5 decimal places. The
    package omitted EAMINTAN entirely.
    """
    inst = _inst(report_date="20260630",
                 interest_income=34_011, interest_expense=15_521,
                 non_interest_income=1_541, non_interest_expense=15_143,
                 intangible_amortization=152)
    # FDIC publishes 74.83899955069641 for CERT 34352 at 20260630.
    assert inst.efficiency_ratio == pytest.approx(74.83899955069641, abs=1e-9)


def test_efficiency_ratio_goodwill_impairment_period_matches_fdic():
    """The 2025Q3 goodwill impairment is exactly where the old formula broke."""
    inst = _inst(report_date="20250930",
                 interest_income=44_989, interest_expense=20_653,
                 non_interest_income=1_064, non_interest_expense=48_529,
                 intangible_amortization=26_094)
    # FDIC publishes 88.32677165354332 for CERT 34352 at 20250930; the formula
    # reproduces it exactly, not approximately.
    assert inst.efficiency_ratio == pytest.approx(88.32677165354332, abs=1e-9)


def test_efficiency_ratio_absent_amortization_does_not_fabricate_a_subtraction():
    """EAMINTAN absent → subtract nothing, never a made-up figure."""
    inst = _inst(interest_income=16_208, interest_expense=7_182,
                 non_interest_income=590, non_interest_expense=7_881,
                 intangible_amortization=None)
    assert inst.efficiency_ratio == pytest.approx(7_881 / 9_616 * 100, abs=1e-6)
