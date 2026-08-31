"""
Core dataclasses and constants for CDFI benchmarking.
Uses FDIC BankFind Suite API — free, no API key required.
"""
from dataclasses import dataclass, field
from typing import Optional


def _is_missing(x) -> bool:
    """True for an absent/unknown value — None or NaN — but NOT a real 0.

    Core financials that the FDIC response omitted arrive as NaN (never a
    fabricated 0.0); this distinguishes "we don't know" from "it is zero" so
    metrics propagate the unknown instead of inventing a verdict.
    """
    return x is None or (isinstance(x, float) and x != x)  # NaN != NaN


# ── FDIC BankFind Suite API ───────────────────────────────────────────────────
# The historical host `banks.data.fdic.gov/api` now answers HTTP 301 and
# redirects every request to `api.fdic.gov/banks`. Measured 2026-08-30:
#
#   $ curl -sS -o /dev/null -w "%{http_code} %{redirect_url}" \
#       "https://banks.data.fdic.gov/api/financials?...&format=json"
#   301 https://api.fdic.gov/banks/financials?...&format=json
#
# `requests` follows the redirect, so the old host still WORKS — which is
# exactly why this went unnoticed. It costs an extra round trip on every call
# and leaves the package depending on a permanent-redirect the FDIC is free to
# retire. Point at the canonical host; the redirect is a courtesy, not a
# contract.
FDIC_API_BASE = "https://api.fdic.gov/banks"
#: Retired host, kept only so a gate can assert we are not using it again.
FDIC_API_BASE_LEGACY = "https://banks.data.fdic.gov/api"

# ── Asset Size Buckets ────────────────────────────────────────────────────────
ASSET_BUCKETS = {
    "micro":    (0,           50_000),      # Under $50MM
    "small":    (50_000,      250_000),     # $50MM - $250MM
    "medium":   (250_000,     1_000_000),   # $250MM - $1B
    "large":    (1_000_000,   5_000_000),   # $1B - $5B
    "mega":     (5_000_000,   float("inf")),# Over $5B
}

# ── Threshold provenance ──────────────────────────────────────────────────────
# Every graded threshold in BENCHMARKS declares a "source". There are exactly
# two legal values and no unmarked third state:
#
#   "HOUSE"        this tool's own rule of thumb. Its numbers MUST come from a
#                  HOUSE_-prefixed constant below, so the attribution travels to
#                  every call site and a house number cannot be quoted as a
#                  standard without its own identifier contradicting the
#                  sentence quoting it.
#   "<instrument>"  a real, checkable citation (a CFR part, an FDIC/FFIEC
#                  definition).
#
# Why the rule exists: 0.2.1 shipped to remove a metric that was labelled and
# graded as something it was not. A house rule-of-thumb rendered in the same
# "Benchmark:" column as a CFR citation is that same defect in threshold form.
# Before 0.3.0, tier1_ratio was the only entry with any citation, and it lived
# in a comment where nothing could render or check it.
#
# NOTE ON WHAT IS *NOT* CITED: bank capital has published regulatory levels
# (below). Earnings, efficiency, funding and reserve-coverage ratios do NOT.
# The FDIC publishes these series and reports them against a peer group in the
# UBPR, but publishes no required or "well capitalized"-equivalent cut point for
# any of them. So every threshold below except tier1_ratio is HOUSE, and saying
# so is the finished work — inventing a citation is the defect.

# Earnings / efficiency rules of thumb. Community-banking conventions, not
# standards. Calibrated to the FDIC's own annualized series (NIMY, ROA, ROE,
# EEFFR) — see METRIC_BASIS below, which is why a non-annualized YTD proxy is
# not graded against them.
HOUSE_NIM_GOOD = 3.5
HOUSE_NIM_WARNING = 2.5
HOUSE_EFFICIENCY_GOOD = 60
HOUSE_EFFICIENCY_WARNING = 80
HOUSE_ROAA_GOOD = 1.0
HOUSE_ROAA_WARNING = 0.5
HOUSE_ROAE_GOOD = 10
HOUSE_ROAE_WARNING = 5

