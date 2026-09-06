"""Every metric's basis line must be true of that metric, and none by default.

`metric_basis` handled `nim` / `roaa` / `roae` / `efficiency_ratio` explicitly
and ENDED IN A FALL-THROUGH to BASIS_STOCK. A fall-through is a decision about
every case nobody enumerated, and this one was wrong for exactly one metric:

    tier1_ratio value   14.9876825620271   <- FDIC RBC1AAJ, carried verbatim
    metric_basis()      "computed from period-end balances (period-neutral)"
    EQ / ASSET          15.19%             <- what that sentence names. A
                                              DIFFERENT number.

Nothing computed it, it did not come from period-end balances, and the quantity
the label describes is a different figure. `metric_basis`'s own docstring
promises that "a value and the basis rendered beside it can never disagree about
where the value came from", which is precisely what it broke — on the one
FDIC-published value in the group, the only metric carrying a CFR citation, and
so the line a reader is most likely to check. The grade never changed
(BASIS_STOCK and the correct basis are both gradeable); the rendered sentence
was false.

So this module gates two things:

1. `tier1_ratio` specifically, in all three states it can be in.
2. THE CLASS. The fall-through is gone — `metric_basis` now reaches BASIS_STOCK
   through an explicit set and ends at BASIS_UNRULED, which is not gradeable. A
   metric added without ruling its basis degrades loudly instead of inheriting
   whichever branch happened to be written last.
"""
import math

import pytest

from cdfibenchmark.data.schema import (
    InstitutionProfile, BENCHMARKS, GRADEABLE_BASES,
    BASIS_STOCK, BASIS_FDIC, BASIS_FDIC_LEVERAGE, BASIS_UNRULED,
    BASIS_UNREPORTED, BASIS_REJECTED_IMPLAUSIBLE, _STOCK_RATIO_METRICS,
)
from cdfibenchmark.report.generator import (
    METRIC_LABELS, _threshold_line, _metric_label,
)


def _inst(**over):
    """CERT 16584 at 20260630, as FDIC serves it. Real, unrounded figures."""
    base = dict(
        cert=16584, name="CARVER STATE BANK", city="SAVANNAH", state="GA",
        report_date="20260630",
        total_assets=111_233.0, total_deposits=98_060.0, net_loans=49_003.0,
        net_income=555.0,
        interest_income=3_536.0, interest_expense=618.0,
        non_interest_income=612.0, non_interest_expense=2_762.0,
        total_equity=16_896.0,
        tier1_ratio=14.9876825620271,
        gross_loans=49_575.0, non_current_loans=182.0, loan_loss_allowance=629.0,
    )
    base.update(over)
    return InstitutionProfile(**base)


# ── B-B: tier1_ratio, in each of its three states ────────────────────────────
def test_tier1_basis_does_not_claim_the_package_computed_it():
    inst = _inst()
    basis = inst.metric_basis("tier1_ratio")
    assert basis != BASIS_STOCK, (
        "tier1_ratio still falls through to the period-end-balances basis. "
        "The value is FDIC's published RBC1AAJ; nothing here computed it."
    )
    assert "computed" not in basis.lower(), (
        f"tier1_ratio's basis says the value was computed: {basis!r}"
    )


def test_tier1_basis_names_the_field_it_actually_came_from():
    basis = _inst().metric_basis("tier1_ratio")
    assert "FDIC" in basis and "RBC1AAJ" in basis, (
        f"tier1_ratio's basis does not name FDIC's published field: {basis!r}"
    )


def test_tier1_basis_does_not_claim_to_be_annualized():
    """BASIS_FDIC is not usable here either: it says "annualized".

    A capital ratio has no flow period to annualize. Reusing the flow-metric
    basis string would swap one false sentence for another.
    """
    basis = _inst().metric_basis("tier1_ratio")
    assert basis != BASIS_FDIC
    assert "not annualized" in basis.lower(), (
        f"tier1_ratio's basis does not say it is unannualized: {basis!r}"
    )


def test_the_basis_line_and_the_value_name_the_same_quantity():
    """The assertion that would have caught the shipped falsehood.

    BASIS_STOCK names a ratio of period-end balances. The nearest such ratio for
    a capital metric is EQ/ASSET, and it is NOT this value: 15.19% against the
    14.9877% FDIC published. A basis that names a different number than the one
    beside it is the defect, whether or not the grade changes.
    """
    inst = _inst()
    eq_over_assets = inst.total_equity / inst.total_assets * 100
    assert inst.tier1_ratio == pytest.approx(14.9876825620271)
    assert eq_over_assets == pytest.approx(15.1897, abs=1e-4)
    assert inst.tier1_ratio != pytest.approx(eq_over_assets, abs=1e-4)
    assert inst.metric_basis("tier1_ratio") == BASIS_FDIC_LEVERAGE


def test_tier1_stays_gradeable_because_no_grade_was_ever_wrong():
    """B-B corrects a sentence, not a grade. The grade must not move."""
    assert BASIS_FDIC_LEVERAGE in GRADEABLE_BASES
    assert _inst().metric_basis("tier1_ratio") in GRADEABLE_BASES


def test_an_unreported_tier1_says_nothing_was_reported():
    inst = _inst(tier1_ratio=None)
    assert inst.metric_basis("tier1_ratio") == BASIS_UNREPORTED
    assert BASIS_UNREPORTED not in GRADEABLE_BASES


