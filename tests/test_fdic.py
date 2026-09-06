"""
Tests for the FDIC data layer's fail-loud contract.

Transport/decode failures raise FDICAPIError. Valid-JSON-but-wrong-shape
raises FDICResponseError. A successful request that legitimately returns zero
rows keeps returning the empty value (None / empty DataFrame / []).

All HTTP is mocked at cdfibenchmark.data.fdic.requests.get — no live network,
no skips — and the real fetchers are called through-function.
"""
import math

import pandas as pd
import pytest
import requests
from unittest.mock import patch, MagicMock

from cdfibenchmark import FDICAPIError, FDICResponseError
from cdfibenchmark.data import fdic
from cdfibenchmark.data.schema import (
    InstitutionProfile, BASIS_REJECTED_IMPLAUSIBLE, BASIS_UNREPORTED,
)


def _response(payload=None, *, raise_status=None, json_exc=None):
    """Build a fake requests.Response.

    raise_status: exception raised by raise_for_status()
    json_exc:     exception raised by .json()
    payload:      object returned by .json() on success
    """
    resp = MagicMock(name="Response")
    if raise_status is not None:
        resp.raise_for_status.side_effect = raise_status
    else:
        resp.raise_for_status.return_value = None
    if json_exc is not None:
        resp.json.side_effect = json_exc
    else:
        resp.json.return_value = payload
    return resp


# Field semantics verified against the FDIC data dictionary + live API, July 2026:
#   RBCT1J  = Tier One (Core) Capital, YTD — DOLLARS (thousands), NOT a ratio.
#   RBC1AAJ = Leverage (Core Capital) Ratio — PERCENT (the real tier1 ratio).
#   NAME    = institution name (NOT INSTNAME, which isn't on these endpoints).
# Do NOT "simplify" RBCT1J to a small round number: its dollar magnitude here is
# exactly what makes the wrong-field-class guard (D1b) testable — a regression
# that remaps RBCT1J into the ratio slot trips the ratio plausibility bound
# [_RATIO_MIN, _RATIO_MAX].
WELL_FORMED_ROW = {
    "CERT": 99001,
    "NAME": "Broadway Federal Bank",
    "CITY": "Los Angeles",
    "STALP": "CA",
    "REPDTE": "20241231",
    "ASSET": 655000,
    "DEP": 520000,
    "LNLSNET": 380000,
    "NETINC": 1950,
    "INTINC": 28000,
    "EINTEXP": 8000,
    "NONII": 3500,
    "NONIX": 22000,
    "EQ": 48000,
    "RBCT1J": 134229,   # dollars (thousands) — present in the response, unmapped
    "RBC1AAJ": 12.2,    # percent — the leverage ratio that grades the tier1 slot
    "LNLSGR": 390000,
    "NCLNLS": 5850,
    "LNATRES": 7800,
}

ONE_RECORD = {"data": [{"data": WELL_FORMED_ROW, "score": 1.0}]}
EMPTY = {"data": []}
MALFORMED = {"data": "oops"}   # valid JSON, wrong shape (data is not a list of records)


# Every (op, callable) pair plus the context token its messages must name.
ALL_FETCHERS = [
    ("get_institution", lambda: fdic.get_institution(99001), "99001"),
    ("search_institutions", lambda: fdic.search_institutions(state="CA"), "CA"),
    ("get_financials", lambda: fdic.get_financials(99001), "99001"),
    ("get_peer_financials", lambda: fdic.get_peer_financials(state="CA"), "CA"),
]


# ── (a) transport / decode failures → FDICAPIError ────────────────────────────
@pytest.mark.parametrize("op,call,ctx", ALL_FETCHERS)
def test_http_error_raises_api_error(op, call, ctx):
    with patch.object(fdic.requests, "get",
                      return_value=_response(raise_status=requests.exceptions.HTTPError("500"))) as mock_get:
        with pytest.raises(FDICAPIError) as exc:
            call()
    assert op in str(exc.value)
    assert ctx in str(exc.value)
    assert mock_get.called


@pytest.mark.parametrize("op,call,ctx", ALL_FETCHERS)
def test_timeout_raises_api_error(op, call, ctx):
    with patch.object(fdic.requests, "get",
                      side_effect=requests.exceptions.Timeout("timed out")) as mock_get:
        with pytest.raises(FDICAPIError) as exc:
            call()
    assert op in str(exc.value)
    assert ctx in str(exc.value)
    assert mock_get.called


