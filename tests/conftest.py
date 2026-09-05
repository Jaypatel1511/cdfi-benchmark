import pytest
from cdfibenchmark.data.schema import InstitutionProfile
from cdfibenchmark.peers.selector import build_sample_peer_group


@pytest.fixture
def sample_institution():
    """A FICTIONAL institution. Its CERT is outside the FDIC's issued range.

    This fixture previously carried cert=57542 with the name "Broadway Federal
    Bank". CERT 57542 is Toyota Financial Savings Bank (Henderson NV, $16.8B) —
    verified against the live FDIC /institutions endpoint. Broadway Federal is
    CERT 30306 and is inactive. A fixture that binds a real cert to the wrong
    real name teaches the binding to every reader who copies it, which is how
    it reached the README's Quickstart as a LIVE call.
    """
    return InstitutionProfile(
        cert=99001,
        name="Riverstone Community Bank (SYNTHETIC)",
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
        tier1_ratio=12.2,   # Tier 1 LEVERAGE ratio (%), sourced from RBC1AAJ
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
        cert=99002,
        name="Zero Income Bank (SYNTHETIC)",
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
        tier1_ratio=12.2,   # Tier 1 LEVERAGE ratio (%), sourced from RBC1AAJ
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
