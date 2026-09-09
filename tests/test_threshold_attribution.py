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
    """A non-HOUSE source must actually point at something checkable.

    THE LOOP IS GUARDED BECAUSE IT CAN EMPTY, AND IT IS ONE EDIT FROM EMPTY.
    Exactly one entry in BENCHMARKS is cited, so the filter below yields one
    item; if that citation ever became "HOUSE" the loop would run zero times and
    this gate would pass having checked nothing -- the same defect class as the
    report-disclosure gate this release fixed, in the module that exists to
    police attribution. Measured, python3.10, setting tier1_ratio's `source` to
    `"HOUSE"` in schema.py:

        PYTHONPATH=. pytest tests -q -k cited_thresholds_name_an_instrument
            (before this guard)  ->  1 passed, 24 deselected
            (after  this guard)  ->  1 failed, 24 deselected

    That mutation was already red elsewhere -- `test_cited_threshold_shows_its_citation`
    and two gates in this module gave `3 failed, 329 passed, 1 skipped` on the
    full suite -- so this was a latent vacuity rather than an open hole. It is
    fixed anyway, because "a gate that cannot be made to fail is a defect in the
    gate" is this suite's rule and coverage sitting in another module is not the
    same as this gate working.
    """
    cited = {metric: cfg["source"] for metric, cfg in BENCHMARKS.items()
             if cfg.get("source") and cfg["source"] != "HOUSE"}
    assert cited, (
        "no entry in BENCHMARKS declares a non-HOUSE source, so this gate has "
        "nothing to check and would pass while certifying nothing. Either every "
        "threshold really is a house rule of thumb -- in which case delete this "
        "gate deliberately and say so -- or a citation was dropped."
    )
    for metric, src in sorted(cited.items()):
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


# ── F2 (0.3.2): a threshold may not be applied to periods before it existed ──
#
# `_CBLR` read, in one flat string:
#
#     "12 CFR 324.12 (CBLR qualifying, lowered 9%->8% eff. 2026-07-01)"
#
# so the 0.3.1 artifact graded a 20260630 report against a level its own prose
# dates to 2026-07-01 -- the day AFTER the period. tier1_ratio is, by this
# module's whole subject, the ONLY cited entry; every other threshold is
# correctly stamped HOUSE. A HOUSE number has no effective date to get wrong.
#
# DERIVED FROM PRIMARY TEXT ON 2026-09-09, not from the string being audited:
#   * eCFR 12 CFR 324.12(a)(1), snapshot 2026-06-30 -> "greater than 9 percent"
#   * eCFR 12 CFR 324.12(a)(1), snapshot 2026-07-01 -> "greater than 8 percent"
#   * the source credit gains "91 FR 22989, Apr. 29, 2026" at that boundary
#   * Federal Register doc 2026-08298, "Regulatory Capital Rule: Community Bank
#     Leverage Ratio Framework", 91 FR 22973, published 2026-04-29,
#     effective_on 2026-07-01
#   * 12 CFR 324.403(b)(1)(i)(D) reads 5.0 percent at BOTH snapshots, so the
#     PCA leg is period-invariant across this window and only the CBLR leg
#     needs resolving.
#
# The change is real and the date in the string is right. What was wrong is
# applying it to a period before it took effect. No grade moves on the settle
# read's own subject (13.20% is strong either way); it moves for any bank
# between 8% and 9% at a report date before 2026-07-01, which is ordinary.
from cdfibenchmark.data.schema import (
    InstitutionProfile, benchmark_for, CBLR_LEVELS, _PCA_LEVEL,
)
import re
from cdfibenchmark.metrics.calculator import benchmark_institution
from cdfibenchmark.report.generator import generate_report
from cdfibenchmark.peers.selector import PeerGroup, HOUSE_MAX_PEERS


def _cblr_bank(cert, repdte, tier1):
    return InstitutionProfile(
        cert=cert, name=f"Bank {cert}", city="Oakland", state="CA",
        report_date=repdte,
        total_assets=655_000, total_deposits=520_000, net_loans=380_000,
        net_income=1_950, interest_income=28_000, interest_expense=8_000,
        non_interest_income=3_500, non_interest_expense=22_000,
        total_equity=48_000, tier1_ratio=tier1,
        gross_loans=390_000, non_current_loans=5_850,
        loan_loss_allowance=7_800,
    )