@pytest.mark.parametrize("op,call,ctx", ALL_FETCHERS)
def test_json_decode_error_raises_api_error(op, call, ctx):
    with patch.object(fdic.requests, "get",
                      return_value=_response(json_exc=ValueError("No JSON could be decoded"))) as mock_get:
        with pytest.raises(FDICAPIError) as exc:
            call()
    assert op in str(exc.value)
    assert ctx in str(exc.value)
    assert mock_get.called


# ── (b) valid JSON, wrong shape → FDICResponseError ───────────────────────────
@pytest.mark.parametrize("op,call,ctx", ALL_FETCHERS)
def test_malformed_shape_raises_response_error(op, call, ctx):
    with patch.object(fdic.requests, "get", return_value=_response(MALFORMED)) as mock_get:
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert ctx in str(exc.value)
    assert mock_get.called


def test_non_numeric_cert_raises_response_error():
    """A row that decodes fine but has a non-numeric CERT is a schema problem."""
    payload = {"data": [{"data": {"CERT": "not-a-number", "NAME": "X"}}]}
    with patch.object(fdic.requests, "get", return_value=_response(payload)) as mock_get:
        with pytest.raises(FDICResponseError):
            fdic.get_financials(99001)
    assert mock_get.called
    with patch.object(fdic.requests, "get", return_value=_response(payload)) as mock_get:
        with pytest.raises(FDICResponseError):
            fdic.get_peer_financials(state="CA")
    assert mock_get.called


# ── (c) legitimate empty (200, {"data": []}) → empty, NOT a raise ─────────────
def test_get_institution_empty_returns_none():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)) as mock_get:
        assert fdic.get_institution(99001) is None
    assert mock_get.called


def test_get_financials_empty_returns_none():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)) as mock_get:
        assert fdic.get_financials(99001) is None
    assert mock_get.called


def test_search_institutions_empty_returns_empty_dataframe():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)) as mock_get:
        result = fdic.search_institutions(state="CA")
    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert mock_get.called


def test_get_peer_financials_empty_returns_empty_list():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)) as mock_get:
        assert fdic.get_peer_financials(state="CA") == []
    assert mock_get.called


# ── (d) happy path (200, one well-formed record) ──────────────────────────────
def test_get_financials_happy_path_parses_to_profile():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)) as mock_get:
        profile = fdic.get_financials(99001)
    assert isinstance(profile, InstitutionProfile)
    assert profile.cert == 99001
    assert profile.name == "Broadway Federal Bank"
    assert mock_get.called


def test_get_institution_happy_path_returns_record():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)) as mock_get:
        record = fdic.get_institution(99001)
    assert record["CERT"] == 99001
    assert mock_get.called


def test_search_institutions_happy_path_returns_dataframe():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)) as mock_get:
        df = fdic.search_institutions(state="CA")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert df.iloc[0]["CERT"] == 99001
    assert mock_get.called


def test_get_peer_financials_happy_path_returns_profiles():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)) as mock_get:
        peers = fdic.get_peer_financials(state="CA")
    assert isinstance(peers, list)
    assert len(peers) == 1
    assert isinstance(peers[0], InstitutionProfile)
    assert peers[0].cert == 99001
    assert mock_get.called


# ── (e) FIELD-LEVEL fail-loud: parse layer must not fabricate ─────────────────
# The two parsing fetchers run a record through _parse_institution. A record
# missing its identity (CERT) or carrying a present-but-garbage core financial
# is a contract problem and must raise FDICResponseError naming the field —
# never become a phantom cert=0 bank or a silent 0.0. Absent (vs garbage)
# fields are legitimately sparse: core → NaN, optional ratio → None, and a
# real present 0.0 is preserved (never erased to None).


def _wrap(record):
    """Wrap one raw record in the FDIC envelope used by the parsing fetchers."""
    return {"data": [{"data": record, "score": 1.0}]}


# Both fetchers that push a record through _parse_institution. A malformed
# record must raise out of BOTH (peer batch fails loud on a bad record too).
PARSE_CALLS = [
    ("get_financials", lambda: fdic.get_financials(99001)),
    ("get_peer_financials", lambda: fdic.get_peer_financials(state="CA")),
]

