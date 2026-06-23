"""
Tests for the FDIC data layer's fail-loud contract.

Transport/decode failures raise FDICAPIError. Valid-JSON-but-wrong-shape
raises FDICResponseError. A successful request that legitimately returns zero
rows keeps returning the empty value (None / empty DataFrame / []).

All HTTP is mocked at cdfibenchmark.data.fdic.requests.get — no live network,
no skips — and the real fetchers are called through-function.
"""
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
                      return_value=_response(raise_status=requests.exceptions.HTTPError("500"))):
        with pytest.raises(FDICAPIError) as exc:
            call()
    assert op in str(exc.value)
    assert ctx in str(exc.value)


@pytest.mark.parametrize("op,call,ctx", ALL_FETCHERS)
def test_timeout_raises_api_error(op, call, ctx):
    with patch.object(fdic.requests, "get",
                      side_effect=requests.exceptions.Timeout("timed out")):
        with pytest.raises(FDICAPIError) as exc:
            call()
    assert op in str(exc.value)
    assert ctx in str(exc.value)


@pytest.mark.parametrize("op,call,ctx", ALL_FETCHERS)
def test_json_decode_error_raises_api_error(op, call, ctx):
    with patch.object(fdic.requests, "get",
                      return_value=_response(json_exc=ValueError("No JSON could be decoded"))):
        with pytest.raises(FDICAPIError) as exc:
            call()
    assert op in str(exc.value)
    assert ctx in str(exc.value)


# ── (b) valid JSON, wrong shape → FDICResponseError ───────────────────────────
@pytest.mark.parametrize("op,call,ctx", ALL_FETCHERS)
def test_malformed_shape_raises_response_error(op, call, ctx):
    with patch.object(fdic.requests, "get", return_value=_response(MALFORMED)):
        with pytest.raises(FDICResponseError) as exc:
            call()
    assert ctx in str(exc.value)


def test_non_numeric_cert_raises_response_error():
    """A row that decodes fine but has a non-numeric CERT is a schema problem."""
    payload = {"data": [{"data": {"CERT": "not-a-number", "INSTNAME": "X"}}]}
    with patch.object(fdic.requests, "get", return_value=_response(payload)):
        with pytest.raises(FDICResponseError):
            fdic.get_financials(57542)
    with patch.object(fdic.requests, "get", return_value=_response(payload)):
        with pytest.raises(FDICResponseError):
            fdic.get_peer_financials(state="CA")


# ── (c) legitimate empty (200, {"data": []}) → empty, NOT a raise ─────────────
def test_get_institution_empty_returns_none():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)):
        assert fdic.get_institution(57542) is None


def test_get_financials_empty_returns_none():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)):
        assert fdic.get_financials(57542) is None


def test_search_institutions_empty_returns_empty_dataframe():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)):
        result = fdic.search_institutions(state="CA")
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_get_peer_financials_empty_returns_empty_list():
    with patch.object(fdic.requests, "get", return_value=_response(EMPTY)):
        assert fdic.get_peer_financials(state="CA") == []


# ── (d) happy path (200, one well-formed record) ──────────────────────────────
def test_get_financials_happy_path_parses_to_profile():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)):
        profile = fdic.get_financials(57542)
    assert isinstance(profile, InstitutionProfile)
    assert profile.cert == 57542
    assert profile.name == "Broadway Federal Bank"


def test_get_institution_happy_path_returns_record():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)):
        record = fdic.get_institution(57542)
    assert record["CERT"] == 57542


def test_search_institutions_happy_path_returns_dataframe():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)):
        df = fdic.search_institutions(state="CA")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert df.iloc[0]["CERT"] == 57542


def test_get_peer_financials_happy_path_returns_profiles():
    with patch.object(fdic.requests, "get", return_value=_response(ONE_RECORD)):
        peers = fdic.get_peer_financials(state="CA")
    assert isinstance(peers, list)
    assert len(peers) == 1
    assert isinstance(peers[0], InstitutionProfile)
    assert peers[0].cert == 57542
