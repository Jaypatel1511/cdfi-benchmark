"""Where am I, and does a missing surface mean "deleted" or "deliberately not shipped"?

Three modules -- `test_package_claims.py`, `test_bound_claims.py` and
`test_calibration_claims.py` -- each carried their own copy of

    _IS_REPO_TREE = (ROOT / "cdfibenchmark").is_dir() or (ROOT / ".git").exists()

Three copies of one predicate is three places for it to drift, and the defect
this module was written to fix could only be fixed once per copy. It lives here
now and each module imports it.

THE QUESTION THIS MODULE EXISTS TO ASK
--------------------------------------
The old predicate answers ONE question -- "is a source tree present here?" --
and every gate then used that single global answer for every surface it reads.
That is the wrong shape, and 0.3.0 shipped because of it.

`examples/` is pruned from the sdist ON PURPOSE. MANIFEST.in says so in words::

    # examples/ is intentionally NOT shipped -- the demo notebook is a repo
    # artifact, not part of the distributed package.
    prune examples

`cdfibenchmark/` DOES ship in the sdist. So an unpacked tarball root answers
"yes, a source tree is present", and `test_package_claims` then demanded a
directory the tarball is designed never to contain. Measured on the 0.3.0
tarball, python3.10::

    cd cdfi_benchmark-0.3.0 && PYTHONPATH=. pytest tests/ -q
    -> 2 failed, 319 passed, 3 skipped

The obvious fix -- anchor on `.git` alone -- is WRONG, and measurably so. A
GitHub zip download or `git archive` has no `.git` but DOES have `examples/`.
Measured on `git archive HEAD | tar -x`, at 0.3.1::

    PYTHONPATH=. pytest tests -q   ->  329 passed, 3 skipped

(That figure read `321 passed, 3 skipped` when this module was written, and it
was already wrong then: the same command at the commit that introduced the
sentence also gives 329. Corrected in 0.3.1 by re-running it. The number is
incidental to the argument -- what matters is that the layout HAS `examples/`
and has no `.git` -- but a wrong measured number in a module about stale claims
is the thing this repository keeps failing at, so it is re-run rather than
deleted.)

Under `.git`-only anchoring that layout stops classifying as a repository tree,
the module skips as a unit, and the cert-binding gate goes silent on a layout
where the notebook is present and scannable. A gate quietly losing reach is
worse than the bug it was meant to fix.

So the question is not "which global anchor". It is per surface:

    Is this surface readable here? If it is not, has the artifact I am standing
    in DECLARED that it omits it?

WHAT COUNTS AS A DECLARATION -- AND WHY ONLY AN SDIST CAN MAKE ONE
------------------------------------------------------------------
A directory can only excuse an absence if it is a distribution that states its
own contents. Exactly one layout here does that: an unpacked sdist, identified
by `PKG-INFO` at its root. That file is written by the build backend into every
sdist and is not a repository file -- verified absent from a fresh clone and
from `git archive HEAD`, and present at the root of the 0.3.0 tarball.

The declaration itself is read from `MANIFEST.in`, which SHIPS INSIDE the sdist
(verified in the 0.3.0 tarball listing) and which is the file a maintainer edits
when they change what ships. Reading it rather than hand-typing a
ships/does-not-ship flag per surface is deliberate: delete `prune examples` and
`examples/` starts shipping, and the rule below automatically starts REQUIRING
it in the tarball. A hand-typed flag would go on excusing an absence that is no
longer intended.

The excuse must be POSITIVE. An absence is excused only if MANIFEST.in names
that surface in an exclusion directive. Anything else missing from an sdist is
RED -- which is the whole point of running the shipped suite from the tarball
root: an incomplete sdist is the defect that produced `58 passed, 38 errors`
from the published 0.2.1. This errs toward a false RED, never a false green, and
a false RED is one loud line to fix.

CONSEQUENTLY
------------
    checkout (.git)          nothing is excused. Every absence is a deletion.
    git archive / zip        nothing is excused. Every absence is a deletion.
    unpacked sdist root      an absence MANIFEST.in declares is excused BY NAME;
                             any other absence is a broken tarball -> RED.
    constructed test dir     no source tree at all. Absences skip, per gate,
                             over that gate's OWN coverage set -- never the
                             whole module, which is how eight assertions that
                             only need README.md and pyproject.toml were being
                             switched off in a directory that HAS both.
"""
import pathlib

import pytest

#: The tree under test. `tests/` sits directly under it in every layout.
ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Every surface any gate in this suite names. A module declares the subset it
#: reads; nothing here is required by merely being listed.
SURFACES = {
    "README.md": ROOT / "README.md",
    "CHANGELOG.md": ROOT / "CHANGELOG.md",
    "CONTRIBUTING.md": ROOT / "CONTRIBUTING.md",
    "pyproject.toml": ROOT / "pyproject.toml",
    "MANIFEST.in": ROOT / "MANIFEST.in",
    "setup.py": ROOT / "setup.py",
    "cdfibenchmark/": ROOT / "cdfibenchmark",
    "tests/": ROOT / "tests",
    "examples/": ROOT / "examples",
}

#: A source tree is present. Unchanged from the three copies this replaces, and
#: kept BECAUSE it is right for the question it actually answers: measured, it
#: separates {checkout, tarball root, git archive} from {wheel-tests dir,
#: sdist-tests dir} exactly. What it must no longer be asked is whether a
#: PARTICULAR surface ought to be here; that is `absence_is_declared` below.
IS_REPO_TREE = (ROOT / "cdfibenchmark").is_dir() or (ROOT / ".git").exists()