# Same two fetchers, but unwrapped to a single InstitutionProfile so the
# parses-but-sparse cases can assert on field values.
PARSE_PROFILE = [
    ("get_financials", lambda: fdic.get_financials(99001)),
    ("get_peer_financials", lambda: fdic.get_peer_financials(state="CA")[0]),
]


@pytest.mark.parametrize("op,call", PARSE_CALLS)
def test_empty_record_raises_naming_cert(op, call):
    """{"data":[{}]} — a record with no fields at all has no identity."""
    with patch.object(fdic.requests, "get", return_value=_response(_wrap({}))) as mock_get:
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert "CERT" in str(exc.value)
    assert mock_get.called


@pytest.mark.parametrize("op,call", PARSE_CALLS)
def test_missing_cert_raises_naming_cert(op, call):
    """A record with financials but no CERT must not become a cert=0 phantom."""
    record = {k: v for k, v in WELL_FORMED_ROW.items() if k != "CERT"}
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert "CERT" in str(exc.value)
    assert mock_get.called


@pytest.mark.parametrize("op,call", PARSE_CALLS)
def test_garbage_core_asset_raises_naming_asset(op, call):
    """ASSET present but non-numeric is garbage, not zero — name ASSET."""
    record = dict(WELL_FORMED_ROW, ASSET="garbage")
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert "ASSET" in str(exc.value)
    assert mock_get.called


@pytest.mark.parametrize("op,call", PARSE_CALLS)
def test_garbage_core_netinc_raises_naming_netinc(op, call):
    """A second core field — NETINC present-but-garbage must also fail loud."""
    record = dict(WELL_FORMED_ROW, NETINC="x")
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert "NETINC" in str(exc.value)
    assert mock_get.called


@pytest.mark.parametrize("op,call", PARSE_CALLS)
def test_garbage_optional_ratio_raises_naming_field(op, call):
    """An optional ratio present-but-garbage is still a contract breach. The
    tier1 slot now sources the ratio field RBC1AAJ, so that is the field named."""
    record = dict(WELL_FORMED_ROW, RBC1AAJ="garbage")
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert "RBC1AAJ" in str(exc.value)
    assert mock_get.called


@pytest.mark.parametrize("op,extract", PARSE_PROFILE)
def test_absent_optional_ratio_is_none_not_zero(op, extract):
    """Optional ratio absent → None (legitimately sparse), never 0.0."""
    record = {k: v for k, v in WELL_FORMED_ROW.items() if k != "RBC1AAJ"}
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        profile = extract()
    assert profile.tier1_ratio is None
    assert profile.tier1_ratio != 0.0
    assert mock_get.called


@pytest.mark.parametrize("op,extract", PARSE_PROFILE)
def test_present_zero_optional_ratio_preserved(op, extract):
    """A real present 0.0 ratio must survive — `safe_float(...) or None` erased it."""
    record = dict(WELL_FORMED_ROW, RBC1AAJ=0.0)
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        profile = extract()
    assert profile.tier1_ratio == 0.0
    assert profile.tier1_ratio is not None
    assert mock_get.called


@pytest.mark.parametrize("op,extract", PARSE_PROFILE)
def test_absent_core_is_nan_not_zero(op, extract):
    """Core financial absent → NaN (unknown), never a fabricated 0.0, and the
    NaN propagates to a downstream metric rather than becoming a real number."""
    record = {k: v for k, v in WELL_FORMED_ROW.items() if k != "ASSET"}
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        profile = extract()
    assert math.isnan(profile.total_assets)
    assert profile.total_assets != 0.0
    assert math.isnan(profile.nim)   # divides by total_assets → NaN, not 0/None
    assert mock_get.called


@pytest.mark.parametrize("op,extract", PARSE_PROFILE)
def test_present_zero_core_preserved(op, extract):
    """A real present 0.0 core must survive as 0.0 — distinct from absent→NaN."""
    record = dict(WELL_FORMED_ROW, ASSET=0)
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        profile = extract()
    assert profile.total_assets == 0.0
    assert not math.isnan(profile.total_assets)
    assert mock_get.called


