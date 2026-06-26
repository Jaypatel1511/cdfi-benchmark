import pytest
import requests
from unittest.mock import patch

from cdfibenchmark import FDICAPIError, FDICResponseError
from cdfibenchmark.data import fdic
from cdfibenchmark.peers.selector import build_peer_group, build_sample_peer_group
from cdfibenchmark.data.schema import InstitutionProfile


def test_sample_peer_group_returns_list(sample_institution):
    peers = build_sample_peer_group(sample_institution)
    assert isinstance(peers, list)
    assert len(peers) > 0


def test_sample_peers_are_institution_profiles(sample_institution):
    peers = build_sample_peer_group(sample_institution)
    assert all(isinstance(p, InstitutionProfile) for p in peers)


def test_sample_peers_exclude_institution(sample_institution):
    peers = build_sample_peer_group(sample_institution)
    certs = [p.cert for p in peers]
    assert sample_institution.cert not in certs


def test_sample_peers_similar_assets(sample_institution):
    peers = build_sample_peer_group(sample_institution)
    for peer in peers:
        ratio = peer.total_assets / sample_institution.total_assets
        assert 0.1 < ratio < 5.0


def test_build_peer_group_propagates_transport_failure(sample_institution):
    """A transport failure during the peer fetch must surface through the real
    selector path, not be swallowed into an empty peer group — an empty result
    in an anomaly-detection pipeline reads as 'nothing anomalous'.

    Through-function: build_peer_group → get_peer_financials → requests.get.
    """
    with patch.object(fdic.requests, "get",
                      side_effect=requests.exceptions.Timeout("timed out")) as mock_get:
        with pytest.raises(FDICAPIError):
            build_peer_group(sample_institution)
    assert mock_get.called


def test_build_peer_group_raises_on_unknown_assets(nan_cored_institution):
    """An institution with unknown (NaN) assets cannot have peers selected.

    Selecting peers requires an asset window; NaN assets make that window
    undefined. The selector must raise FDICResponseError naming the CERT —
    NOT leak a bare ValueError (int(NaN)), and NOT silently return [] (zero
    peers for an unknown-asset bank is the same absence-reads-as-result
    failure this release eliminates).
    """
    with pytest.raises(FDICResponseError) as excinfo:
        build_peer_group(nan_cored_institution)
    assert str(nan_cored_institution.cert) in str(excinfo.value)
