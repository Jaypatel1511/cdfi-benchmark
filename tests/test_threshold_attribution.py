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


@pytest.mark.parametrize("metric", sorted(BENCHMARKS))
def test_house_thresholds_are_named_house_at_the_constant(metric):
    """A HOUSE threshold's numbers must come from HOUSE_-prefixed constants.

    Naming carries the attribution to every call site, so a house number
    cannot be quoted as a standard without its own identifier contradicting
    the sentence it is quoted in.
    """
    cfg = BENCHMARKS[metric]
    if cfg.get("source") != "HOUSE":
        pytest.skip(f"{metric} is cited, not house")

    house_values = {
        v for name, v in vars(schema).items()
        if name.startswith("HOUSE_") and isinstance(v, (int, float))
    }
    for key in ("good", "warning", "floor"):
        if cfg.get(key) is not None:
            assert cfg[key] in house_values, (
                f"{metric}[{key}]={cfg[key]} is a bare literal on a HOUSE "
                f"threshold — it must come from a HOUSE_-prefixed constant"
            )


def test_cited_thresholds_name_an_instrument():
    """A non-HOUSE source must actually point at something checkable."""
    for metric, cfg in BENCHMARKS.items():
        src = cfg.get("source")
        if src and src != "HOUSE":
            assert any(tok in src for tok in ("CFR", "USC", "FDIC", "FFIEC")), (
                f"{metric} declares source {src!r} which names no instrument"
            )
