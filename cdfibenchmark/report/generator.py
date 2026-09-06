"""
Generate CDFI peer benchmarking reports.
"""
import pandas as pd
from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult, BENCHMARKS, _is_missing,
    BASIS_FDIC, GRADEABLE_BASES, BASIS_REJECTED_IMPLAUSIBLE,
    asset_bucket_bounds_text,
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

    A real present 0.0 renders "$0.0MM"; NaN never leaks as "$nanMM". The
    thousands separator is not cosmetic on a financial document: without it this
    rendered "$2027.0MM" and "$4091315.0MM", which a reader has to count digits
    to place.
    """
    if _is_missing(value_mm):
        return "N/A"
    return f"${value_mm:,.1f}MM"


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


#: Decimal places every percentage on the report is rendered at (`_fmt_pct`).
_PCT_DP = 2


def _printed_vs_median(result):
    """The vs-median difference AS PRINTED, computed from the printed operands.

    `BenchmarkResult.vs_median` subtracts the raw values and is what a
    programmatic consumer wants. The REPORT does not show raw values: it shows
    both operands rounded to `_PCT_DP`, and then showed a difference rounded
    independently from the raw ones. On 4 of the 16 rows across two real
    subjects at 20260630 the printed arithmetic therefore did not add up — CERT
    16584's NIM printed `4.36`, `3.94` and `0.41`. Nothing is wrong with the
    number; what is wrong is asking a reader to accept `4.36 - 3.94 = 0.41`.
    The rendered difference is now the difference of the rendered operands.

    None when either operand is absent, exactly like `vs_median`.
    """
    if _is_missing(result.institution_value) or result.peer_median is None:
        return None
    return round(result.institution_value, _PCT_DP) - round(result.peer_median, _PCT_DP)


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


def _asset_bucket_line(institution) -> str:
    """The asset bucket, with the boundaries it means and who set them.

    `**Asset Bucket:** Large` was the only classifying constant naming something
    on the report face with no marker, no boundaries and no attribution — while
    fifteen grading and selection constants next to it carried all three. And
    "Large" is a supervisory word: it means specific, different things under CRA
    and in the FDIC's own definitions, neither of which this band is.
    """
    bucket = institution.asset_bucket
    if bucket == "unknown":
        return "**Asset Bucket:** N/A — total assets are unknown"
    bounds = asset_bucket_bounds_text(bucket)
    return (
        f"**Asset Bucket:** {bucket.title()} ({bounds}) — "
        f"**this tool's own size band (HOUSE)**, not an FFIEC CRA threshold, "
        f"the FDIC community-bank definition, or a UBPR peer group"
    )


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
        _asset_bucket_line(institution),
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

    # The Status column sits beside three peer columns and reads as though it
    # summarised them. It does not: `BenchmarkResult.status` compares the
    # Institution column to the fixed thresholds on the Benchmark line below and
    # never looks at a peer value. Both readings of that are real and neither is
    # a grading bug — measured at 20260630, CERT 58490's NPL ratio of 2.53% is
    # 6.2x its peer median (0.41%) and above the 75th percentile (0.71%) while
    # its reserve coverage is 22% of the peer median and below the 25th
    # percentile, and both grade ADEQUATE; CERT 16584's ROAA is below its peer
    # median and grades STRONG. What was missing is the sentence saying so.
    lines += [
        "",
        "**How to read Status:** Status grades the **Institution** column "
        "against the fixed thresholds shown on each metric's **Benchmark** line "
        "below. It does **not** consult the Peer Median, 25th or 75th percentile "
        "columns. A metric can grade STRONG while sitting below the peer median, "
        "and ADEQUATE while sitting outside the peer range entirely. Read the "
        "grade and the peer columns as two separate questions — this report "
        "answers both and combines neither.",
    ]

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
        vs_printed = _printed_vs_median(result)
        if not _is_missing(vs_printed):
            direction = "above" if vs_printed > 0 else "below"
            lines.append(
                f"**vs Peer Median:** {_fmt_pct(abs(vs_printed))} {direction} median"
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
        # An ABSENT value normally needs no explanation. A REFUSED one does: the
        # number exists, FDIC published it, and this tool decided not to show it.
        # Left unsaid, that is indistinguishable from FDIC never publishing it.
        elif result.basis == BASIS_REJECTED_IMPLAUSIBLE:
            lines.append(
                "**Not shown:** FDIC published a value for this metric that "
                "falls outside this tool's plausibility bound for a percentage, "
                "so it was refused as a wrong-field-class signal rather than "
                "graded. The bound is this tool's own heuristic, not FDIC's — "
                "the published value was a real filing. See "
                "`cdfibenchmark.data.fdic` for the bound and how it was derived."
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
