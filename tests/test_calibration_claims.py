"""A calibration note must be true of the artifact it is rendered in.

B2. README.md carried, inside the paragraph justifying this round's headline
design decision, on a page that renders on PyPI:

    "...this band grades 22 of 50 WEAK, with a peer median of 91.12% sitting
     inside the WEAK zone."

The counts were exact. The zone claim was FALSE. The band is WEAK below 50 or
above 95, and 91.12 satisfies `80 < v <= 95` -> ADEQUATE. Nothing checked it,
and `grep -rn "91.12\\|22 of 50" tests/` returned nothing. The same sentence had
also been copied into CHANGELOG.md, so the defect shipped in two places while
the audit named one.

This gate pins the measurement and asserts the stated median grades to the
stated status THROUGH THE PACKAGE'S OWN `BenchmarkResult.status`. A calibration
note whose zone claim contradicts the constants then cannot ship. It needs no
network: the claim is data, and the grading is the package's.

The measurement itself was re-derived on 2026-09-05 over the peer group B1
produces (the 50 banks NEAREST CERT 34352 in assets), because the previous
numbers described a cohort ~1.4x the subject's size and did not survive that
fix: 22 of 50 WEAK with a 91.12% median became 13 of 50 with an 85.19% median.
"""
import pathlib

import pytest

from cdfibenchmark.data.schema import BENCHMARKS, BenchmarkResult

#: The calibration measurement exactly as the README and CHANGELOG state it.
#: Pinned with everything needed to re-run it.
LTD_CALIBRATION = {
    "cert": 34352,
    "report_date": "20260630",
    "retrieved": "2026-09-05",
    "peer_count": 50,
    "universe": 763,
    "weak_total": 13,
    "weak_above_warning": 11,
    "weak_below_floor": 2,
    "peer_median": 85.19,
    "peer_median_status": "ADEQUATE",
}


def _grade(value):
    cfg = BENCHMARKS["loans_to_deposits"]
    return BenchmarkResult(
        metric="loans_to_deposits", institution_value=value,
        peer_median=None, peer_25th=None, peer_75th=None, peer_count=0,
        lower_is_better=cfg.get("lower_is_better", False),
    ).status


def test_the_stated_peer_median_grades_to_the_stated_status():
    """The assertion that would have caught the shipped falsehood.

    Red-proving this is one edit: set `peer_median_status` to "WEAK", which is
    what the README said for ten weeks.
    """
    claim = LTD_CALIBRATION
    actual = _grade(claim["peer_median"])
    assert actual == claim["peer_median_status"], (
        f"the calibration note says a peer median of {claim['peer_median']}% "
        f"grades {claim['peer_median_status']}, but this package's own "
        f"BenchmarkResult.status grades it {actual}. The note is not true of "
        f"the tool it documents."
    )


def test_the_weak_counts_are_internally_consistent():
    claim = LTD_CALIBRATION
    assert (claim["weak_above_warning"] + claim["weak_below_floor"]
            == claim["weak_total"]), "WEAK tail does not decompose to its total"
    assert claim["weak_total"] <= claim["peer_count"]


def test_the_stated_weak_boundaries_actually_grade_weak():
    """The claim is that the WEAK tail is mostly the funding-strain edge.

    Both edges must really be WEAK, or the sentence describing them is telling
    the reader about a band the code does not implement.
    """
    cfg = BENCHMARKS["loans_to_deposits"]
    assert _grade(cfg["warning"] + 0.01) == "WEAK", "above the band is not WEAK"
    assert _grade(cfg["floor"] - 0.01) == "WEAK", "below the floor is not WEAK"
    assert _grade(cfg["floor"]) != "WEAK", "the floor itself must be inside the band"
    assert _grade(cfg["warning"]) != "WEAK", "the warning bound must be inside the band"


@pytest.mark.parametrize("doc", ["README.md", "CHANGELOG.md"])
def test_the_shipped_docs_state_the_pinned_measurement(doc):
    """The pinned claim and the prose must not drift apart.

    Both files ship in the sdist (MANIFEST.in includes them), so this runs in
    the `test-sdist` job as well as the matrix `test` job — it is not a gate
    with a single execution site.
    """
    path = pathlib.Path(__file__).resolve().parent.parent / doc
    if not path.exists():
        pytest.skip(f"{doc} not present in this install")
    text = path.read_text()
    claim = LTD_CALIBRATION

    assert f"{claim['weak_total']} of {claim['peer_count']} WEAK" in text, (
        f"{doc} does not state the pinned WEAK count"
    )
    assert str(claim["peer_median"]) in text, (
        f"{doc} does not state the pinned peer median {claim['peer_median']}%"
    )
    assert claim["peer_median_status"] in text, (
        f"{doc} does not state that the median grades "
        f"{claim['peer_median_status']}"
    )


def test_the_readme_does_not_assert_the_retracted_claim():
    """The README is the LIVE claim surface — it renders on PyPI.

    The retracted figures must not appear there at all: there is no context in
    which a current calibration paragraph should cite a median measured over a
    peer group of the 50 largest banks in the window.
    """
    text = (pathlib.Path(__file__).resolve().parent.parent / "README.md").read_text()

    assert "91.12" not in text, (
        "README still cites the 91.12% median, which was measured over a peer "
        "group of the 50 LARGEST banks in the window (B1) and grades ADEQUATE, "
        "not WEAK as the retracted sentence claimed"
    )
    assert "inside the WEAK zone" not in text, (
        "README still claims a median sits inside the WEAK zone"
    )


def test_the_changelog_may_quote_the_false_claim_only_to_retract_it():
    """A changelog SHOULD name what it retracted — but must mark it false.

    This is the distinction the gate has to draw: quoting a false sentence in
    order to correct it is the changelog doing its job, while restating it
    unmarked is the defect coming back. The first version of this gate banned
    the string outright and failed on this repository's own retraction entry.
    """
    path = pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    if not path.exists():
        pytest.skip("CHANGELOG.md not present in this install")
    text = path.read_text()

    if "91.12" not in text:
        return

    # Every mention must sit inside an entry that calls the claim false and
    # states the corrected status.
    for para in text.split("\n\n"):
        if "91.12" not in para:
            continue
        window = text[max(0, text.index(para) - 400):
                      text.index(para) + len(para) + 900]
        assert "false" in window.lower(), (
            "CHANGELOG cites the 91.12% median without marking the claim false"
        )
        assert "ADEQUATE" in window, (
            "CHANGELOG cites the 91.12% median without stating that it "
            "actually grades ADEQUATE"
        )
