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
from cdfibenchmark.data.schema import InstitutionProfile


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


WELL_FORMED_ROW = {
    "CERT": 57542,
    "INSTNAME": "Broadway Federal Bank",
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
    "RBCT1J": 12.2,
    "LNLSGR": 390000,
    "NCLNLS": 5850,
    "LNATRES": 7800,
}

ONE_RECORD = {"data": [{"data": WELL_FORMED_ROW, "score": 1.0}]}
EMPTY = {"data": []}
MALFORMED = {"data": "oops"}   # valid JSON, wrong shape (data is not a list of records)


# Every (op, callable) pair plus the context token its messages must name.
ALL_FETCHERS = [
    ("get_institution", lambda: fdic.get_institution(57542), "57542"),
    ("search_institutions", lambda: fdic.search_institutions(state="CA"), "CA"),
    ("get_financials", lambda: fdic.get_financials(57542), "57542"),
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
    payload = {"data": [{"data": {"CERT": "not-a-number", "INSTNAME": "X"}}]}
    with patch.object(fdic.requests, "get", return_value=_response(payload)) as mock_get:
        with pytest.raises(FDICResponseError):
            fdic.get_financials(57542)
    assert mock_get.called
    with patch.object(fdic.requests, "get", return_value=_response(payload)) as mock_get:
        with pytest.raises(FDICResponseError):
            fdic.get_peer_financials(state="CA")
    assert mock_get.called


# ── (c) legitimate empty (200, {"data": []}) → empty, NOT a raise ─────────────
def test_get_institution_empty_returns_none():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)) as mock_get:
        assert fdic.get_institution(57542) is None
    assert mock_get.called


def test_get_financials_empty_returns_none():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)) as mock_get:
        assert fdic.get_financials(57542) is None
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
        profile = fdic.get_financials(57542)
    assert isinstance(profile, InstitutionProfile)
    assert profile.cert == 57542
    assert profile.name == "Broadway Federal Bank"
    assert mock_get.called


def test_get_institution_happy_path_returns_record():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)) as mock_get:
        record = fdic.get_institution(57542)
    assert record["CERT"] == 57542
    assert mock_get.called


def test_search_institutions_happy_path_returns_dataframe():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)) as mock_get:
        df = fdic.search_institutions(state="CA")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert df.iloc[0]["CERT"] == 57542
    assert mock_get.called


def test_get_peer_financials_happy_path_returns_profiles():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)) as mock_get:
        peers = fdic.get_peer_financials(state="CA")
    assert isinstance(peers, list)
    assert len(peers) == 1
    assert isinstance(peers[0], InstitutionProfile)
    assert peers[0].cert == 57542
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
    ("get_financials", lambda: fdic.get_financials(57542)),
    ("get_peer_financials", lambda: fdic.get_peer_financials(state="CA")),
]

# Same two fetchers, but unwrapped to a single InstitutionProfile so the
# parses-but-sparse cases can assert on field values.
PARSE_PROFILE = [
    ("get_financials", lambda: fdic.get_financials(57542)),
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
    """An optional ratio present-but-garbage is still a contract breach."""
    record = dict(WELL_FORMED_ROW, RBCT1J="garbage")
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert "RBCT1J" in str(exc.value)
    assert mock_get.called


@pytest.mark.parametrize("op,extract", PARSE_PROFILE)
def test_absent_optional_ratio_is_none_not_zero(op, extract):
    """Optional ratio absent → None (legitimately sparse), never 0.0."""
    record = {k: v for k, v in WELL_FORMED_ROW.items() if k != "RBCT1J"}
    with patch.object(fdic.requests, "get", return_value=_response(_wrap(record))) as mock_get:
        profile = extract()
    assert profile.tier1_ratio is None
    assert profile.tier1_ratio != 0.0
    assert mock_get.called


@pytest.mark.parametrize("op,extract", PARSE_PROFILE)
def test_present_zero_optional_ratio_preserved(op, extract):
    """A real present 0.0 ratio must survive — `safe_float(...) or None` erased it."""
    record = dict(WELL_FORMED_ROW, RBCT1J=0.0)
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
