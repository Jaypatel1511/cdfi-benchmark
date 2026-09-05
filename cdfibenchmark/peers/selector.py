"""
Peer group selection logic for CDFI benchmarking.
"""
from cdfibenchmark.data.schema import InstitutionProfile, ASSET_BUCKETS, _is_missing
from cdfibenchmark.data.fdic import get_peer_financials, FDIC_MAX_LIMIT
from cdfibenchmark.exceptions import FDICResponseError

# ── Peer-selection parameters ─────────────────────────────────────────────────
# Every number below shapes WHICH BANKS the report compares the subject against,
# and not one of them comes from a standard. They are this tool's own, exactly
# like the HOUSE_ grading thresholds in schema.py, and they were previously bare
# defaults in a signature — unnamed, uncited, and invisible to the reader of the
# report they determine. Naming them carries the attribution to the render layer
# (see PeerGroup.selection_basis), which is this release's whole thesis applied
# to the population rather than to the thresholds.
#
# There is no regulatory or supervisory definition of a bank "peer group" on
# asset size. The FDIC's own UBPR peer groups are a different construct
# (fixed asset bands plus metro/non-metro splits), not a +/-50% window around
# the subject, so this is not that either and must not be read as it.
HOUSE_ASSET_TOLERANCE = 0.5   # +/-50% of the subject's assets
HOUSE_MAX_PEERS = 50          # how many of the window's banks are kept
HOUSE_MIN_PEERS = 10          # below this the group is caveated, not failed


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
        subject_assets=None,
        universe_size=None,
        asset_tolerance=None,
        max_peers=None,
        window_truncated=False,
    ):
        super().__init__(peers)
        self.requested_state = requested_state
        self.state_constraint_dropped = bool(state_constraint_dropped)
        self.min_peers = min_peers
        self.target_report_date = target_report_date
        #: The subject's own assets ($k), so the group can say where the
        #: subject sits INSIDE it rather than only what its range is.
        self.subject_assets = subject_assets
        #: How many banks were in the asset window this group was drawn from.
        self.universe_size = universe_size
        self.asset_tolerance = asset_tolerance
        self.max_peers = max_peers
        self.window_truncated = bool(window_truncated)

    @property
    def asset_percentile(self):
        """Share of this group's peers SMALLER than the subject, 0-100.

        The defect this exists to make visible: the group was previously the N
        LARGEST banks in the window, so this read 0 at every size while the
        report printed a peer asset range and said nothing about where the
        subject fell in it. A number near 50 means the group brackets the
        subject; 0 or 100 means it does not and the comparison is size-skewed.

        None when it cannot be computed (no subject assets, no peer with known
        assets) — never a fabricated 50.
        """
        if _is_missing(self.subject_assets):
            return None
        known = [p.total_assets for p in self if not _is_missing(p.total_assets)]
        if not known:
            return None
        below = sum(1 for a in known if a < self.subject_assets)
        return round(below / len(known) * 100, 1)

    @property
    def selection_basis(self) -> str:
        """How this group was chosen — rendered so the reader can argue with it."""
        tol = self.asset_tolerance
        tol_txt = f"+/-{tol * 100:.0f}%" if tol is not None else "an unrecorded"
        universe = (f"{self.universe_size:,}" if self.universe_size is not None
                    else "an unrecorded number of")
        return (
            f"the {len(self)} banks NEAREST the subject in total assets, out of "
            f"{universe} in a {tol_txt} asset window at "
            f"{self.target_report_date or 'an unpinned period'}. Asset window, "
            f"group size and nearest-neighbour selection are this tool's own "
            f"choices (HOUSE), not a supervisory peer-group definition."
        )

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
        # The size-skew caveat. Through 0.3.0 the group was the N LARGEST banks
        # in the window at every subject size, the subject sat at percentile 0
        # of its own peer group, and `caveats` was EMPTY — the one basis that
        # skewed every number on the page was the one nothing disclosed.
        pct = self.asset_percentile
        if pct is not None and (pct <= 10 or pct >= 90):
            side = "LARGER" if pct <= 10 else "SMALLER"
            out.append(
                f"The subject is at the {pct:g}th percentile of its own peer "
                f"group by assets: nearly every peer is {side} than the "
                f"institution. Comparisons against this group's median carry a "
                f"size bias."
            )
        if self.window_truncated:
            out.append(
                f"The asset window held more banks than a single FDIC query can "
                f"return ({FDIC_MAX_LIMIT:,}), so the group was selected from a "
                f"truncated slice of it rather than from the whole window."
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


def _nearest_by_assets(peers, subject_assets, max_peers):
    """Keep the ``max_peers`` banks CLOSEST to the subject in total assets.

    This replaces ``[:max_peers]`` over an ASSET-DESC query, which returned the
    largest banks in the window at every subject size. Measured against the live
    API at REPDTE 20260630 for six subject sizes from $75MM to $5,000MM, that
    selection returned a group in which EVERY peer was larger than the subject,
    with the smallest peer 1.15x-1.45x the subject's own assets.

    Ties break on CERT so the group is deterministic. A peer whose assets are
    unknown cannot be distance-ranked and sorts last rather than being dropped:
    it is still a real bank in the window.
    """
    def key(p):
        if _is_missing(p.total_assets):
            return (1, 0.0, p.cert)
        return (0, abs(p.total_assets - subject_assets), p.cert)

    return sorted(peers, key=key)[:max_peers]


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
    asset_tolerance: float = HOUSE_ASSET_TOLERANCE,
    min_peers: int = HOUSE_MIN_PEERS,
    max_peers: int = HOUSE_MAX_PEERS,
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

    # Fetch the WHOLE asset window, then choose within it — rather than asking
    # the API for a sorted slice and keeping the head of it.
    #
    # Why the whole window is affordable: the endpoint caps `limit` at 10,000
    # (measured), and the widest +/-50% window anywhere in the CDFI size range
    # holds far fewer. Measured at REPDTE 20260630 across subjects from $25MM to
    # $25,000MM, the largest window was 1,439 banks (at a $400MM subject); the
    # subject's own 764-bank window came back in one 341 KiB request in 0.88s.
    # So this is ONE call, not the two a nearest-above/nearest-below pair of
    # bounded queries would need, and it is exact rather than nearly exact: the
    # selection sees every bank in the window instead of the 30 closest on each
    # side. It also yields the window's true population, which is what lets the
    # report say what the group was drawn FROM.
    def _fetch(state_filter):
        rows = get_peer_financials(
            state=state_filter,
            min_assets=min_assets,
            max_assets=max_assets,
            report_date=target_report_date,
            limit=FDIC_MAX_LIMIT,
            sort_order="ASC",
        )
        # The endpoint truncates at its cap without saying so. If the row count
        # came back AT the cap the window was larger than one query can return,
        # and the selection below is over a slice again — recorded, not hidden.
        truncated = len(rows) >= FDIC_MAX_LIMIT
        rows = [p for p in rows if p.cert != institution.cert]
        rows = _dedupe_by_cert(rows, target_report_date)
        return _nearest_by_assets(rows, assets, max_peers), len(rows), truncated

    peers, universe, truncated = _fetch(state)
    dropped = False

    # If the same-state group is too small, ALSO try nationally — and keep
    # whichever group is better, rather than overwriting with whichever ran
    # last. The old code replaced an 8-peer same-state group with a 3-peer
    # national one (or with []) and said nothing about either.
    #
    # (The old comment here said "widen the asset range". It widened the
    # GEOGRAPHY; the asset window is identical in both queries. Fixed.)
    if same_state and len(peers) < min_peers:
        nat_peers, nat_universe, nat_truncated = _fetch(None)
        if len(nat_peers) > len(peers):
            peers, universe, truncated, dropped = (
                nat_peers, nat_universe, nat_truncated, True
            )

    return PeerGroup(
        peers,
        requested_state=state,
        state_constraint_dropped=dropped,
        min_peers=min_peers,
        target_report_date=target_report_date,
        subject_assets=assets,
        universe_size=universe,
        asset_tolerance=asset_tolerance,
        max_peers=max_peers,
        window_truncated=truncated,
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
        subject_assets=institution.total_assets,
        universe_size=len(peers),
        asset_tolerance=None,
        max_peers=len(peers),
    )
