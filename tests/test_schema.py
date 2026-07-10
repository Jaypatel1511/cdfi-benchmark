import pytest
from cdfibenchmark.data.schema import InstitutionProfile, BenchmarkResult


def test_institution_created(sample_institution):
    assert sample_institution.name == "Broadway Federal Bank"
    assert sample_institution.cert == 57542


def test_total_assets_mm(sample_institution):
    assert sample_institution.total_assets_mm == pytest.approx(655.0)


def test_asset_bucket(sample_institution):
    assert sample_institution.asset_bucket == "medium"


def test_nim_computed(sample_institution):
    nim = sample_institution.nim
    assert nim is not None
    assert nim > 0


def test_efficiency_ratio_computed(sample_institution):
    er = sample_institution.efficiency_ratio
    assert er is not None
    assert 0 < er < 200


def test_roaa_computed(sample_institution):
    roaa = sample_institution.roaa
    assert roaa is not None


def test_roae_computed(sample_institution):
    roae = sample_institution.roae
    assert roae is not None


def test_loans_to_deposits(sample_institution):
    ltd = sample_institution.loans_to_deposits
    assert ltd is not None
    assert ltd > 0


def test_npl_ratio(sample_institution):
    npl = sample_institution.npl_ratio
    assert npl is not None
    assert npl > 0


def test_reserve_coverage(sample_institution):
    rc = sample_institution.reserve_coverage
    assert rc is not None
    assert rc > 0


def test_metrics_dict(sample_institution):
    metrics = sample_institution.metrics_dict()
    assert "nim" in metrics
    assert "efficiency_ratio" in metrics
    assert "roaa" in metrics


# ── D5: efficiency-ratio denominator = NET interest income + non-interest income
# FDIC EEFFR defines the efficiency ratio as "noninterest expense as a percent of
# net interest income plus noninterest income". 0.1.0–0.2.0 used GROSS interest
# income (interest_income + non_interest_income) as the denominator, which
# inflates the denominator and understates the ratio at every period.
def test_efficiency_ratio_uses_net_interest_income_denominator():
    inst = InstitutionProfile(
        cert=1, name="Eff Bank", city="LA", state="CA", report_date="20241231",
        total_assets=500_000, total_deposits=400_000, net_loans=300_000,
        net_income=500,
        interest_income=8520, interest_expense=2196,
        non_interest_income=371, non_interest_expense=2750,
        total_equity=40_000,
    )
    # revenue = (8520 - 2196) + 371 = 6695; efficiency = 2750 / 6695 * 100 = 41.08
    assert inst.efficiency_ratio == pytest.approx(41.08, abs=0.1)


def test_efficiency_ratio_nonpositive_denominator_is_none():
    """Denominator <= 0 → None (existing zero-denominator convention), never a
    negative grade or inf."""
    inst = InstitutionProfile(
        cert=2, name="Neg Bank", city="LA", state="CA", report_date="20241231",
        total_assets=500_000, total_deposits=400_000, net_loans=300_000,
        net_income=-100,
        interest_income=1000, interest_expense=1500,   # net interest income < 0
        non_interest_income=200, non_interest_expense=900,  # revenue = -300
        total_equity=40_000,
    )
    assert inst.efficiency_ratio is None


# ── D1: tier1 slot is graded as a LEVERAGE ratio. Thresholds reset for a
# leverage ratio: STRONG >= 8 (CBLR qualifying level, 12 CFR 324.12, lowered
# 9%->8% eff. 2026-07-01), ADEQUATE >= 5 (well-capitalized leverage minimum,
# PCA), WEAK < 5.
def _tier1_status(value):
    return BenchmarkResult(
        metric="tier1_ratio", institution_value=value,
        peer_median=None, peer_25th=None, peer_75th=None, peer_count=0,
    ).status


def test_tier1_leverage_thresholds():
    assert _tier1_status(21.46) == "STRONG"
    assert _tier1_status(8.0) == "STRONG"    # CBLR qualifying (lowered to 8% 2026-07-01)
    assert _tier1_status(7.99) == "ADEQUATE"
    assert _tier1_status(5.0) == "ADEQUATE"  # PCA well-capitalized minimum
    assert _tier1_status(4.99) == "WEAK"
