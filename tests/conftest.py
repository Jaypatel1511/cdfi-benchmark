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
