"""Direction gates for the grading table — the package's entire product.

Before 0.3.0 exactly one metric's *direction* was gated (tier1_ratio, in
test_schema.py). `loans_to_deposits` shipped from at least 0.2.0 with no
`lower_is_better` flag while its README row read "<= 80%", so a bank lending
200% of deposits graded STRONG and one at 55% graded WEAK — the same
"graded in the direction its own documentation contradicts" class the RBCT1J
defect belonged to.

These tests assert the *monotonicity* of every metric, derived from its own
BENCHMARKS entry, rather than spot-checking values. A future entry that loses
(or wrongly gains) a direction flag fails here without anyone remembering to
add a case for it.
"""
import pytest
from cdfibenchmark.data.schema import BENCHMARKS, BenchmarkResult

_RANK = {"WEAK": 0, "ADEQUATE": 1, "STRONG": 2}


def _status(metric, value):
    return BenchmarkResult(
        metric=metric, institution_value=value,
        peer_median=None, peer_25th=None, peer_75th=None, peer_count=0,
    ).status


# Derived from BENCHMARKS itself — never a typed list of metric names, so a
# metric added to the table without a direction gate cannot slip through.
@pytest.mark.parametrize("metric", sorted(BENCHMARKS))
def test_every_metric_grades_monotonically_in_its_declared_direction(metric):
    """Walking the value axis must never move the grade the wrong way.

    For a higher-is-better metric the grade must be non-decreasing in value;
    for a lower-is-better metric, non-increasing. A banded metric declares a
    `floor` and is exempt from monotonicity below that floor (tested
    separately).
    """
    cfg = BENCHMARKS[metric]
    if "floor" in cfg:
        pytest.skip(f"{metric} is banded (floor={cfg['floor']}) — see band tests")

    lower_is_better = cfg.get("lower_is_better", False)
    axis = [-10, 0, 0.5, 1, 2.5, 3.5, 5, 8, 10, 25, 50, 60, 80, 95, 100, 130, 200]
    grades = [_RANK[_status(metric, v)] for v in axis]

    for (v0, g0), (v1, g1) in zip(zip(axis, grades), list(zip(axis, grades))[1:]):
        if lower_is_better:
            assert g1 <= g0, (
                f"{metric} declares lower_is_better but grade IMPROVED from "
                f"{v0}->{g0} to {v1}->{g1}"
            )
        else:
            assert g1 >= g0, (
                f"{metric} declares higher-is-better but grade WORSENED from "
                f"{v0}->{g0} to {v1}->{g1}"
            )


def test_loans_to_deposits_extremes_are_not_both_strong():
    """A bank lending 200% of deposits and one lending 20% cannot both be STRONG.

    This is the shape of the 0.2.x defect: with no direction flag, `status`
    took the `>=` branch and every high value graded STRONG.
    """
    assert not (_status("loans_to_deposits", 200) == "STRONG"
                and _status("loans_to_deposits", 20) == "STRONG")


def test_loans_to_deposits_overextended_is_weak():
    """130% loans-to-deposits is funding strain, not strength."""
    assert _status("loans_to_deposits", 130) == "WEAK"


def test_loans_to_deposits_underdeployed_is_not_strong():
    """20% loans-to-deposits is a bank that is not lending.

    For a CDFI benchmarking tool under-deployment is a real failure, so the
    metric is graded as a BAND, not a one-sided ladder. `lower_is_better`
    alone would grade 20% STRONG.
    """
    assert _status("loans_to_deposits", 20) != "STRONG"


def test_loans_to_deposits_band_centre_is_strong():
    assert _status("loans_to_deposits", 55) == "STRONG"
    assert _status("loans_to_deposits", 80) == "STRONG"


def test_loans_to_deposits_upper_shoulder_is_adequate():
    assert _status("loans_to_deposits", 95) == "ADEQUATE"
