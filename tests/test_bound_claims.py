"""No prose in this tree may state a numeric bound that the constant contradicts.

The class, seen six times in this portfolio before this gate existed: a comment
justifying a number is copied, quoted, or simply left behind when the number
changes, and the stale prose then reads as a live claim. It has already escaped
into a RENDERED label once (`_disclosure.py:56`), which is the reason the rule
exists at all — a comment that justifies becomes a claim that renders.

The `_RATIO_MIN` / `_RATIO_MAX` bound is where it recurred. When the bound moved
from [-100, 150] the change reached the constant and ONE of the sentences about
it; the audit that found it named one site by hand and missed three, and the
hand-typed list in the brief that ordered this fix named six and missed two more.
So this gate does not work from a list. It SCANS.

What it scans, and why that shape:

* Every ``.py`` file, but only its COMMENT and STRING tokens. Tokenizing rather
  than grepping is what keeps ``_peers_with_roaa([0.1, 0.2])`` — a Python list
  literal, not a claim — from being read as a bound.
* Every ``.md`` file, all of which is prose.

What is allowed:

* A pair equal to the live constants. That is the claim being true.
* A pair inside a sentence marked as HISTORY. A changelog that cannot say what
  it changed is not a changelog, and `fdic.py` explaining why the old bound was
  wrong is the comment doing its job. The marker has to be in the text.
* Any entry under a RELEASED version header in CHANGELOG.md. An entry under
  ``## [0.2.1]`` is a statement about 0.2.1 by construction — at tag v0.2.1 the
  bound really was [-100.0, 150.0] and really did raise, so rewriting that entry
  would replace a true statement with a false one. This is the one ruling in the
  brief that ordering this fix got backwards, and it is recorded here rather
  than argued in a commit message.

WHY THIS WHOLE MODULE IS A REPO GATE
------------------------------------
The scan walks ``ROOT.rglob("*")`` — the repository tree. It cannot be pointed
at an installed package instead, because what it certifies is the tree's PROSE:
``.md`` files, which a wheel does not carry, and the comments in ``tests/``,
which the artifact jobs only have by way of a ``cp -R tests`` in release.yml.
Measured in a full checkout, the six bound-shaped pairs live in CHANGELOG.md
(3), tests/test_fdic.py (1) and this file's own docstring (2); ``cdfibenchmark/``
contributes NONE, because fdic.py's surviving sentence is symbolic
(``[_RATIO_MIN, _RATIO_MAX]``), which is the end state the gate exists to reach.
So "resolve it through the installed module" is not available to this scan: the
installed module is precisely the part of the tree with nothing to find.

Run 34002310309 failed all eight release jobs here. The wrong lesson would be to
skip the module and move on: two assertions in it were never scan-based, and one
of them guards a comment that SHIPS INSIDE THE WHEEL. Those two moved to
``tests/test_shipped_source_claims.py``, where they read ``fdic.__file__`` and
run in every context including the artifact jobs. What is left is the scan, and
the scan is repo-only.
"""
import io
import re
import tokenize
from pathlib import Path

import pytest

from cdfibenchmark.data import fdic

from . import _layout as layout

ROOT = layout.ROOT
SKIP_DIRS = {".git", "build", "dist", ".pytest_cache", "__pycache__",
             "cdfi_benchmark.egg-info", ".venv", "venv"}

#: A bracketed numeric pair, the shape every statement of this bound takes.
_PAIR = re.compile(r"\[\s*(-?\d[\d.,_]*)\s*,\s*(-?\d[\d.,_]*)\s*\]")

#: Words that mark a sentence as describing a PAST state of the code. Kept
#: short and explicit: a loose marker list is a hole, not a gate.
_HISTORY_MARKERS = (
    "was ", "were ", "used to ", "previously", "no longer", "retired",
    "through 0.2", "through 0.3.0", "before this", "old comment", "old bound",
    "it replaces", "moved from",
)

