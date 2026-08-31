"""
Peer group selection logic for CDFI benchmarking.
"""
from cdfibenchmark.data.schema import InstitutionProfile, ASSET_BUCKETS, _is_missing
from cdfibenchmark.data.fdic import get_peer_financials
from cdfibenchmark.exceptions import FDICResponseError


class PeerGroup(list):
    """The peers, plus how the group was actually built.

    A plain ``list`` was the whole problem. Three facts that change how a
    benchmark should be read had nowhere to live, so they were silently
    dropped and the caller saw only a list length:

    * the caller asked for same-state peers and got a NATIONAL group
      (``state_constraint_dropped``),
    * the group is smaller than the floor the caller asked for
      (``below_min_peers``),
    * the peers are not all at one reporting period
      (``is_single_period`` / ``report_dates``).

    This subclasses ``list`` so every existing consumer — ``len(peers)``,
    iteration, indexing, ``compute_peer_metrics(peers)`` — keeps working
    unchanged.
    """

    def __init__(
        self,
        peers=(),
        *,
        requested_state=None,
        state_constraint_dropped=False,
        min_peers=0,
        target_report_date=None,
    ):
        super().__init__(peers)
        self.requested_state = requested_state
        self.state_constraint_dropped = bool(state_constraint_dropped)
        self.min_peers = min_peers
        self.target_report_date = target_report_date

    @property
    def report_dates(self) -> set:
        """Every distinct REPDTE present in the group."""
        return {p.report_date for p in self if p.report_date}

    @property
    def is_single_period(self) -> bool:
        """True when every peer is at the same reporting period.

        A mixed-period group makes the peer median meaningless for any YTD
        flow metric: a Q1 figure and a Q4 figure differ by a factor of four
        before any real difference in performance.
        """
        return len(self.report_dates) <= 1

    @property
    def below_min_peers(self) -> bool:
        return len(self) < self.min_peers

    @property
    def caveats(self) -> list:
        """Human-readable statements of every way this group is not ideal.

        Empty means the group is exactly what was asked for. Rendered on the
        report so an incomplete peer group can never read as a complete one.
        """
        out = []
        if self.state_constraint_dropped:
            out.append(
                f"Same-state peers were requested for {self.requested_state} but "
                f"too few were found; this is a NATIONAL peer group."
            )
        if self.below_min_peers:
            out.append(
                f"Peer group has {len(self)} institutions, below the requested "
                f"minimum of {self.min_peers}. Percentiles over so few peers are "
                f"not a reliable benchmark."
            )
        if not self.is_single_period:
            dates = ", ".join(sorted(self.report_dates))
            out.append(
                f"Peers are NOT all at one reporting period ({dates}). "
                f"Year-to-date flow metrics are not comparable across periods."
            )
        elif (self.target_report_date and self.report_dates
                and self.report_dates != {self.target_report_date}):
            out.append(
                f"Peers are at {sorted(self.report_dates)[0]} but the institution "
                f"is at {self.target_report_date}."
            )
        return out


def _dedupe_by_cert(peers, target_report_date=None):
    """Collapse to one row per CERT, keeping the row nearest the target period.

    The FDIC /financials endpoint returns one row per institution-QUARTER (its
    own ``ID`` is ``"<CERT>_<REPDTE>"``). An unpinned query therefore returns
    the same bank once per historical quarter it has filed. Measured on
    2026-08-30 against the exact query build_peer_group used to send: 55 rows,
    8 distinct CERTs, REPDTEs from 20030930 to 20260630, one CERT appearing 17
    times. Pinning the REPDTE (below) prevents that at the source; this is the
    defence that does not depend on the API honouring the filter.
    """
    best = {}
    for p in peers:
        prior = best.get(p.cert)
        if prior is None or _period_distance(p, target_report_date) < \
                _period_distance(prior, target_report_date):
            best[p.cert] = p
    # Preserve first-seen order so the API's own ASSET sort survives dedup.
    seen, out = set(), []
    for p in peers:
        if p.cert not in seen:
            seen.add(p.cert)
            out.append(best[p.cert])
    return out


def _period_distance(peer, target_report_date):
    """How far a peer's REPDTE is from the target. Exact match sorts first."""
    if not target_report_date:
        return 0
    try:
        return abs(int(peer.report_date) - int(target_report_date))
    except (TypeError, ValueError):
        return float("inf")


