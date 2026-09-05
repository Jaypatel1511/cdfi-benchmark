"""
Generate CDFI peer benchmarking reports.
"""
import pandas as pd
from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult, BENCHMARKS, _is_missing,
    BASIS_FDIC, GRADEABLE_BASES,
)
from cdfibenchmark.metrics.calculator import (
    compute_peer_metrics, benchmark_institution, rank_institution
)


def _fmt_pct(value) -> str:
    """Render a metric as a percentage, mapping absent/unknown to "N/A".

    Gate on missingness, not truthiness: None/NaN → "N/A", but a real present
    0.0 renders "0.00%" (never erased) and NaN never leaks as "nan%".
    """
    if _is_missing(value):
        return "N/A"
    return f"{value:.2f}%"


def _fmt_assets_mm(value_mm) -> str:
    """Render an asset figure (already in $MM), mapping absent/unknown to "N/A".

    A real present 0.0 renders "$0.0MM"; NaN never leaks as "$nanMM".
    """
    if _is_missing(value_mm):
        return "N/A"
    return f"${value_mm:.1f}MM"


METRIC_LABELS = {
    "nim":               "Net Interest Margin (NIM)",
    "efficiency_ratio":  "Efficiency Ratio",
    "roaa":              "Return on Average Assets (ROAA)",
    "roae":              "Return on Average Equity (ROAE)",
    "tier1_ratio":       "Tier 1 Leverage Ratio",
    "loans_to_deposits": "Loans-to-Deposits",
    "npl_ratio":         "Non-Performing Loan Ratio",
    "reserve_coverage":  "Loan Loss Reserve Coverage",
}

# The labels above are true ONLY of FDIC's published series. "Return on AVERAGE
# Assets" was rendered over period-end balances through 0.2.1 — a labelling
# defect independent of the period and denominator ones. When the value is the
# computed proxy rather than FDIC's, the label must say what was actually
# divided by what.
_COMPUTED_LABELS = {
    "nim":  "Net Interest Margin over total assets (NIM)",
    "roaa": "Return on Assets, period-end (ROAA)",
    "roae": "Return on Equity, period-end (ROAE)",
}


def _metric_label(metric: str, basis: str = None) -> str:
    """Label for a metric, told the truth about how the value was measured."""
    if basis is not None and basis != BASIS_FDIC and metric in _COMPUTED_LABELS:
        return _COMPUTED_LABELS[metric]
    return METRIC_LABELS.get(metric, metric)


def _threshold_line(metric: str) -> str:
    """The 'Benchmark:' line, carrying its own provenance.

    A house rule of thumb rendered in the same column as a CFR citation reads
    as a standard. Every line now says which it is.
    """
    benchmark = BENCHMARKS.get(metric, {})
    good = benchmark.get("good")
    warning = benchmark.get("warning")
    floor = benchmark.get("floor")
    lower = benchmark.get("lower_is_better", False)
    source = benchmark.get("source")
    if good is None or warning is None:
        return None

    if floor is not None:
        band = (f"Strong {floor}%-{good}% | Adequate up to {warning}% | "
                f"Weak below {floor}% (under-deployed) or above {warning}%")
    elif lower:
        band = f"Strong <= {good}% | Adequate <= {warning}%"
    else:
        band = f"Strong >= {good}% | Adequate >= {warning}%"

    if source == "HOUSE":
        attribution = " — **this tool's own threshold (HOUSE)**, not a regulatory or supervisory standard"
    elif source:
        attribution = f" — {source}"
    else:
        attribution = ""
    return f"**Benchmark:** {band}{attribution}"