#: Every surface the scan must be able to walk.
#:
#: ALL-OR-NOTHING FOR THIS MODULE, DELIBERATELY -- AND UNLIKE
#: `test_package_claims.py`, which was split into per-gate coverage sets in the
#: same change that wrote this comment. The two modules differ in shape, so the
#: same rule does not fit both: that one has eleven gates reading different
#: documents, several of which are readable in a directory where others are not.
#: This one has ONE gate, a scan over the whole tree, and a scan that quietly
#: drops the surfaces it cannot reach goes GREEN while checking a fraction of
#: what it checks locally. `test_the_scan_finds_the_sites_it_is_supposed_to
#: _guard` is a vacuity self-check, not the gate; without the all-or-nothing
#: rule the parametrized gate below would have gone green over `.py` files alone.
#:
#: Every surface named here SHIPS in the sdist -- MANIFEST.in `include`s the
#: three files and `recursive-include tests *.py` takes the suite -- so unlike
#: `examples/` none of them can ever be legitimately absent from a distribution.
#: That is not assumed: `layout.classify` reads MANIFEST.in inside an sdist root
#: and would start excusing one the day it stopped shipping.
_REQUIRED_SURFACES = (
    "pyproject.toml", "README.md", "CHANGELOG.md", "cdfibenchmark/", "tests/",
)
_PRESENT, _DECLARED_ABSENT, _UNDECLARED_ABSENT = layout.classify(*_REQUIRED_SURFACES)

#: Can the scan run at all? Only when every surface it walks is readable. The
#: three questions this used to conflate -- "is a surface missing", "is there a
#: repository here", "should we skip" -- now live in `tests/_layout.py`, which
#: asks them PER SURFACE and can tell a deletion from a declared omission.
#:
#: THIS IS ALSO WHAT STOPS A DELETION FROM ABORTING COLLECTION. `_hits()` calls
#: `_current_version()`, which reads pyproject.toml unconditionally, and
#: `_SCAN_HITS` calls `_hits()` at IMPORT time. Deleting pyproject.toml from a
#: checkout therefore raised FileNotFoundError during COLLECTION:
#:
#:     ERROR tests/test_bound_claims.py - FileNotFoundError: ... pyproject.toml
#:     !!!! Interrupted: 1 error during collection !!!!
#:     1 error in 0.27s
#:
#: and the entire suite stopped -- 324 tests, not one of them run. The commit
#: that introduced that deletion claimed it was "RED by name in all three
#: modules"; for this surface that was false, and a suite that does not run is
#: not a suite that failed by name. Gating on ABSENCE rather than on the skip
#: predicate means `_hits()` is never called when a surface it needs is gone,
#: and the gates below then fail by name through `layout.require`.
_CAN_SCAN = not _DECLARED_ABSENT and not _UNDECLARED_ABSENT


def _current_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml has no [project] version"
    return m.group(1)


def _shipped_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".md"):
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def _prose_segments(path: Path):
    """(line_number, text) for every stretch of PROSE in ``path``.

    Markdown is prose throughout. Python is prose only inside comments and
    string literals; everything else is code, where a bracketed pair is a list.
    """
    text = path.read_text()
    if path.suffix == ".md":
        for i, line in enumerate(text.splitlines(), 1):
            yield i, line
        return
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover
        pytest.fail(f"{path} could not be tokenized")
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            yield tok.start[0], tok.string


def _claim_window(file_lines, lineno: int) -> str:
    """The sentence a pair sits in: its own line plus the line above it.

    Read from the FILE, not from the segment, so the window is the same width in
    a Markdown file and inside a Python docstring. Two earlier drafts got this
    wrong in opposite directions and both were caught by red-proving:

    * Searching the whole segment exempted too much — a Python docstring is one
      STRING token, so a fourteen-line docstring containing "was" anywhere
      exempted every bound claim inside it. Restoring "150" to `_coerce_float`'s
      docstring PASSED because a sentence four paragraphs away said "it was
      avoiding".
    * Searching the segment with look-back exempted too little in Markdown,
      where each line is its own segment and there was no previous line to look
      back at. It failed this file's own retraction entry, which is precisely
      the sentence a changelog has to be allowed to write.

    One line of context, because that is how far these sentences actually wrap.
    """
    return "\n".join(file_lines[max(0, lineno - 2):lineno])