# ── D1 / D1-guard: the tier1 slot carries the LEVERAGE RATIO (RBC1AAJ, a
# percent), NEVER the dollar Tier-One-Capital field (RBCT1J). And a ratio-class
# field arriving with a dollar-magnitude value fails loud (defense-in-depth).
def _leverage_row(**overrides):
    """A realistic /financials row: RBCT1J is dollars (thousands), RBC1AAJ is a
    percent. Magnitude realism here is what makes the wrong-field-class guard
    testable — do not 'simplify' RBCT1J to a small round number."""
    row = {
        "CERT": 25883, "NAME": "First Eagle  Bank", "CITY": "Chicago",
        "STALP": "IL", "REPDTE": "20260331",
        "ASSET": 655000, "DEP": 520000, "LNLSNET": 380000, "NETINC": 1950,
        "INTINC": 28000, "EINTEXP": 8000, "NONII": 3500, "NONIX": 22000,
        "EQ": 48000,
        "RBCT1J": 134229,   # Tier One (Core) Capital, YTD $ — dollars, NOT a ratio
        "RBC1AAJ": 21.46,   # Leverage (Core Capital) Ratio, % — the real ratio
        "LNLSGR": 390000, "NCLNLS": 5850, "LNATRES": 7800,
    }
    row.update(overrides)
    return row


def test_name_read_from_NAME_key_preserves_double_space():
    """D3: the parser reads the institution name from NAME (not INSTNAME, which
    is absent on these endpoints). The stored name's internal double space is
    preserved, not normalised."""
    row = _leverage_row(NAME="First Eagle  Bank")
    with patch.object(fdic.requests, "get",
                      return_value=_response(_wrap(row))) as mock_get:
        profile = fdic.get_financials(25883)
    assert profile.name == "First Eagle  Bank"
    assert mock_get.called


def test_tier1_slot_uses_leverage_ratio_not_dollar_field():
    """D1a: the graded tier1 value is the leverage ratio 21.46 (RBC1AAJ), not the
    dollar Tier-One-Capital 134229 (RBCT1J)."""
    with patch.object(fdic.requests, "get",
                      return_value=_response(_wrap(_leverage_row()))) as mock_get:
        profile = fdic.get_financials(25883)
    assert profile.tier1_ratio == pytest.approx(21.46)
    assert profile.tier1_ratio != 134229
    assert mock_get.called


def test_ratio_class_field_out_of_range_degrades_the_field_not_the_call():
    """D1b: a dollar-magnitude value in a ratio-class slot is REFUSED, and the
    refusal costs one field — not the request, and not the peer group.

    It used to raise FDICResponseError. The bound is a magnitude heuristic with
    a measured 5.1% margin over the modern population's maximum, so it will be
    wrong about a real bank eventually; making that wrongness fatal to every
    metric on every peer was a worse outcome than the single nonsense cell it
    avoided. Everything else on the row must survive intact.
    """
    row = _leverage_row(RBC1AAJ=134229)   # wrong field class / API drift
    with patch.object(fdic.requests, "get",
                      return_value=_response(_wrap(row))) as mock_get:
        profile = fdic.get_financials(25883)
    assert profile.tier1_ratio is None, "the implausible value was kept"
    assert profile.total_assets == pytest.approx(655000), (
        "one refused optional field discarded the rest of the row"
    )
    assert mock_get.called


def test_a_refused_value_is_recorded_not_swallowed():
    """The cost of degrading is that the user does not watch it happen.

    So the refusal is recorded: `implausible_fields` names the field, and the
    basis line says a value WAS published and refused — which is a different
    statement from "FDIC published nothing", and must not collapse into it.
    """
    row = _leverage_row(RBC1AAJ=134229)
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(row))):
        refused = fdic.get_financials(25883)
    row_absent = _leverage_row()
    del row_absent["RBC1AAJ"]
    with patch.object(fdic.requests, "get",
                      return_value=_response(_wrap(row_absent))):
        absent = fdic.get_financials(25883)

    assert refused.implausible_fields == ("RBC1AAJ",)
    assert absent.implausible_fields == ()
    assert refused.tier1_ratio is absent.tier1_ratio is None
    assert refused.metric_basis("tier1_ratio") == BASIS_REJECTED_IMPLAUSIBLE
    assert absent.metric_basis("tier1_ratio") == BASIS_UNREPORTED
    assert refused.metric_basis("tier1_ratio") != absent.metric_basis("tier1_ratio"), (
        "a refused value is indistinguishable from an unreported one"
    )


