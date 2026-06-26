"""
Compute benchmarking metrics across a peer group.
"""
import pandas as pd
import numpy as np
from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult, BENCHMARKS
)


def compute_peer_metrics(peers: list) -> pd.DataFrame:
    """
    Compute all metrics for a list of InstitutionProfile objects.
    Returns a DataFrame with one row per institution.
    """
    rows = []
    for inst in peers:
        if inst is None:
            continue
        row = {
            "cert": inst.cert,
            "name": inst.name,
            "city": inst.city,
            "state": inst.state,
            "report_date": inst.report_date,
            "total_assets_mm": inst.total_assets_mm,
            "asset_bucket": inst.asset_bucket,
        }
        row.update(inst.metrics_dict())
        rows.append(row)
    return pd.DataFrame(rows)


def benchmark_institution(
    institution: InstitutionProfile,
    peers: list,
) -> list:
    """
    Benchmark an institution against a peer group.

    Args:
        institution: The institution to benchmark
        peers:       List of peer InstitutionProfile objects

    Returns:
        List of BenchmarkResult objects, one per metric
    """
    peer_df = compute_peer_metrics(peers)
    results = []

    for metric, config in BENCHMARKS.items():
        inst_value = institution.metrics_dict().get(metric)

        if metric in peer_df.columns:
            peer_values = peer_df[metric].dropna()
            peer_median = float(peer_values.median()) if len(peer_values) else None
            peer_25th   = float(peer_values.quantile(0.25)) if len(peer_values) else None
            peer_75th   = float(peer_values.quantile(0.75)) if len(peer_values) else None
            peer_count  = len(peer_values)
        else:
            peer_median = peer_25th = peer_75th = None
            peer_count = 0

        results.append(BenchmarkResult(
            metric=metric,
            institution_value=inst_value,
            peer_median=peer_median,
            peer_25th=peer_25th,
            peer_75th=peer_75th,
            peer_count=peer_count,
            unit=config.get("unit", "%"),
            lower_is_better=config.get("lower_is_better", False),
        ))

    return results


def rank_institution(
    institution: InstitutionProfile,
    peers: list,
    metric: str,
) -> dict:
    """
    Rank an institution within its peer group for a specific metric.

    Returns:
        Dict with rank, percentile, and peer count
    """
    peer_df = compute_peer_metrics(peers)
    inst_value = institution.metrics_dict().get(metric)

    # A missing (None) or unknown (NaN) metric can't be ranked — list.index on
    # NaN is meaningless. Treat it as not-available, like the absent case.
    if inst_value is None or pd.isna(inst_value) or metric not in peer_df.columns:
        return {"rank": None, "percentile": None, "peer_count": len(peers)}

    peer_values = peer_df[metric].dropna().tolist()
    peer_values_with_inst = sorted(peer_values + [inst_value], reverse=True)

    lower_is_better = BENCHMARKS.get(metric, {}).get("lower_is_better", False)
    if lower_is_better:
        peer_values_with_inst = sorted(peer_values + [inst_value])

    rank = peer_values_with_inst.index(inst_value) + 1
    percentile = round((1 - rank / len(peer_values_with_inst)) * 100, 1)

    return {
        "rank": rank,
        "percentile": percentile,
        "peer_count": len(peer_values_with_inst),
    }