def _changelog_section_versions(text: str):
    """Line number -> the version header that line sits under, for CHANGELOG.md."""
    current, out = None, {}
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^##\s*\[([^\]]+)\]", line)
        if m:
            current = m.group(1)
        out[i] = current
    return out


def _hits():
    """Every bracketed numeric pair stated in prose anywhere in the tree."""
    version = _current_version()
    for path in _shipped_files():
        rel = path.relative_to(ROOT)
        text = path.read_text()
        file_lines = text.splitlines()
        sections = None
        if path.name == "CHANGELOG.md":
            sections = _changelog_section_versions(text)
        for lineno, segment in _prose_segments(path):
            for m in _PAIR.finditer(segment):
                offset = segment[:m.start()].count("\n")
                yield {
                    "path": rel,
                    "line": lineno + offset,
                    "pair": (m.group(1), m.group(2)),
                    "text": _claim_window(file_lines, lineno + offset),
                    "section": (sections or {}).get(lineno + offset),
                    "released_section": bool(
                        sections
                        and (sections.get(lineno + offset) not in (None, version))
                    ),
                }


def _numeric(token: str) -> float:
    return float(token.replace(",", "").replace("_", ""))


def _is_bound_shaped(hit) -> bool:
    """A pair that could be read as a statement of the ratio-class bound.

    A pair is bound-shaped when it is negative-then-positive, which is the form
    every statement of this bound takes and which a coordinate, a range of dates
    or a list of positive figures is not.
    """
    try:
        low, high = (_numeric(t) for t in hit["pair"])
    except ValueError:  # pragma: no cover - the regex only matches numbers
        return False
    return low < 0 < high


def _is_history(hit) -> bool:
    if hit["released_section"]:
        return True
    # Whitespace-normalised: these sentences wrap, and a marker split across a
    # line break ("moved\nfrom") is still the marker.
    lowered = " ".join(hit["text"].lower().split())
    return any(marker in lowered for marker in _HISTORY_MARKERS)


#: The scan's result, computed ONCE at collection time.
#:
#: A module-level skip is evaluated at SETUP, which is too late for a
#: parametrize list: `empty_parameter_set_mark = fail_at_collect` fires during
#: COLLECTION, so a zero-length list would abort the module with a collection
#: error that no skip could prevent. Hence the two-case shape below:
#:
#: * scanning (every surface readable) -> the real hits, and if the scan finds
#:   NONE the list is empty and `fail_at_collect` ERRORS. That protection is the
#:   whole point and it stays armed exactly where it can mean something.
#: * not scanning -> one placeholder param, which `layout.require` in the body
#:   resolves into a NAMED skip (an artifact directory, or a surface the
#:   distribution declares it omits) or a NAMED failure (a deletion from a
#:   source tree). Never a green pass.
_SCAN_HITS = [h for h in _hits() if _is_bound_shaped(h)] if _CAN_SCAN else []
_SCAN_PARAMS = (
    [pytest.param(h, id=f"{h['path']}:{h['line']}") for h in _SCAN_HITS]
    if _CAN_SCAN else [pytest.param(None, id="scan-did-not-run")]
)


# ── the gate ───────────────────────────────────────────────────
def test_every_surface_the_scan_needs_is_present_or_declared_absent():
    """The mutation gate: a deleted surface must be RED here, never a skip.

    Delete CHANGELOG.md from a checkout and this fails by name; that is what
    stops the module from answering "not applicable" about a tree it should have
    failed over. In `test-wheel` and `test-sdist`'s constructed directory there
    is no source tree, so this skips -- correctly: those directories are not
    repositories and never were.

    Unlike the old version of this gate, "the surface is missing" is no longer
    the same question as "should we skip". `tests/_layout.py` separates them:
    only an artifact that states its own contents can excuse an absence, and
    only for the surfaces it names.
    """
    if not layout.IS_REPO_TREE:
        pytest.skip(
            "no source tree here (no cdfibenchmark/, no .git); nothing was "
            "deleted. The scan runs in ci.yml's `test` job and at the tarball "
            "root, and the two assertions about shipped source moved to "
            "tests/test_shipped_source_claims.py, which runs everywhere."
        )
    assert not _UNDECLARED_ABSENT, (
        f"a source tree is present here (cdfibenchmark/ or .git/) but the "
        f"bound-claim scan cannot reach {', '.join(_UNDECLARED_ABSENT)}, and "
        f"nothing here declares those absent. That is a deleted or moved "
        f"surface, not an installed-artifact run, so it fails instead of "
        f"skipping. Restore the surface, or remove it from _REQUIRED_SURFACES "
        f"and say in the docstring what the scan no longer covers."
    )


