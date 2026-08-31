"""Peer group composition: pinning, distinctness, and disclosed fallback.

B4 (measured, not inferred). The FDIC /financials endpoint is one row per
institution-QUARTER — its own `ID` field is "<CERT>_<REPDTE>". `build_peer_group`
never defaulted `report_date` to the institution's own, so with report_date=None
no REPDTE filter was sent at all and the query sorted by ASSET. Running the exact
query the code builds, for a real institution, on 2026-08-30:

    filters=ASSET:[1 TO *] AND STALP:NV AND ASSET:[8393143 TO *]
            AND ASSET:[* TO 25179429]        limit=55  sort=ASSET DESC
    rows returned:       55
    DISTINCT CERT count:  8
    REPDTE histogram:    20030930 .. 20260630   (23 years, 50 distinct quarters)
    most repeated CERT:  27389 x 17

So a "50-peer group" was 8 banks counted up to 17 times each, across 23 years
of history, and the peer median was computed over that. Meanwhile the
institution itself came from get_financials sorted REPDTE DESC — its most
recent quarter. This compounds B2: a Q1 YTD institution against Q4 YTD peers is
a factor-of-four apples-to-oranges on top of the period error.

B3. The same_state fallback silently returned a NATIONAL group with no signal,
OVERWROTE rather than supplemented (a same-state query returning 8 peers was
replaced by a national one returning 3, or by []), and `min_peers` read as a
floor while only ever being a trigger. The comment said "widen the asset range"
while the code widened the GEOGRAPHY.
"""
import pytest
from unittest.mock import patch

from cdfibenchmark.data import fdic
from cdfibenchmark.data.schema import InstitutionProfile
from cdfibenchmark.peers.selector import build_peer_group, PeerGroup


def _peer(cert, repdte="20260331", state="CA", assets=655_000):
    return InstitutionProfile(
        cert=cert, name=f"Peer {cert}", city="LA", state=state,
        report_date=repdte, total_assets=assets, total_deposits=520_000,
        net_loans=380_000, net_income=1_950, interest_income=28_000,
        interest_expense=8_000, non_interest_income=3_500,
        non_interest_expense=22_000, total_equity=48_000,
    )


@pytest.fixture
def inst():
    return _peer(57542, repdte="20260331")


# ── B4: the peer query must be PINNED to the institution's period ────────────
def test_peer_query_defaults_report_date_to_the_institutions_own(inst):
    """With no explicit report_date, peers must be pinned to the institution's.

    Otherwise the query carries no REPDTE filter at all and returns one row per
    institution-quarter across the endpoint's entire history.
    """
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return [_peer(c) for c in range(1, 21)]

    with patch.object(fdic, "get_peer_financials", side_effect=fake), \
         patch("cdfibenchmark.peers.selector.get_peer_financials", side_effect=fake):
        build_peer_group(inst)

    assert seen.get("report_date") == "20260331", (
        f"peer query was not pinned to the institution's REPDTE: "
        f"report_date={seen.get('report_date')!r}"
    )


def test_peer_group_contains_no_duplicate_certs(inst):
    """One bank must never appear more than once, whatever the API returns."""
    dupes = [_peer(27389, repdte=r) for r in
             ("20030930", "20120630", "20211231", "20260331")]
    dupes += [_peer(26211, repdte=r) for r in ("20040331", "20260331")]
    dupes += [_peer(c) for c in range(100, 112)]

    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=dupes):
        group = build_peer_group(inst)

    certs = [p.cert for p in group]
    assert len(certs) == len(set(certs)), (
        f"peer group repeats CERTs: {sorted(certs)}"
    )


def test_duplicate_certs_resolve_to_the_row_nearest_the_target_period(inst):
    """When a CERT appears at several REPDTEs, keep the pinned period's row."""
    rows = [_peer(27389, repdte="20030930"), _peer(27389, repdte="20260331"),
            _peer(27389, repdte="20120630")]
    rows += [_peer(c) for c in range(100, 115)]

    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        group = build_peer_group(inst, report_date="20260331")

    kept = [p for p in group if p.cert == 27389]
    assert len(kept) == 1
    assert kept[0].report_date == "20260331"


def test_peer_group_reports_its_period_spread(inst):
    rows = [_peer(c, repdte="20260331") for c in range(100, 120)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        group = build_peer_group(inst)
    assert group.report_dates == {"20260331"}
    assert group.is_single_period is True


def test_mixed_period_peer_group_is_flagged(inst):
    rows = [_peer(c, repdte="20260331") for c in range(100, 110)]
    rows += [_peer(c, repdte="20251231") for c in range(200, 210)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        group = build_peer_group(inst)
    assert group.is_single_period is False
    assert len(group.report_dates) == 2


# ── B3: the fallback must be DISCLOSED and must not make things worse ────────
def test_same_state_fallback_is_recorded_on_the_returned_group(inst):
    state_rows = [_peer(c, state="CA") for c in range(1, 4)]        # 3 < min
    national_rows = [_peer(c, state="TX") for c in range(50, 70)]   # 20

    calls = []

    def fake(**kw):
        calls.append(kw)
        return state_rows if kw.get("state") else national_rows

    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               side_effect=fake):
        group = build_peer_group(inst, same_state=True, min_peers=10)

    assert group.state_constraint_dropped is True, (
        "the caller asked for same-state peers, got a national group, and "
        "nothing on the result said so"
    )
    assert group.requested_state == "CA"


def test_no_fallback_means_no_dropped_flag(inst):
    rows = [_peer(c, state="CA") for c in range(1, 21)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        group = build_peer_group(inst, same_state=True, min_peers=10)
    assert group.state_constraint_dropped is False


def test_fallback_never_returns_a_worse_group_than_it_replaced(inst):
    """A same-state group of 8 must not be replaced by a national group of 3."""
    state_rows = [_peer(c, state="CA") for c in range(1, 9)]     # 8
    national_rows = [_peer(c, state="TX") for c in range(50, 53)]  # 3

    def fake(**kw):
        return state_rows if kw.get("state") else national_rows

    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               side_effect=fake):
        group = build_peer_group(inst, same_state=True, min_peers=10)

    assert len(group) == 8, (
        f"fallback replaced an 8-peer same-state group with {len(group)} peers"
    )
    assert group.state_constraint_dropped is False


def test_fallback_returning_empty_does_not_erase_the_state_group(inst):
    state_rows = [_peer(c, state="CA") for c in range(1, 6)]

    def fake(**kw):
        return state_rows if kw.get("state") else []

    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               side_effect=fake):
        group = build_peer_group(inst, same_state=True, min_peers=10)

    assert len(group) == 5


# ── B3: min_peers must MEAN something ────────────────────────────────────────
def test_group_below_min_peers_is_marked_insufficient(inst):
    rows = [_peer(c) for c in range(1, 4)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        group = build_peer_group(inst, min_peers=10)
    assert group.below_min_peers is True
    assert group.min_peers == 10


def test_group_at_or_above_min_peers_is_not_marked_insufficient(inst):
    rows = [_peer(c) for c in range(1, 21)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        group = build_peer_group(inst, min_peers=10)
    assert group.below_min_peers is False


# ── back-compat: a PeerGroup must still behave as the list it replaced ───────
def test_peer_group_is_still_a_sequence_of_profiles(inst):
    rows = [_peer(c) for c in range(1, 21)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        group = build_peer_group(inst)
    assert isinstance(group, PeerGroup)
    assert len(group) == 20
    assert all(isinstance(p, InstitutionProfile) for p in group)
    assert all(isinstance(p, InstitutionProfile) for p in list(group))
    assert isinstance(group[0], InstitutionProfile)
