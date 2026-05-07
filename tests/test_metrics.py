import pytest
import pandas as pd
from cdfibenchmark.metrics.calculator import (
    compute_peer_metrics, benchmark_institution, rank_institution
)
from cdfibenchmark.data.schema import BenchmarkResult


def test_peer_metrics_returns_dataframe(sample_institution, sample_peers):
    df = compute_peer_metrics(sample_peers)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == len(sample_peers)


def test_peer_metrics_has_columns(sample_institution, sample_peers):
    df = compute_peer_metrics(sample_peers)
    assert "nim" in df.columns
    assert "efficiency_ratio" in df.columns
    assert "roaa" in df.columns


def test_benchmark_returns_list(sample_institution, sample_peers):
    results = benchmark_institution(sample_institution, sample_peers)
    assert isinstance(results, list)
    assert len(results) > 0


def test_benchmark_result_type(sample_institution, sample_peers):
    results = benchmark_institution(sample_institution, sample_peers)
    assert all(isinstance(r, BenchmarkResult) for r in results)


def test_benchmark_has_peer_median(sample_institution, sample_peers):
    results = benchmark_institution(sample_institution, sample_peers)
    nim_result = next(r for r in results if r.metric == "nim")
    assert nim_result.peer_median is not None


def test_benchmark_status_valid(sample_institution, sample_peers):
    results = benchmark_institution(sample_institution, sample_peers)
    valid_statuses = {"STRONG", "ADEQUATE", "WEAK", "N/A"}
    for r in results:
        assert r.status in valid_statuses


def test_rank_institution(sample_institution, sample_peers):
    result = rank_institution(sample_institution, sample_peers, "nim")
    assert "rank" in result
    assert "percentile" in result
    assert result["peer_count"] > 0