@pytest.mark.parametrize("leverage,cert,name,repdte", [
    (951.11,  59287, "ENTREBANK",                  "20220331"),
    (758.67,  59265, "WATERFALL BANK",             "20210930"),
    (277.16,  59379, "CORNERSTONE COMMUNITY BANK", "20260630"),
    (194.25,  16281, "FIRST CITY BANK",            "20260630"),
    (142.22,  59378, "EREBOR BANK N A",            "20260331"),
])
def test_a_real_leverage_ratio_in_the_upper_tail_is_not_refused(
        leverage, cert, name, repdte):
    """The modern population's real upper tail, and how close the bound is to it.

    RBC1AAJ is Tier 1 capital over adjusted AVERAGE assets, so a de novo bank
    (whose average assets trail its period-end assets) legitimately runs into
    the hundreds of percent. Swept 2026-09-05 over 46 quarters, 2015Q1-2026Q2,
    every filer: the maximum is 951.11 — ENTREBANK, $33,708k of assets against
    $32,138k of Tier 1 capital, a bank squarely inside the CDFI size band. That
    is 5.1% below `_RATIO_MAX`, which is the whole reason a breach degrades
    instead of raising.

    The bound was [-100, 150] through 0.3.0 and refused CORNERSTONE and FIRST
    CITY, both real, on live 2026Q2 data.
    """
    row = _leverage_row(RBC1AAJ=leverage)
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(row))):
        profile = fdic.get_financials(25883)
    assert profile.tier1_ratio == pytest.approx(leverage), (
        f"a real leverage ratio of {leverage}% ({name}, CERT {cert} at {repdte}) "
        f"was refused as implausible"
    )
    assert profile.implausible_fields == ()


@pytest.mark.parametrize("leverage,cert,name,repdte", [
    (-6.20,  9956, "TRUST CO BANK",       "20160331"),
    (-1.99, 58302, "FIRST NBC BANK",      "20170331"),
    (-893.69, 33132, "STATE STREET B&T CO OF CT NA", "19901231"),
    (-330.93, 33460, "NEW METROPOLITAN FSB",        "19911231"),
])
def test_a_real_negative_leverage_ratio_is_not_refused(leverage, cert, name, repdte):
    """`_RATIO_MIN` had ZERO coverage before this test, at any value.

    The guard's only parametrized case was 277.16 / 194.25 / 142.22 — all
    positive — so the floor was never exercised in either direction, and -100.0
    had never been derived from anything. It is now the mirror of `_RATIO_MAX`.

    A negative leverage ratio is a real filing, not drift: an institution whose
    Tier 1 capital is negative is insolvent on a capital basis, which is a thing
    that happens and that a benchmarking tool should show. Swept 1984Q1-2026Q2,
    169 quarters: 42 quarters have a minimum below -100 (the old floor), and
    exactly one below -1,000 (-1,524.07, CERT 34128 at 19960331). At the modern
    end the deepest value in 46 quarters is -6.20.
    """
    row = _leverage_row(RBC1AAJ=leverage)
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(row))):
        profile = fdic.get_financials(25883)
    assert profile.tier1_ratio == pytest.approx(leverage), (
        f"a real negative leverage ratio of {leverage}% ({name}, CERT {cert} at "
        f"{repdte}) was refused as implausible"
    )
    assert profile.implausible_fields == ()


def test_the_bound_is_symmetric_and_both_ends_refuse():
    """Both ends do work, and neither is a magic number sitting on its own.

    `_RATIO_MIN` is the mirror of `_RATIO_MAX` because what this guard detects
    is MAGNITUDE — RBCT1J runs to -7,789,337 (IndyMac, 20081231) as well as to
    302,589,000, so a one-sided bound would miss half the swap it exists for.
    """
    assert fdic._RATIO_MIN == -fdic._RATIO_MAX, (
        "the floor is not derived from the ceiling; it is a bare constant again"
    )
    for value in (fdic._RATIO_MAX + 0.01, fdic._RATIO_MIN - 0.01,
                  302589000, -7789337):
        row = _leverage_row(RBC1AAJ=value)
        with patch.object(fdic.requests, "get",
                          return_value=_response(_wrap(row))):
            profile = fdic.get_financials(25883)
        assert profile.tier1_ratio is None, f"{value} was admitted as a percentage"
        assert profile.implausible_fields == ("RBC1AAJ",)
    for value in (fdic._RATIO_MAX, fdic._RATIO_MIN):
        row = _leverage_row(RBC1AAJ=value)
        with patch.object(fdic.requests, "get",
                          return_value=_response(_wrap(row))):
            profile = fdic.get_financials(25883)
        assert profile.tier1_ratio == pytest.approx(value), (
            f"the bound {value} is exclusive; it must be inclusive"
        )