#: An unpacked sdist root. PKG-INFO is written into every sdist by the build
#: backend and is not a repository file, so this is a positive identification
#: rather than an inference from what is missing.
IS_SDIST_ROOT = (ROOT / "PKG-INFO").is_file()


def _manifest_token(surface: str) -> str:
    """The name MANIFEST.in would use for this surface (`"examples/"` -> `"examples"`)."""
    return surface.rstrip("/")


def manifest_exclusions():
    """Surfaces MANIFEST.in explicitly excludes, as a set of bare tokens.

    A deliberately narrow reader, for the same reason `_project_meta` in
    `test_package_claims.py` carries one: it must not silently answer "nothing
    is excluded" in a way that turns into a PASS. It cannot -- an empty result
    excuses nothing, so an unreadable or reworded MANIFEST.in makes absences RED
    rather than skipped. `test_the_manifest_reader_still_finds_the_prune_it_reads`
    pins that it is really parsing this repo's file and not returning an empty
    set that happens to be safe.

    Recognises only whole-surface exclusions -- `prune <dir>` and
    `exclude <pat>`. `recursive-exclude` and `global-exclude` narrow the
    contents of a surface rather than removing it, so they are not read as a
    declaration that the surface itself is absent.
    """
    path = SURFACES["MANIFEST.in"]
    if not path.is_file():
        return frozenset()
    out = set()
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "prune" and len(parts) >= 2:
            out.update(p.rstrip("/") for p in parts[1:])
        elif parts[0] == "exclude" and len(parts) >= 2:
            out.update(parts[1:])
    return frozenset(out)


def absence_is_declared(surface: str):
    """Why this surface's absence is EXPECTED here, or None if it is not.

    None means "nothing here declares this absence", which -- inside a source
    tree -- means somebody deleted or moved it.
    """
    if not IS_SDIST_ROOT:
        return None
    token = _manifest_token(surface)
    if token not in manifest_exclusions():
        return None
    return (
        f"this is an unpacked sdist root (PKG-INFO is present) and MANIFEST.in "
        f"declares {token!r} excluded from the distribution, so {surface} is "
        f"absent by design and not by deletion"
    )


def classify(*surfaces):
    """(present, declared_absent, undeclared_absent) for the named surfaces."""
    present, declared, undeclared = [], {}, []
    for name in surfaces:
        path = SURFACES[name]
        if path.exists():
            present.append(name)
            continue
        reason = absence_is_declared(name)
        if reason:
            declared[name] = reason
        else:
            undeclared.append(name)
    return present, declared, sorted(undeclared)


def _skip_reason(declared, undeclared, surfaces):
    bits = []
    if declared:
        bits.append("declared absent: " + "; ".join(
            f"{n} ({r})" for n, r in sorted(declared.items())))
    if undeclared:
        bits.append(
            "absent with no declaration, and there is no source tree here "
            "(no cdfibenchmark/, no .git) so nothing was deleted: "
            + ", ".join(undeclared))
    return (f"gate reads {', '.join(sorted(surfaces))}; "
            + " | ".join(bits)
            + ". It runs where those surfaces are readable -- ci.yml's `test` "
              "job has all of them.")


def require(*surfaces):
    """Runtime guard for a gate that reads `surfaces`. Skip by name, or FAIL by name.

    Three outcomes, and the middle one is the whole point:

    * every surface readable                  -> return, the gate runs
    * absent, and the absence is DECLARED     -> `pytest.skip` naming the
      surface and quoting the declaration. Visible in the report as a skip with
      a reason, never a silent narrowing inside a passing test.
    * absent, no declaration, source tree here -> `pytest.fail` naming the
      surface. A deletion is red, and red by name, not an exception raised from
      whichever assertion happened to open the file first.

    Used by parametrized gates, where each surface is its own test id and its
    skip is therefore visible per surface. `needs` below is the decorator form,
    for gates that are not parametrized over surfaces.
    """
    present, declared, undeclared = classify(*surfaces)
    if not declared and not undeclared:
        return
    if undeclared and IS_REPO_TREE:
        pytest.fail(
            f"a source tree is present here (cdfibenchmark/ or .git/) but these "
            f"surfaces are unreadable: {', '.join(undeclared)}. Nothing here "
            f"declares them absent -- MANIFEST.in can only excuse an absence "
            f"inside an unpacked sdist root, and "
            f"{'this is one' if IS_SDIST_ROOT else 'this is not one'}. That is "
            f"a deleted or moved surface, so it fails instead of skipping."
        )
    pytest.skip(_skip_reason(declared, undeclared, surfaces))


def needs(*surfaces):
    """Decorator form of `require`, for gates not parametrized over surfaces.

    Skips when every absence is excusable -- declared by the distribution, or
    unexplained in a directory that is not a source tree. Does NOT skip when a
    surface is missing from a source tree with nothing declaring it absent: that
    run must be red, and `require`/the module's surface gate say so by name.
    """
    _, declared, undeclared = classify(*surfaces)
    skip = bool(declared or undeclared) and not (undeclared and IS_REPO_TREE)
    return pytest.mark.skipif(
        skip, reason=_skip_reason(declared, undeclared, surfaces))