def _cblr_status(repdte, tier1):
    subject = _cblr_bank(1, repdte, tier1)
    peers = PeerGroup(
        [_cblr_bank(9000 + i, repdte, 11.0) for i in range(20)],
        min_peers=10, target_report_date=repdte,
        subject_assets=subject.total_assets, universe_size=621,
        asset_tolerance=0.5, max_peers=HOUSE_MAX_PEERS,
    )
    result = next(r for r in benchmark_institution(subject, peers)
                  if r.metric == "tier1_ratio")
    return result.status, generate_report(subject, peers)


@pytest.mark.parametrize("repdte,expected", [
    ("20251231", "ADEQUATE"),   # comfortably before the rule
    ("20260331", "ADEQUATE"),
    ("20260630", "ADEQUATE"),   # the settle read's own period; eff. date - 1 day
    ("20260701", "STRONG"),     # the effective date itself
    ("20260930", "STRONG"),
    ("20261231", "STRONG"),
])
def test_the_cblr_band_in_force_at_the_report_date_is_the_one_that_grades(
        repdte, expected):
    """8.5% leverage: STRONG under the 8% band, ADEQUATE under the 9% one.

    This is the whole finding in one row. Before 0.3.2 every date here graded
    STRONG, including the four that predate the rule.
    """
    status, _ = _cblr_status(repdte, 8.5)
    assert status == expected, (
        f"a bank at 8.5% leverage filing at {repdte} graded {status}; the CBLR "
        f"qualifying level in force at that date makes it {expected}"
    )


def test_the_pre_effective_benchmark_line_does_not_present_the_new_level():
    """A reader at 20260630 must not be shown 8% as the applicable level."""
    _, report = _cblr_status("20260630", 8.5)
    block = report[report.index("### Tier 1 Leverage Ratio"):]
    block = block[:block.index("\n###")] if "\n###" in block else block
    assert "Strong >= 9%" in block, (
        f"the pre-effective report grades against a level other than 9%:\n{block}"
    )
    assert "Strong >= 8%" not in block, (
        f"the 8% level is presented as applicable at a period before it took "
        f"effect:\n{block}"
    )


def test_the_benchmark_line_renders_the_effective_date_of_the_band_in_force():
    """A cited threshold must say which period it is the threshold FOR."""
    for repdte in ("20260630", "20260930"):
        _, report = _cblr_status(repdte, 13.2)
        block = report[report.index("### Tier 1 Leverage Ratio"):]
        block = block[:block.index("\n###")] if "\n###" in block else block
        assert "2026-07-01" in block, (
            f"{repdte}: the Tier 1 benchmark line does not carry the effective "
            f"date that separates the two bands:\n{block}"
        )
        assert "12 CFR 324.12" in block and "324.403(b)(1)" in block, (
            f"{repdte}: a citation was dropped:\n{block}"
        )


def test_benchmark_for_resolves_only_the_period_dependent_entry():
    """Every HOUSE threshold is period-invariant; only the CFR one moves."""
    for metric in sorted(BENCHMARKS):
        early = benchmark_for(metric, "20200331")
        late = benchmark_for(metric, "20261231")
        if metric == "tier1_ratio":
            assert early["good"] == 9 and late["good"] == 8, (
                f"tier1_ratio did not resolve by period: "
                f"{early['good']} / {late['good']}"
            )
            assert early["source"] != late["source"], (
                "the two bands render the same citation, so a reader cannot "
                "tell which one graded them"
            )
        else:
            assert early == late == BENCHMARKS[metric], (
                f"{metric} is a HOUSE threshold with no effective date, but "
                f"benchmark_for changed it by period"
            )


def test_an_unknown_report_date_says_so_rather_than_picking_silently():
    """A level with an effective date cannot be checked against no date."""
    cfg = benchmark_for("tier1_ratio", None)
    assert "period" in cfg["source"].lower() or "date" in cfg["source"].lower(), (
        f"an unknown report date resolved to a band without saying so: "
        f"{cfg['source']!r}"
    )