def test_the_scan_finds_the_sites_it_is_supposed_to_guard():
    """A scan that finds nothing certifies nothing.

    This gate's failure mode is a regex that silently stops matching, after
    which every stale bound in the tree passes. Pin that the scan still sees
    the class it was written for, in both file types.

    `fdic.py` is deliberately NOT expected here: its remaining statement of the
    bound is symbolic (`[_RATIO_MIN, _RATIO_MAX]`), which is the end state this
    whole gate is trying to reach — a sentence that cannot go stale because it
    names the constant instead of copying it.
    """
    layout.require(*_REQUIRED_SURFACES)
    hits = _SCAN_HITS
    assert hits, (
        "the bound-claim scan found NO bound-shaped pair anywhere in the tree. "
        "The bound is stated in prose in several places; a scan returning zero "
        "is broken, not clean."
    )
    suffixes = {h["path"].suffix for h in hits}
    assert suffixes == {".py", ".md"}, (
        f"the scan reaches only {suffixes}; the class spans code comments AND "
        f"shipped markdown, and has escaped into both"
    )


def test_the_scan_reads_python_prose_and_not_python_code():
    """Tokenizing, not grepping, is what makes this gate usable.

    `tests/test_ranking.py` contains `_peers_with_roaa([0.1, 0.2])` — a list
    literal, not a claim about anything. A grep-based gate has to either flag it
    or carry an exclusion list, and an exclusion list is the hand-typed list this
    gate exists to replace.
    """
    layout.require(*_REQUIRED_SURFACES)
    sample = ROOT / "tests" / "test_ranking.py"
    assert sample.exists()
    segments = list(_prose_segments(sample))
    assert segments, "no prose found in a file that has a module docstring"
    joined = "\n".join(text for _, text in segments)
    assert "_peers_with_roaa([0.1, 0.2])" not in joined, (
        "a Python list literal was read as prose; the scan is grepping, not "
        "tokenizing"
    )
    assert any("#" in text or text.startswith(('"', "'")) for _, text in segments)


@pytest.mark.parametrize("hit", _SCAN_PARAMS)
def test_no_live_prose_states_a_bound_the_constant_contradicts(hit):
    """Every bound-shaped pair states the live constants, or is marked history.

    Red-proving this is one edit: put "150" back as the upper number of any
    corrected site — `fdic.py`'s `_coerce_float` docstring, or the `test_fdic.py`
    header comment — and this fails naming that file and line.
    """
    if hit is None:
        # The scan did not run. `require` says why, by name: a named skip in a
        # directory that is not a source tree, a named FAILURE for a surface
        # deleted from one.
        layout.require(*_REQUIRED_SURFACES)
        pytest.fail(
            "the scan did not run, yet every surface it needs is readable. "
            "_CAN_SCAN and layout.classify disagree, so this gate is reporting "
            "on a scan that never happened."
        )
    if _is_history(hit):
        return
    low, high = (_numeric(t) for t in hit["pair"])
    assert (low, high) == (fdic._RATIO_MIN, fdic._RATIO_MAX), (
        f"{hit['path']}:{hit['line']} states the ratio-class bound as "
        f"[{hit['pair'][0]}, {hit['pair'][1]}], but the constants are "
        f"[{fdic._RATIO_MIN:g}, {fdic._RATIO_MAX:g}]. Either correct the "
        f"sentence or mark it as history (one of: "
        f"{', '.join(repr(m.strip()) for m in _HISTORY_MARKERS)}).\n"
        f"  text: {hit['text'].strip()[:200]}"
    )
