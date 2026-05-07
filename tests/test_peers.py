import pytest
from cdfibenchmark.peers.selector import build_sample_peer_group
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
