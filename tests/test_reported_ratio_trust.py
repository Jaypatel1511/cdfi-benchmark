"""FDIC's zero-fill must not be graded as a measurement.

B3, measured against the live FDIC API on 2026-09-05, not inferred.

FDIC publishes a literal 0 where it did not compute a ratio.
`_coerce_float(row, "EEFFR", absent=None)` correctly preserves a present 0.0 —
`_is_missing` is intact and is not the defect. The fill arrives from FDIC
ALREADY fabricated, and the `reported_*` short-circuit had no missing-value
discipline of its own: `is not None` was true, so `metric_basis` returned
BASIS_FDIC (gradeable), and because `efficiency_ratio` is `lower_is_better`,
0.0 <= 60 graded **STRONG**.

Executed over all 4,313 active filers at REPDTE 20260630:

    EEFFR == 0   19 (0.44%)      NIMY == 0   22 (0.51%)
    ROA   == 0   17 (0.39%)      ROE  absent 18

    CERT 33492 CRESCENT BANK        ASSET $1,065,126k  NIMY  4.481  ROA  8.336
    CERT 12013 UNION COUNTY SAVINGS ASSET $1,478,885k  NIMY -0.368  ROA -1.450

Both are real operating US banks inside the CDFI size band, both rendered
`Efficiency Ratio | 0.00% | STRONG`, and both can land in a real peer group's
median. The asymmetry is what made it dangerous: the same fill grades NIM and
ROAA WEAK, which looks odd and invites a second look; STRONG does not.

THE RULE (see schema.reported_is_trustworthy): a published ratio is trusted
only when the institution's own financials corroborate it —
  (a) UNVERIFIABLE  an input it derives from is absent      -> 17 of the 19
  (b) CONTRADICTED  published 0 with a non-zero numerator    -> the other 2
Not a magic-zero rule: a zero the financials SUPPORT is trusted.

These gates are offline and run on constructed profiles.
"""
import pytest

from cdfibenchmark.data.schema import (
    InstitutionProfile, BenchmarkResult, BASIS_FDIC, GRADEABLE_BASES,
)

REPORTED_METRICS = ("nim", "roaa", "roae", "efficiency_ratio")


def _profile(**over):
    """A complete, ordinary filer. Overrides model the defect under test."""
    base = dict(
        cert=99100, name="Constructed Bank (SYNTHETIC)", city="Chicago",
        state="IL", report_date="20260630",
        total_assets=1_000_000.0, total_deposits=800_000.0,
        net_loans=600_000.0, net_income=8_000.0,
        interest_income=30_000.0, interest_expense=8_000.0,
        non_interest_income=4_000.0, non_interest_expense=15_000.0,
        total_equity=100_000.0,
    )
    base.update(over)
    return InstitutionProfile(**base)


def _status(profile, metric):
    return BenchmarkResult(
        metric=metric,
        institution_value=profile.metrics_dict()[metric],
        peer_median=None, peer_25th=None, peer_75th=None, peer_count=0,
        lower_is_better=(metric in ("efficiency_ratio", "npl_ratio")),
        basis=profile.metric_basis(metric),
    ).status


# ── (b) CONTRADICTED: a published zero beside a non-zero numerator ───────────
def test_zero_efficiency_ratio_with_real_expenses_is_never_rendered_as_zero():
    """The headline defect: FDIC's fill must not reach the report as a value."""
    p = _profile(reported_efficiency_ratio=0.0)   # NONIX is 15,000k, non-zero

    assert not p.reported_is_trustworthy("efficiency_ratio")
    assert p.efficiency_ratio != 0.0, (
        "FDIC's zero-fill was rendered as a 0.00% efficiency ratio for a bank "
        "reporting $15,000k of noninterest expense"
    )
    assert p.metric_basis("efficiency_ratio") != BASIS_FDIC


def test_the_fill_shaped_like_the_real_banks_renders_not_available():
    """CERT 33492 / CERT 12013 exactly.

    Both have NEGATIVE revenue (net interest income + noninterest income < 0),
    which is precisely when FDIC declines to compute an efficiency ratio and
    fills 0. The computed proxy is genuinely undefined there, so the correct
    rendering is N/A — reached through the round's existing machinery, with no
    new path: `efficiency_ratio` already returns None when revenue <= 0.
    """
    p = _profile(
        interest_income=5_000.0, interest_expense=9_000.0,   # netII = -4,000k
        non_interest_income=1_000.0,                          # revenue = -3,000k
        non_interest_expense=7_318.0,                         # CERT 12013's NONIX
        reported_efficiency_ratio=0.0,
    )
    assert not p.reported_is_trustworthy("efficiency_ratio")
    assert p.efficiency_ratio is None
    assert _status(p, "efficiency_ratio") == "N/A", (
        "a bank whose efficiency ratio FDIC declined to compute rendered a "
        "grade instead of N/A"
    )


def test_a_zero_fill_does_not_grade_strong_when_the_truth_is_weak():
    """The asymmetry that made this dangerous.

    The same fill grades NIM and ROAA WEAK, which looks odd and invites a
    second look. Efficiency grades STRONG, which does not. Here the bank's real
    efficiency ratio is 96.15% — WEAK — and the fill claimed STRONG.
    """
    p = _profile(non_interest_expense=25_000.0, reported_efficiency_ratio=0.0)

    assert p.efficiency_ratio == pytest.approx(25_000.0 / 26_000.0 * 100)
    assert _status(p, "efficiency_ratio") == "WEAK", (
        "FDIC's zero-fill graded STRONG under BASIS_FDIC — the strongest "
        "warrant the package can attach — for a bank whose own filed "
        "financials put it at 96.15%"
    )