# Loans-to-deposits is graded as a BAND, not a one-sided ladder, and all three
# boundaries are this tool's own.
#
# Direction, and why one flag is not enough: through 0.2.1 this entry carried no
# `lower_is_better`, so `status` took the `>=` branch and a bank lending 200% of
# its deposits graded STRONG while one at 55% graded WEAK — inverted against the
# README's own "<= 80%" row. But `lower_is_better` ALONE is also wrong here: it
# grades 20% STRONG, and a CDFI bank lending 20% of deposits is not deploying
# capital into its community. The risk is two-sided — funding strain above,
# under-deployment below — so the grade is a band. There is no regulatory
# loans-to-deposits level to anchor any of it.
HOUSE_LTD_FLOOR = 50
HOUSE_LTD_GOOD = 80
HOUSE_LTD_WARNING = 95

# Asset-quality rules of thumb.
HOUSE_NPL_GOOD = 1.0
HOUSE_NPL_WARNING = 3.0
HOUSE_RESERVE_COVERAGE_GOOD = 100
HOUSE_RESERVE_COVERAGE_WARNING = 50

_CBLR = "12 CFR 324.12 (CBLR qualifying, lowered 9%->8% eff. 2026-07-01)"
_PCA = "12 CFR 324.403(b)(1) (PCA well-capitalized leverage minimum)"


# ── Benchmark Thresholds ──────────────────────────────────────────────────────
BENCHMARKS = {
    "nim": {
        "good": HOUSE_NIM_GOOD, "warning": HOUSE_NIM_WARNING,
        "unit": "%", "source": "HOUSE",
    },
    "efficiency_ratio": {
        "good": HOUSE_EFFICIENCY_GOOD, "warning": HOUSE_EFFICIENCY_WARNING,
        "unit": "%", "lower_is_better": True, "source": "HOUSE",
    },
    "roaa": {
        "good": HOUSE_ROAA_GOOD, "warning": HOUSE_ROAA_WARNING,
        "unit": "%", "source": "HOUSE",
    },
    "roae": {
        "good": HOUSE_ROAE_GOOD, "warning": HOUSE_ROAE_WARNING,
        "unit": "%", "source": "HOUSE",
    },
    # The ONLY cited entry. tier1_ratio grades the Tier 1 LEVERAGE ratio
    # (RBC1AAJ): STRONG >= 8 = CBLR qualifying level; ADEQUATE >= 5 = PCA
    # well-capitalized leverage; WEAK < 5.
    "tier1_ratio": {
        "good": 8, "warning": 5,
        "unit": "%", "source": f"{_CBLR}; {_PCA}",
    },
    # Banded: WEAK below `floor` (under-deployed) as well as above `warning`
    # (funding strain). See the HOUSE_LTD_* block above.
    "loans_to_deposits": {
        "floor": HOUSE_LTD_FLOOR,
        "good": HOUSE_LTD_GOOD, "warning": HOUSE_LTD_WARNING,
        "unit": "%", "lower_is_better": True, "source": "HOUSE",
    },
    "npl_ratio": {
        "good": HOUSE_NPL_GOOD, "warning": HOUSE_NPL_WARNING,
        "unit": "%", "lower_is_better": True, "source": "HOUSE",
    },
    "reserve_coverage": {
        "good": HOUSE_RESERVE_COVERAGE_GOOD,
        "warning": HOUSE_RESERVE_COVERAGE_WARNING,
        "unit": "%", "source": "HOUSE",
    },
}


