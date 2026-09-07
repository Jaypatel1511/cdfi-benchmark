"""Gates on what the package CLAIMS about itself, on every shipped surface.

The retired-claim class: a corrected README does not correct the PyPI
description rendered above it, or a docstring, or a fixture name. 0.2.1 removed
CET1 from the code and the README and left it in pyproject.toml's `description`,
which is exactly the text PyPI shows first.

The shipped-inputs class: the README's Quickstart said

    # Pull call report data for Broadway Federal Bank (CERT 57542)
    institution = get_financials(cert=57542)

CERT 57542 is Toyota Financial Savings Bank, Henderson NV, $16.8B — verified
against the live FDIC /institutions endpoint on 2026-08-30. Broadway Federal is
CERT 30306 and is ACTIVE:0. That block is not sample data; it is a LIVE API call
that returns a real, correct, graded report about an entirely different bank
from the one named beside it.

WHY THIS MODULE NO LONGER SKIPS AS A UNIT
-----------------------------------------
It used to. `_REQUIRED_SURFACES` was all-or-nothing over the whole module, on
the reasoning that a gate which quietly drops the surfaces it cannot reach goes
green while scanning a fraction of what it scans locally. That reasoning is
right about the CERT SCAN and wrong about everything else here, and both halves
were measured on 0.3.0:

* At the TARBALL ROOT the module ran and went RED, because `examples/` is pruned
  from the sdist deliberately (MANIFEST.in says so in words) while
  `cdfibenchmark/` ships — so the tarball answered "repository tree" and the
  module then demanded a directory the tarball is designed never to contain.
  Measured: `2 failed, 319 passed, 3 skipped`. That is how 0.3.0 shipped with
  its own suite red in the layout README.md:271 documents.

* In the CONSTRUCTED sdist test directory the module skipped ALL THIRTEEN of its
  gates — including eight that read nothing but README.md and pyproject.toml,
  BOTH OF WHICH release.yml copies into that directory. Measured on the 0.3.0
  tarball: `test_package_claims: {'skip': 13}`. The module was protecting
  against silent narrowing by narrowing to zero.

So the unit that must not half-run is a GATE'S OWN COVERAGE SET, not the module
— the ruling `test_calibration_claims.py` already reached and this module never
adopted. Each gate below declares the surfaces it opens and skips only for
those. The cert scan, which really is a sweep over many surfaces, is
parametrized BY surface, so a surface it cannot reach is a visible skip with a
named reason rather than a shrunken scan inside a passing test.

Whether an absence is a deletion or a declared omission is `tests/_layout.py`.
"""
import re
from pathlib import Path

import pytest

from . import _layout as layout

try:                      # 3.11+
    import tomllib
except ModuleNotFoundError:
    try:                  # 3.9/3.10 with the backport available
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

ROOT = layout.ROOT
README = layout.SURFACES["README.md"]
PYPROJECT = layout.SURFACES["pyproject.toml"]


