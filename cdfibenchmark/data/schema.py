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
FDIC_API_BASE = "https://banks.data.fdic.gov/api"

# ── Asset Size Buckets ────────────────────────────────────────────────────────
ASSET_BUCKETS = {
    "micro":    (0,           50_000),      # Under $50MM
    "small":    (50_000,      250_000),     # $50MM - $250MM
    "medium":   (250_000,     1_000_000),   # $250MM - $1B
    "large":    (1_000_000,   5_000_000),   # $1B - $5B
    "mega":     (5_000_000,   float("inf")),# Over $5B
}

# ── Benchmark Thresholds ──────────────────────────────────────────────────────
BENCHMARKS = {
    "nim":              {"good": 3.5, "warning": 2.5,  "unit": "%"},
    "efficiency_ratio": {"good": 60,  "warning": 80,   "unit": "%", "lower_is_better": True},
    "roaa":             {"good": 1.0, "warning": 0.5,  "unit": "%"},
    "roae":             {"good": 10,  "warning": 5,    "unit": "%"},
    "tier1_ratio":      {"good": 12,  "warning": 8,    "unit": "%"},
    "loans_to_deposits":{"good": 80,  "warning": 95,   "unit": "%"},
    "npl_ratio":        {"good": 1.0, "warning": 3.0,  "unit": "%", "lower_is_better": True},
    "reserve_coverage": {"good": 100, "warning": 50,   "unit": "%"},
}


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

    # Metric properties divide by a core financial. When that core is missing
    # (absent in the FDIC response → NaN) the metric is unknown, so it
    # propagates NaN rather than inventing a number or collapsing to None. A
    # real denominator of 0 stays None (genuinely undefined, no ZeroDivision).
    @property
    def nim(self) -> Optional[float]:
        if _is_missing(self.total_assets):
            return float("nan")
        if self.total_assets > 0:
            return ((self.interest_income - self.interest_expense)
                    / self.total_assets * 100)
        return None

    @property
    def efficiency_ratio(self) -> Optional[float]:
        revenue = self.interest_income + self.non_interest_income
        if _is_missing(revenue):
            return float("nan")
        if revenue > 0:
            return (self.non_interest_expense / revenue) * 100
        return None

    @property
    def roaa(self) -> Optional[float]:
        if _is_missing(self.total_assets):
            return float("nan")
        if self.total_assets > 0:
            return (self.net_income / self.total_assets) * 100
        return None

    @property
    def roae(self) -> Optional[float]:
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
        benchmark = BENCHMARKS.get(self.metric, {})
        good = benchmark.get("good")
        warning = benchmark.get("warning")
        lower = benchmark.get("lower_is_better", False)

        if good is None:
            return "N/A"

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
