"""
Generate CDFI peer benchmarking reports.
"""
import datetime

import pandas as pd
from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult, BENCHMARKS, benchmark_for, _is_missing,
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

#: Decimal places the RELATIVE gap is rendered at. One is deliberate: the
#: relative figure is a ratio of two already-rounded numbers, and rendering it
#: to 2 dp would claim a precision its operands do not carry.
_REL_DP = 1


def _fmt_pp(value) -> str:
    """Render a difference of two percentages as PERCENTAGE POINTS.

    THIS IS NOT `_fmt_pct`, AND THAT IS THE WHOLE POINT. `_fmt_pct` appends a
    `%`; the difference of two percentages is measured in percentage POINTS,
    and the two are not the same quantity. Rendering 1.17% - 0.32% as "0.85%"
    is the same class of defect as rendering a dollar figure as a percent
    (cdfi-loan-pricing, inflated 100x) or a ratio as basis points
    (cdfi-stress-tester). The portfolio's unit discriminator -- dollars scale
    with the amount, rates do not -- states its own limit: "it cannot separate
    PERCENT from RATIO." This is that unresolved case, so the separation is
    made here, in the type of the formatter, rather than left to a reader.
    """
    if _is_missing(value):
        return "N/A"
    return f"{value:.2f} pp"


def _relative_gap(vs_printed, peer_median_printed):
    """The gap as a SHARE of the peer median, in percent, or None.

    None when the peer median is not a positive number. A percentage of a
    negative median reads as its own opposite: FDIC really publishes negative
    EEFFR (their own arithmetic over negative noninterest expense), and against
    a peer median of -700% an institution at 74.84% is 774.84 pp ABOVE while
    774.84 / -700 = -110.7% would render "110.7% below" on the same line. A
    zero median makes it undefined outright. Both are withheld, with the reason
    stated on the face, rather than rendered as a number that is not one.

    Computed from the PRINTED operands, like `_printed_vs_median`, so a reader
    can reproduce it from the two lines directly above it.
    """
    if _is_missing(vs_printed) or _is_missing(peer_median_printed):
        return None
    if peer_median_printed <= 0:
        return None
    return vs_printed / peer_median_printed * 100.0


def _vs_median_line(vs_printed, peer_median_printed) -> str:
    """The comparison sentence, with the unit of every number on its face.

    Measured on the 0.3.1 artifact (CERT 34352 @ 20260630), the old line was
    sometimes near the relative figure and sometimes an order of magnitude from
    it, with nothing distinguishing the cases:

        metric  inst    median   said              actually
        LTD     95.25%  85.19%   "10.06% above"    11.8% above   (close)
        ROAA     0.32%   1.17%    "0.85% below"    72.6% below   (85x out)

    A banker reading "ROAA 0.85% below median" concludes a near-miss; the bank
    earns less than a third of its peer group's ROAA. Both figures are now
    rendered, each with its unit, so the line cannot be read as the other one.

    Direction is stated as a fact ("above"/"below"), never as better or worse:
    whether above is good depends on `lower_is_better`, and that is what
    `Status` answers. A second, differently-derived verdict on the same line
    could contradict it.
    """
    # A tie is neither above nor below. `"above" if vs_printed > 0 else "below"`
    # called it a shortfall -- and it is reachable well short of exact equality,
    # because both operands are rounded to `_PCT_DP` before subtracting. A bank
    # genuinely ABOVE its peer median by less than half a basis point printed
    # "0.00% below median", which is a directional falsehood, not a rounding
    # artefact.
    if vs_printed == 0:
        return ("**vs Peer Median:** 0.00 pp — at the median "
                f"(both figures round to the same value at {_PCT_DP} dp)")

    direction = "above" if vs_printed > 0 else "below"
    head = f"**vs Peer Median:** {_fmt_pp(abs(vs_printed))} {direction} median"

    relative = _relative_gap(vs_printed, peer_median_printed)
    if relative is None:
        return (f"{head} — relative gap not shown: the peer median is not "
                f"positive, so a percentage of it would read as its own "
                f"opposite")
    return f"{head} ({abs(relative):.{_REL_DP}f}% {direction})"


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


