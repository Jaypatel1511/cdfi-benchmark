"""Every graded threshold must declare where it came from.

0.2.1 existed to remove a metric that was labelled and graded as something it
was not. The same failure has a threshold-shaped form: a house rule-of-thumb
rendered as though it were a supervisory standard. `tier1_ratio` cites
12 CFR 324; before 0.3.0 the other seven entries cited nothing at all while
rendering beside it in the same "Benchmark:" column of the same report.

The rule: an entry either carries a real citation or is explicitly marked
HOUSE. There is no third state, and "unmarked" must never be readable as
"standard".
"""
import ast
import pathlib

import pytest
from cdfibenchmark.data import schema
from cdfibenchmark.data.schema import BENCHMARKS


@pytest.mark.parametrize("metric", sorted(BENCHMARKS))
def test_every_threshold_declares_a_source(metric):
    cfg = BENCHMARKS[metric]
    assert "source" in cfg, (
        f"{metric} grades against good={cfg.get('good')} / "
        f"warning={cfg.get('warning')} but declares no source. An unsourced "
        f"threshold rendered beside a cited one reads as a standard."
    )
    assert cfg["source"], f"{metric} has an empty source"


def _benchmarks_ast():
    """The BENCHMARKS assignment as it is WRITTEN, not as it evaluates.

    ast.walk, not tree.body: this portfolio has been bitten by `.body` finding
    0 of 2 assignments when the target was nested.
    """
    tree = ast.parse(pathlib.Path(schema.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BENCHMARKS":
                    return node.value
    raise AssertionError("BENCHMARKS assignment not found in schema source")


def _entry_nodes(metric):
    """The dict node for one BENCHMARKS entry, keyed by metric name."""
    dict_node = _benchmarks_ast()
    for key, value in zip(dict_node.keys, dict_node.values):
        if isinstance(key, ast.Constant) and key.value == metric:
            assert isinstance(value, ast.Dict), f"{metric} is not a dict literal"
            return {k.value: v for k, v in zip(value.keys, value.values)
                    if isinstance(k, ast.Constant)}
    raise AssertionError(f"{metric} not found in the BENCHMARKS source")


@pytest.mark.parametrize("metric", sorted(BENCHMARKS))
def test_house_thresholds_are_named_house_at_the_constant(metric):
    """A HOUSE threshold's numbers must come from HOUSE_-prefixed constants.

    Naming carries the attribution to every call site, so a house number
    cannot be quoted as a standard without its own identifier contradicting
    the sentence it is quoted in.

    Asserted by AST over the SOURCE. The previous version of this gate stated
    exactly the invariant above and then checked `cfg[key] in house_values` — a
    set of VALUES. Any literal equal to any HOUSE_ constant satisfied that, so
    replacing `HOUSE_ROAA_GOOD, HOUSE_ROAA_WARNING` with bare `1.0, 0.5` left
    the suite at 199 passed, 2 skipped. The gate could not see the thing its
    own docstring names: whether the ATTRIBUTION is present in the code.
    """
    cfg = BENCHMARKS[metric]
    if cfg.get("source") != "HOUSE":
        pytest.skip(f"{metric} is cited, not house")

    entry = _entry_nodes(metric)
    for key in ("good", "warning", "floor"):
        if cfg.get(key) is None:
            continue
        node = entry.get(key)
        assert node is not None, f"{metric}[{key}] missing from the source dict"
        assert isinstance(node, ast.Name), (
            f"{metric}[{key}] is written as {ast.dump(node)} — a bare literal "
            f"on a HOUSE threshold. It must reference a HOUSE_-prefixed "
            f"constant so the attribution travels to every call site."
        )
        assert node.id.startswith("HOUSE_"), (
            f"{metric}[{key}] references {node.id!r}, which is not a "
            f"HOUSE_-prefixed constant"
        )


def test_cited_thresholds_name_an_instrument():
    """A non-HOUSE source must actually point at something checkable."""
    for metric, cfg in BENCHMARKS.items():
        src = cfg.get("source")
        if src and src != "HOUSE":
            assert any(tok in src for tok in ("CFR", "USC", "FDIC", "FFIEC")), (
                f"{metric} declares source {src!r} which names no instrument"
            )


#: Which HOUSE_ prefix each metric's thresholds must come from. Kept explicit
#: because the mapping is not mechanical (loans_to_deposits -> LTD,
#: efficiency_ratio -> EFFICIENCY), and a metric missing from this map fails
#: rather than silently skipping.
_HOUSE_PREFIX = {
    "nim":               "HOUSE_NIM_",
    "efficiency_ratio":  "HOUSE_EFFICIENCY_",
    "roaa":              "HOUSE_ROAA_",
    "roae":              "HOUSE_ROAE_",
    "loans_to_deposits": "HOUSE_LTD_",
    "npl_ratio":         "HOUSE_NPL_",
    "reserve_coverage":  "HOUSE_RESERVE_COVERAGE_",
}


@pytest.mark.parametrize("metric", sorted(BENCHMARKS))
def test_house_thresholds_reference_their_own_metrics_constant(metric):
    """A HOUSE threshold must name the constant belonging to ITS metric.

    Checking only the `HOUSE_` prefix leaves a real hole: `"roaa": {"good":
    HOUSE_NPL_GOOD}` is a HOUSE_-prefixed Name, carries the attribution, and
    happens to be numerically identical (both 1.0) — so it survives both the
    value check and the prefix check while grading return-on-assets against an
    asset-quality rule of thumb. That is this package's founding defect
    (a number labelled as something it is not) in threshold form.
    """
    cfg = BENCHMARKS[metric]
    if cfg.get("source") != "HOUSE":
        pytest.skip(f"{metric} is cited, not house")

    prefix = _HOUSE_PREFIX.get(metric)
    assert prefix is not None, (
        f"{metric} is a HOUSE threshold with no expected constant prefix "
        f"registered in _HOUSE_PREFIX — add it rather than skipping it"
    )

    entry = _entry_nodes(metric)
    for key in ("good", "warning", "floor"):
        if cfg.get(key) is None:
            continue
        node = entry[key]
        assert isinstance(node, ast.Name) and node.id.startswith(prefix), (
            f"{metric}[{key}] references "
            f"{getattr(node, 'id', ast.dump(node))!r}, which does not belong "
            f"to {metric} (expected a {prefix}* constant)"
        )