def build_peer_group(
    institution: InstitutionProfile,
    same_state: bool = False,
    asset_tolerance: float = 0.5,
    min_peers: int = 10,
    max_peers: int = 50,
    report_date: str = None,
) -> PeerGroup:
    """
    Build a peer group for an institution based on asset size and geography.

    Args:
        institution:       The institution to benchmark
        same_state:        Restrict peers to same state
        asset_tolerance:   +/- tolerance for asset size (0.5 = 50%)
        min_peers:         Minimum number of peers for a usable benchmark. Not a
                           hard failure — a shortfall is recorded on the returned
                           group (``below_min_peers``) and rendered as a caveat.
        max_peers:         Maximum number of peers to return
        report_date:       Report date for peer financials. Defaults to the
                           INSTITUTION'S OWN report_date — never left unset.

    Returns:
        PeerGroup (a list of InstitutionProfile, excluding the institution
        itself) carrying how the group was built.
    """
    # Unknown (NaN) assets make the peer asset window undefined. Fail loud —
    # int(NaN) would otherwise raise a bare ValueError, and silently returning
    # [] would let an unknown-asset bank read as "no peers found", the same
    # absence-reads-as-result failure this release eliminates.
    if _is_missing(institution.total_assets):
        raise FDICResponseError(
            f"cannot select peers for an institution with unknown assets: "
            f"CERT {institution.cert}"
        )

    assets = institution.total_assets
    min_assets = int(assets * (1 - asset_tolerance))
    max_assets = int(assets * (1 + asset_tolerance))

    # Pin the peer period to the institution's own. Left unset, get_peer_financials
    # sends NO REPDTE filter at all and the endpoint returns one row per
    # institution-quarter across its whole history — so the "peer group" was a
    # handful of banks repeated across 23 years, and the institution (fetched
    # REPDTE DESC) was compared against them. That also compounds the YTD
    # period error: a Q1 institution against Q4 peers is a factor of four
    # before any real difference.
    target_report_date = report_date or (institution.report_date or None)

    state = institution.state if same_state else None

    def _fetch(state_filter):
        rows = get_peer_financials(
            state=state_filter,
            min_assets=min_assets,
            max_assets=max_assets,
            report_date=target_report_date,
            limit=max_peers + 5,
        )
        rows = [p for p in rows if p.cert != institution.cert]
        return _dedupe_by_cert(rows, target_report_date)[:max_peers]

    peers = _fetch(state)
    dropped = False

    # If the same-state group is too small, ALSO try nationally — and keep
    # whichever group is better, rather than overwriting with whichever ran
    # last. The old code replaced an 8-peer same-state group with a 3-peer
    # national one (or with []) and said nothing about either.
    #
    # (The old comment here said "widen the asset range". It widened the
    # GEOGRAPHY; the asset window is identical in both queries. Fixed.)
    if same_state and len(peers) < min_peers:
        national = _fetch(None)
        if len(national) > len(peers):
            peers, dropped = national, True

    return PeerGroup(
        peers,
        requested_state=state,
        state_constraint_dropped=dropped,
        min_peers=min_peers,
        target_report_date=target_report_date,
    )


def build_sample_peer_group(institution: InstitutionProfile) -> PeerGroup:
    """
    Build a SYNTHETIC peer group for testing and documentation without API calls.

    These institutions do not exist. Their financials are generated by scaling
    the supplied institution's own figures by pseudo-random factors; nothing
    here is measured, and no report built on them describes any real bank.
    """
    import random

    # A LOCAL Random instance. `random.seed(42)` seeded the GLOBAL RNG, so
    # merely building a sample peer group silently reset the caller's process-
    # wide random state.
    rng = random.Random(42)

    peers = []
    for i in range(20):
        scale = rng.uniform(0.6, 1.4)
        peer = InstitutionProfile(
            cert=90000 + i,
            name=f"Sample Community Bank {i+1} (SYNTHETIC)",
            city="Chicago",
            state=institution.state,
            report_date=institution.report_date,
            total_assets=institution.total_assets * scale,
            total_deposits=institution.total_deposits * scale * rng.uniform(0.85, 1.1),
            net_loans=institution.net_loans * scale * rng.uniform(0.7, 1.2),
            net_income=institution.net_income * scale * rng.uniform(0.5, 1.5),
            interest_income=institution.interest_income * scale * rng.uniform(0.9, 1.1),
            interest_expense=institution.interest_expense * scale * rng.uniform(0.8, 1.2),
            non_interest_income=institution.non_interest_income * scale * rng.uniform(0.7, 1.3),
            non_interest_expense=institution.non_interest_expense * scale * rng.uniform(0.85, 1.15),
            total_equity=institution.total_equity * scale * rng.uniform(0.8, 1.2),
            tier1_ratio=rng.uniform(8.0, 18.0),
            gross_loans=institution.net_loans * scale * 1.05,
            non_current_loans=institution.net_loans * scale * rng.uniform(0.005, 0.04),
            loan_loss_allowance=institution.net_loans * scale * rng.uniform(0.008, 0.02),
        )
        peers.append(peer)
    return PeerGroup(
        peers,
        requested_state=institution.state,
        min_peers=0,
        target_report_date=institution.report_date,
    )