def test_a_rejected_published_value_falls_back_to_the_computed_basis():
    """Rejection must use the round's existing machinery, not a new path."""
    p = _profile(reported_efficiency_ratio=0.0)
    basis = p.metric_basis("efficiency_ratio")

    assert basis != BASIS_FDIC, (
        "a rejected published value still claimed FDIC's basis, so the report "
        "would warrant a fill as FDIC's own annualized series"
    )
    # The computed proxy is what renders, and it is the real ratio.
    expected = (15_000.0 / ((30_000.0 - 8_000.0) + 4_000.0)) * 100
    assert p.efficiency_ratio == pytest.approx(expected)


@pytest.mark.parametrize("metric,field,numerator_override", [
    ("nim", "reported_nim", {}),                      # netII = 22,000k
    ("roaa", "reported_roaa", {}),                    # NETINC = 8,000k
    ("roae", "reported_roae", {}),                    # NETINC = 8,000k
    ("efficiency_ratio", "reported_efficiency_ratio", {}),
])
def test_every_reported_field_rejects_a_contradicted_zero(metric, field, numerator_override):
    """Swept across ALL FOUR reported_* fields, not the one that was noticed.

    This portfolio's most repeated fix defect is landing on the noticed site
    rather than the class.
    """
    p = _profile(**{field: 0.0}, **numerator_override)
    assert not p.reported_is_trustworthy(metric), (
        f"{field}=0.0 was trusted although this profile's {metric} numerator "
        f"is non-zero"
    )
    assert p.metric_basis(metric) != BASIS_FDIC


# ── NOT a magic-zero rule: a supported zero is still trusted ─────────────────
def test_a_zero_the_financials_support_is_trusted():
    """A genuinely break-even bank publishing ROA == 0 must keep it.

    This is why the rule checks the numerator rather than special-casing zero:
    `ROA == 0.00` is plausible for a break-even bank, `EEFFR == 0.0` is not
    achievable by an operating one, and a rule that special-cased zero would be
    wrong for one of the four metrics.
    """
    p = _profile(net_income=0.0, reported_roaa=0.0)

    assert p.reported_is_trustworthy("roaa"), (
        "a published ROA of 0 beside a reported NETINC of 0 is a measurement, "
        "not a fill, and must not be rejected"
    )
    assert p.metric_basis("roaa") == BASIS_FDIC
    assert p.roaa == 0.0


def test_zero_efficiency_ratio_with_zero_expenses_is_trusted():
    p = _profile(non_interest_expense=0.0, reported_efficiency_ratio=0.0)
    assert p.reported_is_trustworthy("efficiency_ratio")
    assert p.metric_basis("efficiency_ratio") == BASIS_FDIC


# ── (a) UNVERIFIABLE: an input the ratio derives from is absent ──────────────
@pytest.mark.parametrize("metric,field,absent_input", [
    ("efficiency_ratio", "reported_efficiency_ratio", "non_interest_expense"),
    ("efficiency_ratio", "reported_efficiency_ratio", "interest_income"),
    ("nim", "reported_nim", "interest_income"),
    ("nim", "reported_nim", "interest_expense"),
    ("roaa", "reported_roaa", "net_income"),
    ("roae", "reported_roae", "net_income"),
])
def test_a_published_ratio_is_rejected_when_its_inputs_are_absent(
        metric, field, absent_input):
    """The 17 foreign branches and agencies: FDIC omits the call-report detail
    entirely, so there is nothing to corroborate the published value against."""
    p = _profile(**{field: 55.0, absent_input: float("nan")})
    assert not p.reported_is_trustworthy(metric), (
        f"{field} was trusted although {absent_input} is absent — the "
        f"published value cannot be checked against anything"
    )


def test_an_ordinary_filer_keeps_every_published_ratio():
    """The rule must not cost a normal bank its FDIC basis.

    Measured over the live population at 20260630: 4,294 of 4,313 banks
    (99.56%) keep their published efficiency ratio, and ZERO rows anywhere have
    an absent numerator input together with a non-zero published value.
    """
    p = _profile(reported_nim=3.9, reported_roaa=1.2,
                 reported_roae=11.0, reported_efficiency_ratio=58.0)
    for metric in REPORTED_METRICS:
        assert p.reported_is_trustworthy(metric), f"{metric} wrongly rejected"
        assert p.metric_basis(metric) == BASIS_FDIC
    assert _status(p, "efficiency_ratio") == "STRONG"


def test_value_and_basis_never_disagree_about_where_the_value_came_from():
    """The property and metric_basis must ask the SAME question.

    If they diverged, a report could render FDIC's fill while attributing it to
    the computed proxy, or the reverse.
    """
    for kwargs in ({"reported_efficiency_ratio": 0.0},
                   {"reported_nim": 0.0},
                   {"reported_roaa": 0.0, "net_income": 0.0},
                   {"reported_roae": 11.0}):
        p = _profile(**kwargs)
        for metric in REPORTED_METRICS:
            trusted = p.reported_is_trustworthy(metric)
            claims_fdic = p.metric_basis(metric) == BASIS_FDIC
            assert trusted == claims_fdic, (
                f"{metric}: trusted={trusted} but basis claims FDIC="
                f"{claims_fdic} for {kwargs}"
            )
