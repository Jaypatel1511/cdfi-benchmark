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
"""
import re
from pathlib import Path

import pytest

try:                      # 3.11+
    import tomllib
except ModuleNotFoundError:
    try:                  # 3.9/3.10 with the backport available
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"


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

#: Every surface these gates must be able to read. This module is a REPO gate,
#: not an artifact gate: it runs in full against a checkout, or not at all.
#:
#: All-or-nothing on purpose. release.yml's test-sdist job runs the suite from a
#: directory holding ONLY tests/ + README.md + pyproject.toml (deliberately no
#: checkout, so the checkout cannot leak into the thing under test). A gate that
#: merely skipped its unreadable surfaces would go GREEN there while scanning a
#: fraction of what it scans locally — passing while checking less, which is the
#: vacuity class release.yml exists to close. So: if any surface is absent, the
#: whole module skips with a reason naming what was missing, and the assertions
#: are made where they can actually be made (the ci.yml `test` job, which has a
#: full checkout).
_REQUIRED_SURFACES = {
    "README.md": README,
    "pyproject.toml": PYPROJECT,
    "CHANGELOG.md": ROOT / "CHANGELOG.md",
    "cdfibenchmark/": ROOT / "cdfibenchmark",
    "examples/": ROOT / "examples",
}
_MISSING = sorted(n for n, path in _REQUIRED_SURFACES.items() if not path.exists())

#: The all-or-nothing rule above was right and is unchanged. What it could not do
#: was tell an artifact run apart from a DELETION: `exists()` is False in both,
#: so deleting examples/ from a checkout made this whole module answer "skipped —
#: expected in an installed-artifact run", which is a false statement about a
#: checkout and leaves eleven gates certifying nothing while reporting no
#: problem. A gate that skips when it should fail is the same defect as a gate
#: that passes when it should fail.
#:
#: Either anchor means "there is a repository here", and release.yml's wheel-tests
#: and sdist-tests directories have neither.
_IS_REPO_TREE = (ROOT / "cdfibenchmark").is_dir() or (ROOT / ".git").exists()

pytestmark = pytest.mark.skipif(
    bool(_MISSING) and not _IS_REPO_TREE,
    reason=(
        "no repository tree here (no cdfibenchmark/, no .git) and these repo-root "
        "surfaces are absent, so these gates cannot run in full: "
        + ", ".join(_MISSING)
        + " (expected in an installed-artifact run; they run in the `test` job)"
    ),
)


def test_every_surface_these_gates_need_is_present_in_a_repo_tree():
    """A deleted surface must be RED here, never a skip.

    Reached only inside a repository tree, where "examples/ is missing" can only
    mean it was deleted or moved — never "we are testing a wheel".
    """
    assert not _MISSING, (
        f"this is a repository tree (cdfibenchmark/ or .git/ is present) but these "
        f"surfaces are unreadable: {', '.join(_MISSING)}. That is a deleted or "
        f"moved surface, not an installed-artifact run, so it fails instead of "
        f"skipping."
    )

#: Claims retired in earlier releases. None may reappear on ANY shipped surface.
RETIRED_CLAIMS = ["CET1", "Tier 1 Capital Ratio", "INSTNAME"]

#: (cert, name) bindings that are FALSE. Verified against FDIC /institutions.
FALSE_CERT_BINDINGS = [(57542, "Broadway Federal")]


def _shipped_text():
    """Every surface a user reads, keyed by path.

    examples/ is pruned from the sdist but is read on GitHub, and that is
    where the wrong binding was most emphatic — the demo notebook attributed
    "one of the largest Black-owned banks" to a CERT belonging to Toyota
    Financial Savings Bank. A surface not in the tarball is still a surface.
    """
    out = {}
    for p in [README, PYPROJECT, ROOT / "CHANGELOG.md"]:
        # Not `if p.exists()`. The module-level skipif already guaranteed these
        # are here; a silent skip at THIS level would shrink the scan surface
        # without shrinking the pass.
        out[p.name] = p.read_text()
    for sub, pattern in (("cdfibenchmark", "*.py"), ("tests", "*.py"),
                         ("examples", "*.ipynb")):
        d = ROOT / sub
        assert d.exists(), f"expected surface {sub} is missing"
        for p in sorted(d.rglob(pattern)):
            out[str(p.relative_to(ROOT))] = p.read_text()
    return out


#: A line may NAME a false binding in order to correct or document it.
_NEGATIONS = ("is not", "is NOT", "previously", "no longer", "was ",
              "not a real", "wrong", "belongs to")


@pytest.mark.parametrize("claim", RETIRED_CLAIMS)
def test_retired_claims_do_not_reappear_in_package_metadata(claim):
    """The PyPI description is a shipped surface and drifts on its own."""
    meta = _project_meta()
    blob = " ".join(str(meta.get(k, "")) for k in ("description", "name"))
    assert claim.lower() not in blob.lower(), (
        f"retired claim {claim!r} still in pyproject [project] metadata — this "
        f"is the text PyPI renders above the README"
    )


@pytest.mark.parametrize("cert,name", FALSE_CERT_BINDINGS)
def test_no_surface_binds_a_cert_to_the_wrong_institution(cert, name):
    """A wrong cert->name binding runs, returns data, and names another bank."""
    offenders = []
    for path, text in _shipped_text().items():
        # The changelog and this gate itself must be able to DESCRIBE the
        # defect in order to record and detect it. Compare on the dict key,
        # which is a repo-relative path, not a bare filename.
        if path == "CHANGELOG.md" or Path(path).name == Path(__file__).name:
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


def test_readme_discloses_the_period_basis():
    """B2's ruling has to be readable by someone who never opens the source."""
    text = README.read_text().lower()
    assert "ytd" in text or "year-to-date" in text
    assert "annualiz" in text
    assert "nimy" in text


def test_readme_marks_house_thresholds_as_house():
    text = README.read_text()
    assert "HOUSE" in text, (
        "the metrics table renders seven house rules of thumb beside one CFR "
        "citation with nothing distinguishing them"
    )


def test_readme_does_not_hand_type_a_test_count():
    """Six recorded instances of a hand-typed count in this portfolio.

    A number that must be edited by hand every time a test is added is a claim
    that goes stale silently.
    """
    m = re.search(r"(\d+)\s+tests\b", README.read_text())
    assert m is None, (
        f"README hand-types a test count ({m.group(0)!r}); it will go stale"
    )


def test_readme_does_not_claim_credit_union_coverage():
    """The FDIC API covers FDIC-insured banks. Credit unions are NCUA."""
    text = README.read_text().lower()
    assert "credit union" not in text or "not" in text, "see explicit gate below"


def test_readme_credit_union_mention_is_an_exclusion_not_an_audience():
    text = README.read_text()
    for line in text.splitlines():
        if "credit union" in line.lower():
            assert any(w in line.lower() for w in ("no ", "not ", "never", "exclud")), (
                f"README offers the tool to credit unions, which the FDIC API "
                f"does not cover: {line.strip()!r}"
            )


def test_readme_points_at_the_live_api_host():
    """banks.data.fdic.gov now 301-redirects to api.fdic.gov/banks."""
    from cdfibenchmark.data.schema import FDIC_API_BASE
    assert FDIC_API_BASE in README.read_text()


def test_version_is_bumped_for_a_release_that_changes_grades():
    meta = _project_meta()
    assert meta["version"] == "0.3.0"


def test_changelog_documents_the_current_version():
    text = (ROOT / "CHANGELOG.md").read_text()
    assert "## [0.3.0]" in text