def test_a_refused_tier1_says_it_was_refused_not_that_it_was_absent():
    """B-A and B-B touch the same metric and are ruled together.

    Once an out-of-band RBC1AAJ degrades to None, `metric_basis` has a THIRD
    state to be true about. A refusal that renders as "no value was reported"
    would be this same defect again, one release later.
    """
    refused = _inst(tier1_ratio=None, implausible_fields=("RBC1AAJ",))
    absent = _inst(tier1_ratio=None)
    assert refused.metric_basis("tier1_ratio") == BASIS_REJECTED_IMPLAUSIBLE
    assert refused.metric_basis("tier1_ratio") != absent.metric_basis("tier1_ratio")
    assert BASIS_REJECTED_IMPLAUSIBLE not in GRADEABLE_BASES


# ── the class: the fall-through is gone ──────────────────────────────────────
@pytest.mark.parametrize("metric", sorted(_inst().metrics_dict()))
def test_every_metric_has_a_ruled_basis(metric):
    """Not one metric may reach the end of `metric_basis` unruled.

    Red-proving this is one edit: add a key to `metrics_dict` without giving it
    a branch or listing it in `_STOCK_RATIO_METRICS`.
    """
    basis = _inst().metric_basis(metric)
    assert basis != BASIS_UNRULED, (
        f"{metric} has no ruled basis — it reached the fall-through. Give it a "
        f"branch in metric_basis, or add it to _STOCK_RATIO_METRICS if its "
        f"value really is a ratio of two period-end balances."
    )
    assert basis, f"{metric} has an empty basis"


def test_an_unruled_metric_is_not_gradeable():
    """The fall-through's replacement must degrade, not grade.

    The old fall-through handed an unruled metric a specific, confident and
    GRADEABLE claim. That is what let a false basis render under a CFR citation.
    """
    assert BASIS_UNRULED not in GRADEABLE_BASES
    assert _inst().metric_basis("a_metric_nobody_ruled") == BASIS_UNRULED


@pytest.mark.parametrize("metric", sorted(_STOCK_RATIO_METRICS))
def test_a_stock_basis_metric_really_is_a_ratio_of_period_end_stocks(metric):
    """BASIS_STOCK is a checkable claim, so check it.

    Each of these must be reproducible from two balance-sheet fields carried on
    the profile. `tier1_ratio` is not, which is exactly why it left this set.
    """
    inst = _inst()
    expected = {
        "loans_to_deposits": inst.net_loans / inst.total_deposits * 100,
        "npl_ratio": inst.non_current_loans / inst.gross_loans * 100,
        "reserve_coverage": inst.loan_loss_allowance / inst.non_current_loans * 100,
    }[metric]
    assert inst.metric_basis(metric) == BASIS_STOCK
    assert inst.metrics_dict()[metric] == pytest.approx(expected)


def test_tier1_is_not_reproducible_from_this_profiles_stocks():
    """The negative half of the test above, on the metric that failed it."""
    inst = _inst()
    for numerator in (inst.total_equity,):
        for denominator in (inst.total_assets, inst.total_deposits):
            assert inst.tier1_ratio != pytest.approx(
                numerator / denominator * 100, abs=1e-4
            ), "tier1_ratio IS a period-end stock ratio after all; re-rule it"


# ── the same class, one layer out: every graded metric is fully wired ────────
@pytest.mark.parametrize("metric", sorted(BENCHMARKS))
def test_every_graded_metric_is_complete_across_every_map_that_renders_it(metric):
    """Four independent `.get(key, default)` fall-throughs decide this row.

    `metrics_dict().get(metric)` (silently None -> N/A), `metric_basis` (was a
    silent BASIS_STOCK), `METRIC_LABELS.get(metric, metric)` (renders the raw
    key as the row label) and `_threshold_line` (returns None and the Benchmark
    line silently vanishes). A metric added to BENCHMARKS alone renders a row
    with a raw-key label, no value, no benchmark and no grade — and nothing
    fails. Red-proving this is one edit: add a key to BENCHMARKS.
    """
    inst = _inst()
    assert metric in inst.metrics_dict(), (
        f"{metric} is graded but has no value: metrics_dict().get() returns "
        f"None and the row silently renders N/A"
    )
    assert inst.metric_basis(metric) != BASIS_UNRULED, (
        f"{metric} is graded but its basis was never ruled"
    )
    assert metric in METRIC_LABELS, (
        f"{metric} has no display label; the report renders the raw key "
        f"{metric!r} as the row heading"
    )
    assert _metric_label(metric, inst.metric_basis(metric)) != metric
    assert _threshold_line(metric), (
        f"{metric} renders no Benchmark line, so its grade would appear with "
        f"no threshold and no attribution beside it"
    )


def test_the_metrics_and_the_graded_metrics_have_not_drifted_apart():
    """Every metric this package computes is either graded or knowingly not."""
    computed = set(_inst().metrics_dict())
    graded = set(BENCHMARKS)
    assert graded <= computed, (
        f"graded metrics with no value: {sorted(graded - computed)}"
    )
    assert not (computed - graded), (
        f"metrics computed but never graded, with no ruling recorded: "
        f"{sorted(computed - graded)}"
    )


def test_no_metric_reports_nan_dressed_as_a_number():
    """Unrelated to basis, and the reason this sweep is worth running at all.

    Every value `metrics_dict` returns must be a real float, None, or NaN — and
    a NaN must be recognised as missing by the same predicate the renderer uses.
    """
    from cdfibenchmark.data.schema import _is_missing
    for metric, value in _inst().metrics_dict().items():
        if value is None:
            continue
        assert isinstance(value, float), f"{metric} is {type(value).__name__}"
        if math.isnan(value):
            assert _is_missing(value), f"{metric} NaN not seen as missing"
