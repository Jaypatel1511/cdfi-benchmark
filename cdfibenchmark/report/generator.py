"""
Generate CDFI peer benchmarking reports.
"""
import pandas as pd
from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult, BENCHMARKS
)
from cdfibenchmark.metrics.calculator import (
    compute_peer_metrics, benchmark_institution, rank_institution
)


METRIC_LABELS = {
    "nim":               "Net Interest Margin (NIM)",
    "efficiency_ratio":  "Efficiency Ratio",
    "roaa":              "Return on Avg Assets (ROAA)",
    "roae":              "Return on Avg Equity (ROAE)",
    "tier1_ratio":       "Tier 1 Capital Ratio",
    "loans_to_deposits": "Loans-to-Deposits",
    "npl_ratio":         "Non-Performing Loan Ratio",
    "reserve_coverage":  "Loan Loss Reserve Coverage",
}


def generate_report(
    institution: InstitutionProfile,
    peers: list,
    title: str = None,
) -> str:
    """
    Generate a full peer benchmarking report as a Markdown string.
    """
    results = benchmark_institution(institution, peers)

    lines = [
        f"# CDFI Peer Benchmarking Report",
        f"## {title or institution.name}",
        "",
        f"**Institution:** {institution.name}",
        f"**Location:** {institution.city}, {institution.state}",
        f"**Total Assets:** ${institution.total_assets_mm:.1f}MM",
        f"**Asset Bucket:** {institution.asset_bucket.title()}",
        f"**Report Date:** {institution.report_date}",
        f"**Peer Group Size:** {len(peers)} institutions",
        "",
        "---",
        "",
        "## Performance Summary",
        "",
        "| Metric | Institution | Peer Median | 25th Pctile | 75th Pctile | Status |",
        "|--------|-------------|-------------|-------------|-------------|--------|",
    ]

    for result in results:
        label = METRIC_LABELS.get(result.metric, result.metric)
        inst_val = f"{result.institution_value:.2f}%" if result.institution_value else "N/A"
        median = f"{result.peer_median:.2f}%" if result.peer_median else "N/A"
        p25 = f"{result.peer_25th:.2f}%" if result.peer_25th else "N/A"
        p75 = f"{result.peer_75th:.2f}%" if result.peer_75th else "N/A"
        status_emoji = {
            "STRONG": "✅ STRONG",
            "ADEQUATE": "⚠️ ADEQUATE",
            "WEAK": "❌ WEAK",
            "N/A": "—",
        }.get(result.status, result.status)

        lines.append(
            f"| {label} | {inst_val} | {median} | {p25} | {p75} | {status_emoji} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Metric Detail",
        "",
    ]

    for result in results:
        label = METRIC_LABELS.get(result.metric, result.metric)
        lines.append(f"### {label}")
        lines.append("")

        if result.institution_value is not None:
            lines.append(f"**Institution Value:** {result.institution_value:.2f}%")
        if result.peer_median is not None:
            lines.append(f"**Peer Median:** {result.peer_median:.2f}%")
        if result.vs_median is not None:
            direction = "above" if result.vs_median > 0 else "below"
            lines.append(
                f"**vs Peer Median:** {abs(result.vs_median):.2f}% {direction} median"
            )

        benchmark = BENCHMARKS.get(result.metric, {})
        good = benchmark.get("good")
        warning = benchmark.get("warning")
        lower = benchmark.get("lower_is_better", False)

        if good and warning:
            if lower:
                lines.append(
                    f"**Benchmark:** Strong <= {good}% | Adequate <= {warning}%"
                )
            else:
                lines.append(
                    f"**Benchmark:** Strong >= {good}% | Adequate >= {warning}%"
                )

        lines.append(f"**Status:** {result.status}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Peer Group Summary",
        "",
    ]

    peer_df = compute_peer_metrics(peers)
    lines.append(f"**Peer Count:** {len(peers)}")
    if "total_assets_mm" in peer_df.columns:
        lines.append(
            f"**Peer Asset Range:** "
            f"${peer_df['total_assets_mm'].min():.1f}MM – "
            f"${peer_df['total_assets_mm'].max():.1f}MM"
        )
    if "state" in peer_df.columns:
        states = peer_df["state"].nunique()
        lines.append(f"**States Represented:** {states}")
    lines.append("")

    return "\n".join(lines)


def summary_table(
    institution: InstitutionProfile,
    peers: list,
) -> pd.DataFrame:
    """Return benchmarking results as a pandas DataFrame."""
    results = benchmark_institution(institution, peers)
    rows = []
    for r in results:
        rows.append({
            "metric": METRIC_LABELS.get(r.metric, r.metric),
            "institution": r.institution_value,
            "peer_median": r.peer_median,
            "peer_25th": r.peer_25th,
            "peer_75th": r.peer_75th,
            "vs_median": r.vs_median,
            "status": r.status,
            "peer_count": r.peer_count,
        })
    return pd.DataFrame(rows)