# ── Metric basis ──────────────────────────────────────────────────────────────
# A threshold is only meaningful against a value measured the same way the
# threshold was calibrated. These constants record how each metric on a given
# InstitutionProfile was actually obtained, and GRADEABLE_BASES says which of
# those may be compared to a BENCHMARKS entry at all. Everything else renders
# its value with the basis on its face and grades N/A.
#
# Measured against the live FDIC API for CERT 34352 (five REPDTEs, 2025Q2-2026Q2)
# while writing this: computing nim/roaa/roae from YTD flows read 4.30x / 4.12x /
# 4.01x low at a Q1 REPDTE versus FDIC's published NIMY / ROA / ROE.
BASIS_FDIC = "FDIC published — annualized, average balances"
BASIS_STOCK = "computed from period-end balances (period-neutral)"
BASIS_FLOW_RATIO = "computed from same-period YTD flows (period-neutral)"
BASIS_COMPUTED_FY = "computed from full-year YTD flows over period-end balances"
BASIS_COMPUTED_YTD = "computed from YTD flows through Q{q} — NOT annualized"
BASIS_COMPUTED_YTD_UNKNOWN = "computed from YTD flows, period unknown — NOT annualized"
# NIM over TOTAL assets is not FDIC's NIMY (average EARNING assets), whatever
# the period — a strictly larger denominator biases it low even at a full year.
BASIS_NIM_TOTAL_ASSETS = "computed over TOTAL assets — not FDIC NIMY (avg earning assets)"

#: Bases whose values may be graded against a BENCHMARKS threshold.
GRADEABLE_BASES = frozenset({
    BASIS_FDIC, BASIS_STOCK, BASIS_FLOW_RATIO, BASIS_COMPUTED_FY,
})

#: Metrics computed from YTD flow items over point-in-time stocks.
_FLOW_OVER_STOCK_METRICS = frozenset({"nim", "roaa", "roae"})


