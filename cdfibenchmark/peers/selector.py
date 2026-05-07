"""
Peer group selection logic for CDFI benchmarking.
"""
from cdfibenchmark.data.schema import InstitutionProfile, ASSET_BUCKETS
from cdfibenchmark.data.fdic import get_peer_financials


def build_peer_group(
    institution: InstitutionProfile,
    same_state: bool = False,
    asset_tolerance: float = 0.5,
    min_peers: int = 10,
    max_peers: int = 50,
    report_date: str = None,
) -> list:
    """
    Build a peer group for an institution based on asset size and geography.

    Args:
        institution:       The institution to benchmark
        same_state:        Restrict peers to same state
        asset_tolerance:   +/- tolerance for asset size (0.5 = 50%)
        min_peers:         Minimum number of peers to return
        max_peers:         Maximum number of peers to return
        report_date:       Report date for peer financials

    Returns:
        List of InstitutionProfile objects (excluding the institution itself)
    """
    assets = institution.total_assets
    min_assets = int(assets * (1 - asset_tolerance))
    max_assets = int(assets * (1 + asset_tolerance))

    state = institution.state if same_state else None

    peers = get_peer_financials(
        state=state,
        min_assets=min_assets,
        max_assets=max_assets,
        report_date=report_date,
        limit=max_peers + 5,
    )

    # Exclude the institution itself
    peers = [p for p in peers if p.cert != institution.cert]

    # If not enough peers, widen the asset range
    if len(peers) < min_peers and same_state:
        peers = get_peer_financials(
            min_assets=min_assets,
            max_assets=max_assets,
            report_date=report_date,
            limit=max_peers + 5,
        )
        peers = [p for p in peers if p.cert != institution.cert]

    return peers[:max_peers]


def build_sample_peer_group(institution: InstitutionProfile) -> list:
    """
    Build a synthetic peer group for testing without API calls.
    Generates realistic peer institutions based on the target institution.
    """
    import random
    import copy
    random.seed(42)

    peers = []
    for i in range(20):
        scale = random.uniform(0.6, 1.4)
        peer = InstitutionProfile(
            cert=90000 + i,
            name=f"Community Bank {i+1}",
            city="Chicago",
            state=institution.state,
            report_date=institution.report_date,
            total_assets=institution.total_assets * scale,
            total_deposits=institution.total_deposits * scale * random.uniform(0.85, 1.1),
            net_loans=institution.net_loans * scale * random.uniform(0.7, 1.2),
            net_income=institution.net_income * scale * random.uniform(0.5, 1.5),
            interest_income=institution.interest_income * scale * random.uniform(0.9, 1.1),
            interest_expense=institution.interest_expense * scale * random.uniform(0.8, 1.2),
            non_interest_income=institution.non_interest_income * scale * random.uniform(0.7, 1.3),
            non_interest_expense=institution.non_interest_expense * scale * random.uniform(0.85, 1.15),
            total_equity=institution.total_equity * scale * random.uniform(0.8, 1.2),
            tier1_ratio=random.uniform(8.0, 18.0),
            gross_loans=institution.net_loans * scale * 1.05,
            non_current_loans=institution.net_loans * scale * random.uniform(0.005, 0.04),
            loan_loss_allowance=institution.net_loans * scale * random.uniform(0.008, 0.02),
        )
        peers.append(peer)
    return peers
