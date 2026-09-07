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
own contents. Exactly one layout here does that: an unpacked sdist.

IDENTIFYING ONE IS NOT A FILENAME TEST. Until this change the module asked

    IS_SDIST_ROOT = (ROOT / "PKG-INFO").is_file()

which is a cheap local question standing in for the one it means. Measured in a
full git checkout at 6097238, python3.10:

    : > PKG-INFO && rm -rf examples
    PYTHONPATH=. pytest tests -q   ->  328 passed, 4 skipped   exit 0

A zero-byte file excused a real deletion, and the skip it printed asserted
"this is an unpacked sdist root (PKG-INFO is present)" in a tree with `.git`
sitting beside it. That is a false statement about the tree, printed as the
reason a deletion was forgiven.

So the question is now asked directly, in three parts, all of which must hold:

    1. CONTENT.   The file parses as RFC-822 distribution metadata carrying
       `Metadata-Version` and `Name`. An empty or arbitrary file does not.
    2. IDENTITY.  That `Name`, normalised per PEP 503, equals `[project].name`
       in THIS tree's pyproject.toml. Metadata about some other package is not
       this tree declaring its own contents. `Version` is deliberately NOT
       compared: in a real sdist the two always agree, and the only tree where
       they can differ is one somebody is editing in place, where the extra
       false RED buys nothing the identity check has not already bought.
    3. PROVENANCE. There is no `.git`. A working checkout is not a
       distribution, whatever files have been dropped into it.

Part 3 is a DISQUALIFIER, not a second proxy for the question: it can only ever
refuse an excuse, never grant one. It was rejected as the whole remedy for
exactly the reason a proxy is the wrong shape -- on its own it closes the git
checkout and leaves a stray or forged PKG-INFO excusing deletions anywhere else.
It costs nothing in normal development, because no routine command writes
PKG-INFO to a checkout root. Measured on a copy of this repo, python3.10, each
in a fresh copy (`cp -a`), checking for `./PKG-INFO` afterwards:

    python3 setup.py sdist                       -> root PKG-INFO: no
    python3 setup.py egg_info                    -> root PKG-INFO: no
    python3 -m build                             -> root PKG-INFO: no
    python3 -m build --sdist                     -> root PKG-INFO: no
    python3 -m pip install -e . --no-deps        -> root PKG-INFO: no

The first four write it under `cdfi_benchmark.egg-info/` instead. So the only
trees part 3 disqualifies are an unpacked sdist somebody has `git init`ed or is
editing in place -- working trees by then, and neither may excuse a deletion.

Whatever the answer, the reason string records WHAT WAS OBSERVED -- the parsed
`Metadata-Version`, the `Name` it matched, and the absence of `.git` -- rather
than announcing a conclusion about the tree. A skip message is a claim like any
other, and this one was false.

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
    unpacked sdist root      an absence is excused BY NAME when this module's
                             policy allows that surface to be omitted AND
                             MANIFEST.in declares it; any other absence is a
                             broken tarball -> RED.
    constructed test dir     no source tree at all. Absences skip, per gate,
                             over that gate's OWN coverage set -- never the
                             whole module, which is how eight assertions that
                             only need README.md and pyproject.toml were being
                             switched off in a directory that HAS both.