@dataclass
class InstitutionProfile:
    """Profile of a single FDIC-insured institution from call report data."""
    cert: int
    name: str
    city: str
    state: str
    report_date: str
    total_assets: float             # in thousands
    total_deposits: float
    net_loans: float
    net_income: float
    interest_income: float
    interest_expense: float
    non_interest_income: float
    non_interest_expense: float
    total_equity: float
    tier1_ratio: Optional[float] = None
    gross_loans: Optional[float] = None
    non_current_loans: Optional[float] = None
    loan_loss_allowance: Optional[float] = None
    # Amortization of intangibles + goodwill impairment (FDIC EAMINTAN, YTD $k).
    # FDIC's EEFFR subtracts this from noninterest expense; omitting it read
    # 191.06% where FDIC published 88.33% for CERT 34352 at 20250930.
    intangible_amortization: Optional[float] = None

    # ── FDIC-published ratios (preferred over the computed proxy) ───────────
    # The FDIC /financials endpoint publishes these already annualized and over
    # the correct average denominators, which is what the thresholds are
    # calibrated to. Absent (a hand-built profile, or a field the API omitted)
    # → None, and the computed proxy is used and marked as such.
    reported_nim: Optional[float] = None                # NIMY
    reported_roaa: Optional[float] = None               # ROA
    reported_roae: Optional[float] = None               # ROE
    reported_efficiency_ratio: Optional[float] = None   # EEFFR

    @property
    def total_assets_mm(self) -> float:
        return self.total_assets / 1_000

    @property
    def asset_bucket(self) -> str:
        # Unknown assets must not be silently labelled the largest bucket.
        if _is_missing(self.total_assets):
            return "unknown"
        assets = self.total_assets
        for bucket, (low, high) in ASSET_BUCKETS.items():
            if low <= assets < high:
                return bucket
        return "mega"

    @property
    def fiscal_quarter(self) -> Optional[int]:
        """Calendar quarter of ``report_date`` (YYYYMMDD), or None if unparsable.

        FDIC call-report flow items are YEAR-TO-DATE, so the quarter is what
        says how many months a flow figure actually covers. An unparsable
        report_date yields None and is treated as "period unknown" — never
        assumed to be a full year.
        """
        d = (self.report_date or "").strip()
        if len(d) != 8 or not d.isdigit():
            return None
        return {"0331": 1, "0630": 2, "0930": 3, "1231": 4}.get(d[4:])

    def metric_basis(self, metric: str) -> str:
        """How ``metric`` was obtained on this profile — see BASIS_* above."""
        if metric == "nim":
            if self.reported_nim is not None:
                return BASIS_FDIC
            return BASIS_NIM_TOTAL_ASSETS
        if metric == "roaa":
            if self.reported_roaa is not None:
                return BASIS_FDIC
            return self._computed_flow_basis()
        if metric == "roae":
            if self.reported_roae is not None:
                return BASIS_FDIC
            return self._computed_flow_basis()
        if metric == "efficiency_ratio":
            if self.reported_efficiency_ratio is not None:
                return BASIS_FDIC
            # Numerator and denominator are both YTD flows over the same
            # period, so the period cancels exactly. Annualizing this would
            # INTRODUCE an error where there is none.
            return BASIS_FLOW_RATIO
        return BASIS_STOCK

    def _computed_flow_basis(self) -> str:
        q = self.fiscal_quarter
        if q == 4:
            return BASIS_COMPUTED_FY
        if q is None:
            return BASIS_COMPUTED_YTD_UNKNOWN
        return BASIS_COMPUTED_YTD.format(q=q)

    def basis_dict(self) -> dict:
        return {m: self.metric_basis(m) for m in self.metrics_dict()}

    # Metric properties divide by a core financial. When that core is missing
    # (absent in the FDIC response → NaN) the metric is unknown, so it
    # propagates NaN rather than inventing a number or collapsing to None. A
    # real denominator of 0 stays None (genuinely undefined, no ZeroDivision).
    @property
    def nim(self) -> Optional[float]:
        # FDIC NIMY when published: annualized, over average EARNING assets —
        # the basis the 3.5%/2.5% thresholds are calibrated to. The fallback
        # below is a YTD proxy over TOTAL assets and is NOT graded (see
        # metric_basis / GRADEABLE_BASES).
        if self.reported_nim is not None:
            return self.reported_nim
        if _is_missing(self.total_assets):
            return float("nan")
        if self.total_assets > 0:
            return ((self.interest_income - self.interest_expense)
                    / self.total_assets * 100)
        return None

    @property
    def efficiency_ratio(self) -> Optional[float]:
        """FDIC EEFFR.

        EEFFR = (NONIX − EAMINTAN) / ((INTINC − EINTEXP) + NONII) × 100

        0.2.1 fixed the DENOMINATOR (net, not gross, interest income) and left
        the NUMERATOR wrong: FDIC subtracts amortization of intangibles and
        goodwill-impairment losses from noninterest expense, and the package
        did not. Verified against the live API for CERT 34352 at five REPDTEs —
        the formula above reproduces FDIC's published EEFFR to 5 decimals, while
        the old one read 191.06% at 20250930 where FDIC published 88.33%.

        Both numerator and denominator are YTD flows over the same period, so
        the period cancels: this metric is period-neutral and must NOT be
        annualized. Annualizing it would introduce an error where there is none.
        """
        if self.reported_efficiency_ratio is not None:
            return self.reported_efficiency_ratio
        revenue = ((self.interest_income - self.interest_expense)
                   + self.non_interest_income)
        if _is_missing(revenue):
            return float("nan")
        # An absent EAMINTAN subtracts nothing — never a fabricated figure.
        expense = self.non_interest_expense
        if self.intangible_amortization is not None:
            expense = expense - self.intangible_amortization
        if revenue > 0:
            return (expense / revenue) * 100
        return None

    @property
    def roaa(self) -> Optional[float]:
        # FDIC ROA when published: annualized over AVERAGE assets. The fallback
        # is YTD net income over PERIOD-END assets and is graded only at a Q4
        # report date, where the flow covers the full year.
        if self.reported_roaa is not None:
            return self.reported_roaa
        if _is_missing(self.total_assets):
            return float("nan")
        if self.total_assets > 0:
            return (self.net_income / self.total_assets) * 100
        return None

    @property
    def roae(self) -> Optional[float]:
        # FDIC ROE when published: annualized over AVERAGE equity. See roaa.
        if self.reported_roae is not None:
            return self.reported_roae
        if _is_missing(self.total_equity):
            return float("nan")
        if self.total_equity > 0:
            return (self.net_income / self.total_equity) * 100
        return None

    @property
    def loans_to_deposits(self) -> Optional[float]:
        if _is_missing(self.total_deposits):
            return float("nan")
        if self.total_deposits > 0:
            return (self.net_loans / self.total_deposits) * 100
        return None

    @property
    def npl_ratio(self) -> Optional[float]:
        if (self.non_current_loans is not None and
                self.gross_loans and self.gross_loans > 0):
            return (self.non_current_loans / self.gross_loans) * 100
        return None

    @property
    def reserve_coverage(self) -> Optional[float]:
        if (self.loan_loss_allowance is not None and
                self.non_current_loans and self.non_current_loans > 0):
            return (self.loan_loss_allowance / self.non_current_loans) * 100
        return None

    def metrics_dict(self) -> dict:
        return {
            "nim":               self.nim,
            "efficiency_ratio":  self.efficiency_ratio,
            "roaa":              self.roaa,
            "roae":              self.roae,
            "tier1_ratio":       self.tier1_ratio,
            "loans_to_deposits": self.loans_to_deposits,
            "npl_ratio":         self.npl_ratio,
            "reserve_coverage":  self.reserve_coverage,
        }


