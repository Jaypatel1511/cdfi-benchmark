import pytest
from cdfibenchmark.data.schema import InstitutionProfile
from cdfibenchmark.peers.selector import build_sample_peer_group


@pytest.fixture
def sample_institution():
    return InstitutionProfile(
        cert=57542,
        name="Broadway Federal Bank",
        city="Los Angeles",
        state="CA",
        report_date="20241231",
        total_assets=655_000,
        total_deposits=520_000,
        net_loans=380_000,
        net_income=1_950,
        interest_income=28_000,
        interest_expense=8_000,
        non_interest_income=3_500,
        non_interest_expense=22_000,
        total_equity=48_000,
        tier1_ratio=12.2,
        gross_loans=390_000,
        non_current_loans=5_850,
        loan_loss_allowance=7_800,
    )


@pytest.fixture
def sample_peers(sample_institution):
    return build_sample_peer_group(sample_institution)


@pytest.fixture
def present_zero_cored_institution():
    """An institution that genuinely reported zero for a core metric.

    net_income is a real reported 0.0 (not absent), so roaa computes to a real
    0.0% against a positive asset base. Used to verify the report renders a
    present zero as "0.00%" and still grades it — never erasing a legitimate
    zero to "N/A" the way a truthiness gate would.
    """
    return InstitutionProfile(
        cert=57543,
        name="Zero Income Bank",
        city="Los Angeles",
        state="CA",
        report_date="20241231",
        total_assets=655_000,
        total_deposits=520_000,
        net_loans=380_000,
        net_income=0,          # real reported zero → roaa == 0.0%
        interest_income=28_000,
        interest_expense=8_000,
        non_interest_income=3_500,
        non_interest_expense=22_000,
        total_equity=48_000,
        tier1_ratio=12.2,
        gross_loans=390_000,
        non_current_loans=5_850,
        loan_loss_allowance=7_800,
    )


@pytest.fixture
def nan_cored_institution():
    """An institution whose core financials the FDIC response omitted.

    Every core field is NaN (exactly what _parse_institution produces for an
    all-core-absent record) and optional ratios are None. Used to verify the
    downstream consumers treat an unknown-value institution as not-available
    rather than fabricating a metric, bucket, grade, or rank.
    """
    nan = float("nan")
    return InstitutionProfile(
        cert=99999,
        name="Sparse Bank",
        city="Nowhere",
        state="CA",
        report_date="20241231",
        total_assets=nan,
        total_deposits=nan,
        net_loans=nan,
        net_income=nan,
        interest_income=nan,
        interest_expense=nan,
        non_interest_income=nan,
        non_interest_expense=nan,
        total_equity=nan,
    )
