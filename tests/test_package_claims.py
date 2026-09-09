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

    AND THE SAME RULE ONE LEVEL UP, WHICH THIS FUNCTION USED TO BREAK. For a
    directory surface `layout.require` can only answer "the DIRECTORY is there".
    The glob below then decides what is actually scanned, and a glob that
    matches nothing returned `{}` -- so the gate asserted over an empty dict and
    PASSED, with no skip, no reason and no signal. Measured at 6097238,
    python3.10, in a full checkout:

        mv examples/cdfi_benchmarking_demo.ipynb examples/…demo.ipynb.bak
        PYTHONPATH=. pytest tests -q            -> 329 passed, 3 skipped
                                                   (byte-identical to control)
        PYTHONPATH=. pytest tests/test_package_claims.py -q -k wrong_institution
                                                -> 7 passed, 14 deselected

    The examples/ leg passed having read nothing. That leg is the ONLY automated
    defence on the demo notebook -- `RETIRED_CLAIMS` is not swept over it (see
    the note there) -- and it is the gate that caught the fabricated Carver row.
    It disarmed on a rename, and would equally on a jupytext conversion to `.py`
    or `.md`, or on the directory being emptied.

    So an empty result is RED here, always, and never a skip. There is no
    declaration mechanism for "present but contributes nothing": MANIFEST.in
    declares that a surface is ABSENT, and `layout.require` has already ruled
    that this one is present. A conversion or a rename is a real maintenance
    signal -- update `_SURFACE_GLOBS` -- and the failure names the directory and
    the pattern so the reader knows which.
    """
    if name not in _SURFACE_GLOBS:
        path = layout.SURFACES[name]
        return {name: path.read_text()}
    sub, pattern = _SURFACE_GLOBS[name]
    d = ROOT / sub
    found = {str(p.relative_to(ROOT)): p.read_text()
             for p in sorted(d.rglob(pattern))}
    assert found, (
        f"surface {name!r} is present at {d} -- layout.require passed it -- but "
        f"rglob({pattern!r}) matched NO files under it, so this gate would scan "
        f"nothing and pass. A surface that contributes zero files to a scan is "
        f"a silently disarmed gate, not a clean one. Either the files were "
        f"renamed, moved or converted (restore them), or the surface genuinely "
        f"holds a different file type now, in which case update _SURFACE_GLOBS "
        f"and red-prove the new pattern."
    )
    return found


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

    EXHAUSTIVE OVER `SURFACES`, NOT A HAND-TYPED SHORTLIST. This gate used to
    name three never-excusable surfaces by hand, which left six of the nine in
    `SURFACES` uncovered -- and each of those six was absorbable by one appended
    MANIFEST.in line. Re-derived at the root of the 0.3.1 tarball, python3.10
    (`tar xzf`, append the line, delete the file, `PYTHONPATH=. pytest tests/ -q`):

        control                                        328 passed,  4 skipped
        rm CHANGELOG.md                                  9 FAILED, 314 passed
        prune CHANGELOG.md   + rm CHANGELOG.md         316 passed, 11 skipped
        exclude setup.py     + rm setup.py             327 passed,  5 skipped
        exclude CONTRIBUTING.md + rm CONTRIBUTING.md   327 passed,  5 skipped

    One line turned nine named failures into exit 0. A hand-typed list inside a
    vacuity guard is the exact shape this suite says it distrusts, and this
    project has six recorded prior instances of a hand-typed list going stale.

    So the set of surfaces a distribution may omit is `layout.EXCUSABLE_SURFACES`
    -- consulted by `absence_is_declared` itself, so MANIFEST.in can no longer
    widen it -- and this gate walks ALL of `SURFACES` against it. A surface added
    to `SURFACES` is never-excusable until somebody deliberately says otherwise.
    """
    assert layout.EXCUSABLE_SURFACES <= set(layout.SURFACES), (
        f"EXCUSABLE_SURFACES names {sorted(set(layout.EXCUSABLE_SURFACES) - set(layout.SURFACES))} "
        f"which is not in SURFACES, so this gate would walk past it without "
        f"ever checking it"
    )
    for never_excused in sorted(set(layout.SURFACES) - layout.EXCUSABLE_SURFACES):
        assert layout.absence_is_declared(never_excused) is None, (
            f"{never_excused} is not in layout.EXCUSABLE_SURFACES, so no layout "
            f"may excuse its absence -- but absence_is_declared did. Either the "
            f"policy set changed without this being re-argued, or MANIFEST.in "
            f"has been given power to absorb a deletion."
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


@layout.needs("MANIFEST.in")
def test_manifest_excludes_no_surface_the_policy_requires_this_package_to_ship():
    """Catch the absorbing edit where it is MADE, not where it lands.

    `absence_is_declared` already refuses to excuse anything outside
    `layout.EXCUSABLE_SURFACES`, so an appended `exclude setup.py` can no longer
    turn a deletion green. But it would still stop setup.py SHIPPING, and the
    first sign of that would be a confusing red at a tarball root that no longer
    contains a file every gate still demands -- one release later, in an
    artifact, rather than here, in the diff that caused it.

    This runs wherever MANIFEST.in is readable, which includes the plain
    checkout, so the edit fails in the pull request that makes it.

    THE SENTENCE ABOVE WAS FALSE FOR GLOB-SHAPED EXCLUSIONS UNTIL NOW, and the
    correction is `layout.manifest_excludes_surface`. This gate compared each
    surface's token against the directive arguments with `in`, a LITERAL test,
    while MANIFEST.in arguments are glob patterns. Measured in a checkout,
    python3.10, appending one line and running `PYTHONPATH=. pytest tests -q`:

        exclude *.md   (before this change)  ->  330 passed, 3 skipped, silent
        exclude *.md   (after  this change)  ->  1 failed, 329 passed, 3 skipped

    The edit was never harmless: the sdist it builds ships no CHANGELOG.md and
    no CONTRIBUTING.md, and running that tarball's own suite from its root gives
    `10 failed`. `test-sdist` in release.yml catches that before a tag, so this
    was an overstatement rather than an open hole -- but "where it is MADE" is
    now true of the shape that actually gets typed.

    Red-proving this is one line: append `exclude setup.py` (literal) or
    `exclude *.md` (glob) to MANIFEST.in.
    """
    offenders = {}
    for surface in sorted(layout.SURFACES):
        if surface in layout.EXCUSABLE_SURFACES:
            continue
        pattern = layout.manifest_excludes_surface(surface)
        if pattern:
            offenders[surface] = pattern
    assert not offenders, (
        f"MANIFEST.in keeps these surfaces out of the distribution — surface: "
        f"the directive argument that matches it — "
        f"{ {k: v for k, v in sorted(offenders.items())} }. "
        f"layout.EXCUSABLE_SURFACES says this package ships them and every gate "
        f"here still requires them. Shipping is a policy decision: change "
        f"EXCUSABLE_SURFACES in tests/_layout.py deliberately, with the "
        f"reasoning, or drop the exclusion."
    )


#: Claims retired in earlier releases. None may reappear on ANY shipped surface.
#:
#: SCOPE, STATED HONESTLY: the docstring above says no retired claim may appear
#: on any shipped surface. The gate below does not enforce that. It reads
#: pyproject's [project] table and nothing else; this list is never swept across
#: `_read_surface`. The sentence that used to sit here recorded the consequence
#: -- "the demo notebook can and does still say CET1" -- and that is no longer
#: true, because 0.3.1 corrected it by hand:
#:
#:     grep -rn CET1 examples/   ->  no matches   (measured on this tree)
#:
#: The notebook said "Compute key performance metrics (NIM, efficiency ratio,
#: ROAA, CET1, etc.)". The package computes no CET1 and never has: `tier1_ratio`
#: is the Tier 1 LEVERAGE ratio, which is a different regulatory measure, and
#: CET1 was struck from pyproject's `description` in 0.3.0 for exactly that
#: reason. So the claim was retired everywhere except the one surface this gate
#: cannot see, and a human had to find it.
#:
#: WHY THE GATE IS STILL NOT WIDENED, AND WHAT WIDENING WOULD COST
#: Widening it is NOT a pure widening of this parametrization. The gate takes
#: one `claim` parameter and calls `_project_meta()`; covering surfaces means a
#: second `@parametrize("surface", ...)`, a `layout.require(surface)` call and a
#: `_read_surface` loop -- new logic on a gate, in a release scoped to metadata
#: and prose. It also has a live consequence: `examples/` is pruned from the
#: sdist, so a surface-parametrized retired-claim gate acquires a skip at the
#: tarball root and in the constructed sdist directory, which is precisely the
#: layout behaviour PR #4 exists to settle. Doing both in one change makes
#: neither reviewable.
#:
#: Deferred to 0.3.2 as its own change, red-proven per added surface. Until then
#: this gate covers ONE surface and the docstring's "any shipped surface" is an
#: aspiration, not a description -- which is why it is written down here.
RETIRED_CLAIMS = ["CET1", "Tier 1 Capital Ratio", "INSTNAME"]

#: (cert, name) bindings that are FALSE. Verified against FDIC /institutions.
FALSE_CERT_BINDINGS = [(57542, "Broadway Federal")]

#: A line may NAME a false binding in order to correct or document it.
#:
#: SCOPE OF THE HOLE THIS LEAVES, CORRECTED. The exemption is applied PER LINE
#: and is satisfied by any one of these words appearing ANYWHERE on the line, so
#: a line that both asserts the false binding and contains an unrelated "was" is
#: wholly exempt. The 0.3.1 round-3 commit message (cd9e4ee) described that as
#: "latent for line-shaped files, real for minified JSON". THAT SENTENCE IS
#: WRONG and is corrected here, where the code it describes lives. Measured at
#: 6097238+round-4, python3.10, appending one line to README.md and running
#: `PYTHONPATH=. pytest tests -q -k wrong_institution`:
#:
#:   "CERT 57542 is Broadway Federal Bank, and the sky was blue."
#:                                                    -> 7 passed   (EXEMPT)
#:   "CERT 57542 is Broadway Federal Bank, and the sky is  blue."
#:                                                    -> 1 failed, 6 passed
#:   "CERT 57542 is Broadway Federal Bank. It was reported elsewhere."
#:                                                    -> 7 passed   (EXEMPT)
#:
#: Ordinary Markdown, not minified JSON. Every wrapped prose paragraph is
#: line-shaped for this purpose, so the hole is live on the surfaces this gate
#: most needs to cover. The DEFERRAL still stands -- narrowing the exemption
#: (proximity to the binding, or a phrase-level match) is gate logic and belongs
#: in 0.3.2 with its own red-proofs -- but it is deferred on an accurate
#: description of what it leaves open, not a comforting one.
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


#: Phrases that ASSERT NON-COVERAGE. A credit-union mention in README prose must
#: carry one of them.
#:
#: WHY THIS IS A PHRASE LIST AND NOT THE NEGATION-WORD TUPLE IT REPLACES.
#: The gate used to accept any of `"no "`, `"not "`, `"never"`, `"exclud"`
#: appearing ANYWHERE on the line. That is the same per-line, any-word shape as
#: `_NEGATIONS` above, and it admitted the exact sentence the gate exists to
#: refuse. Measured at 98d071a, python3.10, appending one line to README.md and
#: running `PYTHONPATH=. pytest tests -q`:
#:
#:   "We proudly serve credit unions, with no setup required."
#:                                          -> 330 passed, 3 skipped   (ADMITTED)
#:   "Credit unions are welcome; nothing is excluded from our audience."
#:                                          -> 330 passed, 3 skipped   (ADMITTED)
#:   "We proudly serve credit unions and CDFI loan funds."
#:                                          -> 1 failed, 329 passed, 3 skipped
#:
#: An unrelated "no setup" and an unrelated "excluded" each bought a pass. These
#: phrases cannot be satisfied by an incidental negation elsewhere in the
#: sentence: each one states that something is not covered. `"exclud"` is
#: deliberately NOT among them -- "nothing is excluded" is how the second
#: sentence above got in.
_EXCLUSION_PHRASES = (
    "not covered", "does not cover", "do not cover", "cannot cover",
    "not supported", "does not support", "do not support",
    "out of scope", "outside the scope", "not in scope",
    "not included", "does not include",
)

#: An inline code span. A mention inside one is QUOTED CODE, not prose offering
#: the tool to anybody -- README.md quotes the deleted `assert "credit union"
#: not in text or "not" in text` in order to record it, and a gate that cannot
#: distinguish a quotation from an assertion forces the documentation out. This
#: is the same allowance `_CERT_SCAN_SURFACES` makes for CHANGELOG.md, narrowed
#: to a span rather than a whole surface: the span is REMOVED and the rest of
#: the line is still judged, so `` `x` We serve credit unions `` stays red.
_CODE_SPAN = re.compile(r"`[^`]*`")


@layout.needs("README.md")
def test_readme_credit_union_mention_is_an_exclusion_not_an_audience():
    """The FDIC API covers FDIC-insured banks. Credit unions are NCUA.

    THIS GATE ABSORBED A SIBLING THAT COULD NOT FAIL. Alongside it stood

        assert "credit union" not in text or "not" in text, "see explicit gate below"

    whose second limb is true of every README ever written -- "not" appears in
    all of them -- so the assertion was unfailable. Demonstrated by the 0.3.1
    audit: appending *"We proudly serve credit unions and CDFI loan funds."* to
    README.md left it green. It was deleted rather than repaired.

    AND ITS OWN VACUITY IS CLOSED. This gate's assertion lives inside a loop
    over lines that mention credit unions, so a README that stopped mentioning
    them at all would pass while certifying nothing. The exclusion is a scope
    limit users rely on, so its DISAPPEARANCE is a regression in its own right:
    the gate requires the README to state it, and then requires every statement
    of it to be an exclusion.

    AND THE HOLE IT INHERITED IS CLOSED TOO -- IT HAD THE SAME DEFECT AS THE
    ASSERTION IT REPLACED, ONE SCREEN AWAY. Accepting any of `"no "`, `"not "`,
    `"never"`, `"exclud"` anywhere on the line let two sentences through that
    offer the tool to credit unions; the measurements are recorded at
    `_EXCLUSION_PHRASES` above. It now takes a phrase that states non-coverage,
    the mention is read from PROSE with inline code spans removed, and the
    exclusion must be stated in prose at least once rather than only inside a
    quotation.

    WHAT IT STILL DOES NOT CATCH, SO THE CLAIM MATCHES THE CODE:

    * A sentence that offers the tool AND contains an exclusion phrase --
      *"We serve credit unions; other lenders are not covered."* -- passes. That
      is an adversarial sentence rather than the drift this gate defends
      against, and deciding it needs to parse the sentence, not match it.
    * The scan is per LINE. A "credit unions" that wraps across a newline is not
      seen at all. Every mention in this README is on one line, and a
      hard-wrapped one would be a silent miss, not a false pass on a mention it
      read.
    * A false RED is the failure direction everywhere else: rewording the
      exclusion to a phrase not on the list fails loudly, which is one line to
      fix and is the trade this suite takes deliberately.

    Red-proven both ways; the mutations and counts are at `_EXCLUSION_PHRASES`
    and in the CHANGELOG.
    """
    text = README.read_text()
    prose = {}
    for line in text.splitlines():
        stripped = _CODE_SPAN.sub(" ", line)
        if "credit union" in stripped.lower():
            prose[line] = stripped

    assert prose, (
        "README.md no longer mentions credit unions in prose anywhere (inline "
        "code spans are not counted -- a quotation is not a statement of "
        "scope). This tool reads the FDIC API, which covers FDIC-insured banks "
        "only; credit unions are NCUA-regulated and out of scope, and the "
        "README has to say so. With no mention at all this gate would loop over "
        "nothing and pass while certifying nothing."
    )
    for line, stripped in prose.items():
        assert any(ph in stripped.lower() for ph in _EXCLUSION_PHRASES), (
            f"this README line mentions credit unions without stating that they "
            f"are not covered -- the FDIC API does not reach them, so a mention "
            f"that is not an exclusion is an offer: {line.strip()!r}. It must "
            f"carry one of {list(_EXCLUSION_PHRASES)}. A bare negation "
            f"elsewhere in the sentence is not enough; that is exactly what let "
            f"'with no setup required' and 'nothing is excluded' through."
        )


@layout.needs("README.md")
def test_readme_points_at_the_live_api_host():
    """banks.data.fdic.gov now 301-redirects to api.fdic.gov/banks."""
    from cdfibenchmark.data.schema import FDIC_API_BASE
    assert FDIC_API_BASE in README.read_text()


def _build_requires() -> list:
    """`[build-system].requires`, as a list of requirement strings.

    Narrow and section-aware, and it RAISES rather than returning empty -- the
    same rule as `_project_meta` above. A reader that answers "no requirements"
    for a pyproject it failed to parse would turn the gate below into a silent
    pass, which is the class of defect this module exists to close. Not tomllib:
    the CI matrix runs 3.9 and 3.10, where it does not exist.
    """
    text = PYPROJECT.read_text()
    lines, out, in_bs, collecting = text.splitlines(), [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and not collecting:
            in_bs = stripped == "[build-system]"
            continue
        if not in_bs:
            continue
        if stripped.startswith("#"):
            continue
        if not collecting and re.match(r"^requires\s*=", stripped):
            collecting = True
            stripped = stripped.split("=", 1)[1].strip()
        if collecting:
            out += re.findall(r'"([^"]+)"', stripped)
            if "]" in stripped:
                return out
    raise AssertionError(
        "could not read [build-system].requires from pyproject.toml; this gate "
        "must not pass without reading it"
    )


@layout.needs("pyproject.toml")
def test_the_declared_build_requirement_can_read_this_metadata():
    """A build requirement is a claim, and this one was false by 19 versions.

    Every packaging field this project has lives in the PEP 621 `[project]`
    table. setuptools only learned to read that table in 61.0.0, and
    `[build-system].requires` said `setuptools>=42`.

    The failure is silent and total. Measured, python3.10, on the unpacked 0.3.1
    sdist, `pip wheel --no-deps --no-build-isolation` in a venv pinned to each:

        setuptools 60.10.0 -> "Successfully built UNKNOWN", a wheel named
                              UNKNOWN-0.0.0 whose only entries are its own
                              dist-info -- no package code -- exit 0
        setuptools 61.0.0  -> "Successfully built cdfi-benchmark"

    and with the floor itself as the variable, system setuptools 59.6.0,
    `python -m build --wheel --no-isolation`:

        requires = ["setuptools>=42"] -> builds UNKNOWN-0.0.0, exit 0
        requires = ["setuptools>=61"] -> ERROR Unmet dependencies: setuptools>=61,
                                         found 59.6.0 -- refuses to build

    This gate holds the DECLARATION true. It cannot make every tool honour it:
    `pip wheel --no-build-isolation` checks no build requirement at all and
    still builds UNKNOWN on an old setuptools under either floor. Stating that
    limit here rather than implying the gate closes the hole outright.

    No existing gate could see it, because no gate read the build requirement
    and CI always builds in an isolated env holding the newest setuptools. That
    is the shape of every defect this suite keeps finding: a written claim, no
    gate over it, and a failure mode that exits 0.

    Red-proving this is one edit: put `setuptools>=42` back.
    """
    requires = _build_requires()
    setuptools_reqs = [r for r in requires if r.lower().replace("_", "-").startswith("setuptools")]
    assert setuptools_reqs, (
        f"[build-system].requires is {requires} and names no setuptools "
        f"requirement, but build-backend is setuptools.build_meta and every "
        f"packaging field is in the [project] table it has to read"
    )
    for req in setuptools_reqs:
        m = re.search(r">=\s*(\d+)", req)
        assert m, (
            f"the setuptools build requirement {req!r} states no lower bound, so "
            f"nothing stops a build with a setuptools too old to read the "
            f"[project] table -- which produces an UNKNOWN-0.0.0 wheel with no "
            f"package code in it, and exits 0"
        )
        assert int(m.group(1)) >= 61, (
            f"the setuptools build requirement is {req!r}, but PEP 621 "
            f"[project] support landed in setuptools 61.0.0. Measured: 60.10.0 "
            f"builds this sdist into an empty UNKNOWN-0.0.0 wheel and exits 0."
        )


@layout.needs("pyproject.toml")
def test_version_is_bumped_for_a_release_that_changes_grades():
    meta = _project_meta()
    assert meta["version"] == "0.3.2"


@layout.needs("CHANGELOG.md")
def test_changelog_documents_the_current_version():
    text = layout.SURFACES["CHANGELOG.md"].read_text()
    assert "## [0.3.2]" in text


@layout.needs("pyproject.toml")
def test_the_pep639_license_form_declares_the_floor_it_needs():
    """The SPDX license expression and the setuptools floor must move together.

    `license = {text = "MIT"}` is the deprecated table form; setuptools has
    announced its removal for 2027-02-18. The replacement is a bare SPDX
    expression, `license = "MIT"`, which setuptools only learned to read in
    77.0.0 -- so switching the form without raising the floor declares a build
    requirement that cannot read the metadata it is there to read. That is the
    exact defect `test_the_declared_build_requirement_can_read_this_metadata`
    above was written for, one PEP later.

    Measured 2026-09-09, PyPI JSON API: 77.0.3 / 78.1.1 / 80.9.0 all declare
    Requires-Python >=3.9, so the raised floor is satisfiable on every
    interpreter this package supports. The current latest, 84.0.0, declares
    >=3.10 -- which does NOT conflict, because pip resolves `setuptools>=77` on
    3.9 to the newest release still admitting 3.9. Recorded because "the newest
    setuptools" and "the setuptools a 3.9 build uses" have stopped being the
    same thing, and the next person to reason about this floor will assume they
    are.
    """
    text = PYPROJECT.read_text()
    spdx = re.search(r'^license\s*=\s*"([^"]+)"\s*$', text, re.M)
    table = re.search(r'^license\s*=\s*\{', text, re.M)

    assert not table, (
        "pyproject still uses the deprecated `license = {text = ...}` table "
        "form; setuptools has announced its removal for 2027-02-18"
    )
    assert spdx, (
        "no PEP 639 SPDX license expression found in pyproject.toml; a "
        "distribution that declares no license is not the same as one that "
        "declares MIT"
    )

    floors = [int(m.group(1)) for m in
              (re.search(r">=\s*(\d+)", r) for r in _build_requires()
               if r.lower().startswith("setuptools")) if m]
    assert floors, "no setuptools lower bound to check the license form against"
    assert min(floors) >= 77, (
        f"pyproject declares the PEP 639 form `license = \"{spdx.group(1)}\"` "
        f"but only requires setuptools>={min(floors)}. Support for a bare SPDX "
        f"expression landed in 77.0.0; below it the field is not understood."
    )