@dataclass
class BenchmarkResult:
    """Benchmarking result for a single metric."""
    metric: str
    institution_value: Optional[float]
    peer_median: Optional[float]
    peer_25th: Optional[float]
    peer_75th: Optional[float]
    peer_count: int
    unit: str = "%"
    lower_is_better: bool = False
    #: How institution_value was measured — see BASIS_* in this module. A basis
    #: outside GRADEABLE_BASES degrades the STATUS to N/A while still reporting
    #: the value: the number is a measurement, but not one this threshold was
    #: calibrated against. None means "unspecified" and grades as before.
    basis: Optional[str] = None
    #: Where this metric's threshold comes from: "HOUSE" or a citation.
    source: Optional[str] = None

    @property
    def vs_median(self) -> Optional[float]:
        if _is_missing(self.institution_value) or self.peer_median is None:
            return None
        return self.institution_value - self.peer_median

    @property
    def status(self) -> str:
        # A missing (None) or unknown (NaN) value is "N/A", never graded WEAK.
        if _is_missing(self.institution_value):
            return "N/A"
        # A value measured on a different basis than the threshold was
        # calibrated on is reported but NOT graded. Degrade the cell, not the
        # number: institution_value is still returned in full.
        if self.basis is not None and self.basis not in GRADEABLE_BASES:
            return "N/A"
        benchmark = BENCHMARKS.get(self.metric, {})
        good = benchmark.get("good")
        warning = benchmark.get("warning")
        lower = benchmark.get("lower_is_better", False)

        if good is None:
            return "N/A"

        # Banded metric: a value below `floor` is WEAK regardless of the ladder
        # above it. Without this, a lower_is_better ladder grades a bank that
        # barely lends as STRONG.
        floor = benchmark.get("floor")
        if floor is not None and self.institution_value < floor:
            return "WEAK"

        if lower:
            if self.institution_value <= good:
                return "STRONG"
            elif self.institution_value <= warning:
                return "ADEQUATE"
            return "WEAK"
        else:
            if self.institution_value >= good:
                return "STRONG"
            elif self.institution_value >= warning:
                return "ADEQUATE"
            return "WEAK"
