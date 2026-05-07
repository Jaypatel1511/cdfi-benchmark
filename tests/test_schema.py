import pytest
from cdfibenchmark.data.schema import InstitutionProfile


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
