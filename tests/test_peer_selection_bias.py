"""The peer group must BRACKET the institution, not sit to one side of it.

B1, measured against the live FDIC API on 2026-09-05, not inferred.

`get_peer_financials` sent `sort_by=ASSET, sort_order=DESC, limit=max_peers+5`
and `build_peer_group` kept `[:50]`. Once 0.3.0 pinned the REPDTE — its own fix
— all 55 rows became distinct institutions at one date, so the group was
exactly the 50 LARGEST banks in the +/-50% asset window. Executed against the
live endpoint at REPDTE 20260630:

    CERT 34352, assets $1562.0MM, window $781.0MM-$2343.0MM
      banks actually in the window: 764
      peer group n=50   asset range $2119.3MM-$2341.3MM
      -> the subject sat at percentile 0 of its own peer group
      -> PeerGroup.caveats was EMPTY

    swept at 20260630, subjects $75MM / $150MM / $400MM / $1,000MM / $1,562MM /
    $5,000MM: every group truncated, EVERY peer larger than the subject at every
    size, smallest peer 1.15x-1.45x the subject's own assets.

Pinning the period converted a LOUD defect (55 rows, 8 certs, 23 years) into a
quiet one: a clean-looking 50-bank single-period group that is silently
size-skewed, which the README then presented as "the 50 real peers".

These gates are offline and run on constructed profiles. They assert the
OUTCOME — where the subject falls inside its own group — so they fail against
any selection that takes a sorted slice, whatever query shape produces it.
"""
import pytest
from unittest.mock import patch

from cdfibenchmark.data.schema import InstitutionProfile
from cdfibenchmark.peers.selector import build_peer_group

SUBJECT_ASSETS = 1_000_000  # $1.0B in thousands


def _bank(cert, assets, repdte="20260630"):
    return InstitutionProfile(
        cert=cert, name=f"Bank {cert}", city="Chicago", state="IL",
        report_date=repdte, total_assets=float(assets), total_deposits=assets * 0.8,
        net_loans=assets * 0.6, net_income=assets * 0.01,
        interest_income=assets * 0.04, interest_expense=assets * 0.01,
        non_interest_income=assets * 0.005, non_interest_expense=assets * 0.025,
        total_equity=assets * 0.1,
    )


def _subject():
    return _bank(99001, SUBJECT_ASSETS)


def _window(n=400):
    """A realistic window: `n` banks spread evenly across +/-50% of the subject.

    The subject sits in the middle by construction, so a group of its nearest
    neighbours must bracket it and a group of the window's largest cannot.
    """
    lo, hi = SUBJECT_ASSETS * 0.5, SUBJECT_ASSETS * 1.5
    return [_bank(1000 + i, lo + (hi - lo) * i / (n - 1)) for i in range(n)]


@pytest.fixture
def fake_api():
    """Stands in for FDIC /financials: honours sort_order and limit like the API."""
    rows = _window()

    def fake(**kwargs):
        ordered = sorted(rows, key=lambda p: p.total_assets,
                         reverse=(kwargs.get("sort_order", "DESC") == "DESC"))
        return ordered[:kwargs.get("limit", 100)]

    return fake


def test_subject_is_bracketed_by_its_own_peer_group(fake_api):
    """The subject must not sit at an extreme of its own peer asset range.

    This is the gate that fails against sort-by-ASSET-DESC + [:50], which put
    the subject at percentile 0 at every size measured.
    """
    with patch("cdfibenchmark.peers.selector.get_peer_financials", side_effect=fake_api):
        peers = build_peer_group(_subject())

    pct = peers.asset_percentile
    assert pct is not None, "peer group reported no asset percentile for the subject"
    assert 25 <= pct <= 75, (
        f"the subject sits at percentile {pct} of its own peer group. A group "
        f"selected by size rather than by proximity puts it at an extreme "
        f"(measured: percentile 0 against the live API at every subject size "
        f"from $75MM to $5,000MM), and every peer-median comparison on the "
        f"report then carries an undisclosed size bias."
    )


def test_peer_group_contains_banks_both_larger_and_smaller(fake_api):
    """A 'peer' group in which every bank is larger is not a peer group."""
    with patch("cdfibenchmark.peers.selector.get_peer_financials", side_effect=fake_api):
        peers = build_peer_group(_subject())

    smaller = [p for p in peers if p.total_assets < SUBJECT_ASSETS]
    larger = [p for p in peers if p.total_assets > SUBJECT_ASSETS]
    assert smaller and larger, (
        f"peer group has {len(smaller)} banks smaller and {len(larger)} larger "
        f"than the subject — it lies entirely to one side of the institution "
        f"it is meant to benchmark."
    )


