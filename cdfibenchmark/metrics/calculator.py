"""
Compute benchmarking metrics across a peer group.
"""
import pandas as pd
import numpy as np
from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult, BENCHMARKS, benchmark_for
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

    for metric in BENCHMARKS:
        # The threshold in force AT THE INSTITUTION'S OWN PERIOD. For the seven
        # HOUSE entries this is BENCHMARKS[metric] unchanged; for tier1_ratio,
        # the only entry citing a real instrument, it selects the CBLR band that
        # actually applied at that report date.
        config = benchmark_for(metric, institution.report_date)
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
            # How the institution's value was measured, and where the threshold
            # it is compared against comes from. Both ride along to the render
            # layer so no cell can show a grade without showing its warrant.
            basis=institution.metric_basis(metric),
            source=config.get("source"),
            report_date=institution.report_date,
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
        Dict with rank, percentile, peer_count, and — when the metric cannot be
        ranked — a `reason` naming why.

    `percentile` is the share of PEERS this institution beats, so it spans the
    full 0-100 range. The previous formula, ``(1 - rank / N) * 100`` over peers
    PLUS the institution, could never return 100 (the best of 21 scored 95.2)
    and pinned the worst at exactly 0. `peer_count` likewise counted the
    institution itself, so it disagreed with `BenchmarkResult.peer_count` — the
    same key name meaning two different things in one package.
    """
    peer_df = compute_peer_metrics(peers)
    inst_value = institution.metrics_dict().get(metric)

    config = benchmark_for(metric, institution.report_date)

    # A missing (None) or unknown (NaN) metric can't be ranked — list.index on
    # NaN is meaningless. Treat it as not-available, like the absent case.
    if inst_value is None or pd.isna(inst_value) or metric not in peer_df.columns:
        return {"rank": None, "percentile": None, "peer_count": len(peers),
                "reason": "institution value is missing or unknown"}

    # A BANDED metric has no monotone "better" direction: both a value above
    # the band and one below it are worse than the middle. Ranking it as though
    # lower (or higher) always won produced a direct contradiction between the
    # two surfaces of the same metric — measured before this fix, a bank at 15%
    # loans-to-deposits graded WEAK and ranked 1st of 21 at the 95.2nd
    # percentile. Refuse the rank and say so rather than order the unorderable;
    # any distance-from-band ordering would be a house construct on top of
    # already-house boundaries.
    if config.get("floor") is not None:
        return {
            "rank": None, "percentile": None, "peer_count": len(peers),
            "reason": (
                f"{metric} is graded as a band, so there is no monotone "
                f"better-direction to rank on"
            ),
        }

    peer_values = peer_df[metric].dropna().tolist()
    if not peer_values:
        return {"rank": None, "percentile": None, "peer_count": 0,
                "reason": "no peer has a value for this metric"}

    lower_is_better = config.get("lower_is_better", False)
    if lower_is_better:
        beaten = sum(1 for v in peer_values if v > inst_value)
        ahead = sum(1 for v in peer_values if v < inst_value)
    else:
        beaten = sum(1 for v in peer_values if v < inst_value)
        ahead = sum(1 for v in peer_values if v > inst_value)

    return {
        "rank": ahead + 1,
        # `rank` places the institution AMONG the peers, so it runs 1..N+1,
        # while `peer_count` counts peers only. Reported alone the pair reads
        # as nonsense ("rank 21, peer_count 20"); rank_of names the denominator.
        "rank_of": len(peer_values) + 1,
        "percentile": round(beaten / len(peer_values) * 100, 1),
        "peer_count": len(peer_values),
    }