def test_ratio_class_guard_still_catches_a_dollar_magnitude_capital_figure():
    """Degrading must not disarm the guard.

    RBCT1J (Tier 1 capital, $k) reaches 302,589,000 — five orders of magnitude
    outside the band — which is the swap this guard exists to catch. Measured at
    20260630, the band refuses 4,295 of the 4,296 RBCT1J values in the
    population, and refuses zero real RBC1AAJ values.
    """
    row = _leverage_row(RBC1AAJ=302589000)
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(row))):
        profile = fdic.get_financials(25883)
    assert profile.tier1_ratio is None
    assert "RBC1AAJ" in profile.implausible_fields


def test_a_systematic_field_swap_is_still_loud_across_a_batch():
    """Degrading the ROW must not make a systematic swap quiet.

    The objection to degrading is that a real API drift stops raising. It does
    not stop being visible: every record breaches, so the metric goes N/A for
    the whole batch and every profile names the field.
    """
    rows = [_leverage_row(CERT=c, RBC1AAJ=134229 + c) for c in (101, 102, 103)]
    payload = {"data": [{"data": r} for r in rows]}
    with patch.object(fdic.requests, "get", return_value=_response(payload)):
        profiles = fdic.get_peer_financials(report_date="20260630")
    assert len(profiles) == 3
    assert all(p.tier1_ratio is None for p in profiles)
    assert all(p.implausible_fields == ("RBC1AAJ",) for p in profiles)


def test_dollar_class_field_large_value_not_bounded():
    """The guard must NOT bound dollar-class fields: gross loans of 390000 (a
    legitimate thousands-of-dollars magnitude) must parse without raising."""
    with patch.object(fdic.requests, "get",
                      return_value=_response(_wrap(_leverage_row(LNLSGR=5_000_000)))) as mock_get:
        profile = fdic.get_financials(25883)
    assert profile.gross_loans == pytest.approx(5_000_000)
    assert mock_get.called


# ── D2: name search must use the search=NAME: parameter, not an INSTNAME filter
# The FDIC API matches names via the `search` query parameter (search=NAME:Eagle
# → 60 hits). The old code used filters=INSTNAME:"<name>" — an exact-phrase
# filter that never matches substrings and reads a field (INSTNAME) that isn't on
# the /institutions response. This surfaced nothing for real name queries.
def _name_search_response():
    """Mock the real /institutions response shape for a NAME query, including
    First Eagle's stored double-space name."""
    return _response({"data": [
        {"data": {"CERT": 25883, "NAME": "First Eagle  Bank",
                  "CITY": "Chicago", "STALP": "IL", "ASSET": 500000}},
        {"data": {"CERT": 12345, "NAME": "Eagle Bank",
                  "CITY": "Everett", "STALP": "MA", "ASSET": 900000}},
    ]})


def test_search_by_name_surfaces_matches():
    with patch.object(fdic.requests, "get",
                      return_value=_name_search_response()) as mock_get:
        df = fdic.search_institutions("Eagle")
    assert not df.empty
    # double space preserved, not normalised
    assert "First Eagle  Bank" in df["NAME"].values


def test_search_by_name_uses_search_param_not_instname_filter():
    with patch.object(fdic.requests, "get",
                      return_value=_name_search_response()) as mock_get:
        fdic.search_institutions("Eagle")
    params = mock_get.call_args.kwargs["params"]
    assert params.get("search") == "NAME:Eagle", (
        f"expected search=NAME:Eagle, got params={params!r}"
    )
    # the failed exact-phrase INSTNAME filter must be gone
    assert "INSTNAME" not in params.get("filters", "")
    # ACTIVE:1 is still enforced in filters
    assert "ACTIVE:1" in params.get("filters", "")


# ── (f) top-level "data": null → FDICResponseError on ALL FOUR fetchers ───────
# Key absent / null / non-list is wrong-shape and must raise; only a present
# empty list ({"data": []}) is the legitimate "zero rows" answer.
@pytest.mark.parametrize("op,call,ctx", ALL_FETCHERS)
def test_data_null_raises_response_error(op, call, ctx):
    with patch.object(fdic.requests, "get", return_value=_response({"data": None})) as mock_get:
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert ctx in str(exc.value)
    assert mock_get.called