def _threshold_line(metric: str, report_date: str = None) -> str:
    """The 'Benchmark:' line, carrying its own provenance AND its own period.

    A house rule of thumb rendered in the same column as a CFR citation reads
    as a standard. Every line says which it is.

    And a citation carrying an effective date must state which period it is the
    threshold FOR. This line resolves through the same `benchmark_for` the
    grade does, so the band shown and the band graded against are the same one
    by construction rather than by two call sites agreeing.
    """
    benchmark = benchmark_for(metric, report_date)
    good = benchmark.get("good")
    warning = benchmark.get("warning")
    floor = benchmark.get("floor")
    lower = benchmark.get("lower_is_better", False)
    source = benchmark.get("source")
    if good is None or warning is None:
        return None

    if floor is not None:
        # "Adequate up to {warning}%" spanned 0-95%, overlapping both the Strong
        # band stated immediately before it and the Weak floor stated
        # immediately after. It resolved only because the Weak clause names the
        # below-floor case afterwards, so the reader had to let the third clause
        # correct the second. The three clauses now partition the range and meet
        # only at their shared bounds -- which is also what `status` implements:
        # WEAK below floor, STRONG on [floor, good], ADEQUATE on (good, warning],
        # WEAK above warning.
        band = (f"Strong {floor}%-{good}% | Adequate {good}%-{warning}% | "
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



def _provenance_block(institution, peers) -> list:
    """What produced this document, and when the data under it was pulled.

    Every metric line on this page carries `Basis:` because this package cares
    that a figure carries what it was computed from. The DOCUMENT did not carry
    the same for itself: 115 lines destined for a credit memo, with nothing
    saying which tool version rendered them or when the FDIC data was
    retrieved. `Report Date:` is the CALL-REPORT PERIOD, and a reader had no
    way to know that from the line.

    The version is read from `cdfibenchmark.__version__` AT RENDER TIME, and
    read from nowhere else. Not from pyproject.toml -- that is the DECLARED
    version, which the running code may not be -- and never hand-typed: that is
    exactly how setup.py came to ship `version="0.2.1"` through two further
    releases. When there is no installed distribution to read, the sentinel
    reaches the page WITH ITS REASON rather than being suppressed. Running from
    a clone is precisely when a reader most needs to know that the version
    cannot be established.
    """
    import cdfibenchmark

    generated = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC")

    version = cdfibenchmark.__version__
    if version == cdfibenchmark.UNKNOWN_VERSION:
        tool = (f"cdfi-benchmark {version} — running from a source tree with "
                f"no installed distribution metadata, so the exact code "
                f"version that produced this report cannot be established")
    else:
        tool = f"cdfi-benchmark {version}"

    lines = [
        "---",
        "",
        "## Provenance",
        "",
        f"**Tool:** {tool}",
        f"**Report Generated:** {generated}",
    ]

    if institution.retrieved_at:
        lines.append(f"**FDIC Data Retrieved:** {institution.retrieved_at}")
    else:
        lines.append(
            "**FDIC Data Retrieved:** unknown — this institution profile was "
            "not built from an FDIC API response, so no retrieval moment was "
            "recorded"
        )

    stamps = sorted({p.retrieved_at for p in peers if p.retrieved_at})
    if stamps:
        span = stamps[0] if len(stamps) == 1 else f"{stamps[0]} – {stamps[-1]}"
        lines.append(f"**Peer Data Retrieved:** {span}")
    else:
        lines.append(
            "**Peer Data Retrieved:** unknown — no peer profile records a "
            "retrieval moment"
        )

    lines += [
        f"**Call Report Period:** {institution.report_date or 'N/A'} — the "
        f"FDIC reporting period these figures describe. This is **not** the "
        f"date the data was retrieved, and not the date this report was "
        f"generated; both of those are stated above.",
        "",
    ]
    return lines


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
            lines.append(_vs_median_line(
                vs_printed, round(result.peer_median, _PCT_DP)))

        if result.basis:
            lines.append(f"**Basis:** {result.basis}")

        threshold = _threshold_line(result.metric, result.report_date)
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

    lines += _provenance_block(institution, peers)

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