"""
import email.parser
import pathlib
import re

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

#: The ONLY surfaces whose absence any distribution may ever excuse.
#:
#: WHY A WRITTEN-DOWN SET, AND WHY IT IS NOT THE ANTI-PATTERN IT RESEMBLES.
#: "Which surfaces must this project ship?" is a POLICY. Nothing in the tree
#: states it: the one file that says what ships is MANIFEST.in, and MANIFEST.in
#: is precisely the file a careless edit changes. A rule that consults only
#: MANIFEST.in therefore lets ONE LINE absorb a real deletion. Measured at the
#: root of the 0.3.1 tarball, python3.10, before this set existed:
#:
#:     control                                       -> 328 passed,  4 skipped
#:     rm CHANGELOG.md                               ->   9 failed, 314 passed
#:     echo 'prune CHANGELOG.md' >>MANIFEST.in; rm CHANGELOG.md
#:                                                   -> 316 passed, 11 skipped
#:     echo 'exclude setup.py' >>MANIFEST.in; rm setup.py
#:                                                   -> 327 passed,  5 skipped
#:     echo 'exclude CONTRIBUTING.md' >>MANIFEST.in; rm CONTRIBUTING.md
#:                                                   -> 327 passed,  5 skipped
#:
#: (each: `tar xzf`, edit, `cd <root> && PYTHONPATH=. pytest tests/ -q`). One
#: appended line turned nine named failures into exit 0.
#:
#: So the policy lives HERE, where changing it is a reviewable edit next to the
#: reasoning, and MANIFEST.in can only ever NARROW the excuse: a surface must be
#: in this set AND be named by MANIFEST.in before its absence is forgiven. The
#: cost of forgetting to add a surface here is a false RED -- one loud line. The
#: cost of the shape it replaces was a silent green.
#:
#: It is checked EXHAUSTIVELY against `SURFACES`, not against a hand-typed list
#: of the never-excusable, by `test_only_a_declared_omission_is_ever_excused`.
#: Adding a surface to `SURFACES` therefore makes it never-excusable by default,
#: and making it excusable is a deliberate edit to this line.
EXCUSABLE_SURFACES = frozenset({"examples/"})


def _project_name() -> str:
    """`[project].name` as declared in THIS tree, or "" if it cannot be read.

    Deliberately narrow and section-aware, the same shape and for the same
    reason as `_project_meta` in `test_package_claims.py`: it must never answer
    with a name it did not actually read. "" makes the identity check below
    fail, which makes the tree NOT an sdist root, which makes an absence RED
    rather than excused -- the safe direction.
    """
    path = SURFACES["pyproject.toml"]
    if not path.is_file():
        return ""
    in_project = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if not in_project:
            continue
        m = re.match(r'^name\s*=\s*"([^"]+)"\s*$', stripped)
        if m:
            return m.group(1)
    return ""


def _normalised(name: str) -> str:
    """PEP 503 name normalisation: `cdfi_benchmark` and `cdfi-benchmark` are one."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _sdist_root_evidence():
    """What was OBSERVED about this tree, or None if it is not an sdist root.

    Returns the sentence the skip message will quote, so the message can only
    ever state findings this function actually made. See the module docstring
    for why each of the three parts is here and what a filename test let past.
    """
    if (ROOT / ".git").exists():
        return None
    path = ROOT / "PKG-INFO"
    if not path.is_file():
        return None
    meta = email.parser.Parser().parsestr(path.read_text(errors="replace"))
    metadata_version, name = meta.get("Metadata-Version"), meta.get("Name")
    if not metadata_version or not name:
        return None
    declared = _project_name()
    if not declared or _normalised(name) != _normalised(declared):
        return None
    return (
        f"the PKG-INFO at this root parses as distribution metadata "
        f"(Metadata-Version: {metadata_version}) naming {name!r}, which matches "
        f"[project].name in this tree's pyproject.toml, and there is no .git "
        f"here -- so this tree is an unpacked source distribution of this "
        f"package and not a working checkout"
    )


#: Evidence that this tree is an unpacked sdist root, or None. Not a filename
#: test: content, identity and provenance, all three. The string it holds is the
#: only thing any skip is allowed to say about why the tree qualified.
SDIST_ROOT_EVIDENCE = _sdist_root_evidence()

#: The yes/no, for the gates that need only that.
IS_SDIST_ROOT = SDIST_ROOT_EVIDENCE is not None


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

    Three things must all hold, and each closes a different hole:

    * this project's POLICY allows a distribution to omit the surface at all
      (`EXCUSABLE_SURFACES`), so one appended MANIFEST.in line cannot absorb a
      deletion of something this package actually ships;
    * this tree really is an unpacked sdist (`_sdist_root_evidence`), tested by
      content, identity and provenance rather than by a filename;
    * MANIFEST.in, which ships inside that sdist, names the surface in a
      whole-surface exclusion -- so deleting `prune examples` makes the tarball
      start REQUIRING examples/ again, with no second flag to remember.
    """
    if surface not in EXCUSABLE_SURFACES:
        return None
    if SDIST_ROOT_EVIDENCE is None:
        return None
    token = _manifest_token(surface)
    if token not in manifest_exclusions():
        return None
    return (
        f"{SDIST_ROOT_EVIDENCE}; and MANIFEST.in, which ships inside it, "
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