def test_the_benchmarks_default_is_the_current_cblr_level():
    """`BENCHMARKS` stays readable directly, so its default must not go stale.

    A caller who reads `BENCHMARKS["tier1_ratio"]["good"]` without a period
    gets current law. When the next CBLR change lands, appending a row to
    `CBLR_LEVELS` must move this too -- and it does, because the entry is
    built from `CBLR_LEVELS[-1]` rather than hand-typed. This gate is what
    stops someone re-typing the number.
    """
    assert BENCHMARKS["tier1_ratio"]["good"] == CBLR_LEVELS[-1][1]
    assert BENCHMARKS["tier1_ratio"]["warning"] == _PCA_LEVEL
    assert BENCHMARKS["tier1_ratio"] == benchmark_for("tier1_ratio", None), (
        "the no-period resolution and the BENCHMARKS default have drifted apart"
    )


def test_the_cblr_period_table_is_ordered_and_uses_repdte_shaped_dates():
    """`_cblr_at` compares REPDTE strings, which is only correct if they sort."""
    dates = [eff for eff, _, _ in CBLR_LEVELS]
    assert dates == sorted(dates), f"CBLR_LEVELS is not oldest-first: {dates}"
    for eff, level, rule in CBLR_LEVELS:
        assert re.fullmatch(r"\d{8}", eff), (
            f"{eff!r} is not a zero-padded YYYYMMDD, so the string comparison "
            f"in _cblr_at is not a date comparison"
        )
        assert level > 0 and rule


def test_the_source_string_is_not_hand_typed_anywhere():
    """The 0.3.1 defect was a flat string stating a band and a date together.

    Nothing may re-introduce one: the citation is built from `CBLR_LEVELS`.
    """
    source = pathlib.Path(schema.__file__).read_text()
    body = source[source.index("BENCHMARKS = {"):]
    assert "9%->8%" not in body, (
        "the flat two-band citation string is back inside BENCHMARKS"
    )


def test_the_result_cites_the_same_band_it_was_graded_against():
    """Found by mutation, not by design: the two resolutions were independent.

    `status` resolves the band from `BenchmarkResult.report_date`; `source` is
    handed in by `benchmark_institution` from its own `benchmark_for` call.
    Swapping the calculator's call to `benchmark_for(metric, None)` left every
    grade correct and every gate green while `source` -- which `summary_table`
    exposes as `threshold_source`, and which the Benchmark line is built from
    -- cited the wrong band. A grade and its stated warrant must not be able to
    come from different periods.
    """
    for repdte in ("20251231", "20260630", "20260701", "20261231"):
        subject = _cblr_bank(1, repdte, 8.5)
        peers = PeerGroup(
            [_cblr_bank(9000 + i, repdte, 11.0) for i in range(20)],
            min_peers=10, target_report_date=repdte,
            subject_assets=subject.total_assets, universe_size=621,
            asset_tolerance=0.5, max_peers=HOUSE_MAX_PEERS,
        )
        for result in benchmark_institution(subject, peers):
            expected = benchmark_for(result.metric, repdte)
            assert result.source == expected["source"], (
                f"{repdte} {result.metric}: graded against the band for "
                f"{result.report_date!r} but cites {result.source!r}, which is "
                f"not that band's citation"
            )
            assert result.report_date == repdte, (
                f"{result.metric} lost the period it was graded for"
            )


def test_summary_table_reports_the_period_resolved_threshold_source():
    """The DataFrame surface carries the same warrant the report does."""
    from cdfibenchmark.report.generator import summary_table
    repdte = "20260630"
    subject = _cblr_bank(1, repdte, 8.5)
    peers = PeerGroup(
        [_cblr_bank(9000 + i, repdte, 11.0) for i in range(20)],
        min_peers=10, target_report_date=repdte,
        subject_assets=subject.total_assets, universe_size=621,
        asset_tolerance=0.5, max_peers=HOUSE_MAX_PEERS,
    )
    df = summary_table(subject, peers)
    row = df[df["metric"] == "Tier 1 Leverage Ratio"].iloc[0]
    assert "9%" in row["threshold_source"], (
        f"summary_table cites a band other than the one in force at {repdte}: "
        f"{row['threshold_source']!r}"
    )
    assert row["status"] == "ADEQUATE"