def _project_meta() -> dict:
    """The [project] table of pyproject.toml, on every supported Python.

    The CI matrix runs 3.9 and 3.10, where `tomllib` does not exist. Skipping
    there would leave these gates vacuous on half the matrix -- the exact
    failure mode release.yml was written to close. So when no TOML parser is
    available we fall back to a deliberately narrow reader for the two scalar
    string keys these gates need, and it RAISES rather than returning empty if
    it cannot find them. An unparsable pyproject fails the gate; it never
    silently passes it.
    """
    text = PYPROJECT.read_text()
    if tomllib is not None:
        return tomllib.loads(text)["project"]

    in_project, out = False, {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if not in_project:
            continue
        m = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*"(.*)"\s*$', stripped)
        if m:
            out[m.group(1)] = m.group(2)
    for required in ("name", "version", "description"):
        if required not in out:
            raise AssertionError(
                f"could not read [project].{required} from pyproject.toml; "
                f"these gates must not pass without reading it"
            )
    return out


#: Every surface this module reads, across all of its gates. Membership here is
#: not by itself a requirement: a surface is required WHERE IT IS READABLE, and
#: `layout.require` decides what an absence means -- deletion (red, by name) or
#: an omission the distribution declares (skip, by name, quoting the
#: declaration).
_REQUIRED_SURFACES = (
    "README.md", "pyproject.toml", "CHANGELOG.md", "CONTRIBUTING.md",
    "setup.py", "cdfibenchmark/", "tests/", "examples/",
)

#: (directory, glob) for the surfaces that are trees rather than single files.
_SURFACE_GLOBS = {
    "cdfibenchmark/": ("cdfibenchmark", "*.py"),
    "tests/": ("tests", "*.py"),
    "examples/": ("examples", "*.ipynb"),
}

#: The surfaces the cert scan sweeps: everything above EXCEPT CHANGELOG.md.
#:
#: The changelog is excluded because it must be able to DESCRIBE the false
#: binding in order to record it -- the same allowance
#: `test_calibration_claims.py` makes for the 91.12 retraction. It is still a
#: required surface (deleting it is red); it is simply not a surface where
#: naming the binding is a defect.
_CERT_SCAN_SURFACES = tuple(s for s in _REQUIRED_SURFACES if s != "CHANGELOG.md")


def _read_surface(name: str) -> dict:
    """Every file of one surface, keyed by repo-relative path.

    Not `if p.exists()` per file. The caller has already been through
    `layout.require`, so reaching here means the surface is readable; a silent
    per-file skip at THIS level would shrink the scan without shrinking the
    pass.
    """
    if name not in _SURFACE_GLOBS:
        path = layout.SURFACES[name]
        return {name: path.read_text()}
    sub, pattern = _SURFACE_GLOBS[name]
    d = ROOT / sub
    return {str(p.relative_to(ROOT)): p.read_text()
            for p in sorted(d.rglob(pattern))}


def test_every_surface_this_module_reads_is_present_or_declared_absent():
    """A deleted surface must be RED here, never a skip.

    The distinction a bare `exists()` cannot draw: "examples/ is absent" is true
    both when someone deleted it and when we are standing in the sdist that
    prunes it on purpose. Only the first may be red, and only an artifact that
    states its own contents may excuse the second -- see `tests/_layout.py`.

    Skipped where there is no source tree, because nothing was deleted there.
    """
    if not layout.IS_REPO_TREE:
        pytest.skip(
            "no source tree here (no cdfibenchmark/, no .git); nothing was "
            "deleted, and each gate declares its own surfaces via layout.require"
        )
    _, declared, undeclared = layout.classify(*_REQUIRED_SURFACES)
    assert not undeclared, (
        f"a source tree is present here (cdfibenchmark/ or .git/) but these "
        f"surfaces are unreadable: {', '.join(undeclared)}. Nothing declares "
        f"them absent, so that is a deleted or moved surface, not an "
        f"installed-artifact run, and it fails instead of skipping. "
        f"(Declared absent, and therefore fine: "
        f"{', '.join(sorted(declared)) or 'nothing'}.)"
    )


def test_only_a_declared_omission_is_ever_excused():
    """The vacuity guard on the excusing mechanism itself.

    `absence_is_declared` is the one thing standing between "skip because the
    tarball prunes it" and "skip because anything missing is fine", and a
    version of it that returned a reason for everything would turn every gate
    in this module into a silent pass. So pin what it must and must not excuse,
    in whatever layout this happens to be running in.

    Reads no files, so it runs in EVERY layout -- checkout, tarball root,
    git archive, constructed sdist dir, wheel dir.
    """
    for never_excused in ("README.md", "pyproject.toml", "cdfibenchmark/"):
        assert layout.absence_is_declared(never_excused) is None, (
            f"{never_excused} ships in the sdist and is in the repository; no "
            f"layout may excuse its absence, but absence_is_declared did"
        )
    excuse = layout.absence_is_declared("examples/")
    if layout.IS_SDIST_ROOT:
        assert excuse is not None, (
            "this is an unpacked sdist root, where MANIFEST.in's `prune "
            "examples` is what makes examples/ legitimately absent, but "
            "absence_is_declared would call that a deletion"
        )
    else:
        assert excuse is None, (
            "examples/ may only be excused inside an unpacked sdist root. "
            "Outside one, its absence is a deletion and must be red."
        )


@layout.needs("MANIFEST.in")
def test_the_manifest_reader_still_finds_the_prune_it_reads():
    """A reader that silently returns nothing excuses nothing -- and pins nothing.

    `manifest_exclusions` is safe when it breaks (an empty set excuses no
    absence, so surfaces go red rather than skipped), but "safe when broken" is
    not the same as "working". If it stopped parsing, the tarball-root run would
    go red again with a confusing message rather than skipping examples/ by
    name. Assert it is really reading this repository's file.

    Red-proving this is one edit: change `prune examples` in MANIFEST.in to
    `recursive-exclude examples *`, which is not a whole-surface exclusion.
    """
    exclusions = layout.manifest_exclusions()
    assert "examples" in exclusions, (
        f"MANIFEST.in is present but the reader did not find `examples` among "
        f"its whole-surface exclusions (found: {sorted(exclusions) or 'nothing'}). "
        f"Either the prune directive was reworded, or the reader stopped "
        f"parsing -- and the tarball-root layout depends on this answer."
    )
    assert "README.md" not in exclusions, (
        "the reader reports README.md as excluded from the distribution; "
        "MANIFEST.in `include`s it, so the reader is matching the wrong lines"
    )


#: Claims retired in earlier releases. None may reappear on ANY shipped surface.
#:
#: SCOPE, STATED HONESTLY: the gate below reads pyproject's [project] table and
#: nothing else. This list is NOT swept across `_read_surface`, which is why the
#: demo notebook can and does still say "CET1" (examples/cdfi_benchmarking_demo
#: .ipynb:13, `grep -n CET1 examples/*.ipynb`). Widening it is a live claim
#: correction and belongs with the other prose corrections, not with a change to
#: how layouts are detected.
RETIRED_CLAIMS = ["CET1", "Tier 1 Capital Ratio", "INSTNAME"]

#: (cert, name) bindings that are FALSE. Verified against FDIC /institutions.
FALSE_CERT_BINDINGS = [(57542, "Broadway Federal")]

#: A line may NAME a false binding in order to correct or document it.
_NEGATIONS = ("is not", "is NOT", "previously", "no longer", "was ",
              "not a real", "wrong", "belongs to")


@pytest.mark.parametrize("claim", RETIRED_CLAIMS)
@layout.needs("pyproject.toml")
def test_retired_claims_do_not_reappear_in_package_metadata(claim):
    """The PyPI description is a shipped surface and drifts on its own."""
    meta = _project_meta()
    blob = " ".join(str(meta.get(k, "")) for k in ("description", "name"))
    assert claim.lower() not in blob.lower(), (
        f"retired claim {claim!r} still in pyproject [project] metadata — this "
        f"is the text PyPI renders above the README"
    )


@pytest.mark.parametrize("cert,name", FALSE_CERT_BINDINGS)
@pytest.mark.parametrize("surface", _CERT_SCAN_SURFACES)
def test_no_surface_binds_a_cert_to_the_wrong_institution(surface, cert, name):
    """A wrong cert->name binding runs, returns data, and names another bank.

    PARAMETRIZED BY SURFACE, not a single sweep, because the two layouts that
    matter disagree about exactly one surface and the disagreement has to be
    visible. `examples/` is pruned from the sdist and read on GitHub — the
    notebook is where the wrong binding was most emphatic, attributing "one of
    the largest Black-owned banks" to a CERT belonging to Toyota Financial
    Savings Bank. At the tarball root that surface is legitimately absent; on
    GitHub, in a checkout and in a `git archive` it is present and must be
    scanned. One sweep can only answer both by shrinking silently. Eight test
    ids answer per surface, and the report says which one skipped and why.

    A surface deleted from a source tree fails here BY NAME rather than
    skipping: `layout.require` draws that line.
    """
    layout.require(surface)
    offenders = []
    for path, text in _read_surface(surface).items():
        # This gate itself must be able to describe the defect in order to
        # detect it. Compare on the dict key, which is a repo-relative path.
        if Path(path).name == Path(__file__).name:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if str(cert) not in line or name.lower() not in line.lower():
                continue
            if any(neg.lower() in line.lower() for neg in _NEGATIONS):
                continue  # a correction, not an assertion
            offenders.append(f"{path}:{line_no}: {line.strip()}")
    assert not offenders, (
        f"CERT {cert} is NOT {name} (it is Toyota Financial Savings Bank, "
        f"Henderson NV). Offending surfaces:\n  " + "\n  ".join(offenders)
    )


@layout.needs("README.md")
def test_readme_discloses_the_period_basis():
    """B2's ruling has to be readable by someone who never opens the source."""
    text = README.read_text().lower()
    assert "ytd" in text or "year-to-date" in text
    assert "annualiz" in text
    assert "nimy" in text


@layout.needs("README.md")
def test_readme_marks_house_thresholds_as_house():
    text = README.read_text()
    assert "HOUSE" in text, (
        "the metrics table renders seven house rules of thumb beside one CFR "
        "citation with nothing distinguishing them"
    )


@layout.needs("README.md")
def test_readme_does_not_hand_type_a_test_count():
    """Six recorded instances of a hand-typed count in this portfolio.

    A number that must be edited by hand every time a test is added is a claim
    that goes stale silently.
    """
    m = re.search(r"(\d+)\s+tests\b", README.read_text())
    assert m is None, (
        f"README hand-types a test count ({m.group(0)!r}); it will go stale"
    )


@layout.needs("README.md")
def test_readme_does_not_claim_credit_union_coverage():
    """The FDIC API covers FDIC-insured banks. Credit unions are NCUA."""
    text = README.read_text().lower()
    assert "credit union" not in text or "not" in text, "see explicit gate below"


@layout.needs("README.md")
def test_readme_credit_union_mention_is_an_exclusion_not_an_audience():
    text = README.read_text()
    for line in text.splitlines():
        if "credit union" in line.lower():
            assert any(w in line.lower() for w in ("no ", "not ", "never", "exclud")), (
                f"README offers the tool to credit unions, which the FDIC API "
                f"does not cover: {line.strip()!r}"
            )


@layout.needs("README.md")
def test_readme_points_at_the_live_api_host():
    """banks.data.fdic.gov now 301-redirects to api.fdic.gov/banks."""
    from cdfibenchmark.data.schema import FDIC_API_BASE
    assert FDIC_API_BASE in README.read_text()


@layout.needs("pyproject.toml")
def test_version_is_bumped_for_a_release_that_changes_grades():
    meta = _project_meta()
    assert meta["version"] == "0.3.0"


@layout.needs("CHANGELOG.md")
def test_changelog_documents_the_current_version():
    text = layout.SURFACES["CHANGELOG.md"].read_text()
    assert "## [0.3.0]" in text
