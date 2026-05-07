from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult,
    BENCHMARKS, ASSET_BUCKETS,
)
from cdfibenchmark.data.fdic import (
    get_institution, get_financials,
    search_institutions, get_peer_financials,
)
from cdfibenchmark.metrics.calculator import (
    compute_peer_metrics, benchmark_institution, rank_institution,
)
from cdfibenchmark.peers.selector import (
    build_peer_group, build_sample_peer_group,
)
from cdfibenchmark.report.generator import (
    generate_report, summary_table,
)

__version__ = "0.1.0"
__all__ = [
    "InstitutionProfile", "BenchmarkResult",
    "get_institution", "get_financials",
    "search_institutions", "get_peer_financials",
    "compute_peer_metrics", "benchmark_institution", "rank_institution",
    "build_peer_group", "build_sample_peer_group",
    "generate_report", "summary_table",
    "BENCHMARKS", "ASSET_BUCKETS",
]