def _peer_period_line(peers) -> str:
    """How to describe the peers' own reporting period."""
    dates = sorted(getattr(peers, "report_dates", None)
                   or {p.report_date for p in peers if p.report_date})
    if not dates:
        return "**Peer Report Date:** N/A"
    if len(dates) == 1:
        return f"**Peer Report Date:** {dates[0]}"
    return f"**Peer Report Date:** MIXED — {', '.join(dates)}"


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
        f"**Total Assets:** {_fmt_assets_mm(institution.total_assets_mm)}",
        f"**Asset Bucket:** {institution.asset_bucket.title()}",
        f"**Report Date:** {institution.report_date}",
        f"**Peer Group Size:** {len(peers)} institutions",
        _peer_period_line(peers),
        "",
    ]

    # Every way this peer group is not what was asked for, stated before any
    # number is shown. An incomplete peer group must never read as a complete
    # one.
    caveats = list(getattr(peers, "caveats", []))
    if caveats:
        lines += ["> **Peer group caveats**", ">"]
        lines += [f"> - {c}" for c in caveats]
        lines.append("")

    lines += [
        "---",
        "",
        "## Performance Summary",
        "",
        "| Metric | Institution | Peer Median | 25th Pctile | 75th Pctile | Status |",
        "|--------|-------------|-------------|-------------|-------------|--------|",
    ]

    for result in results:
        label = _metric_label(result.metric, result.basis)
        inst_val = _fmt_pct(result.institution_value)
        median = _fmt_pct(result.peer_median)
        p25 = _fmt_pct(result.peer_25th)
        p75 = _fmt_pct(result.peer_75th)
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
        label = _metric_label(result.metric, result.basis)
        lines.append(f"### {label}")
        lines.append("")

        if not _is_missing(result.institution_value):
            lines.append(f"**Institution Value:** {_fmt_pct(result.institution_value)}")
        if not _is_missing(result.peer_median):
            lines.append(f"**Peer Median:** {_fmt_pct(result.peer_median)}")
        if not _is_missing(result.vs_median):
            direction = "above" if result.vs_median > 0 else "below"
            lines.append(
                f"**vs Peer Median:** {_fmt_pct(abs(result.vs_median))} {direction} median"
            )

        if result.basis:
            lines.append(f"**Basis:** {result.basis}")

        threshold = _threshold_line(result.metric)
        if threshold:
            lines.append(threshold)

        lines.append(f"**Status:** {result.status}")
        # A value that is present but ungraded must say WHY, or an em-dash in
        # the Status column reads as missing data.
        if (result.basis and result.basis not in GRADEABLE_BASES
                and not _is_missing(result.institution_value)):
            lines.append(
                f"**Not graded:** this value is {result.basis}. The threshold "
                f"is calibrated to FDIC's published annualized series, so the "
                f"two are not comparable; the measured value is reported above."
            )
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
            f"{_fmt_assets_mm(peer_df['total_assets_mm'].min())} – "
            f"{_fmt_assets_mm(peer_df['total_assets_mm'].max())}"
        )
        # A peer asset range printed near the institution's own assets, with no
        # relationship stated between them, is what let a group of the 50
        # LARGEST banks in the window read as "the 50 real peers". State the
        # relationship: where the subject falls INSIDE its own peer group.
        percentile = getattr(peers, "asset_percentile", None)
        if percentile is not None:
            below = sum(
                1 for p in peers
                if not _is_missing(p.total_assets)
                and p.total_assets < peers.subject_assets
            )
            known = sum(1 for p in peers if not _is_missing(p.total_assets))
            lines.append(
                f"**Institution's Position in the Peer Asset Range:** "
                f"{_fmt_assets_mm(institution.total_assets_mm)} — "
                f"percentile {percentile:g} of its own peer group "
                f"({below} of {known} peers are smaller). 50 means the group "
                f"brackets the institution; 0 or 100 means it does not, and the "
                f"peer median carries a size bias."
            )
    basis = getattr(peers, "selection_basis", None)
    if basis:
        lines.append(f"**Peer Selection Basis:** {basis}")
    if "state" in peer_df.columns:
        states = peer_df["state"].nunique()
        lines.append(f"**States Represented:** {states}")
    lines.append(_peer_period_line(peers))
    distinct_certs = len({p.cert for p in peers})
    lines.append(f"**Distinct Institutions:** {distinct_certs}")
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
            "metric": _metric_label(r.metric, r.basis),
            "institution": r.institution_value,
            "peer_median": r.peer_median,
            "peer_25th": r.peer_25th,
            "peer_75th": r.peer_75th,
            "vs_median": r.vs_median,
            "status": r.status,
            "peer_count": r.peer_count,
            "basis": r.basis,
            "threshold_source": r.source,
        })
    return pd.DataFrame(rows)
