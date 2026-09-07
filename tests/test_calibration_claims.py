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

TWO KINDS OF ASSERTION LIVE HERE, AND THEY HAVE DIFFERENT CONTEXTS
------------------------------------------------------------------
* The grading assertions read NO files. They put the pinned number through the
  installed package's own `BenchmarkResult.status`. They run everywhere,
  unconditionally, including in `test-wheel` and `test-sdist`.
* The three doc assertions read REPO PROSE — README.md and CHANGELOG.md — which
  an installed-artifact test directory does not have in full. Each declares the
  documents IT opens and is all-or-nothing over THAT set (`_needs` below), so
  the README gate still runs in `test-sdist`, where README.md is present.

Until this fix they did not share anything. Each one carried its own
`if not path.exists(): pytest.skip(...)`, except `test_the_readme_does_not_assert
_the_retracted_claim`, which carried no guard at all. Run 34002310309 shows both
halves of what that costs, in the same eight jobs:

* the unguarded one raised FileNotFoundError on README.md in `test-wheel`;
* the guarded ones went GREEN in `test-wheel` having read neither document.

The second is the worse outcome, and it is why the fix is not "add the missing
`exists()` check to the third one". A gate that skips the surfaces it cannot
reach and passes on the rest reports success over a fraction of its coverage —
the silent narrowing this suite has a standing rule against. All-or-nothing over
each gate's own coverage set, or the pass means nothing.
"""
import pytest

from cdfibenchmark.data.schema import BENCHMARKS, BenchmarkResult

from . import _layout as layout

ROOT = layout.ROOT

#: Every repo-prose document any gate in this module opens, resolved once.
#: Scoped to these two files, not to the repo root as a whole: a gate should
#: require what it reads and no more, or the reason it prints when it skips is
#: not the truth about why it skipped.
_DOC_SURFACES = {
    "README.md": layout.SURFACES["README.md"],
    "CHANGELOG.md": layout.SURFACES["CHANGELOG.md"],
}


#: This module already had the ruling the other two lacked: the unit that must
#: not half-run is a GATE'S OWN COVERAGE SET, not the module. What it did NOT
#: have was a way to tell a deletion from an omission the distribution declares
#: -- it carried its own third copy of
#:
#:     _IS_REPO_TREE = (ROOT / "cdfibenchmark").is_dir() or (ROOT / ".git").exists()
#:
#: which answers "is a source tree present" and was then used to answer "should
#: this particular surface be here". Both questions now live in
#: `tests/_layout.py`, once, and `_needs` is `layout.needs` -- so a fix to that
#: distinction reaches all three modules instead of one.
#:
#: Neither README.md nor CHANGELOG.md is ever legitimately absent from a
#: distribution (MANIFEST.in `include`s both), so nothing here is ever excused
#: by a declaration; the change is that the RULE is now shared rather than that
#: this module's behaviour moves.
_needs = layout.needs


#: Named once so the decorators below read as declarations of what each gate
#: opens. The grading assertions carry none of these: they read no files and
#: must run against the shipped artifact.
_needs_readme = _needs("README.md")
_needs_changelog = _needs("CHANGELOG.md")
_needs_both_docs = _needs("README.md", "CHANGELOG.md")


def test_every_document_this_module_reads_is_present_in_a_repo_tree():
    """A deleted document must be RED by name, never a skip.

    The `_needs` gates already go red on a deletion rather than skipping, but
    they do it by raising FileNotFoundError from inside whichever assertion
    happens to open the file first. This says it in one place, in a sentence,
    and matches `test_bound_claims.py` and `test_package_claims.py` so all three
    repo-prose modules answer a deletion the same way.

    Skipped in an artifact run, where there is no repository and nothing was
    deleted.
    """
    if not layout.IS_REPO_TREE:
        pytest.skip("no source tree here; nothing was deleted, see _needs")
    _, _declared, missing = layout.classify(*sorted(_DOC_SURFACES))
    assert not missing, (
        f"a source tree is present here (cdfibenchmark/ or .git/) but "
        f"{', '.join(missing)} is unreadable, and nothing declares it absent. "
        f"That is a deleted or moved "
        f"document, not an installed-artifact run, so it fails instead of "
        f"skipping."
    )

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


@_needs_both_docs
@pytest.mark.parametrize("doc", ["README.md", "CHANGELOG.md"])
def test_the_shipped_docs_state_the_pinned_measurement(doc):
    """The pinned claim and the prose must not drift apart.

    The docstring here used to claim "Both files ship in the sdist (MANIFEST.in
    includes them), so this runs in the `test-sdist` job as well". Half true and
    the wrong half: both are IN the tarball, but test-sdist copies only
    README.md into the directory it runs from, so CHANGELOG.md was never present
    and this test's CHANGELOG.md leg silently skipped in that job for its whole
    life. Being in the tarball is not the same as being in the run directory.

    Now it does not skip one leg and run the other — see `_needs`.
    """
    path = _DOC_SURFACES[doc]
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


@_needs_readme
def test_the_readme_does_not_assert_the_retracted_claim():
    """The README is the LIVE claim surface — it renders on PyPI.

    The retracted figures must not appear there at all: there is no context in
    which a current calibration paragraph should cite a median measured over a
    peer group of the 50 largest banks in the window.
    """
    text = _DOC_SURFACES["README.md"].read_text()

    assert "91.12" not in text, (
        "README still cites the 91.12% median, which was measured over a peer "
        "group of the 50 LARGEST banks in the window (B1) and grades ADEQUATE, "
        "not WEAK as the retracted sentence claimed"
    )
    assert "inside the WEAK zone" not in text, (
        "README still claims a median sits inside the WEAK zone"
    )


@_needs_changelog
def test_the_changelog_may_quote_the_false_claim_only_to_retract_it():
    """A changelog SHOULD name what it retracted — but must mark it false.

    This is the distinction the gate has to draw: quoting a false sentence in
    order to correct it is the changelog doing its job, while restating it
    unmarked is the defect coming back. The first version of this gate banned
    the string outright and failed on this repository's own retraction entry.
    """
    text = _DOC_SURFACES["CHANGELOG.md"].read_text()

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