def test_peer_group_is_the_nearest_banks_in_the_window(fake_api):
    """Selection must be by distance from the subject, exactly."""
    with patch("cdfibenchmark.peers.selector.get_peer_financials", side_effect=fake_api):
        peers = build_peer_group(_subject())

    chosen = {p.cert for p in peers}
    expected = {
        p.cert for p in sorted(
            _window(), key=lambda p: abs(p.total_assets - SUBJECT_ASSETS)
        )[:len(peers)]
    }
    assert chosen == expected, (
        "peer group is not the nearest-by-assets banks in the window"
    )


def test_a_size_skewed_group_is_caveated(fake_api):
    """If the group IS one-sided, the report must say so rather than imply not.

    Selection is the primary remedy; this is the disclosure that must hold even
    when a window genuinely has nothing on one side of the subject.
    """
    # A window with nothing below the subject at all.
    rows = [_bank(2000 + i, SUBJECT_ASSETS * (1.05 + 0.001 * i)) for i in range(60)]

    def one_sided(**kwargs):
        return rows[:kwargs.get("limit", 100)]

    with patch("cdfibenchmark.peers.selector.get_peer_financials", side_effect=one_sided):
        peers = build_peer_group(_subject())

    assert peers.asset_percentile == 0, "constructed group should be one-sided"
    joined = " ".join(peers.caveats).lower()
    assert "percentile" in joined and "size bias" in joined, (
        f"a peer group in which every bank is larger than the subject produced "
        f"caveats {peers.caveats!r} — through 0.3.0 this list was EMPTY while "
        f"the report printed a peer asset range two lines under the "
        f"institution's own assets and stated no relationship between them."
    )


def test_report_states_where_the_subject_sits_in_the_peer_range(fake_api):
    """The disclosure half: a range with no stated relationship is what let
    a size-skewed group read as 'the 50 real peers'."""
    from cdfibenchmark.report.generator import generate_report

    subject = _subject()
    with patch("cdfibenchmark.peers.selector.get_peer_financials", side_effect=fake_api):
        peers = build_peer_group(subject)
    report = generate_report(subject, peers)

    assert "Institution's Position in the Peer Asset Range" in report, (
        "report shows a Peer Asset Range but never says where the institution "
        "falls inside it"
    )
    assert "Peer Selection Basis" in report, (
        "report does not disclose how the peer group was selected"
    )


def test_selection_parameters_are_named_constants_not_bare_defaults():
    """The window, the cap and the floor shape the population and are HOUSE.

    They were bare literals in a signature: unnamed, uncited, and invisible to
    the reader of the report they determine — the same defect the round fixed
    for the grading thresholds, on the population instead.

    Asserted over the SOURCE, by AST, not over the resolved values. The
    first version of this gate compared `sig.parameters[...].default` to the
    constant by identity and PASSED against bare `0.5` / `10` / `50` — because
    CPython caches small ints and folds equal float constants, so an equal
    literal IS the same object. That is exactly the defect this release fixes
    in `test_house_thresholds_are_named_house_at_the_constant`: a gate that
    checks a VALUE cannot see whether the attribution is present in the code.
    """
    import ast
    import pathlib
    from cdfibenchmark.peers import selector

    tree = ast.parse(pathlib.Path(selector.__file__).read_text())
    func = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "build_peer_group"),
        None,
    )
    assert func is not None, "build_peer_group not found in selector source"

    args = func.args.args + func.args.kwonlyargs
    defaults = ([None] * (len(func.args.args) - len(func.args.defaults))
                + list(func.args.defaults) + list(func.args.kw_defaults))
    by_name = dict(zip([a.arg for a in args], defaults))

    for param in ("asset_tolerance", "min_peers", "max_peers"):
        node = by_name.get(param)
        assert node is not None, f"{param} has no default in build_peer_group"
        assert isinstance(node, ast.Name) and node.id.startswith("HOUSE_"), (
            f"build_peer_group({param}=...) defaults to "
            f"{ast.dump(node)} — a bare literal. It must name a HOUSE_ "
            f"constant so the attribution travels to the render layer; this "
            f"number decides WHICH BANKS the report compares against."
        )
